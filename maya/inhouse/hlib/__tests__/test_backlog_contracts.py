"""後始末・衝突検出・一括引数検証の失敗経路を検証する。"""
import importlib
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock


class BacklogContractsTest(unittest.TestCase):
    """本処理の例外を後始末で失わず、共有処理の契約を維持する。"""

    def test_undo_close_preserves_primary(self):
        """チャンク終了失敗を警告し元の例外を再送出する。"""
        undo = importlib.import_module('hlib.decorators.undo')
        logger = importlib.import_module('hlib.utils.logger')
        error = ValueError('primary')
        with mock.patch.object(undo.cmds, 'undoInfo', side_effect=[None, RuntimeError('close')]), mock.patch.object(logger, 'warning') as warning:
            with self.assertRaises(ValueError) as caught:
                with undo.undo_chunk():
                    raise error
            self.assertIs(caught.exception, error)
            warning.assert_called_once()

    def test_transaction_cleanup_failures(self):
        """ガード・終了・復旧失敗をそれぞれ通知し元の例外を保つ。"""
        undo = importlib.import_module('hlib.decorators.undo')
        logger = importlib.import_module('hlib.utils.logger')
        with mock.patch.object(undo.cmds, 'undoInfo', side_effect=[None, RuntimeError('close')]), mock.patch.object(undo.cmds, 'createNode', side_effect=RuntimeError('guard')), mock.patch.object(undo.cmds, 'undo', side_effect=RuntimeError('rollback')) as rollback, mock.patch.object(logger, 'warning') as warning:
            with self.assertRaisesRegex(ValueError, 'primary'):
                with undo.undo_transaction():
                    raise ValueError('primary')
            self.assertEqual(warning.call_count, 3)
            rollback.assert_not_called()

    def test_transaction_rollback_error(self):
        """安全に閉じた後のundo失敗も元例外を維持する。"""
        undo = importlib.import_module('hlib.decorators.undo')
        logger = importlib.import_module('hlib.utils.logger')
        with mock.patch.object(undo.cmds, 'undoInfo'), mock.patch.object(undo.cmds, 'createNode', return_value='guard'), mock.patch.object(undo.cmds, 'delete'), mock.patch.object(undo.cmds, 'undo', side_effect=RuntimeError('rollback')), mock.patch.object(logger, 'warning') as warning:
            with self.assertRaisesRegex(ValueError, 'primary'):
                with undo.undo_transaction():
                    raise ValueError('primary')
            warning.assert_called_once()

    def test_jobs_continue_and_retry(self):
        """解除失敗後も続行し、失敗分だけ再試行する。"""
        cls = importlib.import_module('hlib.general.scriptJobs').ScriptJobs
        logger = importlib.import_module('hlib.utils.logger')
        group = cls()
        bad, good = mock.Mock(), mock.Mock()
        bad.stop.side_effect = RuntimeError('busy')
        group._jobs = {'bad': bad, 'good': good}
        with mock.patch.object(logger, 'warning'):
            with self.assertRaises(RuntimeError):
                group.stop()
        good.stop.assert_called_once_with()
        self.assertEqual(list(group._jobs), ['bad'])
        bad.stop.side_effect = None
        group.stop()
        self.assertFalse(group._jobs)

    def test_json_keeps_original_error(self):
        """保存失敗に削除失敗が重なっても保存例外を維持する。"""
        storage = importlib.import_module('hlib.json.storage')
        logger = importlib.import_module('hlib.utils.logger')
        primary = OSError('replace failed')
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(storage.os, 'replace', side_effect=primary), mock.patch.object(Path, 'unlink', side_effect=OSError('cleanup')), mock.patch.object(logger, 'warning') as warning:
                with self.assertRaises(OSError) as caught:
                    storage.dump({}, Path(folder) / 'value.json')
                self.assertIs(caught.exception, primary)
                warning.assert_called_once()

    def test_public_name_collision(self):
        """別モジュールの同名公開クラスは両方の定義元を示して拒否する。"""
        discovery = importlib.import_module('hlib._core.discovery')
        package = types.ModuleType('fixture'); package.__path__ = []
        modules = {'fixture': package}
        for suffix in ('a', 'b'):
            module = types.ModuleType('fixture.' + suffix)
            module.Sample = type('Sample', (), {'__module__': module.__name__, '__hlib_public__': True})
            modules[module.__name__] = module
        with mock.patch.object(discovery.pkgutil, 'iter_modules', return_value=[(None, 'a', False), (None, 'b', False)]), mock.patch.object(discovery.importlib, 'import_module', side_effect=modules.__getitem__):
            with self.assertRaisesRegex(ValueError, 'fixture.a.Sample and fixture.b.Sample'):
                discovery.discover_node_package('fixture')

    def test_signature_cache_respects_overrides(self):
        """派生ごとの引数と後からの変更を独立に検証する。"""
        bulk = importlib.import_module('hlib._core.collection')
        class A:
            def edit(self, value):
                """1引数を受け取る。"""
        class B:
            def edit(self, value, required):
                """2引数を受け取る。"""
        group = bulk.BulkCollection()
        group._bulk_methods = {'edit': A.edit}
        group._items = [A(), A(), B()]
        with self.assertRaises(TypeError):
            group._prepare_calls('edit', [(1,)] * 3, None)
        with mock.patch.object(bulk.inspect, 'signature', wraps=bulk.inspect.signature) as signature:
            group._prepare_calls('edit', [(1,), (2,), (3, 4)], None)
            self.assertEqual(signature.call_count, 2)
        B.edit = A.edit
        group._prepare_calls('edit', [(1,)] * 3, None)


if __name__ == '__main__':
    unittest.main()
