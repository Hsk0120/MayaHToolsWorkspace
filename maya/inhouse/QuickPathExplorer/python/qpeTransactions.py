"""Qtに依存しないファイル操作と、変更検出付きの永続Undo履歴。"""
import ctypes
import hashlib
import json
import os
import shutil
import stat
import threading
import uuid
import time
import copy
from contextlib import contextmanager
from pathlib import Path
from qpeFileOperations import validateName


class Cancelled(Exception):
    """利用者が中止した処理を通常のI/O失敗から区別する。"""


def checkCancel(cancel):
    """中止要求をファイル境界やコピー中に確認する。"""
    if cancel is not None and cancel.is_set():
        raise Cancelled('Cancelled')


def isLink(path):
    """Windowsのジャンクションも再帰処理の対象から外す。"""
    info = Path(path).lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 1024)


def fingerprint(path, cancel=None):
    """内容と相対名をハッシュ化し、Undo時の外部変更を検出する。"""
    path = Path(path)
    digest = hashlib.sha256()
    if isLink(path):
        raise ValueError('Links and junctions are not modified: ' + str(path))
    if path.is_dir():
        digest.update(b'D')
        for child in sorted(path.iterdir(), key=lambda p: p.name):
            checkCancel(cancel)
            digest.update(child.name.encode('utf8'))
            digest.update(fingerprint(child, cancel).encode('ascii'))
    else:
        digest.update(b'F')
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                checkCancel(cancel)
                digest.update(block)
    return digest.hexdigest()


def copyEntry(source, target, cancel=None, progress=None):
    """リンクを辿らず、新規の作業先へ中止可能なコピーを作る。"""
    source, target = Path(source), Path(target)
    checkCancel(cancel)
    if isLink(source):
        raise ValueError('Links and junctions are not copied: ' + str(source))
    if source.is_dir():
        target.mkdir()
        for child in source.iterdir():
            copyEntry(child, target / child.name, cancel, progress)
    else:
        with source.open('rb') as src, target.open('xb') as dst:
            for block in iter(lambda: src.read(1024 * 1024), b''):
                checkCancel(cancel)
                dst.write(block)
                if progress:
                    progress(str(source), len(block))
    shutil.copystat(str(source), str(target))


def removeEntry(path):
    """処理が所有するバックアップ・作業コピーのみを削除する。"""
    path = Path(path)
    if path.is_dir() and not isLink(path):
        shutil.rmtree(str(path))
    else:
        path.unlink()


def overlayEntry(source, target, choices, cancel=None, progress=None, relative=''):
    """作業コピー内だけで結合し、行先だけにある項目を保持する。"""
    source, target = Path(source), Path(target)
    checkCancel(cancel)
    if target.exists() and source.is_dir() and target.is_dir():
        for child in source.iterdir():
            overlayEntry(child, target / child.name, choices, cancel, progress,
                         (relative + '/' + child.name).lstrip('/'))
        return
    if target.exists():
        decision = choices.get(str(source), choices.get(relative, 'replace'))
        if decision == 'skip':
            return
        if decision == 'rename':
            number = 2
            while target.exists():
                target = target.parent / '{} ({}){}'.format(source.stem, number, source.suffix)
                number += 1
        else:
            removeEntry(target)
    copyEntry(source, target, cancel, progress)


