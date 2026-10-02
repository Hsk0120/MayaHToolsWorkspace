"""Bifrost 3以降の型付き操作。import時はプラグインをロードしない。"""

import importlib as _importlib

HLIB_EXTENSION_API = 1


def is_available():
    """bool: hlib拡張検出プロトコルから対応プラグインの状態を照会する。"""
    from .environment import Bifrost
    return Bifrost.is_available()


def __getattr__(name):
    """宣言の初期化完了後、要求された公開サブパッケージだけを読み込む。

    Args:
        name (str): 公開サブパッケージ名。
    Returns:
        module: 読み込み済みのサブパッケージ。
    Raises:
        AttributeError: 公開対象以外の名前の場合。
    """
    if name not in {"nodes", "plugs", "utils", "environment"}:
        raise AttributeError(name)
    module = _importlib.import_module(__name__ + "." + name)
    globals()[name] = module
    return module


__all__ = ["nodes", "plugs", "utils", "environment", "is_available"]
