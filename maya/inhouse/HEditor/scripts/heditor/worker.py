"""外部mayapyで動く標準ライブラリだけの静的インデクサー。

Mayaを初期化せず、対象のPythonファイルをimport/実行しない。
JSON Linesを受け取り、候補一覧を返す。C++側が表示と要求の世代管理を担う。
"""
import ast
import builtins
import json
import keyword
import os
import re
import sys


class Index:
    def __init__(self, paths, modules=None):
        self.paths = paths
        self.modules = modules or {}
        self.cache = {}
        self.top = set(sys.builtin_module_names)
        self.top.update(name.split('.')[0] for name in self.modules)
        self.top_scanned = False

    def scan_top(self):
        if self.top_scanned:
            return
        for path in self.paths:
            try:
                with os.scandir(path) as entries:
                    for entry in entries:
                        if entry.name.endswith('.py'):
                            self.top.add(entry.name[:-3])
                        elif entry.is_dir() and entry.name.isidentifier():
                            self.top.add(entry.name)
            except OSError:
                pass
        self.top_scanned = True

    def module(self, name):
        """ディレクトリ型パッケージと.pyを解決。mtime/sizeで再解析する。"""
        result = dict(self.modules.get(name, {}))
        # 実在する公開名の補完に、ネットワークドライブ等の走査を要求しない。
        if result:
            return result
        parts = name.split('.')
        if not all(part.isidentifier() for part in parts):
            return result
        for root in self.paths:
            base = os.path.join(root, *parts)
            filename = base + '.py'
            if os.path.isdir(base):
                filename = os.path.join(base, '__init__.py')
                try:
                    with os.scandir(base) as entries:
                        for entry in entries:
                            stem = entry.name[:-3] if entry.name.endswith('.py') else entry.name
                            if stem.isidentifier() and not stem.startswith('_') and (entry.is_dir() or entry.name.endswith('.py')):
                                result.setdefault(stem, {'target': name + '.' + stem})
                except OSError:
                    pass
            if not os.path.isfile(filename):
                continue
            try:
                stat = os.stat(filename)
                stamp = (stat.st_mtime_ns, stat.st_size)
                cached = self.cache.get(filename)
                if cached is None or cached[0] != stamp:
                    import tokenize
                    with tokenize.open(filename) as stream:
                        tree = ast.parse(stream.read())
                    cached = (stamp, self.symbols(tree, name + '.__init__' if os.path.basename(filename) == '__init__.py' else name))
                    self.cache[filename] = cached
                # 実行時の公開名を残しつつ関数シグネチャを静的情報で補う。
                result.update(cached[1])
            except (OSError, SyntaxError, UnicodeError):
                pass
            break
        return result

    def symbols(self, tree, module=''):
        result = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in getattr(node.args, 'posonlyargs', []) + node.args.args]
                if node.args.vararg:
                    args.append('*' + node.args.vararg.arg)
                args.extend(arg.arg for arg in node.args.kwonlyargs)
                if node.args.kwarg:
                    args.append('**' + node.args.kwarg.arg)
                result[node.name] = {'detail': node.name + '(' + ', '.join(args) + ')'}
            elif isinstance(node, ast.ClassDef):
                result[node.name] = {'members': self.symbols(node, module), 'detail': 'class ' + node.name}
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    result[alias.asname or alias.name.split('.')[0]] = {'target': alias.name if alias.asname else alias.name.split('.')[0]}
            elif isinstance(node, ast.ImportFrom):
                parent = node.module or ''
                if node.level:
                    parent = '.'.join(module.split('.')[:-node.level] + ([parent] if parent else []))
                for alias in node.names:
                    if alias.name != '*':
                        result[alias.asname or alias.name] = {'from': parent, 'name': alias.name}
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        result[target.id] = {}
        return result

    def resolve(self, item, depth=0):
        if depth > 8:
            return {}
        if 'from' in item:
            parent = self.module(item['from'])
            value = parent.get(item['name'], {'target': item['from'] + '.' + item['name']})
            return self.resolve(value, depth + 1)
        if item.get('target'):
            return self.module(item['target'])
        return item.get('members', {})

    def complete(self, source):
        match = re.search(r'[A-Za-z_][\w.]*$|(?<=\.)$', source)
        token = match.group() if match else ''
        line = source.split('\n')[-1]
        if re.match(r'^\s*(import|from)\s+[\w.]*$', line):
            if '.' in token:
                parent, prefix = token.rsplit('.', 1)
                symbols = self.module(parent)
            else:
                self.scan_top()
                prefix, symbols = token, {name: {} for name in self.top}
        else:
            # 編集途中の末尾行を順に除去し、確定した宣言を解析する。
            lines = source.splitlines()
            symbols = {}
            while lines:
                try:
                    symbols = self.symbols(ast.parse('\n'.join(lines)))
                    break
                except SyntaxError:
                    lines.pop()
            from_match = re.match(r'^\s*from\s+([\w.]+)\s+import\s+(\w*)$', line)
            if from_match:
                symbols, prefix = self.module(from_match.group(1)), from_match.group(2)
            elif '.' in token:
                parts = token.split('.')
                item = symbols.get(parts[0], {'target': parts[0]})
                for part in parts[1:-1]:
                    item = self.resolve(item).get(part, {})
                symbols, prefix = self.resolve(item), parts[-1]
            else:
                prefix = token
                symbols = dict({name: {} for name in list(vars(builtins)) + keyword.kwlist}, **symbols)
        return [{'name': name, 'detail': value.get('detail', '')}
                for name, value in sorted(symbols.items())
                if name.startswith(prefix) and (prefix.startswith('_') or not name.startswith('_'))][:250]


def main():
    index = Index([])
    for line in sys.stdin:
        request = {}
        try:
            request = json.loads(line)
            if 'paths' in request:
                index = Index(request['paths'], request.get('modules'))
                response = {'id': request.get('id', -1), 'ready': True}
            else:
                response = {'id': request['id'], 'items': index.complete(request['source'])}
        except Exception as exc:
            response = {'id': request.get('id', -1), 'error': str(exc)}
        print(json.dumps(response, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
