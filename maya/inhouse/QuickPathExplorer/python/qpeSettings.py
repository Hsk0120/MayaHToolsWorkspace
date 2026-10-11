"""QuickPathExplorer専用の設定だけをUTF-8 JSONへ原子的に保存する。"""
import json
import os
from pathlib import Path
from qpeQt import QtCore


def settingsPath():
    """設定ファイルの場所を返す。

    Returns:
        Path: 検証用環境変数、またはユーザーの専用アプリ設定ファイル。
    """
    override = os.environ.get('QPE_SETTINGS_FILE')
    if override:
        return Path(override)
    base = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.GenericConfigLocation)
    return Path(base) / 'QuickPathExplorer' / 'settings.json'


def readSettings():
    """設定を読む。破損や未作成の場合は空設定として扱う。

    Returns:
        dict: 読み込めた設定。
    """
    try:
        value = json.loads(settingsPath().read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            return {}
        for key in ('favorites', 'recents'):
            paths = value.get(key, [])
            value[key] = [p for p in paths if isinstance(p, str) and p] if isinstance(paths, list) else []
        for key in ('mayaLayout', 'standaloneLayout'):
            if not isinstance(value.get(key, {}), dict):
                value[key] = {}
        if not isinstance(value.get('lastPath', ''), str):
            value.pop('lastPath', None)
        return value
    except (OSError, ValueError):
        return {}


def writeSettings(changes):
    """最新設定の指定キーだけを更新し、一時ファイルから置き換える。

    Args:
        changes (dict): 変更するキーと値。

    Returns:
        bool: 保存に成功したか。
    """
    value = readSettings()
    value.update(changes)
    path = settingsPath()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        output = QtCore.QSaveFile(str(path))
        if not output.open(QtCore.QIODevice.WriteOnly):
            return False
        data = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
        if output.write(data) != len(data):
            output.cancelWriting()
            return False
        return output.commit()
    except OSError:
        return False
