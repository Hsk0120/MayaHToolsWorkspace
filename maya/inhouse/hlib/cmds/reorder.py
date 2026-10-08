"""DAGの兄弟順序を変更する。"""

import maya.cmds as cmds

from .._core.flags import flag_aliases
from ..decorator import undoChunk


@flag_aliases("reorder")
@undoChunk("hlib.cmds.reorder")
def reorder(*args, **kwargs):
    """DAGの兄弟順序を変更する。

    Args:
        *args: 対象の名前またはhlib参照。省略時の扱いはMayaに従う。
        **kwargs: Mayaの長名・短名フラグ。重複指定は拒否する。

    Returns:
        list[Node]: 操作したノード。未選択時は空リスト。

    Raises:
        TypeError: 入力型やフラグの重複が不正な場合。
        RuntimeError: Mayaが操作を拒否した場合。


    """
    from .._core.object import Object as _InputObject
    from ..nodes.node import Node

    names = _InputObject._input_names(args)
    if not names:
        names = cmds.ls(selection=True, long=True) or []
    if not names:
        return []
    cmds.reorder(*names, **kwargs)
    return [Node(name) for name in names]
