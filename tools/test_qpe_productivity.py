"""追加8機能のファイル保全と再開条件を専用データで検証する。"""
import errno
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maya/inhouse/QuickPathExplorer/python'))
from qpeProductivityIO import contentMatches, zipEntries, extractSelected, availability, requireLocal, errorAdvice
from qpeRecovery import createJob, executeJob, PauseControl, pendingJobs, writeJob
from qpeTransactions import FileTransactions
from qpeAdvancedIO import searchAdvanced


class ProductivityTests(unittest.TestCase):
    """実ファイルを使用し、既存データやユーザー設定へ触れない。"""

    def setUp(self):
        """独立したコピー元・先と履歴を用意する。"""
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.src, self.dst = self.root/'src', self.root/'dst'
        self.src.mkdir()
        self.dst.mkdir()
        self.a, self.b = self.src/'a.txt', self.src/'b.txt'
        self.a.write_text('first\n日本語 Hero\nlast', encoding='utf8')
        self.b.write_text('other')
        self.engine = FileTransactions(self.root/'undo')

    def tearDown(self):
        """生成物だけ削除する。"""
        self.temp.cleanup()

    def job(self, action='copy', conflict='rename'):
        """テスト用の保存ジョブを作る。"""
        return createJob(self.root/'jobs', action, [str(self.a), str(self.b)], str(self.dst), conflict, {})

    def test_text_search_snippet_and_utf16(self):
        """本文が一致しない名前とバイナリを除外する。"""
        (self.src/'wide.txt').write_text('日本語 Hero', encoding='utf-16')
        (self.src/'fake.txt').write_bytes(b'Hero\x00binary')
        result = searchAdvanced([str(self.src)], content='hero')
        self.assertEqual(len(result['paths']), 2)
        self.assertEqual(result['matches'][str(self.a)][0][0], 2)
        self.assertTrue(result['omitted'])

    def test_cloud_does_not_open(self):
        """オンライン属性では本文もプレビュー入口も内容を開かない。"""
        for attrs in (0x1000, 0x400000, 0x40000):
            self.assertTrue(availability(attributes=attrs)[1])
        self.assertFalse(availability(attributes=0x80000)[1])
        with patch('qpeProductivityIO.availability', return_value=('Online', True)):
            with self.assertRaises(OSError):
                contentMatches(str(self.a), 'Hero')

    def test_text_limit(self):
        """大きな本文を黙って途中検索しない。"""
        hits, reason = contentMatches(str(self.a), 'Hero', limit=1)
        self.assertFalse(hits)
        self.assertIn('limit', reason)

    def test_zip_select_only(self):
        """ZIPから必要な項目だけ抽出する。"""
        path = self.root/'sample.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('folder/', '')
            archive.writestr('folder/a.txt', 'chosen')
            archive.writestr('b.txt', 'not chosen')
        self.assertEqual(len(zipEntries(path)), 3)
        output = self.root/'extracted'
        extractSelected(path, ['folder/'], output)
        self.assertEqual((output/'folder/a.txt').read_text(), 'chosen')
        self.assertFalse((output/'b.txt').exists())
        with self.assertRaises(FileExistsError):
            extractSelected(path, ['b.txt'], output)

    def test_zip_traversal_refused(self):
        """パス逸脱するZIPは抽出前に拒否する。"""
        path = self.root/'unsafe.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('../outside.txt', 'bad')
        with self.assertRaises(ValueError):
            extractSelected(path, ['../outside.txt'], self.root/'out')
        self.assertFalse((self.root/'out').exists())

    def test_persisted_transfer_and_undo(self):
        """新しいエンジンでも保存ジョブを完了しUndoを維持する。"""
        path = self.job()
        self.assertEqual(len(pendingJobs(self.root/'jobs')), 1)
        result = executeJob(FileTransactions(self.root/'undo'), path, None, lambda *args: None)
        self.assertEqual(len(result['completed']), 2)
        self.assertEqual(pendingJobs(self.root/'jobs'), [])
        self.assertEqual((self.dst/'a.txt').read_bytes(), self.a.read_bytes())
        self.engine.undo()
        self.assertFalse((self.dst/'b.txt').exists())
        self.assertFalse((self.dst/'a.txt').exists())

    def test_cancel_then_resume(self):
        """途中中止は元データを保持し、再起動後に未完了分を転送する。"""
        self.a.write_bytes(b'x' * (3*1024*1024))
        path = self.job()
        cancel = threading.Event()
        executeJob(self.engine, path, cancel, lambda *args: cancel.set())
        self.assertTrue(self.a.exists())
        self.assertFalse((self.dst/'a.txt').exists())
        result = executeJob(FileTransactions(self.root/'undo'), path, None, lambda *args: None)
        self.assertFalse(result['errors'])
        self.assertEqual(len(result['completed']), 2)

    def test_resume_rejects_source_change(self):
        """保存時から変わった原本を勝手に転送しない。"""
        path = self.job()
        cancel = threading.Event()
        executeJob(self.engine, path, cancel, lambda *args: cancel.set())
        self.a.write_text('changed')
        result = executeJob(self.engine, path, None, lambda *args: None)
        self.assertIn('Source changed', result['errors'][0])

    def test_resume_rejects_destination_change(self):
        """他アプリが作った行先を上書きしない。"""
        path = self.job()
        cancel = threading.Event()
        executeJob(self.engine, path, cancel, lambda *args: cancel.set())
        (self.dst/'a.txt').write_text('external')
        result = executeJob(self.engine, path, None, lambda *args: None)
        self.assertIn('Destination changed', result['errors'][0])
        self.assertEqual((self.dst/'a.txt').read_text(), 'external')

    def test_ambiguous_commit_refused(self):
        """確定中に中断したジョブを重複実行しない。"""
        path = self.job()
        value = json.loads(Path(path).read_text())
        value.update(prepared=True, items=[dict(source=str(self.a), state='Running', transaction='missing')])
        writeJob(path, value)
        result = executeJob(self.engine, path, None, lambda *args: None)
        self.assertIn('review', result['errors'][0])
        self.assertEqual(list(self.dst.iterdir()), [])

    def test_pause_then_cancel(self):
        """停止待ち中も中止して終了できる。"""
        paused, cancel = threading.Event(), threading.Event()
        paused.set()
        output = []
        worker = threading.Thread(target=lambda: output.append(PauseControl(cancel, paused).is_set()))
        worker.start()
        time.sleep(.15)
        self.assertTrue(worker.is_alive())
        cancel.set()
        worker.join(2)
        self.assertEqual(output, [True])

    def test_cloud_filter_sync_flags(self):
        """未同期と同期失敗を混同せず、未取得は自動読込しない。"""
        with patch('qpeProductivityIO.cloudState', return_value=9):
            self.assertIn('in sync', availability(attributes=0x80000, reparse_tag=1)[0])
        with patch('qpeProductivityIO.cloudState', return_value=1):
            self.assertIn('not in sync', availability(attributes=0x80000, reparse_tag=1)[0])
        with patch('qpeProductivityIO.cloudState', return_value=0x31):
            self.assertTrue(availability(attributes=0, reparse_tag=1)[1])

    def test_recorded_commit_is_not_repeated(self):
        """履歴確定後・ジョブ保存前の中断を照合し重複コピーしない。"""
        path = self.job()
        result = executeJob(self.engine, path, None, lambda *args: None)
        self.assertFalse(result['errors'])
        value = json.loads(Path(path).read_text())
        value['state'] = 'Running'
        value['items'][0]['state'] = 'Running'
        writeJob(path, value)
        result = executeJob(FileTransactions(self.root/'undo'), path, None, lambda *args: None)
        self.assertFalse(result['errors'])
        self.assertEqual(len(list(self.dst.iterdir())), 2)

    def test_completed_output_changed_before_resume(self):
        """完了済み出力が外部変更された途中ジョブを完了扱いにしない。"""
        path = self.job()
        executeJob(self.engine, path, None, lambda *args: None)
        value = json.loads(Path(path).read_text())
        value['state'] = 'Stopped'
        writeJob(path, value)
        (self.dst/'a.txt').write_text('external')
        result = executeJob(self.engine, path, None, lambda *args: None)
        self.assertIn('Previously completed destination changed', result['errors'][0])

    def test_atomic_record_retries_brief_sharing_denial(self):
        """短いWindows共有拒否では古い記録を壊さず再試行する。"""
        path = self.root/'job.json'
        original = os.replace
        calls = []
        def replace(source, target):
            """最初だけファイル保持を再現する。"""
            calls.append(1)
            if len(calls) == 1:
                raise PermissionError('brief sharing denial')
            original(source, target)
        with patch('qpeRecovery.os.replace', side_effect=replace):
            writeJob(path, {'version': 1})
        self.assertEqual(len(calls), 2)
        self.assertEqual(json.loads(path.read_text()), {'version': 1})

    def test_diagnosis(self):
        """失敗理由をディスク容量や権限の対処へ分類する。"""
        self.assertIn('disk space', errorAdvice(OSError(errno.ENOSPC, 'full')))
        self.assertIn('Access denied', errorAdvice(PermissionError(errno.EACCES, 'denied')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
