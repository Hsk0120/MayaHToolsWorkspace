"""本文検索・ZIP選択抽出・Windows状態の読取専用基盤。"""
import ctypes
import errno
from functools import lru_cache
import os
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

TEXT_TYPES = {'.txt', '.md', '.markdown', '.py', '.mel', '.ma', '.json', '.csv', '.log', '.ini', '.xml', '.yaml', '.yml'}


@lru_cache(maxsize=1)
def cloudFunction():
    """Windows標準DLLから属性だけを使う照会関数を取得する。"""
    if os.name != 'nt':
        return None
    try:
        function = ctypes.WinDLL('CldApi.dll').CfGetPlaceholderStateFromAttributeTag
        function.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        function.restype = ctypes.c_uint32
        return function
    except (OSError, AttributeError):
        return None


def cloudState(attributes, reparse_tag):
    """クラウドフィルターに登録された状態だけを返す。内容は開かない。"""
    function = cloudFunction()
    return function(attributes, reparse_tag) if function and reparse_tag else 0


def availability(path=None, attributes=None, reparse_tag=0):
    """内容を開かずWindowsの取得状態を調べる。同期成否は推測しない。

    Args:
        path (str): 照会するファイル。
        attributes (int): テスト等で明示したWindows属性。
        reparse_tag (int): Windowsクラウド判定用のタグ。

    Returns:
        tuple: 表示名と自動読込を避けるか。
    """
    if attributes is None:
        try:
            info = os.stat(path, follow_symlinks=False)
            attributes = getattr(info, 'st_file_attributes', 0)
            reparse_tag = getattr(info, 'st_reparse_tag', 0)
        except OSError:
            return 'Unavailable', True
    cloud = cloudState(attributes, reparse_tag)
    suffix = ''
    if cloud != 0xffffffff and cloud & 1:
        suffix = ' / in sync' if cloud & 8 else ' / not in sync (provider details required)'
        if cloud & 0x30:
            return 'Cloud content not ready' + suffix, True
    if attributes & (0x1000 | 0x400000 | 0x40000):
        return 'Online / recall required' + suffix, True
    if attributes & 0x80000:
        return 'Pinned locally' + suffix, False
    if attributes & 0x100000:
        return 'Locally available (unpinned)' + suffix, False
    return ('Locally available' + suffix if suffix else 'Local / provider status unknown'), False


def requireLocal(path):
    """選択だけでオンライン素材のダウンロードを開始しない。"""
    state, blocked = availability(path)
    if blocked:
        raise OSError('Automatic read skipped: {}. Download explicitly in Windows Explorer first. {}'.format(state, path))


