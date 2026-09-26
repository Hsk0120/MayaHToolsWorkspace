"""Maya初期化不要の補完テスト。外部パッケージは不要。"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import types
import threading
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from hedit.completion import Index
from hedit import bridge
from hedit.analysis import analyze


class CompletionTests(unittest.TestCase):
    def test_history_compaction_is_only_for_legacy_snapshot(self):
        self.assertEqual(bridge.compact_history('one\n\noptimization\n \non\n\n\nnext\n'),
                         'one\noptimization on\nnext\n')

    def test_slow_import_scan_does_not_block_caller(self):
        entered, release = threading.Event(), threading.Event()
        def slow_scan(path):
            entered.set()
            release.wait(2)
            raise OSError('offline directory')
        index = Index(['offline'], {'available_module': {}}, async_scan=True)
        try:
            with mock.patch('os.scandir', side_effect=slow_scan):
                start = time.perf_counter()
                items = index.complete('import available')
                self.assertLess(time.perf_counter()-start, .2)
                self.assertEqual(items[0]['name'], 'available_module')
                self.assertTrue(entered.wait(1))
                release.set(); index.scan_thread.join(1)
        finally:
            release.set()

    def test_incomplete_large_source_has_bounded_parse_attempts(self):
        import ast
        source = 'import sample\ninvalid (\n' + 'value = 1\n'*5000 + 'sample.cre'
        with mock.patch('ast.parse', wraps=ast.parse) as parse:
            self.index.complete(source)
            self.assertLessEqual(parse.call_count, 5)
            before = parse.call_count
            self.index.complete(source+'a')
            self.assertEqual(parse.call_count, before)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.root.joinpath('sample.py').write_text('raise RuntimeError("must not execute")\n\ndef create_node(name, **kwargs):\n    pass\n\nclass Example:\n    def get_value(self):\n        pass\n', encoding='utf-8')
        self.index = Index([str(self.root)], {'dynamic': {'createNode': {}, 'ls': {}}})

    def tearDown(self):
        self.directory.cleanup()

    def names(self, code):
        return [item['name'] for item in self.index.complete(code)]

    def test_import_alias_and_signature_without_execution(self):
        items = self.index.complete('import sample as s\ns.cre')
        self.assertEqual(items, [{'name': 'create_node', 'detail': 'create_node(name, **kwargs)'}])
        self.assertNotIn('sample', sys.modules)

    def test_dynamic_exports(self):
        self.assertEqual(self.names('import dynamic as d\nd.l'), ['ls'])

    def test_dot_completion_never_scans_runtime_paths(self):
        with mock.patch('os.scandir', side_effect=AssertionError('must not scan')), mock.patch('os.path.isfile', side_effect=AssertionError('must not probe')):
            index = Index(['//unavailable/share'], {'maya.cmds': {'ls': {}, 'createNode': {}}})
            self.assertEqual([row['name'] for row in index.complete('import maya.cmds as cmds\ncmds.')], ['createNode', 'ls'])

    def test_local_function_and_class(self):
        self.assertIn('function', self.names('def function(arg):\n    pass\nfun'))
        self.assertEqual(self.names('import sample\nsample.Example.get_'), ['get_value'])

    def test_from_import_and_discovery(self):
        self.assertIn('sample', self.names('import sam'))
        self.assertEqual(self.names('from sample import cre'), ['create_node'])
        self.assertEqual(self.names('from sample import Example as E\nE.get'), ['get_value'])

    def test_relative_export(self):
        package = self.root / 'package'; package.mkdir()
        (package / '__init__.py').write_text('from .api import Example\n', encoding='utf-8')
        (package / 'api.py').write_text('class Example:\n    def member(self):\n        pass\n', encoding='utf-8')
        self.assertEqual(self.names('import package\npackage.Example.mem'), ['member'])

    def test_nested_relative_package_and_type_checking_exports(self):
        package = self.root / 'package'; package.mkdir()
        nodes = package / 'nodes'; nodes.mkdir()
        (package / '__init__.py').write_text('from . import nodes\n', encoding='utf-8')
        (nodes / '__init__.py').write_text('from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .joint import Joint\n', encoding='utf-8')
        (nodes / 'joint.py').write_text('class Joint:\n    def get_matrix(self): pass\n', encoding='utf-8')
        self.assertIn('Joint', self.names('import package\npackage.nodes.'))
        self.assertEqual(self.names('import package as p\np.nodes.Joint.get_'), ['get_matrix'])
        self.assertIn('Joint', self.names('from package import nodes\nnodes.'))
        self.assertNotIn('package', sys.modules)

    def test_absolute_subpackage_reexport_does_not_recurse(self):
        package = self.root / 'package'; package.mkdir()
        (package / '__init__.py').write_text('from package import nodes\n', encoding='utf-8')
        (package / 'nodes.py').write_text('class Node: pass\n', encoding='utf-8')
        self.assertIn('Node', self.names('import package\npackage.nodes.'))

    def test_cache_invalidation(self):
        self.assertTrue(self.names('import sample\nsample.cre'))
        self.root.joinpath('sample.py').write_text('def changed():\n    pass\n', encoding='utf-8')
        self.assertEqual(self.names('import sample\nsample.ch'), ['changed'])
        self.assertEqual(self.names('import sample\nsample.cre'), [])

    def test_live_exports_follow_changes_without_refresh(self):
        module = types.ModuleType('hedit_fixture')
        module.before = 1
        index = Index([], runtime=bridge.runtime_module)
        with mock.patch.dict(sys.modules, {'hedit_fixture': module}):
            self.assertEqual([r['name'] for r in index.complete('import hedit_fixture as f\nf.')], ['before'])
            del module.before
            module.after = 2
            self.assertEqual([r['name'] for r in index.complete('import hedit_fixture as f\nf.')], ['after'])

    def test_loaded_source_and_class_follow_edits_without_execution(self):
        module = types.ModuleType('sample')
        module.__file__ = str(self.root / 'sample.py')
        index = Index([], runtime=bridge.runtime_module)
        with mock.patch.dict(sys.modules, {'sample': module}), mock.patch('os.scandir', side_effect=AssertionError('no scan')):
            self.assertIn('get_value', [r['name'] for r in index.complete('import sample\nsample.Example.')])
            (self.root / 'sample.py').write_text('raise RuntimeError("never run")\nclass Example:\n    def new_method(self): pass\n', encoding='utf-8')
            self.assertEqual([r['name'] for r in index.complete('import sample\nsample.Example.')], ['new_method'])
            (self.root / 'sample.py').write_text('class Example: (', encoding='utf-8')
            self.assertEqual([r['name'] for r in index.complete('import sample\nsample.Example.')], ['new_method'])

    def test_new_and_removed_top_level_files(self):
        self.names('import sam')
        (self.root / 'newly_added.py').write_text('', encoding='utf-8')
        self.assertIn('newly_added', self.names('import newly'))
        (self.root / 'newly_added.py').unlink()
        self.assertNotIn('newly_added', self.names('import newly'))

    def test_keyword_and_builtin_categories(self):
        self.assertEqual(self.index.complete('ret')[0]['kind'], 'keyword')
        self.assertEqual(self.index.complete('pri')[0]['kind'], 'builtin')

    def test_in_process_unicode_and_recovery(self):
        with mock.patch.object(bridge, '_index', self.index), mock.patch('subprocess.Popen', side_effect=AssertionError('must not spawn')):
            response = json.loads(bridge.complete('# 日本語\nimport sample\nsample.cre'))
            self.assertEqual(response['items'][0]['name'], 'create_node')
            self.assertIn('error', json.loads(bridge.complete(None)))
            self.assertEqual(json.loads(bridge.complete('pri'))['items'][0]['name'], 'print')

    def test_warm_timing(self):
        self.index.complete('import sample\nsample.cre')
        start = time.perf_counter()
        for _ in range(200):
            self.index.complete('import sample\nsample.cre')
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
