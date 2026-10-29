# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""MayaのUndo状態を変更せず照会する。"""

import maya.cmds as cmds


def isEnabled() -> bool:
    """現在のUndo記録が有効か問い合わせる。

    Returns:
        bool: Undo記録が有効ならTrue。履歴や設定は変更しない。
    """
    ...
