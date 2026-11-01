"""専用データだけで高速削除・永続Undoと完全削除の拒否を検証する。"""
import copy
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
import qpeRecycle
from qpeTransactions import FileTransactions, fingerprint, copyEntry


@unittest.skipUnless(os.name == 'nt', 'Windows Shell')
class RecycleTests(unittest.TestCase):
    """実ごみ箱に入れた試験項目は必ず復元してから一時領域を掃除する。"""

    def setUp(self):
        """リポジトリの専用出力領域に限定して試験データを作る。"""
        base = ROOT / '.maya-output/qpe-delete-20261101/tests'
        base.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=str(base))
        self.root = Path(self.temporary.name)
        self.folder = self.root / '日本語 ‐ folder'
        self.folder.mkdir()
        self.file = self.folder / 'asset.dat'
        self.file.write_bytes(b'original')
        self.engine = FileTransactions(self.root / 'undo')
        self.receipts = []
        original = qpeRecycle.recycle

        def recording(*args, **kwargs):
            """失敗した試験でもこの試験が作ったごみ箱項目を特定できるようにする。"""
            receipt = original(*args, **kwargs)
            self.receipts.append((receipt, str(args[0])))
            return receipt

        self.patcher = patch('qpeTransactions.recycle', side_effect=recording)
        self.patcher.start()

    def tearDown(self):
        """既存のごみ箱には触れず、記録済みの試験項目だけを戻す。"""
        self.patcher.stop()
        for receipt, path in self.receipts:
            if Path(receipt['physicalPath']).exists():
                output = Path(path)
                if output.exists():
                    output = self.root / ('recovered-' + Path(receipt['physicalPath']).name)
                output.parent.mkdir(parents=True, exist_ok=True)
                qpeRecycle.restore(receipt, output)
        self.temporary.cleanup()

    def trash(self, path=None, **kwargs):
        """失敗を見逃さず専用データをごみ箱へ送る。"""
        result = self.engine.run('trash', [str(path or self.folder)], **kwargs)
        self.assertFalse(result['errors'], result)
        self.assertEqual(len(result['completed']), 1, result)
        return result

    def test_no_content_read_or_copy_and_persisted_undo_redo(self):
        """削除・再起動後Undo・Redoすべてで内容ハッシュとコピーを呼ばない。"""
        with patch('qpeTransactions.fingerprint', side_effect=AssertionError('content read')), \
             patch('qpeTransactions.copyEntry', side_effect=AssertionError('content copy')):
            self.trash()
            self.assertFalse(self.folder.exists())
            self.assertEqual(set(p.name for p in self.engine.directory.iterdir()), {'journal.json', 'operation.lock'})
            self.engine = FileTransactions(self.engine.directory)
            self.engine.undo()
            self.assertEqual(self.file.read_bytes(), b'original')
            result = self.engine.redo()
            self.assertFalse(result['errors'], result)
            self.engine.undo()
            self.assertEqual(self.file.read_bytes(), b'original')

    def test_no_orphan_shell_metadata_after_restore(self):
        """復元後は今回作ったごみ箱のデータと管理項目が残らない。"""
        self.trash()
        receipt = self.receipts[-1][0]
        self.engine.undo()
        self.assertFalse(Path(receipt['physicalPath']).exists())
        self.assertFalse(Path(receipt['metadataPath']).exists())

    def test_pre_cancel(self):
        """開始前の中止ではShellへ渡さず原本を維持する。"""
        cancel = threading.Event()
        cancel.set()
        result = self.engine.run('trash', [str(self.folder)], cancel=cancel)
        self.assertTrue(result['cancelled'])
        self.assertTrue(self.file.exists())
        self.assertFalse(self.receipts)

    def test_cancel_at_shell_pre_delete(self):
        """Shell直前の中止でも原本が残り、完了履歴が作られない。"""
        cancel = threading.Event()
        result = self.engine.run('trash', [str(self.folder)], cancel=cancel,
                                 progress=lambda path, size: cancel.set())
        self.assertTrue(result['cancelled'], result)
        self.assertFalse(result['completed'])
        self.assertTrue(self.file.exists())
        self.assertFalse(self.engine.history)

    def test_permanent_delete_callback_refused(self):
        """完全削除に切り替わった通知をShell実行前に拒否する。"""
        sink = qpeRecycle._ProgressSink()
        self.assertLess(sink._pre_delete(None, 0, None), 0)
        self.assertIn('Permanent deletion was refused', str(sink.error))

    def test_restore_collision_keeps_both(self):
        """復元先の同名フォルダーを上書き・結合しない。"""
        self.trash()
        self.folder.mkdir()
        self.file.write_bytes(b'new')
        with self.assertRaises(FileExistsError):
            self.engine.undo()
        self.assertEqual(self.file.read_bytes(), b'new')
        self.assertTrue(Path(self.receipts[-1][0]['physicalPath']).exists())

    def test_restore_identity_mismatch_refused(self):
        """ごみ箱項目が別物へ差し替わった場合は復元を拒否する。"""
        self.trash()
        receipt = copy.deepcopy(self.receipts[-1][0])
        receipt['identity'][1] += 1
        with self.assertRaises(ValueError):
            qpeRecycle.restore(receipt, self.folder)
        self.assertFalse(self.folder.exists())

    def test_missing_recycled_item_refused(self):
        """ごみ箱から項目が失われた状態を明示的な失敗にする。"""
        self.trash()
        receipt = self.receipts[-1][0]
        qpeRecycle.restore(receipt, self.root / 'restored-elsewhere')
        with self.assertRaises(FileNotFoundError):
            self.engine.undo()

    def test_redo_refuses_modified_file(self):
        """復元後の編集を検出し、Redoで編集済みデータを削除しない。"""
        self.trash()
        self.engine.undo()
        self.file.write_bytes(b'changed size')
        with self.assertRaises(ValueError):
            self.engine.redo()
        self.assertTrue(self.file.exists())

    def test_same_name_distinct_deletions(self):
        """同名を二度削除しても、それぞれの正しい内容へUndoできる。"""
        self.trash()
        self.folder.mkdir()
        self.file.write_bytes(b'second')
        self.trash()
        self.engine.undo()
        self.assertEqual(self.file.read_bytes(), b'second')
        self.folder.rename(self.root / 'second-restored')
        self.engine.undo()
        self.assertEqual(self.file.read_bytes(), b'original')

    def test_legacy_backup_undo(self):
        """旧版の独立したバックアップ履歴も復元できる。"""
        backup = self.engine.directory / 'legacy'
        copyEntry(self.file, backup)
        stamp = fingerprint(backup)
        self.file.unlink()
        self.engine.history = [dict(id='legacy', action='trash', entries=[
            dict(source=str(self.file), target='', backup=str(backup), backupStamp=stamp, stamp=stamp)])]
        self.engine.save()
        self.engine.undo()
        self.assertEqual(self.file.read_bytes(), b'original')

    def test_history_cleanup_does_not_empty_recycle_bin(self):
        """QPE履歴の整理だけでWindowsごみ箱の原本を消さない。"""
        self.trash()
        self.engine.discardHistory()
        self.assertTrue(Path(self.receipts[-1][0]['physicalPath']).exists())

    def test_history_save_failure_keeps_receipt(self):
        """履歴確定失敗でも削除を再試行せず、復旧用履歴からUndoする。"""
        with patch('qpeTransactions.os.replace', side_effect=PermissionError('injected')), \
             patch('qpeTransactions.time.sleep'):
            result = self.trash()
        self.assertTrue(result['warnings'])
        self.assertFalse(result['retry'])
        self.engine = FileTransactions(self.engine.directory)
        self.engine.undo()
        self.assertEqual(self.file.read_bytes(), b'original')

    def test_missing_source_after_shell_error_is_not_retried(self):
        """削除後の通知取得失敗は再削除候補にせず、手動復元を案内する。"""
        def lost_receipt(path, cancel, progress):
            """専用原本を別名で保持し、完了通知だけの失敗を注入する。"""
            Path(path).rename(self.root / 'simulated-recycled')
            raise OSError('receipt unavailable')

        with patch('qpeTransactions.recycle', side_effect=lost_receipt):
            result = self.engine.run('trash', [str(self.folder)])
        self.assertTrue(result['errors'])
        self.assertTrue(result['warnings'])
        self.assertFalse(result['retry'])
        self.assertTrue((self.root / 'simulated-recycled/asset.dat').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
