"""範囲検索・比較・アーカイブ・Maya ASCII情報を扱う読取中心の処理。"""
import fnmatch
import hashlib
import os
import re
import shutil
import subprocess
import zipfile
import tempfile
from pathlib import Path, PurePosixPath
from qpeTransactions import checkCancel, isLink


def walkFiles(root, hidden=False, cancel=None, errors=None):
    """ジャンクションを辿らず列挙し、権限エラーを呼出元へ残す。"""
    stack = [str(root)]
    while stack:
        checkCancel(cancel)
        directory = stack.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    checkCancel(cancel)
                    try:
                        info = entry.stat(follow_symlinks=False)
                        if isLink(entry.path):
                            continue
                        if not hidden and (entry.name.startswith('.') or getattr(info, 'st_file_attributes', 0) & 2):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            yield entry.path, info
                    except OSError as error:
                        if errors is not None:
                            errors.append(str(error))
        except OSError as error:
            if errors is not None:
                errors.append(str(error))


def searchFiles(root, query='', extensions='', since=0, hidden=False, cancel=None, emit=None):
    """名前・拡張子・更新日をAND条件で子孫まで検索する。

    Returns:
        dict: パス一覧と読めなかった場所のエラー。
    """
    matches, errors = [], []
    patterns = [p.strip().lower() for p in extensions.split(';') if p.strip()]
    for path, info in walkFiles(root, hidden, cancel, errors):
        name = Path(path).name.lower()
        accepted = fnmatch.fnmatch(name, query.lower()) if any(c in query for c in '*?[') else query.lower() in name
        if accepted and info.st_mtime >= since and (not patterns or any(fnmatch.fnmatch(name, p) for p in patterns)):
            matches.append(path)
            if emit and len(matches) % 100 == 0:
                emit('{} results'.format(len(matches)), 0)
    return dict(paths=matches, errors=errors)


def hashFile(path, cancel=None):
    """ファイル本体のSHA-256を中止可能に計算する。"""
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checkCancel(cancel)
            digest.update(block)
    return digest.hexdigest()


def duplicateFiles(root, cancel=None):
    """同じサイズだけをハッシュ比較し、削除せず重複候補を返す。"""
    sizes, hashes, errors = {}, {}, []
    for path, info in walkFiles(root, cancel=cancel, errors=errors):
        sizes.setdefault(info.st_size, []).append(path)
    for paths in sizes.values():
        if len(paths) > 1:
            for path in paths:
                hashes.setdefault(hashFile(path, cancel), []).append(path)
    return dict(groups=[paths for paths in hashes.values() if len(paths) > 1], errors=errors)


def compareFolders(source, target, cancel=None):
    """相対パスと内容で比較する。同期は呼出側で明示的に実行する。"""
    errors = []
    source_path, target_path = Path(source).resolve(), Path(target).resolve()
    if source_path == target_path or source_path in target_path.parents or target_path in source_path.parents:
        raise ValueError('Choose two independent folders, not a parent and its child.')
    left = {os.path.relpath(p, source): p for p, _ in walkFiles(source, True, cancel, errors)}
    right = {os.path.relpath(p, target): p for p, _ in walkFiles(target, True, cancel, errors)}
    changes = []
    for name, path in sorted(left.items()):
        checkCancel(cancel)
        other = right.get(name)
        if other is None or hashFile(path, cancel) != hashFile(other, cancel):
            changes.append(dict(source=path, target=str(Path(target) / name), state='Changed' if other else 'New'))
    return dict(changes=changes, targetOnly=sorted(set(right) - set(left)), errors=errors)


def createZip(paths, target, cancel=None):
    """既存アーカイブを上書きせず、元の選択名を保ってZIPを作る。"""
    target = Path(target)
    temporary = target.with_name(target.name + '.qpe-part')
    if target.exists() or temporary.exists():
        raise FileExistsError(str(target))
    names = set()
    try:
        with zipfile.ZipFile(str(temporary), 'x', zipfile.ZIP_DEFLATED) as archive:
            for value in paths:
                path = Path(value)
                if isLink(path):
                    raise ValueError('Links are not archived')
                errors = []
                if path.is_dir():
                    for directory, folders, unused in os.walk(str(path), followlinks=False):
                        checkCancel(cancel)
                        if isLink(directory):
                            raise ValueError('Links are not archived: ' + directory)
                        relative = os.path.relpath(directory, path.parent).replace('\\', '/') + '/'
                        if relative in names:
                            raise ValueError('Duplicate archive name: ' + relative)
                        names.add(relative)
                        archive.write(directory, relative)
                files = walkFiles(path, True, cancel, errors) if path.is_dir() else [(str(path), path.stat())]
                for filename, unused in files:
                    checkCancel(cancel)
                    relative = os.path.relpath(filename, path.parent).replace('\\', '/')
                    if relative in names:
                        raise ValueError('Duplicate archive name: ' + relative)
                    names.add(relative)
                    archive.write(filename, relative)
                if errors:
                    raise OSError('\n'.join(errors))
        os.rename(str(temporary), str(target))
    finally:
        if temporary.exists():
            temporary.unlink()
    return str(target)