def recycle(path):
    """Windows標準のごみ箱へ送る。失敗時に完全削除へ代替しない。"""
    if os.name != 'nt':
        raise OSError('Recycle Bin is supported on Windows only.')
    from ctypes import wintypes

    class FileOperation(ctypes.Structure):
        """SHFileOperationWのABIを保持する。"""
        _fields_ = [('hwnd', wintypes.HWND), ('wFunc', wintypes.UINT),
                    ('pFrom', wintypes.LPCWSTR), ('pTo', wintypes.LPCWSTR),
                    ('fFlags', ctypes.c_ushort), ('fAnyOperationsAborted', wintypes.BOOL),
                    ('hNameMappings', ctypes.c_void_p), ('lpszProgressTitle', wintypes.LPCWSTR)]
    source = ctypes.create_unicode_buffer(os.path.abspath(path) + '\0\0')
    operation = FileOperation()
    operation.wFunc = 3
    operation.pFrom = ctypes.cast(source, wintypes.LPCWSTR)
    operation.fFlags = 0x40 | 0x10 | 0x4 | 0x400
    function = ctypes.windll.shell32.SHFileOperationW
    function.argtypes = [ctypes.POINTER(FileOperation)]
    function.restype = ctypes.c_int
    result = function(ctypes.byref(operation))
    if result or operation.fAnyOperationsAborted or os.path.exists(path):
        raise OSError('Recycle Bin failed or was cancelled ({})'.format(result))


