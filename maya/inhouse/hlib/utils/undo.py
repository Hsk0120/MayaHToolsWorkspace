"""MayaのUndo状態を変更せず照会する。"""

from maya import cmds


def is_enabled():
    """現在のUndo記録が有効か問い合わせる。

    Returns:
        bool: Undo記録が有効ならTrue。履歴や設定は変更しない。
    """
    return bool(cmds.undoInfo(query=True, state=True))
