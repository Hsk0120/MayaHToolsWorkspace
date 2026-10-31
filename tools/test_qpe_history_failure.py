"""転送成功後の履歴保存失敗と再起動時の復旧を専用データで検証する。"""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maya/inhouse/QuickPathExplorer/python'))
from qpeTransactions import FileTransactions
from qpeRecovery import createJob, executeJob


class HistoryFailureTests(unittest.TestCase):
    """完了済みのファイルを再試行対象へ戻さないことを照合する。"""

    def test_journal_lock(self):
        """一時/継続ロック、直接転送/保存ジョブの四通りを検証する。"""
        for persistent in (False, True):
            for job in (False, True):
                with self.subTest(persistent=persistent, job=job), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    source = root / 'source.txt'
                    source.write_text('unchanged', encoding='utf8')
                    target = root / 'target'
                    target.mkdir()
                    engine = FileTransactions(root / 'undo')
                    replace = os.replace
                    attempts = []

                    def locked(src, dst):
                        """Undo履歴だけにWindows共有違反を注入する。"""
                        if Path(dst) == engine.journal:
                            attempts.append(dst)
                            if persistent or len(attempts) == 1:
                                raise PermissionError('simulated journal sharing violation')
                        return replace(src, dst)

                    with patch('qpeTransactions.os.replace', side_effect=locked), patch('qpeTransactions.time.sleep'):
                        if job:
                            record = createJob(root / 'jobs', 'copy', [str(source)], str(target), 'rename', {})
                            result = executeJob(engine, record, None, None)
                        else:
                            result = engine.run('copy', [str(source)], str(target))
                    self.assertEqual(result['completed'], [str(target / source.name)])
                    self.assertEqual(result['retry'], [])
                    self.assertEqual(result['errors'], [])
                    self.assertEqual(bool(result.get('warnings')), persistent)
                    self.assertEqual((target / source.name).read_text(encoding='utf8'), 'unchanged')
                    restored = FileTransactions(root / 'undo')
                    restored.undo()
                    self.assertFalse((target / source.name).exists())
                    self.assertEqual(source.read_text(encoding='utf8'), 'unchanged')

    def test_move_history_failure_preserves_source(self):
        """Moveの途中で履歴を保存できなければ元を消さず、コピー先を再作成しない。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.txt'
            source.write_text('original', encoding='utf8')
            target = root / 'target'
            target.mkdir()
            engine = FileTransactions(root / 'undo')
            with patch('qpeTransactions.os.replace', side_effect=PermissionError('locked')), patch('qpeTransactions.time.sleep'):
                result = engine.run('move', [str(source)], str(target))
            self.assertTrue(result['errors'])
            self.assertEqual(result['retry'], [])
            self.assertTrue(source.exists())
            self.assertTrue((target / source.name).exists())
            FileTransactions(root / 'undo').undo()
            self.assertTrue(source.exists())
            self.assertFalse((target / source.name).exists())


if __name__ == '__main__':
    unittest.main()
