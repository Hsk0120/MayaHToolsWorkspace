"""追加整理機能の状態・失敗・外部変更を実ファイルで検証する。"""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maya/inhouse/QuickPathExplorer/python'))
from qpeTransactions import FileTransactions
from qpeAdvancedIO import searchAdvanced, summarize, synchronize


class AdvancedTests(unittest.TestCase):
    """利用者のファイルは使わず、専用一時ディレクトリで試験する。"""

    def setUp(self):
        """衝突を含むコピー元と先を用意する。"""
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.target = self.root / 'target'
        self.source.mkdir()
        self.target.mkdir()
        self.file = self.source / 'sample.txt'
        self.file.write_text('new content')
        self.engine = FileTransactions(self.root / 'undo')

    def tearDown(self):
        """このテストが作成したデータだけを終了時に消す。"""
        self.temp.cleanup()

    def test_merge_preserves_destination_only_and_undo(self):
        """結合は先だけのデータを残し、Undoで元の先へ戻る。"""
        target = self.target / self.source.name
        target.mkdir()
        (target / 'keep.txt').write_text('keep')
        (target / self.file.name).write_text('old')
        outcome = self.engine.run('copy', [str(self.source)], str(self.target), 'merge')
        self.assertFalse(outcome['errors'])
        self.assertEqual((target / 'keep.txt').read_text(), 'keep')
        self.assertEqual((target / self.file.name).read_text(), 'new content')
        self.engine.undo()
        self.assertEqual((target / self.file.name).read_text(), 'old')
        self.assertEqual((target / 'keep.txt').read_text(), 'keep')
        self.engine.redo()
        self.assertEqual((target / self.file.name).read_text(), 'new content')

    def test_merge_individual_choices(self):
        """個別スキップと別名を適用する。"""
        target = self.target / self.source.name
        target.mkdir()
        (target / self.file.name).write_text('old')
        self.engine.run('copy', [str(self.source)], str(self.target), 'merge', choices={'sample.txt': 'skip'})
        self.assertEqual((target / self.file.name).read_text(), 'old')
        self.engine.run('copy', [str(self.source)], str(self.target), 'merge', choices={'sample.txt': 'rename'})
        self.assertEqual((target / 'sample (2).txt').read_text(), 'new content')

    def test_merge_move_rejected(self):
        """スキップした元を失う曖昧な結合移動を拒否する。"""
        with self.assertRaises(ValueError):
            self.engine.run('move', [str(self.source)], str(self.target), 'merge')

    def test_redo_copy_persists(self):
        """再起動相当の別エンジンでもRedoでき再度Undoできる。"""
        self.engine.run('copy', [str(self.file)], str(self.target))
        self.engine.undo()
        engine = FileTransactions(self.engine.directory)
        engine.redo()
        self.assertTrue((self.target / self.file.name).exists())
        engine.undo()
        self.assertFalse((self.target / self.file.name).exists())

    def test_redo_refuses_external_change(self):
        """Undo後に編集された元を無断で再転送しない。"""
        self.engine.run('copy', [str(self.file)], str(self.target))
        self.engine.undo()
        self.file.write_text('externally changed')
        with self.assertRaises(ValueError):
            self.engine.redo()
        self.assertFalse((self.target / self.file.name).exists())

    def test_redo_move(self):
        """移動のRedoでも元の退避と内容が正しい。"""
        self.engine.run('move', [str(self.file)], str(self.target))
        self.engine.undo()
        self.engine.redo()
        self.assertFalse(self.file.exists())
        self.assertEqual((self.target / self.file.name).read_text(), 'new content')

    def test_redo_creation_and_rename(self):
        """作成物の内容を保持し、改名も往復できる。"""
        self.engine.recordCreation(self.file)
        self.engine.undo()
        self.engine.redo()
        self.assertEqual(self.file.read_text(), 'new content')
        self.engine.rename([(str(self.file), 'renamed.txt')])
        self.engine.undo()
        self.engine.redo()
        self.assertTrue((self.source / 'renamed.txt').exists())

    def test_prune_preserves_completed_files(self):
        """容量超過の古い履歴を除去しても操作結果は残る。"""
        (self.target / self.file.name).write_text('old')
        self.engine.run('copy', [str(self.file)], str(self.target), 'replace')
        self.engine.prune(30, 0)
        self.assertFalse(self.engine.history)
        self.assertEqual((self.target / self.file.name).read_text(), 'new content')

    def test_prune_rejects_modified_backup(self):
        """外部変更されたバックアップは期限切れでも削除しない。"""
        (self.target / self.file.name).write_text('old')
        self.engine.run('copy', [str(self.file)], str(self.target), 'replace')
        Path(self.engine.history[-1]['entries'][0]['backup']).write_text('external')
        with self.assertRaises(ValueError):
            self.engine.prune(30, 0)
        self.assertTrue(self.engine.history)

    def test_search_folders_sizes_tags_and_exclusion(self):
        """種類、サイズ、タグ、除外条件を組み合わせる。"""
        hidden = self.source / 'cache'
        hidden.mkdir()
        (hidden / 'other.txt').write_text('skip')
        labels = {os.path.normcase(str(self.file)): {'tags': ['Hero', 'Approved']}}
        result = searchAdvanced([str(self.source)], tags='hero,approved', labels=labels, minimum=10, exclude='cache')
        self.assertEqual(result['paths'], [str(self.file)])
        self.assertEqual(searchAdvanced([str(self.source)], kind='Folders')['paths'], [str(hidden)])
        self.assertFalse(searchAdvanced([str(self.source)], maximum=2)['paths'])

    def test_search_multiple_roots_no_duplicates_and_batches(self):
        """親子ルートが重なっても重複せず、段階通知が最終結果と一致する。"""
        for number in range(110):
            (self.target / ('%03d.txt' % number)).write_text('x')
        batches = []
        result = searchAdvanced([str(self.root), str(self.target)], exclude='undo', batch=batches.extend)
        self.assertEqual(len(result['paths']), 111)
        self.assertEqual(set(batches), set(result['paths']))

    def test_search_cancel(self):
        """中止と空の正常結果を区別する。"""
        cancel = threading.Event()
        cancel.set()
        self.assertTrue(searchAdvanced([str(self.source)], cancel=cancel)['cancelled'])

    def test_summary_no_double_count(self):
        """親とその中のファイルを選んでも二重集計しない。"""
        result = summarize([str(self.source), str(self.file)])
        self.assertEqual(result['files'], 1)
        self.assertEqual(result['bytes'], self.file.stat().st_size)

    def test_sync_failure_and_cancel_not_success(self):
        """部分失敗・中止・再試行対象を正しく集約する。"""
        changes = [dict(source=str(self.file), target=str(self.target / self.file.name)),
                   dict(source=str(self.source / 'missing.txt'), target=str(self.target / 'missing.txt'))]
        result = synchronize(self.engine, changes)
        self.assertEqual(len(result['completed']), 1)
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(result['retry'], changes[1:])
        cancel = threading.Event()
        cancel.set()
        result = synchronize(self.engine, changes, cancel)
        self.assertTrue(result['cancelled'])
        self.assertFalse(result['completed'])
        self.assertEqual(result['retry'], changes)


if __name__ == '__main__':
    unittest.main(verbosity=2)
