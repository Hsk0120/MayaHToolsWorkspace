"""拡張検索・容量集計・同期結果をQtから独立して扱う。"""
import fnmatch
import os
import shutil
from pathlib import Path
from qpeTransactions import checkCancel, Cancelled, isLink


def searchAdvanced(roots, query='', extensions='', since=0, hidden=False, minimum=0,
                   maximum=0, kind='Files', exclude='', tags='', tagMode='All', labels=None,
                   cancel=None, batch=None, content=''):
    """複数ルートを重複なく検索し、結果を小分けで通知する。

    Args:
        roots (list[str]): 明示した検索範囲。
        query (str): 名前の部分一致またはワイルドカード。
        extensions (str): セミコロンで区切った形式。
        since (float): 更新日の下限。
        hidden (bool): 隠し項目も対象にするか。
        minimum (int): ファイルサイズ下限。
        maximum (int): 上限。0は制限なし。
        kind (str): Files / Folders / Both。
        exclude (str): 除外フォルダー名または相対パスのパターン。
        tags (str): カンマ区切りのタグ。
        tagMode (str): All / Any。
        labels (dict): 呼出時点のラベル情報。
        cancel (threading.Event): 中止要求。
        batch (callable): 100件単位のパス通知。
        content (str): テキスト本文の部分一致。空なら内容を開かない。

    Returns:
        dict: paths、errors、cancelled。
    """
    labels = labels or {}
    patterns = [p.strip().lower() for p in extensions.split(';') if p.strip()]
    exclusions = [p.strip().lower().replace('\\', '/') for p in exclude.split(';') if p.strip()]
    wanted = {t.strip().casefold() for t in tags.split(',') if t.strip()}
    result = dict(paths=[], errors=[], cancelled=False, matches={}, omitted=[])
    visited, pending = set(), []
    try:
        for root in roots:
            stack = [os.path.abspath(root)]
            while stack:
                checkCancel(cancel)
                directory = stack.pop()
                key = os.path.normcase(directory)
                if key in visited:
                    continue
                visited.add(key)
                try:
                    with os.scandir(directory) as entries:
                        for entry in entries:
                            checkCancel(cancel)
                            try:
                                info = entry.stat(follow_symlinks=False)
                                if isLink(entry.path) or entry.name.startswith('.qpe-'):
                                    continue
                                if not hidden and (entry.name.startswith('.') or getattr(info, 'st_file_attributes', 0) & 2):
                                    continue
                                folder = entry.is_dir(follow_symlinks=False)
                                relative = os.path.relpath(entry.path, root).replace('\\', '/').lower()
                                if folder and any(fnmatch.fnmatch(entry.name.lower(), p) or fnmatch.fnmatch(relative, p) for p in exclusions):
                                    continue
                                if folder:
                                    stack.append(entry.path)
                                if (folder and kind == 'Files') or (not folder and kind == 'Folders'):
                                    continue
                                name = entry.name.lower()
                                if not (fnmatch.fnmatch(name, query.lower()) if any(c in query for c in '*?[') else query.lower() in name):
                                    continue
                                if patterns and not any(fnmatch.fnmatch(name, p) for p in patterns):
                                    continue
                                if info.st_mtime < since or (not folder and (info.st_size < minimum or maximum and info.st_size > maximum)):
                                    continue
                                actual = {t.casefold() for t in labels.get(os.path.normcase(os.path.abspath(entry.path)), {}).get('tags', [])}
                                if wanted and not (wanted <= actual if tagMode == 'All' else bool(wanted & actual)):
                                    continue
                                if content:
                                    if folder:
                                        continue
                                    from qpeProductivityIO import contentMatches
                                    hits, reason = contentMatches(entry.path, content, cancel)
                                    if reason:
                                        result['omitted'].append(entry.path + ': ' + reason)
                                    if not hits:
                                        continue
                                    result['matches'][entry.path] = hits
                                result['paths'].append(entry.path)
                                pending.append(entry.path)
                                if len(pending) >= 100:
                                    if batch:
                                        batch(pending[:])
                                    pending.clear()
                            except OSError as error:
                                result['errors'].append(str(error))
                except OSError as error:
                    result['errors'].append(str(error))
    except Cancelled:
        result['cancelled'] = True
    if pending and batch:
        batch(pending)
    return result


def summarize(paths, cancel=None):
    """選択の親子重複を除外し、必要時だけ再帰容量を集計する。"""
    roots = sorted({Path(p).absolute() for p in paths}, key=lambda p: len(p.parts))
    roots = [p for p in roots if not any(parent in roots for parent in p.parents)]
    size, files, folders, errors = 0, 0, 0, []
    stack = roots[:]
    while stack:
        checkCancel(cancel)
        path = stack.pop()
        try:
            if isLink(path):
                continue
            if path.is_dir():
                folders += 1
                stack.extend(p for p in path.iterdir() if not p.name.startswith('.qpe-'))
            else:
                size += path.stat().st_size
                files += 1
        except OSError as error:
            errors.append(str(error))
    free = shutil.disk_usage(str(roots[0].anchor)).free if roots else 0
    return dict(bytes=size, files=files, folders=folders, free=free, errors=errors)


def synchronize(engine, changes, cancel=None, progress=None):
    """各コピー結果を集約し、部分失敗や中止を完了と混同しない。"""
    result = dict(completed=[], errors=[], skipped=[], cancelled=False, retry=[])
    for number, change in enumerate(changes):
        if cancel is not None and cancel.is_set():
            result['cancelled'] = True
            result['retry'].extend(changes[number:])
            break
        try:
            parent = Path(change['target']).parent
            parent.mkdir(parents=True, exist_ok=True)
            part = engine.run('copy', [change['source']], str(parent), 'replace', cancel, progress)
            for key in ('completed', 'errors', 'skipped'):
                result[key].extend(part[key])
            if part['errors'] or part['cancelled']:
                result['retry'].append(change)
            result['cancelled'] |= part['cancelled']
        except (OSError, ValueError) as error:
            result['errors'].append(str(error))
            result['retry'].append(change)
    return result