class FileTransactions:
    """一つの操作を直列実行し、完了した項目だけをUndoへ登録する。

    バックアップは専用ディレクトリへ残す。外部変更を検出したUndoは拒否する。
    MayaのシーンUndoには一切接続しない。
    """

    def __init__(self, directory):
        """永続履歴の保存先を準備する。

        Args:
            directory (str): QPE専用のUndoデータ保存先。
        """
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.journal = self.directory / 'journal.json'
        self.redoJournal = self.directory / 'redo.json'
        self.lock = threading.Lock()
        self._owner = None
        self._depth = 0
        self._lease = None
        self.history = []
        try:
            self.history = json.loads(self.historyPath().read_text(encoding='utf8'))
            if not isinstance(self.history, list):
                self.history = []
        except (OSError, ValueError):
            pass

    def historyPath(self):
        """確定履歴と未反映の復旧用コピーのうち最新のものを読む。"""
        candidates = list(self.directory.glob('journal-recovery-*.json'))
        if self.journal.exists():
            candidates.append(self.journal)
        return max(candidates, key=lambda p: p.stat().st_mtime_ns) if candidates else self.journal

    def acquire(self):
        """別ウィンドウ・別Mayaプロセスの操作と履歴更新を排他する。"""
        if self._owner == threading.get_ident():
            self._depth += 1
            return
        if not self.lock.acquire(False):
            raise RuntimeError('Another file operation is running')
        try:
            self._lease = (self.directory / 'operation.lock').open('a+b')
            self._lease.seek(0)
            if os.name == 'nt':
                import msvcrt
                self._lease.write(b'0')
                self._lease.flush()
                self._lease.seek(0)
                msvcrt.locking(self._lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            latest = self.historyPath()
            if latest.exists():
                self.history = json.loads(latest.read_text(encoding='utf8'))
                if not isinstance(self.history, list):
                    raise ValueError('Invalid Undo history')
            # 確定済み操作の保存失敗を次の操作で上書きしない。
            if latest != self.journal:
                self.save()
            self._owner, self._depth = threading.get_ident(), 1
        except Exception:
            if self._lease:
                self._lease.close()
                self._lease = None
            self.lock.release()
            raise

    def release(self):
        """OSロックはプロセス終了時にも解放される。"""
        if self._depth > 1:
            self._depth -= 1
            return
        if self._lease:
            self._lease.close()
            self._lease = None
        self._owner, self._depth = None, 0
        self.lock.release()

    @contextmanager
    def exclusive(self):
        """全ての書込み入口で同じ排他規則を使う。"""
        self.acquire()
        try:
            yield
        finally:
            self.release()

    def save(self):
        """一時ロックを有限回再試行し、失敗時にも確定履歴の復旧用コピーを残す。"""
        temporary = self.directory / ('journal-recovery-' + uuid.uuid4().hex + '.json')
        with temporary.open('x', encoding='utf8') as stream:
            json.dump(self.history, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(6):
            try:
                os.replace(str(temporary), str(self.journal))
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(.03 * (2 ** attempt))
        for previous in self.directory.glob('journal-recovery-*.json'):
            try:
                previous.unlink()
            except OSError:
                # 古いコピーの掃除の失敗は、確定した新しい履歴の失敗ではない。
                pass

    def saveResult(self, result):
        """ファイルの完了と履歴永続化の警告を分離し、再転送対象にしない。"""
        try:
            self.save()
        except OSError as error:
            result.setdefault('warnings', []).append('Files were changed. Undo history needs recovery; do not repeat the transfer. ' + str(error))

    def run(self, action, paths, destination='', conflict='rename', cancel=None, progress=None, choices=None, transactionId=None):
        """コピー・移動・複製・ごみ箱を項目単位で実行する。

        Args:
            action (str): copy/move/duplicate/trash。
            paths (list[str]): 明示的な対象。
            destination (str): コピー・移動先。
            conflict (str): rename/skip/replace。
            cancel (threading.Event): 中止要求。
            progress (callable): コピーしたパスとバイト数の通知。

        Returns:
            dict: 完了・失敗・スキップ・中止の別々の結果。
        """
        if action not in ('copy', 'move', 'duplicate', 'trash') or conflict not in ('rename', 'skip', 'replace', 'merge'):
            raise ValueError('Unknown file operation')
        if conflict == 'merge' and action != 'copy':
            raise ValueError('Folder merge supports Copy only; originals are retained.')
        self.acquire()
        result = dict(completed=[], errors=[], skipped=[], cancelled=False, retry=[], warnings=[])
        transaction = dict(id=transactionId or uuid.uuid4().hex, action=action, entries=[], time=time.time(), conflict=conflict, choices=choices or {})
        try:
            self.clearRedo()
            self.history.append(transaction)
            originals = list(dict.fromkeys(paths))
            sources = [Path(p).absolute() for p in originals]
            for original, source in zip(originals, sources):
                backup = None
                entry = None
                try:
                    checkCancel(cancel)
                    if source.parent == source or source == self.directory or self.directory in source.parents or source in self.directory.parents:
                        raise ValueError('A root or QPE Undo directory cannot be changed')
                    if any(parent in sources for parent in source.parents):
                        result['skipped'].append(str(source))
                        continue
                    # resolve前のリンクも明示的に拒否する。
                    if isLink(original):
                        raise ValueError('Links and junctions are not modified')
                    stamp = fingerprint(source, cancel)
                    backup = self.directory / uuid.uuid4().hex
                    if action == 'trash':
                        copyEntry(source, backup, cancel, progress)
                        if fingerprint(backup, cancel) != stamp or fingerprint(source, cancel) != stamp:
                            raise OSError('Source changed while preparing Recycle Bin backup')
                        checkCancel(cancel)
                        recycle(str(source))
                        entry = dict(source=str(source), target='', backup=str(backup), backupStamp=stamp, stamp=stamp)
                    else:
                        folder = source.parent if action == 'duplicate' else Path(destination).resolve()
                        if not folder.is_dir() or folder == source or source in folder.parents:
                            raise ValueError('Choose an existing destination outside the source')
                        target = folder / source.name
                        if target == source and action == 'move':
                            result['skipped'].append(str(source))
                            continue
                        replaced = ''
                        backup_stamp = ''
                        if target.exists():
                            policy = (choices or {}).get(str(source), 'replace') if conflict == 'merge' and not (source.is_dir() and target.is_dir()) else conflict
                            if policy == 'skip':
                                result['skipped'].append(str(source))
                                continue
                            if policy == 'rename' or target == source:
                                number = 2
                                while target.exists():
                                    target = folder / '{} ({}){}'.format(source.stem, number, source.suffix)
                                    number += 1
                            else:
                                backup_stamp = fingerprint(target, cancel)
                                replaced = str(backup)
                        temporary = folder / ('.qpe-' + uuid.uuid4().hex)
                        try:
                            merging = conflict == 'merge' and target.is_dir() and source.is_dir()
                            if merging:
                                copyEntry(target, temporary, cancel, progress)
                                overlayEntry(source, temporary, choices or {}, cancel, progress)
                                output_stamp = fingerprint(temporary, cancel)
                            else:
                                copyEntry(source, temporary, cancel, progress)
                                output_stamp = stamp
                            if fingerprint(temporary, cancel) != output_stamp or fingerprint(source, cancel) != stamp:
                                raise OSError('Source changed during copy')
                            checkCancel(cancel)
                            if replaced:
                                if fingerprint(target, cancel) != backup_stamp:
                                    raise OSError('Destination changed during copy; replacement refused')
                                shutil.move(str(target), replaced)
                            try:
                                # Windows renameは競合を上書きしない。
                                os.rename(str(temporary), str(target))
                            except Exception:
                                if replaced and not target.exists():
                                    shutil.move(replaced, str(target))
                                raise
                            entry = dict(source=str(source), target=str(target), backup=replaced, backupStamp=backup_stamp, stamp=output_stamp)
                            if action == 'move':
                                # コピーが確定するまで元ファイルを保持。元の削除失敗時もUndo可能にする。
                                entry['moved'] = False
                                transaction['entries'].append(entry)
                                self.save()
                                # 再帰削除は途中失敗で元を部分欠損させるため、同じボリュームで
                                # 原子的に退避する。Undo確定まではこの原本を保持する。
                                source_backup = source.parent / ('.qpe-undo-' + uuid.uuid4().hex)
                                os.rename(str(source), str(source_backup))
                                entry['sourceBackup'] = str(source_backup)
                                entry['moved'] = True
                        finally:
                            if temporary.exists():
                                removeEntry(temporary)
                    if entry not in transaction['entries']:
                        transaction['entries'].append(entry)
                    result['completed'].append(str(source if action == 'trash' else target))
                    self.saveResult(result)
                except Cancelled:
                    result['cancelled'] = True
                    result['retry'].extend(str(p) for p in sources[sources.index(source):])
                    break
                except (OSError, ValueError) as error:
                    from qpeProductivityIO import errorAdvice
                    result['errors'].append('{}: {}\n{}'.format(source, error, errorAdvice(error)))
                    # 元の退避前に失敗したMoveはコピーが既に存在する。自動再試行しない。
                    if entry is not None and entry in transaction['entries']:
                        result['errors'].append('Review the completed destination and use File Undo before retrying: ' + entry['target'])
                    else:
                        result['retry'].append(str(source))
                finally:
                    if backup and backup.exists() and not any(e['backup'] == str(backup) for e in transaction['entries']):
                        # 未採用の自分の作業コピーだけを削除する。
                        # 置換前の退避物は復旧が必要な可能性があるため残す。
                        if action == 'trash':
                            removeEntry(backup)
            if not transaction['entries']:
                self.history.remove(transaction)
            self.saveResult(result)
            return result
        finally:
            self.release()

    def rename(self, pairs):
        """一括リネームを事前検証し、失敗時は完了項目を巻き戻す。

        Args:
            pairs (list[tuple[str, str]]): 元パスと新しい単一名。
        """
        with self.exclusive():
            self.clearRedo()
            targets, entries = set(), []
            for path, name in pairs:
                source = Path(path).absolute()
                target = source.with_name(validateName(name))
                if source.name == name:
                    continue
                key = os.path.normcase(str(target))
                if key in targets or (target.exists() and key != os.path.normcase(str(source))):
                    raise FileExistsError('Duplicate or existing name: ' + str(target))
                targets.add(key)
                entries.append(dict(source=str(source), target=str(target), stamp=fingerprint(source), backup=''))
            done = []
            try:
                for entry in entries:
                    os.rename(entry['source'], entry['target'])
                    done.append(entry)
            except OSError:
                for entry in reversed(done):
                    os.rename(entry['target'], entry['source'])
                raise
            if done:
                self.history.append(dict(id=uuid.uuid4().hex, action='rename', entries=done, time=time.time()))
                self.save()

    def undo(self):
        """最新操作を戻す。外部変更・復元先の衝突があれば全体を開始しない。"""
        with self.exclusive():
            if not self.history:
                return []
            transaction = self.history[-1]
            redo = copy.deepcopy(transaction)
            action = transaction['action']
            for entry in transaction['entries']:
                source, target = Path(entry['source']), entry['target']
                if target and (not Path(target).exists() or fingerprint(target) != entry['stamp']):
                    raise ValueError('Undo refused: target was changed: ' + target)
                restores = action in ('trash', 'rename') or (action == 'move' and entry.get('moved'))
                same_name = bool(target) and os.path.normcase(str(source)) == os.path.normcase(target)
                if restores and source.exists() and not (action == 'rename' and same_name):
                    raise FileExistsError('Undo destination already exists: ' + str(source))
                if entry['backup'] and not Path(entry['backup']).exists():
                    raise FileNotFoundError('Undo backup is missing: ' + entry['backup'])
                if entry.get('backupStamp') and fingerprint(entry['backup']) != entry['backupStamp']:
                    raise ValueError('Undo refused: backup was changed')
                if entry.get('sourceBackup') and fingerprint(entry['sourceBackup']) != entry['stamp']:
                    raise ValueError('Undo refused: moved source backup was changed')
            self.clearRedo()
            if action == 'create':
                for entry in redo['entries']:
                    saved = self.directory / ('redo-' + uuid.uuid4().hex)
                    copyEntry(entry['target'], saved)
                    entry['redoCopy'] = str(saved)
            restored = []
            for entry in list(reversed(transaction['entries'])):
                source, target, backup = entry['source'], entry['target'], entry['backup']
                if action == 'trash':
                    shutil.move(backup, source)
                elif action == 'move' and entry.get('sourceBackup'):
                    os.rename(entry['sourceBackup'], source)
                    removeEntry(target)
                elif action == 'rename' or (action == 'move' and entry.get('moved')):
                    shutil.move(target, source)
                else:
                    removeEntry(target)
                if backup and action != 'trash':
                    shutil.move(backup, target)
                transaction['entries'].remove(entry)
                restored.append(source)
                self.save()
            self.history.pop()
            self.save()
            watched = {e[k] for e in redo['entries'] for k in ('source', 'target') if e[k]}
            redo['expected'] = {p: fingerprint(p) if Path(p).exists() else None for p in watched}
            self.redoJournal.write_text(json.dumps(redo, ensure_ascii=False), encoding='utf8')
            return restored

    def clearRedo(self):
        """新しい操作ではやり直しを無効化し、所有する作業コピーだけを除く。"""
        if self.redoJournal.exists():
            self.redoJournal.unlink()
        for path in self.directory.glob('redo-*'):
            if path.parent == self.directory and not isLink(path):
                removeEntry(path)

    def redo(self):
        """最後に取り消した操作を、対象の外部変更を検証して再実行する。"""
        with self.exclusive():
            record = json.loads(self.redoJournal.read_text(encoding='utf8'))
            for path, stamp in record['expected'].items():
                actual = fingerprint(path) if Path(path).exists() else None
                if actual != stamp:
                    raise ValueError('Redo refused: item was changed: ' + path)
            # 新規作成だけは元ファイルがないため、保存した内容を直接復元する。
            if record['action'] == 'create':
                for entry in record['entries']:
                    if fingerprint(entry['redoCopy']) != entry['stamp']:
                        raise ValueError('Redo copy changed')
                for entry in record['entries']:
                    copyEntry(entry['redoCopy'], entry['target'])
                self.history.append(dict(id=uuid.uuid4().hex, action='create', time=time.time(), entries=[
                    {k: v for k, v in e.items() if k != 'redoCopy'} for e in record['entries']]))
                self.save()
                self.clearRedo()
                return dict(completed=[e['target'] for e in record['entries']], errors=[], skipped=[], cancelled=False)
            return self._redoRecord(record)

    def _redoRecord(self, record):
        """外側のOSロックを保持したまま再実行し、一回の履歴へ集約する。"""
        if record['action'] == 'rename':
            self.rename([(e['source'], Path(e['target']).name) for e in record['entries']])
            return dict(completed=[e['target'] for e in record['entries']], errors=[], skipped=[], cancelled=False)
        results = dict(completed=[], errors=[], skipped=[], cancelled=False)
        before = len(self.history)
        for entry in record['entries']:
            part = self.run(record['action'], [entry['source']], str(Path(entry['target']).parent) if entry['target'] else '',
                            record.get('conflict', 'replace' if entry['backup'] else 'rename'), choices=record.get('choices'))
            for key in ('completed', 'errors', 'skipped'):
                results[key].extend(part[key])
            results['cancelled'] |= part['cancelled']
        created = self.history[before:]
        if created:
            merged = dict(created[0])
            merged['entries'] = [entry for transaction in created for entry in transaction['entries']]
            self.history[before:] = [merged]
            self.save()
        return results

    def recordCreation(self, path):
        """作成に成功したファイルや展開フォルダーをUndoへ登録する。"""
        with self.exclusive():
            self.clearRedo()
            self.history.append(dict(id=uuid.uuid4().hex, action='create', time=time.time(), entries=[
                dict(source=str(path), target=str(path), backup='', stamp=fingerprint(path))]))
            self.save()

    def discardHistory(self):
        """変更されていない専用バックアップだけを破棄して容量を戻す。"""
        with self.exclusive():
            backups = []
            for transaction in self.history:
                for entry in transaction['entries']:
                    for key, stamp_key in [('backup', 'backupStamp'), ('sourceBackup', 'stamp')]:
                        value = entry.get(key)
                        if not value:
                            continue
                        path = Path(value).absolute()
                        expected_parent = self.directory if key == 'backup' else Path(entry['source']).absolute().parent
                        if path.parent != expected_parent or (key == 'sourceBackup' and not path.name.startswith('.qpe-undo-')):
                            raise ValueError('Backup path is outside QPE storage')
                        if not entry.get(stamp_key) or fingerprint(path) != entry[stamp_key]:
                            raise ValueError('Backup changed; history was retained: ' + str(path))
                        backups.append(path)
            for path in backups:
                removeEntry(path)
            self.history = []
            self.save()
            self.clearRedo()

    def prune(self, days, budget):
        """期限または容量を超える古い履歴だけを、検証後に破棄する。"""
        with self.exclusive():
            now = time.time()
            records, total = [], 0
            for record in self.history:
                paths, size = [], 0
                for entry in record['entries']:
                    for key, stamp in (('backup', 'backupStamp'), ('sourceBackup', 'stamp')):
                        if not entry.get(key):
                            continue
                        path = Path(entry[key]).absolute()
                        expected = self.directory if key == 'backup' else Path(entry['source']).absolute().parent
                        if path.parent != expected or (key == 'sourceBackup' and not path.name.startswith('.qpe-undo-')):
                            raise ValueError('Unexpected backup location')
                        if fingerprint(path) != entry.get(stamp):
                            raise ValueError('Backup changed; cleanup refused: ' + str(path))
                        paths.append(path)
                        size += sum(p.stat().st_size for p in path.rglob('*') if p.is_file()) if path.is_dir() else path.stat().st_size
                records.append((record, paths, size))
                total += size
            removed = []
            for record, paths, size in records:
                if total <= budget and now - record.get('time', 0) < days * 86400:
                    break
                for path in paths:
                    removeEntry(path)
                total -= size
                self.history.remove(record)
                self.save()
                removed.append(record['id'])
            return dict(completed=removed, errors=[], skipped=[], cancelled=False)