def extractZip(path, destination, cancel=None):
    """ZIPを新規フォルダーへ展開し、パス逸脱・リンク・過大展開を拒否する。"""
    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError('Choose a new extraction folder')
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if sum(i.file_size for i in members) > 20 * 1024 ** 3 or len(members) > 100000:
            raise ValueError('Archive exceeds extraction limit (20 GiB / 100000 entries)')
        names = set()
        for item in members:
            name = PurePosixPath(item.filename.replace('\\', '/'))
            if (name.is_absolute() or '..' in name.parts or any(':' in p for p in name.parts)
                    or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('Unsafe archive path: ' + item.filename)
            from qpeFileOperations import validateName
            for part in name.parts:
                validateName(part)
            key = str(name).lower()
            if key in names:
                raise ValueError('Duplicate archive path: ' + item.filename)
            names.add(key)
        destination.mkdir()
        try:
            for item in members:
                checkCancel(cancel)
                output = destination.joinpath(*PurePosixPath(item.filename.replace('\\', '/')).parts)
                if item.is_dir():
                    output.mkdir(parents=True, exist_ok=True)
                else:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as src, output.open('xb') as dst:
                        for block in iter(lambda: src.read(1024 * 1024), b''):
                            checkCancel(cancel)
                            dst.write(block)
        except Exception:
            shutil.rmtree(str(destination))
            raise
    return str(destination)


def sceneInfo(path):
    """Mayaを起動せずASCIIの宣言だけを読む。解析の制限を明記する。"""
    path = Path(path)
    sidecar = path.with_suffix(path.suffix + '.qpe.json')
    result = ['Read-only: ' + str(not os.access(str(path), os.W_OK))]
    if sidecar.is_file():
        result.append('Sidecar: ' + str(sidecar))
        result.append(sidecar.read_text(encoding='utf8')[:32768])
    if path.suffix.lower() != '.ma':
        return '\n'.join(result + ['Binary scene: dependency analysis requires a saved sidecar.'])
    with path.open('rb') as stream:
        text = stream.read(8 * 1024 * 1024).decode('utf8', errors='replace')
    result.append('ASCII declaration scan (first 8 MiB; not a complete dependency graph)')
    result.extend(re.findall(r'^requires\s+[^;]+;', text, re.MULTILINE)[:30])
    paths = re.findall(r'(?:file\s+[^;]*?-r\b[^;]*|setAttr\s+"\.(?:ftn|filename)"[^;]*)"([^"\r\n]+)"\s*;', text)
    for value in dict.fromkeys(paths):
        candidate = Path(os.path.expandvars(value))
        if not candidate.is_absolute():
            result.append('Relative (project resolution needed): ' + value)
        elif '<' in value or '%' in value:
            result.append('Sequence / UDIM pattern: ' + value)
        else:
            result.append(('Exists: ' if candidate.exists() else 'Missing: ') + value)
    return '\n'.join(result)


def everythingSearch(query, root, executable, cancel=None):
    """任意導入のEverything CLIをシェルを介さず呼ぶ。"""
    storage = tempfile.TemporaryDirectory(prefix='qpe-everything-')
    output_path = Path(storage.name) / 'results.txt'
    process = subprocess.Popen([executable, '-path', str(root), '-full-path', '-export-txt', str(output_path),
                                '-utf8-bom', '--', query], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        while True:
            checkCancel(cancel)
            try:
                output, error = process.communicate(timeout=.2)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode:
            raise OSError(error.decode(errors='replace'))
        values = output_path.read_text(encoding='utf-8-sig').splitlines()
        return dict(paths=[p for p in values if os.path.isfile(p)], errors=[])
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
        storage.cleanup()
