"""補完(C++の補完エンジン)と構文チェック(同梱Python)をmayapyで検証する。

補完の判断はhedit.mllの中のC++が行うので、テスト用の ``hedit -complete`` コマンドで呼ぶ。
モジュールの情報(sys.path・sys.modules)は実行中のPythonから取るので、テストはそれらを一時的に差し替える。
対象のソースは実行しない(実行されると ``RuntimeError`` になる内容で確かめる)。
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
cmds.loadPlugin('hedit')
from hedit import bridge
from hedit.analysis import analyze


def complete(source):
    """dict: C++の補完の結果(JSON)。"""
    return json.loads(cmds.hedit(complete=source))


def names(source):
    """list[str]: 補完候補の名前。"""
    return [item['name'] for item in complete(source)['items']]


def describe(source):
    """dict: 本文の末尾の名前のホバーの説明(``{"signature": ..., "doc": ...}``)。"""
    return json.loads(cmds.hedit(describe=source))


class CompletionTests(unittest.TestCase):
    """``hedit -complete`` による補完と、``hedit.analysis`` による構文チェックの検証。"""
    # import行のトップレベル名(sys.pathの走査)はC++(src/core/module_scanner.cpp)が扱い、tests/ui_smoke.cppで検証する。

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.root.joinpath('sample.py').write_text(
            'raise RuntimeError("must not execute")\n\ndef create_node(name, **kwargs):\n    pass\n\n'
            'class Example:\n    def get_value(self):\n        pass\n', encoding='utf-8')
        # C++は補完のたびにPythonのsys.pathを読む。一時フォルダーを先頭に置く。
        self.path = mock.patch.object(sys, 'path', [str(self.root)] + sys.path)
        self.path.start()
        cmds.hedit(complete='')  # 前のテストのファイルのキャッシュに影響されないよう、まず1回呼ぶ。

    def tearDown(self):
        self.path.stop()
        self.directory.cleanup()

    def test_top_level_names_come_from_cpp(self):
        """C++へ渡す検索パスと、組み込み・読み込み済みのトップレベル名。フォルダーは走査しない。"""
        with mock.patch('os.scandir', side_effect=AssertionError('must not scan')):
            data = json.loads(bridge.module_names())
        self.assertIn('sys', data['names'])
        self.assertIn('maya', data['names'])
        self.assertTrue(all(os.path.isabs(path) for path in data['paths']))

    def test_import_alias_and_signature_without_execution(self):
        items = complete('import sample as s\ns.cre')['items']
        self.assertEqual(items, [{'name': 'create_node', 'detail': 'create_node(name, **kwargs)'}])
        self.assertNotIn('sample', sys.modules)

    def test_dynamic_exports(self):
        module = types.ModuleType('dynamic')
        module.createNode = 1
        module.ls = 2
        with mock.patch.dict(sys.modules, {'dynamic': module}):
            self.assertEqual(names('import dynamic as d\nd.l'), ['ls'])

    def test_describe_source_file_without_execution(self):
        """まだ読み込んでいない .py のdocstringは、実行せずに字句解析で読む(ホバー)。"""
        self.root.joinpath('documented.py').write_text(
            '"""Documented module."""\nraise RuntimeError("must not execute")\n\n'
            'def make(name, size=1):\n    """Make a thing.\n\n    Args:\n        name (str): The name.\n    """\n',
            encoding='utf-8')
        info = describe('import documented\ndocumented.make')
        self.assertEqual(info, {'signature': 'def make(name, size=1)',
                                'doc': 'Make a thing.\n\nArgs:\n    name (str): The name.'})
        self.assertEqual(describe('import documented\ndocumented')['doc'], 'Documented module.')
        self.assertNotIn('documented', sys.modules)

    def test_describe_loaded_module_without_source(self):
        """ソースの無い読み込み済みの名前は、vars()でたどった__doc__を使う。propertyは実行しない。"""
        module = types.ModuleType('dynamic_doc', 'Dynamic module.')

        def create(name, flag=True):
            """Create something."""

        class Widget:
            """A widget."""

            def __init__(self, parent=None):
                pass

            @property
            def value(self):
                raise RuntimeError('must not execute')

        module.create = create
        module.Widget = Widget
        with mock.patch.dict(sys.modules, {'dynamic_doc': module}):
            self.assertEqual(describe('import dynamic_doc\ndynamic_doc.create'),
                             {'signature': 'def create(name, flag=True)', 'doc': 'Create something.'})
            self.assertEqual(describe('from dynamic_doc import Widget\nWidget'),
                             {'signature': 'class Widget(parent=None)', 'doc': 'A widget.'})
            self.assertEqual(describe('import dynamic_doc\ndynamic_doc'),
                             {'signature': 'module dynamic_doc', 'doc': 'Dynamic module.'})
            self.assertEqual(json.loads(bridge.describe('dynamic_doc', ['Widget', 'value']))['signature'],
                             'property value')
        self.assertEqual(describe('len')['signature'], 'def len(obj, /)')
        self.assertEqual(describe('return'), {'signature': '', 'doc': ''})

    def test_loaded_module_never_scans_search_paths(self):
        """読み込み済みのモジュールは、sys.path(遅いネットワーク上かもしれない)を見ずに補完する。"""
        with mock.patch.object(sys, 'path', ['//unavailable/share'] + sys.path):
            start = time.perf_counter()
            result = names('import maya.cmds as cmds\ncmds.createNod')
            self.assertLess(time.perf_counter() - start, 1.0)
        self.assertEqual(result, ['createNode'])

    def test_local_function_and_class(self):
        self.assertIn('function', names('def function(arg):\n    pass\nfun'))
        self.assertEqual(names('import sample\nsample.Example.get_'), ['get_value'])

    def test_from_import(self):
        self.assertEqual(names('from sample import cre'), ['create_node'])
        self.assertEqual(names('from sample import Example as E\nE.get'), ['get_value'])

    def test_relative_export(self):
        package = self.root / 'package'; package.mkdir()
        (package / '__init__.py').write_text('from .api import Example\n', encoding='utf-8')
        (package / 'api.py').write_text('class Example:\n    def member(self):\n        pass\n', encoding='utf-8')
        self.assertEqual(names('import package\npackage.Example.mem'), ['member'])

    def test_nested_relative_package_and_type_checking_exports(self):
        package = self.root / 'package'; package.mkdir()
        nodes = package / 'nodes'; nodes.mkdir()
        (package / '__init__.py').write_text('from . import nodes\n', encoding='utf-8')
        (nodes / '__init__.py').write_text('from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .joint import Joint\n', encoding='utf-8')
        (nodes / 'joint.py').write_text('class Joint:\n    def get_matrix(self): pass\n', encoding='utf-8')
        self.assertIn('Joint', names('import package\npackage.nodes.'))
        self.assertEqual(names('import package as p\np.nodes.Joint.get_'), ['get_matrix'])
        self.assertIn('Joint', names('from package import nodes\nnodes.'))
        self.assertNotIn('package', sys.modules)

    def test_absolute_subpackage_reexport_does_not_recurse(self):
        package = self.root / 'package'; package.mkdir()
        (package / '__init__.py').write_text('from package import nodes\n', encoding='utf-8')
        (package / 'nodes.py').write_text('class Node: pass\n', encoding='utf-8')
        self.assertIn('Node', names('import package\npackage.nodes.'))

    def test_cache_invalidation(self):
        self.assertTrue(names('import sample\nsample.cre'))
        self.root.joinpath('sample.py').write_text('def changed():\n    pass\n', encoding='utf-8')
        self.assertEqual(names('import sample\nsample.ch'), ['changed'])
        self.assertEqual(names('import sample\nsample.cre'), [])

    def test_live_exports_follow_changes_without_refresh(self):
        module = types.ModuleType('hedit_fixture')
        module.before = 1
        with mock.patch.dict(sys.modules, {'hedit_fixture': module}):
            self.assertEqual(names('import hedit_fixture as f\nf.'), ['before'])
            del module.before
            module.after = 2
            self.assertEqual(names('import hedit_fixture as f\nf.'), ['after'])

    def test_loaded_source_and_class_follow_edits_without_execution(self):
        module = types.ModuleType('sample')
        module.__file__ = str(self.root / 'sample.py')
        with mock.patch.dict(sys.modules, {'sample': module}):
            self.assertIn('get_value', names('import sample\nsample.Example.'))
            (self.root / 'sample.py').write_text('raise RuntimeError("never run")\nclass Example:\n    def new_method(self): pass\n', encoding='utf-8')
            self.assertEqual(names('import sample\nsample.Example.'), ['new_method'])
            # 書きかけ(括弧が閉じていない)のファイルは、前回の正しい結果を使い続ける。
            (self.root / 'sample.py').write_text('class Example: (', encoding='utf-8')
            self.assertEqual(names('import sample\nsample.Example.'), ['new_method'])

    def test_keyword_and_builtin_categories(self):
        self.assertEqual(complete('ret')['items'][0]['kind'], 'keyword')
        self.assertEqual(complete('pri')['items'][0]['kind'], 'builtin')

    def test_unicode_and_in_process(self):
        with mock.patch('subprocess.Popen', side_effect=AssertionError('must not spawn')):
            self.assertEqual(complete('# 日本語\nimport sample\nsample.cre')['items'][0]['name'], 'create_node')
            self.assertEqual(complete('pri')['items'][0]['name'], 'print')

    def test_large_incomplete_source_is_fast(self):
        """5,000行の書きかけの本文でも、宣言はC++で読むので短時間で終わる(以前のastでは約100ms)。"""
        source = 'import sample\ninvalid (\n' + 'value = 1\n' * 5000 + 'sample.cre'
        complete(source)
        start = time.perf_counter()
        for index in range(10):
            complete(source.replace('value = 1', 'value = %d' % index, 1))
        average = (time.perf_counter() - start) * 100
        print('5,000-line completion with edits: %.2f ms' % average)
        self.assertLess(average, 50)

    def test_warm_timing(self):
        complete('import sample\nsample.cre')
        start = time.perf_counter()
        for _ in range(200):
            complete('import sample\nsample.cre')
        print('warm static lookup average: %.3f ms' % ((time.perf_counter()-start)*1000/200))

    def test_analysis_never_executes_or_imports_source(self):
        result = json.loads(analyze('import nonexistent_hedit_test_module\nraise RuntimeError("never execute")'))
        self.assertEqual(result['diagnostics'], [])

    def test_analysis_syntax_line_and_top_level_return(self):
        error = json.loads(analyze('# 日本語\nif True\n    pass'))['diagnostics'][0]
        self.assertEqual(error['line'], 2)
        self.assertEqual(error['severity'], 'error')
        self.assertIn('return', json.loads(analyze('return 1'))['diagnostics'][0]['message'])

    def test_analysis_warning_and_valid_source(self):
        diagnostics = json.loads(analyze('value = 1 is 2'))['diagnostics']
        # 定数のis比較へのSyntaxWarningはPython 3.8以降。2022の3.7は警告しない。
        if sys.version_info >= (3, 8):
            self.assertEqual(diagnostics[0]['severity'], 'warning')
        else:
            self.assertEqual(diagnostics, [])
        self.assertEqual(json.loads(analyze('value = 1 == 2'))['diagnostics'], [])

    def test_analysis_limits_and_null(self):
        self.assertIn('skipped', json.loads(analyze(' ' * 1_000_001)))
        self.assertIn('skipped', json.loads(analyze('\n' * 20_000)))
        self.assertTrue(json.loads(analyze('\x00')).get('diagnostics') or json.loads(analyze('\x00')).get('skipped'))


if __name__ == '__main__':
    unittest.main()
