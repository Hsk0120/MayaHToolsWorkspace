"""C++の宣言の抽出(hedit -declarations)が、以前のPython(ast)と同じ結果になるかを突き合わせる。

以前のheditは、Pythonの ``ast.parse`` で宣言を読んでいた(hedit.completion.Index.symbols)。
C++(src/core/python_declarations.cpp)へ移したので、実在の多数の.pyファイルで両方の結果を比べる。
下の ``reference_symbols`` は、以前のPythonの実装をそのまま残した比較用の基準。
構文エラーのファイル(astで読めないもの)は比べない(C++は読める部分を取り出すため)。
"""
import ast
import json
from pathlib import Path
import sys
import unittest

import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
cmds.loadPlugin('hedit')

WORKSPACE = Path(__file__).resolve().parents[4]


def reference_symbols(tree, module=''):
    """以前のhedit.completion.Index.symbolsと同じ処理(比較の基準)。"""
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
            result[node.name] = {'members': reference_symbols(node, module), 'detail': 'class ' + node.name}
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result[alias.asname or alias.name.split('.')[0]] = {'target': alias.name if alias.asname else alias.name.split('.')[0]}
        elif isinstance(node, ast.ImportFrom):
            parent = node.module or ''
            if node.level:
                parent = '.'.join(module.split('.')[:-node.level] + ([parent] if parent else []))
            for alias in node.names:
                if alias.name != '*':
                    result[alias.asname or alias.name] = (
                        {'target': parent + '.' + alias.name} if node.level and not node.module
                        else {'from': parent, 'name': alias.name})
        elif isinstance(node, ast.If) and (
                isinstance(node.test, ast.Name) and node.test.id == 'TYPE_CHECKING'
                or isinstance(node.test, ast.Attribute) and isinstance(node.test.value, ast.Name)
                and node.test.value.id == 'typing' and node.test.attr == 'TYPE_CHECKING'):
            result.update(reference_symbols(node, module))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    result[target.id] = {}
    return result


def corpus():
    """list[Path]: 比べる.pyファイル(内製のhlib・hrig・hedit、Maya同梱Pythonの標準ライブラリの一部)。"""
    files = []
    for folder in ('maya/inhouse/hlib', 'maya/inhouse/hrig', 'maya/inhouse/HTools', 'maya/inhouse/hedit'):
        files.extend(sorted((WORKSPACE / folder).rglob('*.py')))
    stdlib = Path(ast.__file__).parent
    for name in ('os.py', 'ast.py', 'typing.py', 'dataclasses.py', 'functools.py', 'pathlib.py', 'argparse.py',
                 'subprocess.py', 'inspect.py', 'enum.py', 'json/__init__.py', 'json/decoder.py', 'unittest/case.py',
                 'logging/__init__.py', 'collections/__init__.py', 'importlib/util.py'):
        if (stdlib / name).is_file():
            files.append(stdlib / name)
    return [path for path in files if '.venv' not in path.parts and '_build' not in path.parts]


class DeclarationParityTests(unittest.TestCase):
    def test_matches_ast_on_real_files(self):
        compared = 0
        mismatches = []
        for path in corpus():
            source = path.read_text(encoding='utf-8', errors='replace')
            try:
                tree = ast.parse(source)
            except (SyntaxError, ValueError):
                continue
            expected = reference_symbols(tree)
            actual = json.loads(cmds.hedit(declarations=source))
            compared += 1
            if actual != expected:
                missing = sorted(set(expected) - set(actual))
                extra = sorted(set(actual) - set(expected))
                differ = sorted(k for k in set(expected) & set(actual) if expected[k] != actual[k])
                mismatches.append('%s: missing=%s extra=%s differ=%s' % (path, missing[:5], extra[:5], differ[:5]))
        print('compared %d files with ast' % compared)
        self.assertGreater(compared, 100)
        self.assertEqual(mismatches, [], '\n'.join(mismatches[:20]))


if __name__ == '__main__':
    unittest.main()
