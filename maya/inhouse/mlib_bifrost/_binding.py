"""拡張名の接頭辞から対応するコアを解決する。"""

from importlib import import_module


def coreModule(suffix=""):
    """同じ接頭辞のコアモジュールを取得する。

    Args:
        suffix (str): コア配下のモジュール名。空ならコア自身。

    Returns:
        module: 現在のコアモジュール。reload 前のクラスを保持しない。
    """
    name = __package__[:-len("_bifrost")]
    return import_module(name + ("." + suffix if suffix else ""))
