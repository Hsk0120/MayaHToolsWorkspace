"""MayaのUndo状態を変更せず照会する。"""

import maya.cmds as cmds

from .._core.getterAlias import _is_alias


def isEnabled():
    """現在のUndo記録が有効か問い合わせる。

    Returns:
        bool: Undo記録が有効ならTrue。履歴や設定は変更しない。
    """
    return bool(cmds.undoInfo(query=True, state=True))


@_is_alias(isEnabled)
def enabled(*args, **kwargs):
    """isEnabledへ委譲するis省略の判定入口。

    Args:
        *args: 判定本体へ渡す位置引数。
        **kwargs: 判定本体へ渡すキーワード引数。

    Returns:
        object: 判定本体と同じ結果。
    """
    return isEnabled(*args, **kwargs)


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ('is_enabled',):
    globals().pop(_obsolete_name, None)