def contentMatches(path, query, cancel=None, limit=16 * 1024 * 1024):
    """対応テキストから一致行を返す。大容量・バイナリ・クラウドは明示して除外する。"""
    from qpeTransactions import checkCancel
    if Path(path).suffix.lower() not in TEXT_TYPES:
        return [], 'Unsupported text type'
    requireLocal(path)
    if os.path.getsize(path) > limit:
        return [], 'Text exceeds 16 MiB limit'
    checkCancel(cancel)
    with open(path, 'rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        return [], 'Text exceeds 16 MiB limit'
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        text = data.decode('utf-16')
    else:
        if b'\x00' in data:
            return [], 'Binary content'
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = data.decode('cp932', errors='replace')
    matches = []
    for number, line in enumerate(text.splitlines(), 1):
        checkCancel(cancel)
        if query.casefold() in line.casefold():
            matches.append((number, line[:400]))
            if len(matches) == 200:
                break
    return matches, ''


def zipEntries(path):
    """ZIP中央ディレクトリを検査して表示可能な項目を返す。"""
    from qpeFileOperations import validateName
    requireLocal(path)
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 100000 or sum(i.file_size for i in entries) > 20 * 1024 ** 3:
            raise ValueError('Archive limit: 100000 entries / 20 GiB')
        seen = set()
        result = []
        for item in entries:
            name = PurePosixPath(item.filename.replace('\\', '/'))
            if not name.parts or name.is_absolute() or '..' in name.parts or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Unsafe archive entry: ' + item.filename)
            for part in name.parts:
                validateName(part)
            key = str(name).casefold()
            if key in seen:
                raise ValueError('Duplicate archive path: ' + item.filename)
            seen.add(key)
            result.append(dict(name=item.filename, size=item.file_size, folder=item.is_dir(), encrypted=bool(item.flag_bits & 1)))
        return result


def extractSelected(path, names, destination, cancel=None):
    """選択したZIP項目だけ新規フォルダーへ展開し、既存データを上書きしない。"""
    from qpeTransactions import checkCancel
    entries = zipEntries(path)
    known = {i['name']: i for i in entries}
    if not names or any(name not in known for name in names):
        raise ValueError('Select existing ZIP entries')
    selected = [i for i in entries if any(i['name'] == n or (known[n]['folder'] and i['name'].startswith(n)) for n in names)]
    if any(i['encrypted'] for i in selected):
        raise ValueError('Encrypted entries require an external archive application')
    destination = Path(destination).absolute()
    destination.mkdir()  # 既存フォルダーやリンクへの書込みを拒否する。
    try:
        with zipfile.ZipFile(path) as archive:
            for item in selected:
                checkCancel(cancel)
                output = destination.joinpath(*PurePosixPath(item['name'].replace('\\', '/')).parts)
                if item['folder']:
                    output.mkdir(parents=True, exist_ok=True)
                    continue
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item['name']) as src, output.open('xb') as dst:
                    while True:
                        checkCancel(cancel)
                        block = src.read(1024 * 1024)
                        if not block:
                            break
                        dst.write(block)
        return str(destination)
    except Exception:
        shutil.rmtree(str(destination))
        raise


def errorAdvice(error):
    """OSエラー番号から次の確認先を示し、権限変更やプロセス終了はしない。"""
    win = getattr(error, 'winerror', None)
    code = getattr(error, 'errno', None)
    if win in (32, 33):
        return 'File is in use. Diagnose file usage to identify the owning application.'
    if win in (112, 39) or code == errno.ENOSPC:
        return 'Not enough disk space. Check destination and Undo backup storage.'
    if win in (53, 64, 67, 121, 1231):
        return 'Network location unavailable. Reconnect before retrying.'
    if code in (errno.EACCES, errno.EPERM) or win == 5:
        return 'Access denied or read-only. Check Windows Properties and file usage.'
    if code == errno.ENOENT:
        return 'File or folder no longer exists. Refresh its parent folder.'
    return 'Check the path, connection and access permissions before retrying.'


def diagnose(paths, executable=''):
    """属性と任意File Locksmith CLIの結果を読み取る。プロセス終了はしない。"""
    lines = []
    for path in paths:
        try:
            info = os.stat(path)
            state, blocked = availability(path)
            lines.append('{}\n  {} | {} bytes | readonly={}\n  Sync status: provider-specific / not queried'.format(
                path, state, info.st_size, bool(getattr(info, 'st_file_attributes', 0) & 1)))
        except OSError as error:
            lines.append('{}\n  {}\n  {}'.format(path, error, errorAdvice(error)))
    executable = executable or shutil.which('FileLocksmithCLI.exe')
    if executable:
        try:
            run = subprocess.run([executable, '--json'] + list(paths), capture_output=True, timeout=30,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            lines.append('File Locksmith (read only):\n' + (run.stdout or run.stderr).decode('utf8', errors='replace')[:30000])
            if run.returncode:
                lines.append('CLI exit code: {}'.format(run.returncode))
        except (OSError, subprocess.TimeoutExpired) as error:
            lines.append(str(error))
    else:
        lines.append('Process identification: configure the optional PowerToys FileLocksmithCLI.exe in Tools.')
    return '\n\n'.join(lines)
