"""Maya内で呼び出す標準ライブラリだけの静的補完。対象ソースは実行しない。"""
import ast
import builtins
import keyword
import os
import re
import sys
import threading
import time


class Index:
    def __init__(self, paths, modules=None, runtime=None, async_scan=False):
        self.paths = paths
        self.modules = modules or {}
        self.cache = {}
        self.runtime = runtime
        self.top = set(sys.builtin_module_names)
        self.top.update(name.split('.')[0] for name in self.modules)
        self.top_scanned = False
        self.async_scan = async_scan
        self.scan_thread = None
        self.scan_started = 0
        self.local_source = None
        self.local_symbols = {}

    def scan_top(self):
        """GUIではファイル列挙を同一プロセスの別スレッドで実行する。"""
        if self.async_scan:
            if self.scan_thread and (self.scan_thread.is_alive() or time.monotonic()-self.scan_started < 5):
                return
            self.scan_started = time.monotonic()
            self.scan_thread = threading.Thread(target=self._scan_top, args=(tuple(self.paths), tuple(self.modules)), daemon=True)
            self.scan_thread.start()
        else:
            self._scan_top(tuple(self.paths), tuple(self.modules))

    def _scan_top(self, paths, modules):
        """Maya APIやUIを呼ばず、完了した候補集合を一度に交換する。"""
        top = set(sys.builtin_module_names)
        top.update(name.split('.')[0] for name in modules)
        for path in paths:
            try:
                with os.scandir(path) as entries:
                    for entry in entries:
                        if entry.name.endswith('.py'):
                            top.add(entry.name[:-3])
                        elif entry.is_dir() and entry.name.isidentifier():
                            top.add(entry.name)
            except OSError:
                pass
        self.top_scanned = True
        self.top = top

    def locals(self, source):
        """同じ宣言部分を再解析せず、構文エラー時の全行再試行を最大4回に制限する。"""
        if source == self.local_source:
            return dict(self.local_symbols)
        lines = source.splitlines()
        symbols = {}
        for _ in range(4):
            if not lines:
                break
            try:
                symbols = self.symbols(ast.parse('\n'.join(lines)))
                break
            except SyntaxError as error:
                # エラー位置以後をまとめて除外する。1行ずつ削ると二乗時間になる。
                lines = lines[:max(0, min(len(lines)-1, (error.lineno or 1)-1))]
        self.local_source, self.local_symbols = source, symbols
        return dict(symbols)

    def module(self, name):
        """ディレクトリ型パッケージと.pyを解決。mtime/sizeで再解析する。"""
        result = dict(self.modules.get(name, {}))
        if self.runtime:
            live = self.runtime(name)
            if live is not None:
                result, filename = live
                # 読み込み済みモジュールは判明しているファイルだけ調べる。
                if filename and filename.endswith('.py'):
                    result.update(self.source(filename, name))
                return result
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

    def source(self, filename, name):
        """確定済みパスだけを再解析。編集中の構文エラーは最後の正常な候補を維持。"""
        cached = self.cache.get(filename)
        try:
            stat = os.stat(filename)
            stamp = (stat.st_mtime_ns, stat.st_size)
            if cached is None or cached[0] != stamp:
                import tokenize
                with tokenize.open(filename) as stream:
                    tree = ast.parse(stream.read())
                module = name + '.__init__' if os.path.basename(filename) == '__init__.py' else name
                cached = (stamp, self.symbols(tree, module))
                self.cache[filename] = cached
        except (OSError, SyntaxError, UnicodeError):
            pass
        return dict(cached[1]) if cached else {}

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
                        # from . import nodes は親の同じ公開名を再解決すると循環する。
                        result[alias.asname or alias.name] = (
                            {'target': parent + '.' + alias.name} if node.level and not node.module
                            else {'from': parent, 'name': alias.name})
            elif isinstance(node, ast.If) and (
                    isinstance(node.test, ast.Name) and node.test.id == 'TYPE_CHECKING'
                    or isinstance(node.test, ast.Attribute) and isinstance(node.test.value, ast.Name)
                    and node.test.value.id == 'typing' and node.test.attr == 'TYPE_CHECKING'):
                # 型宣言も静的に読む。対象パッケージをimport・実行することはない。
                result.update(self.symbols(node, module))
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
            if value == item:
                return self.module(item['from'] + '.' + item['name'])
            return self.resolve(value, depth + 1)
        if item.get('target'):
            return self.module(item['target'])
        return item.get('members', {})

    def complete(self, source):
        if len(source) > 200000:
            return []
        match = re.search(r'[A-Za-z_][\w.]*$|(?<=\.)$', source)
        token = match.group() if match else ''
        line = source.split('\n')[-1]
        if re.match(r'^\s*(import|from)\s+[\w.]*$', line):
            if '.' in token:
                parent, prefix = token.rsplit('.', 1)
                symbols = self.module(parent)
            else:
                self.scan_top()
                prefix, symbols = token, {name: {} for name in self.top | {n.split('.')[0] for n in self.modules}}
        else:
            # 編集途中の末尾行を順に除去し、確定した宣言を解析する。
            # 補完している最終行を除いた宣言部分は、文字を打つたびには変化しない。
            symbols = self.locals(source.rpartition('\n')[0])
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
                base = {name: {'kind': 'builtin'} for name in vars(builtins)}
                base.update({name: {'kind': 'keyword'} for name in keyword.kwlist})
                symbols = dict(base, **symbols)
        return [dict({'name': name, 'detail': value.get('detail', '')}, **({'kind': value['kind']} if 'kind' in value else {}))
                for name, value in sorted(symbols.items())
                if name.startswith(prefix) and (prefix.startswith('_') or not name.startswith('_'))][:250]

