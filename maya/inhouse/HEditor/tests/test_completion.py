"""Maya初期化不要の補完テスト。外部パッケージは不要。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from heditor.worker import Index


class CompletionTests(unittest.TestCase):
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

    def test_cache_invalidation(self):
        self.assertTrue(self.names('import sample\nsample.cre'))
        self.root.joinpath('sample.py').write_text('def changed():\n    pass\n', encoding='utf-8')
        self.assertEqual(self.names('import sample\nsample.ch'), ['changed'])
        self.assertEqual(self.names('import sample\nsample.cre'), [])

    def test_worker_protocol_unicode_and_recovery(self):
        requests = [{'paths': [str(self.root)]}, {'id': 2, 'source': '# 日本語\nimport sample\nsample.cre'}, {'id': 3}, {'id': 4, 'source': 'pri'}]
        result = subprocess.run([sys.executable, '-S', '-u', str(ROOT / 'scripts/heditor/worker.py')], input=''.join(json.dumps(row)+'\n' for row in requests), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertTrue(responses[0]['ready'])
        self.assertEqual(responses[1]['items'][0]['name'], 'create_node')
        self.assertIn('error', responses[2])
        self.assertEqual(responses[3]['items'][0]['name'], 'print')

    def test_warm_timing(self):
        self.index.complete('import sample\nsample.cre')
        start = time.perf_counter()
        for _ in range(200):
            self.index.complete('import sample\nsample.cre')
        print('warm static lookup average: %.3f ms' % ((time.perf_counter()-start)*1000/200))


if __name__ == '__main__':
    unittest.main()
