"""専用一時データでファイル整理基盤の異常系を検証する。"""
import os
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maya/inhouse/QuickPathExplorer/python'))
from qpeTransactions import FileTransactions, Cancelled
from qpeSearch import searchFiles, createZip, extractZip, hashFile, duplicateFiles, compareFolders, sceneInfo


class OrganizerTests(unittest.TestCase):
    """実ファイルを使い、完了と失敗時の保存内容を照合する。"""

    def setUp(self):
        """利用者のファイルと設定に触れない実験領域を作る。"""
        self.temp = tempfile.TemporaryDirectory(prefix='qpe-operations-')
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.target = self.root / 'target'
        self.source.mkdir()
        self.target.mkdir()
        self.file = self.source / '日本語 file.txt'
        self.file.write_text('original', encoding='utf8')
        self.engine = FileTransactions(self.root / 'undo')

    def tearDown(self):
        """このテストが作った領域だけを片付ける。"""
        self.temp.cleanup()

    def test_copy_and_persisted_undo(self):
        """再起動相当の新規エンジンでもコピーを戻せる。"""
        result = self.engine.run('copy', [str(self.file)], str(self.target))
        self.assertFalse(result['errors'])
        self.assertEqual((self.target / self.file.name).read_text(), 'original')
        FileTransactions(self.root / 'undo').undo()
        self.assertFalse((self.target / self.file.name).exists())
        self.assertTrue(self.file.exists())

    def test_replace_undo(self):
        """上書き前の内容をUndoで復元する。"""
        target = self.target / self.file.name
        target.write_text('old')
        self.engine.run('copy', [str(self.file)], str(self.target), 'replace')
        self.assertEqual(target.read_text(), 'original')
        self.engine.undo()
        self.assertEqual(target.read_text(), 'old')

    def test_move_undo(self):
        """移動のUndoでは元の場所へ戻す。"""
        result = self.engine.run('move', [str(self.file)], str(self.target))
        self.assertFalse(result['errors'])
        self.assertFalse(self.file.exists())
        self.engine.undo()
        self.assertEqual(self.file.read_text(), 'original')

    def test_duplicate(self):
        """複製は同名の元ファイルを上書きしない。"""
        result = self.engine.run('duplicate', [str(self.file)])
        self.assertEqual(len(result['completed']), 1)
        self.assertNotEqual(result['completed'][0], str(self.file))
        self.engine.undo()
        self.assertTrue(self.file.exists())

    def test_skip(self):
        """スキップは成功やUndo履歴として数えない。"""
        result = self.engine.run('copy', [str(self.file)], str(self.source), 'skip')
        self.assertEqual(result['skipped'], [str(self.file)])
        self.assertFalse(self.engine.history)

    def test_undo_refuses_modified_target(self):
        """コピー後に利用者が変更した内容を消さない。"""
        self.engine.run('copy', [str(self.file)], str(self.target))
        target = self.target / self.file.name
        target.write_text('user changed')
        with self.assertRaises(ValueError):
            self.engine.undo()
        self.assertEqual(target.read_text(), 'user changed')

    def test_undo_refuses_occupied_source(self):
        """移動元の同名ファイルをUndoで上書きしない。"""
        self.engine.run('move', [str(self.file)], str(self.target))
        self.file.write_text('new user file')
        with self.assertRaises(FileExistsError):
            self.engine.undo()
        self.assertEqual(self.file.read_text(), 'new user file')

    def test_cancel_during_copy(self):
        """中止時は作業ファイルを消し、コピー元を維持する。"""
        self.file.write_bytes(b'x' * (3 * 1024 * 1024))
        cancel = threading.Event()
        result = self.engine.run('copy', [str(self.file)], str(self.target), cancel=cancel,
                                 progress=lambda path, size: cancel.set())
        self.assertTrue(result['cancelled'])
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertTrue(self.file.exists())

    def test_partial_failure_keeps_undo(self):
        """複数選択の一部失敗でも完了分を戻せる。"""
        result = self.engine.run('copy', [str(self.file), str(self.source / 'missing')], str(self.target))
        self.assertEqual(len(result['completed']), 1)
        self.assertEqual(len(result['errors']), 1)
        self.engine.undo()
        self.assertEqual(list(self.target.iterdir()), [])

    def test_descendant_destination_rejected(self):
        """自身の子孫への再帰コピーを拒否する。"""
        result = self.engine.run('copy', [str(self.source)], str(self.source))
        self.assertTrue(result['errors'])

    def test_nested_selection(self):
        """親と子の同時指定で子を二重に処理しない。"""
        result = self.engine.run('copy', [str(self.source), str(self.file)], str(self.target))
        self.assertEqual(len(result['completed']), 1)
        self.assertEqual(len(result['skipped']), 1)

    def test_failed_copy_preserves_existing(self):
        """コピー準備失敗時は上書き先を動かさない。"""
        target = self.target / self.file.name
        target.write_text('old')
        with patch('qpeTransactions.copyEntry', side_effect=PermissionError('denied')):
            result = self.engine.run('copy', [str(self.file)], str(self.target), 'replace')
        self.assertTrue(result['errors'])
        self.assertEqual(target.read_text(), 'old')

    def test_batch_rename_and_undo(self):
        """日本語を含む一括変更とUndoを照合する。"""
        second = self.source / 'two.txt'
        second.write_text('two')
        self.engine.rename([(str(self.file), 'new.txt'), (str(second), '新規.txt')])
        self.assertFalse(self.file.exists())
        self.engine.undo()
        self.assertEqual(self.file.read_text(), 'original')
        self.assertEqual(second.read_text(), 'two')

    def test_batch_conflict_is_atomic(self):
        """競合は全ての変更前に検出する。"""
        with self.assertRaises(FileExistsError):
            self.engine.rename([(str(self.file), 'new.txt'), (str(self.file), 'new.txt')])
        self.assertTrue(self.file.exists())

    def test_trash_failure_keeps_source(self):
        """ごみ箱が使えなくても完全削除に切り替えない。"""
        with patch('qpeTransactions.recycle', side_effect=OSError('unavailable')):
            result = self.engine.run('trash', [str(self.file)])
        self.assertTrue(result['errors'])
        self.assertTrue(self.file.exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows recycle bin')
    def test_windows_recycle_and_undo(self):
        """専用の一時ファイルだけを実際のごみ箱へ送り復元する。"""
        result = self.engine.run('trash', [str(self.file)])
        self.assertFalse(result['errors'], result)
        self.assertFalse(self.file.exists())
        self.engine.undo()
        self.assertEqual(self.file.read_text(), 'original')

    def test_recursive_search(self):
        """再帰・拡張子・名前・隠しファイルを区別する。"""
        sub = self.source / 'sub'
        sub.mkdir()
        (sub / 'asset.ma').write_text('scene')
        (sub / '.hidden.ma').write_text('hidden')
        result = searchFiles(str(self.source), 'asset', '*.ma;*.mb')
        self.assertEqual(len(result['paths']), 1)
        self.assertEqual(len(searchFiles(str(self.source), extensions='*.ma', hidden=True)['paths']), 2)

    def test_search_cancel(self):
        """キャンセル要求を無視して検索を続けない。"""
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            searchFiles(str(self.source), cancel=cancel)

    def test_zip_roundtrip(self):
        """日本語ファイルを圧縮して同じ内容へ展開する。"""
        archive = self.root / 'bundle.zip'
        createZip([str(self.source)], archive)
        output = self.root / 'unpacked'
        extractZip(archive, output)
        self.assertEqual((output / 'source' / self.file.name).read_text(), 'original')

    def test_zip_path_escape(self):
        """アーカイブが展開先の外へ書き込めない。"""
        archive = self.root / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.writestr('../escape.txt', 'bad')
        with self.assertRaises(ValueError):
            extractZip(archive, self.root / 'out')
        self.assertFalse((self.root / 'escape.txt').exists())

    def test_compare_and_duplicates(self):
        """同じ内容と異なる内容を名前だけで判定しない。"""
        twin = self.source / 'twin.txt'
        twin.write_text('original')
        groups = duplicateFiles(str(self.source))['groups']
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 2)
        (self.target / self.file.name).write_text('different')
        result = compareFolders(str(self.source), str(self.target))
        self.assertEqual({c['state'] for c in result['changes']}, {'Changed', 'New'})

    def test_scene_metadata(self):
        """Mayaを起動せず宣言と欠損パスを抽出する。"""
        scene = self.source / 'scene.ma'
        missing = (self.source / 'missing.png').as_posix()
        scene.write_text('requires maya "2027";\nsetAttr ".ftn" -type "string" "' + missing + '";')
        info = sceneInfo(scene)
        self.assertIn('2027', info)
        self.assertIn('Missing: ' + missing, info)

    def test_created_file_undo(self):
        """新規作成も変更されていなければ戻せる。"""
        self.engine.recordCreation(self.file)
        self.engine.undo()
        self.assertFalse(self.file.exists())

    def test_case_only_rename(self):
        """大文字小文字だけの変更とUndoで実際の名前を戻す。"""
        original = self.file.name
        self.engine.rename([(str(self.file), original.upper())])
        self.assertIn(original.upper(), [entry.name for entry in self.source.iterdir()])
        self.engine.undo()
        self.assertIn(original, [entry.name for entry in self.source.iterdir()])

    def test_empty_directory_zip(self):
        """空フォルダーも圧縮から失われない。"""
        (self.source / 'empty').mkdir()
        archive = self.root / 'empty.zip'
        createZip([str(self.source)], archive)
        extractZip(archive, self.root / 'expanded')
        self.assertTrue((self.root / 'expanded/source/empty').is_dir())

    def test_compare_rejects_overlap(self):
        """親子フォルダー間の同期計画を拒否する。"""
        with self.assertRaises(ValueError):
            compareFolders(str(self.root), str(self.source))

    def test_shared_history_is_reloaded(self):
        """2ウィンドウからの操作で履歴を上書きしない。"""
        other = FileTransactions(self.root / 'undo')
        self.engine.run('copy', [str(self.file)], str(self.target))
        other.run('duplicate', [str(self.file)])
        self.assertEqual(len(other.history), 2)
        self.engine.undo()
        self.assertTrue((self.target / self.file.name).exists())
        self.engine.undo()
        self.assertFalse((self.target / self.file.name).exists())

    def test_operation_lock(self):
        """別エンジンの同時書込みをOSロックで拒否する。"""
        other = FileTransactions(self.root / 'undo')
        with self.engine.exclusive():
            with self.assertRaises(OSError):
                other.run('copy', [str(self.file)], str(self.target))

    def test_discard_history_preserves_result(self):
        """履歴の破棄は実行済みファイルを消さず退避物だけを消す。"""
        self.engine.run('move', [str(self.file)], str(self.target))
        backup = self.engine.history[-1]['entries'][0]['sourceBackup']
        self.assertTrue(Path(backup).exists())
        self.engine.discardHistory()
        self.assertFalse(Path(backup).exists())
        self.assertTrue((self.target / self.file.name).exists())
        self.assertFalse(self.engine.history)

    def test_undo_backup_change(self):
        """退避物が外部で変更されても勝手に戻さない。"""
        target = self.target / self.file.name
        target.write_text('old')
        self.engine.run('copy', [str(self.file)], str(self.target), 'replace')
        backup = self.engine.history[-1]['entries'][0]['backup']
        Path(backup).write_text('external change')
        with self.assertRaises(ValueError):
            self.engine.undo()
        self.assertEqual(target.read_text(), 'original')


if __name__ == '__main__':
    unittest.main(verbosity=2)
