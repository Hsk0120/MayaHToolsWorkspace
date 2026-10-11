"""既存ファイルを上書きしない、単一項目のファイル操作。"""
import os
import re
from pathlib import Path


def validateName(name):
    """Windowsで使える単一の名前を検証する。

    Args:
        name (str): 拡張子を含む名前。

    Returns:
        str: 検証済みの名前。

    Raises:
        ValueError: パス・予約名・禁止文字を含む場合。
    """
    if (not name or name in ('.', '..') or name.endswith((' ', '.'))
            or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name)
            or re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])', name.split('.')[0])):
        raise ValueError('Enter a valid Windows file name (no paths or reserved names).')
    return name


def createEntry(directory, name, folder=False):
    """既存項目を置き換えず、空ファイルまたはフォルダーを作る。

    Args:
        directory (str): 作成先。
        name (str): 単一の名前。
        folder (bool): フォルダーを作るか。

    Returns:
        str: 作成したパス。
    """
    path = Path(directory) / validateName(name)
    if folder:
        path.mkdir()
    else:
        with path.open('xb'):
            pass
    return path.as_posix()


def renameEntry(path, name):
    """同じ親の中で名前を変更する。既存の別項目は上書きしない。

    Args:
        path (str): 対象ファイルまたはフォルダー。
        name (str): 新しい単一の名前。

    Returns:
        str: 変更後のパス。
    """
    source = Path(path)
    if source.parent == source:
        raise ValueError('A drive root cannot be renamed.')
    target = source.with_name(validateName(name))
    if source.name == name:
        return source.as_posix()
    if os.path.lexists(target) and os.path.normcase(str(source)) != os.path.normcase(str(target)):
        raise FileExistsError('An item with that name already exists: ' + str(target))
    # Windowsのrenameは競合時に失敗する。replaceによる上書きは行わない。
    os.rename(str(source), str(target))
    return target.as_posix()
