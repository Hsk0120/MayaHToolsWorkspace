"""Bifrost 3以降の型付き操作。import時はプラグインをロードしない。"""

from . import nodes, plugs, utils, general

HLIB_EXTENSION_API = 1


def is_available():
    """bool: hlib拡張検出プロトコルから対応プラグインの状態を照会する。"""
    return general.Bifrost.is_available()


__all__ = ["nodes", "plugs", "utils", "general", "is_available"]
