"""後始末・衝突検出の失敗経路を検証する。"""
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
        undo = importlib.import_module('mlib.decorator')
        logger = importlib.import_module('mlib.logger')
        error = ValueError('primary')
        # 1回目はUndo状態の問い合わせ(有効)、2回目が開く、3回目が閉じる。
        with mock.patch.object(undo.cmds, 'undoInfo', side_effect=[True, None, RuntimeError('close')]), mock.patch.object(logger, 'warning') as warning:
            with self.assertRaises(ValueError) as caught:
                with undo.undoChunk():
                    raise error
            self.assertIs(caught.exception, error)
            warning.assert_called_once()

    def test_transaction_cleanup_failures(self):
        """ガード・終了・復旧失敗をそれぞれ通知し元の例外を保つ。"""
        undo = importlib.import_module('mlib.decorator')
        logger = importlib.import_module('mlib.logger')
        with mock.patch.object(undo.cmds, 'undoInfo', side_effect=[None, RuntimeError('close')]), mock.patch.object(undo.cmds, 'createNode', side_effect=RuntimeError('guard')), mock.patch.object(undo.cmds, 'undo', side_effect=RuntimeError('rollback')) as rollback, mock.patch.object(logger, 'warning') as warning:
            with self.assertRaisesRegex(ValueError, 'primary'):
                with undo.undoTransaction():
                    raise ValueError('primary')
            self.assertEqual(warning.call_count, 3)
            rollback.assert_not_called()

    def test_transaction_rollback_error(self):
        """安全に閉じた後のundo失敗も元例外を維持する。"""
        undo = importlib.import_module('mlib.decorator')
        logger = importlib.import_module('mlib.logger')
        with mock.patch.object(undo.cmds, 'undoInfo'), mock.patch.object(undo.cmds, 'createNode', return_value='guard'), mock.patch.object(undo.cmds, 'delete'), mock.patch.object(undo.cmds, 'undo', side_effect=RuntimeError('rollback')), mock.patch.object(logger, 'warning') as warning:
            with self.assertRaisesRegex(ValueError, 'primary'):
                with undo.undoTransaction():
                    raise ValueError('primary')
            warning.assert_called_once()

    def test_jobs_continue_and_retry(self):
        """解除失敗後も続行し、失敗分だけ再試行する。"""
        cls = importlib.import_module('mlib.common.scriptJobs').ScriptJobs
        logger = importlib.import_module('mlib.logger')
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


    def test_public_name_collision(self):
        """別モジュールの同名公開クラスは両方の定義元を示して拒否する。"""
        import sys
        tools = Path(__file__).resolve().parents[1] / 'checks'
        sys.path.insert(0, str(tools))
        try:
            from check_mlib_exports import CLASS_PACKAGES, check
        finally:
            sys.path.remove(str(tools))
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / 'fixture'
            package.mkdir()
            (package / '__init__.py').write_text('__all__ = []\n', encoding='utf-8')
            for folder in CLASS_PACKAGES + ('cmds',):
                (package / folder).mkdir()
                (package / folder / '__init__.py').write_text('__all__ = []\n', encoding='utf-8')
            for suffix in ('a', 'b'):
                (package / 'nodes' / (suffix + '.py')).write_text('class Sample:\n    pass\n', encoding='utf-8')
            issues = [issue for issue in check(package) if issue.code == 'E011']
            self.assertEqual(len(issues), 1)
            diagnostic = str(issues[0])
            self.assertIn('fixture.nodes.a', diagnostic)
            self.assertIn('nodes\\b.py', diagnostic.replace('/', '\\'))
            self.assertIn('Sample', diagnostic)


if __name__ == '__main__':
    unittest.main()
