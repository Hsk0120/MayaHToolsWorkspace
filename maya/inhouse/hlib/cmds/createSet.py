"""選択セットを生成する。照会・編集はObjectSetのメソッドを使用する。"""

import maya.cmds as cmds

from .._core.flags import flag_aliases
from ..decorators.undo import undoChunk


@flag_aliases("sets")
@undoChunk("hlib.cmds.createSet")
def createSet(*members, **kwargs):
    """メンバーを含む新規セットを生成する。

    Args:
        *members (Node | Component | str | Iterable): 初期メンバー。省略時はMayaの選択を使う。
        **kwargs (object): name/empty/renderable等の作成フラグ。長短名を使用可能。

    Returns:
        ObjectSet: 生成したセット。

    Raises:
        ValueError: 照会・編集フラグを指定した場合。
        TypeError: 入力型または長短フラグの指定が不正な場合。
        RuntimeError: Mayaが生成を拒否した場合。
    """
    from ..object import Object as _InputObject
    from ..nodes.objectSet import ObjectSet

    operations = ("query", "edit", "addElement", "forceElement", "remove", "isMember",
                  "isIntersecting", "union", "intersection", "subtract", "clear", "flatten", "size")
    if any(kwargs.get(key) for key in operations):
        raise ValueError("createSet supports creation only; use ObjectSet methods")
    return ObjectSet(cmds.sets(*_InputObject._input_names(members), **kwargs))
