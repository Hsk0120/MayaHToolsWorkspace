"""転送ジョブの永続化と項目単位の再開を、Undoの排他下で扱う。"""
import json
import os
import threading
import time
import uuid
from pathlib import Path
from qpeTransactions import checkCancel, fingerprint, Cancelled


class PauseControl:
    """処理中のハッシュ/コピーをブロック境界で一時停止する。"""

    def __init__(self, cancel, paused):
        """停止待ち中にも中止要求を受け付ける。"""
        self.cancel, self.paused = cancel, paused

    def is_set(self):
        """既存threading.Event互換の中止照会で一時停止を待つ。"""
        while self.paused.is_set() and not self.cancel.is_set():
            self.cancel.wait(.1)
        return self.cancel.is_set()


def writeJob(path, value):
    """同じジョブの更新は一つの実行者だけが原子的に保存する。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    for attempt in range(6):
        try:
            os.replace(str(temporary), str(path))
            return
        except PermissionError:
            # Windowsで読取側が短時間ファイルを保持する場合だけ待つ。
            # 権限変更や別形式での上書きに迂回せず、上限後は失敗を返す。
            if attempt == 5:
                raise
            time.sleep(.03 * (2 ** attempt))


def createJob(directory, action, paths, destination, conflict, choices):
    """実行内容を保存する。未開始ジョブを勝手に再開しない。"""
    identifier = uuid.uuid4().hex
    value = dict(version=1, id=identifier, action=action, paths=list(paths), destination=destination,
                 conflict=conflict, choices=choices, state='Queued', items=[], prepared=False,
                 created=time.time(), order=time.time())
    path = Path(directory) / (identifier + '.json')
    writeJob(path, value)
    return str(path)


def pendingJobs(directory):
    """未完了ジョブだけを読み、壊れた記録を実行対象にしない。"""
    values = []
    for path in Path(directory).glob('*.json'):
        try:
            value = json.loads(path.read_text(encoding='utf8'))
            if value.get('version') == 1 and value.get('state') not in ('Completed', 'Discarded'):
                values.append((str(path), value))
        except (OSError, ValueError, AttributeError):
            continue
    return sorted(values, key=lambda pair: pair[1].get('order', 0))


def targetStamp(source, destination, action, cancel):
    """対象名の行先が外部変更されていないか比較する。"""
    target = Path(source).parent / Path(source).name if action == 'duplicate' else Path(destination) / Path(source).name
    return fingerprint(target, cancel) if target.exists() else None


def committedEntry(engine, item):
    """グループ化したUndo履歴からも確定済み項目を照合する。"""
    for transaction in engine.history:
        ids = transaction.get('recoveryTransactions', [transaction['id']])
        if item['transaction'] in ids:
            return next((e for e in transaction['entries'] if e['source'] == item['source']), None)
    return None


def groupHistory(engine, value):
    """末尾の同一ジョブだけをまとめ、一回のUndoで今回の転送を戻す。"""
    ids = {i['transaction'] for i in value['items']}
    tail = []
    while engine.history:
        last = engine.history[-1]
        members = set(last.get('recoveryTransactions', [last['id']]))
        if not members or not members <= ids:
            break
        tail.insert(0, engine.history.pop())
    if tail:
        grouped = dict(tail[0])
        grouped['recoveryTransactions'] = [identifier for t in tail for identifier in t.get('recoveryTransactions', [t['id']])]
        grouped['entries'] = [entry for t in tail for entry in t['entries']]
        engine.history.append(grouped)
        engine.save()


def executeJob(engine, path, cancel, progress):
    """未完了項目を検証して再実行する。中断ファイルは先頭からコピーする。

    Args:
        engine (FileTransactions): 共有Undo基盤。
        path (str): 保存済みジョブ。
        cancel (PauseControl): 一時停止と中止の制御。
        progress (callable): 転送進捗。

    Returns:
        dict: 完了・中止・再試行対象。曖昧な確定状態は手動確認として停止。
    """
    result = dict(completed=[], skipped=[], errors=[], cancelled=False, retry=[])
    with engine.exclusive():
        value = json.loads(Path(path).read_text(encoding='utf8'))
        if value.get('state') == 'Discarded':
            raise ValueError('This saved transfer was discarded')
        if value.get('version') != 1 or value['action'] not in ('copy', 'move', 'duplicate'):
            raise ValueError('Unsupported saved transfer')
        try:
            if not value['prepared']:
                sources = list(dict.fromkeys(os.path.abspath(p) for p in value['paths']))
                sources = [p for p in sources if not any(str(parent) in sources for parent in Path(p).parents)]
                items = []
                for source in sources:
                    checkCancel(cancel)
                    entry = Path(source)
                    if entry.parent == entry or entry == engine.directory or engine.directory in entry.parents or entry in engine.directory.parents:
                        raise ValueError('A root or QPE Undo directory cannot be transferred')
                    items.append(dict(source=source, stamp=fingerprint(source, cancel),
                        targetStamp=targetStamp(source, value['destination'], value['action'], cancel),
                        state='Pending', transaction=uuid.uuid4().hex))
                value.update(items=items, prepared=True)
                writeJob(path, value)
            value['state'] = 'Running'
            writeJob(path, value)
            for item in value['items']:
                checkCancel(cancel)
                if item['state'] == 'Completed':
                    if item.get('output') and (not Path(item['output']).exists() or fingerprint(item['output'], cancel) != item['outputStamp']):
                        raise ValueError('Previously completed destination changed; review required: ' + item['output'])
                    continue
                source = item['source']
                if item['state'] == 'Running':
                    entry = committedEntry(engine, item)
                    if entry:
                        if fingerprint(entry['target'], cancel) != entry['stamp']:
                            raise ValueError('Completed destination changed; review required: ' + entry['target'])
                        if value['action'] == 'move' and not entry.get('moved'):
                            raise ValueError('Move was interrupted during commit. Use file history / Undo before retrying: ' + source)
                        item.update(state='Completed', output=entry['target'], outputStamp=entry['stamp'])
                        writeJob(path, value)
                        continue
                    raise ValueError('Interrupted commit needs review; automatic replay refused: ' + source)
                if fingerprint(source, cancel) != item['stamp']:
                    raise ValueError('Source changed since the saved job: ' + source)
                if targetStamp(source, value['destination'], value['action'], cancel) != item['targetStamp']:
                    raise ValueError('Destination changed since the saved job: ' + source)
                item['state'] = 'Running'
                writeJob(path, value)
                sub = engine.run(value['action'], [source], value['destination'], value['conflict'],
                                 cancel, progress, value['choices'], transactionId=item['transaction'])
                for key in ('completed', 'skipped', 'errors', 'retry'):
                    result[key].extend(sub[key])
                result['cancelled'] = sub['cancelled']
                committed = committedEntry(engine, item)
                if committed:
                    item.update(output=committed['target'], outputStamp=committed['stamp'])
                item['state'] = 'Completed' if sub['completed'] or sub['skipped'] else ('Running' if committed else 'Pending')
                writeJob(path, value)
                if sub['errors'] or sub['cancelled']:
                    break
            value['state'] = 'Completed' if all(i['state'] == 'Completed' for i in value['items']) else 'Stopped'
        except Cancelled:
            result['cancelled'] = True
            value['state'] = 'Stopped'
        except (OSError, ValueError) as error:
            from qpeProductivityIO import errorAdvice
            result['errors'].append(str(error) + '\n' + errorAdvice(error))
            value['state'] = 'Review required'
        finally:
            groupHistory(engine, value)
            result['retry'] = [i['source'] for i in value['items'] if i['state'] != 'Completed'] or ([] if value['prepared'] else value['paths'])
            value['lastResult'] = result
            writeJob(path, value)
    return result
