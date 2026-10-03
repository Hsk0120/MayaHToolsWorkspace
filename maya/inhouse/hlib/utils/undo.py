"""MayaのUndo状態を変更せず照会する。"""

from maya import cmds


def isEnabled():
    """現在のUndo記録が有効か問い合わせる。

    Returns:
        bool: Undo記録が有効ならTrue。履歴や設定は変更しない。
    """
    return bool(cmds.undoInfo(query=True, state=True))


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ('is_enabled',):
    globals().pop(_obsolete_name, None)
