"""Bifrost 3以降のグラフ操作。import時はプラグインをロードしない。"""

import re
from maya import cmds

HLIB_EXTENSION_API = 1
MIN_VERSION = (3, 0, 0, 0)


def is_available():
    """bool: 対応プラグインがロード済みか、副作用なしで照会する。"""
    if int(cmds.about(apiVersion=True)) < 20250000:
        return False
    if not cmds.pluginInfo('bifrostGraph', query=True, loaded=True):
        return False
    version = cmds.pluginInfo('bifrostGraph', query=True, version=True)
    match = re.match(r'(\d+)\.(\d+)\.(\d+)\.(\d+)', version)
    return bool(match and tuple(map(int, match.groups())) >= MIN_VERSION)


def ensure_available():
    """対応版をロードする。永続autoloadとセキュリティ設定は変更しない。"""
    if int(cmds.about(apiVersion=True)) < 20250000:
        raise RuntimeError('hlib_bifrost requires Maya 2025 or newer')
    from hlib.plugins import Plugin
    Plugin('bifrostGraph').ensure_loaded()
    if not is_available():
        raise RuntimeError('hlib_bifrost requires Bifrost 3.0.0.0 or newer')


from .graph import Graph, Compound, Node, Port

__all__ = ['Graph', 'Compound', 'Node', 'Port', 'is_available', 'ensure_available']
