"""Maya標準のNURBSカーブを作成する。"""

import maya.cmds as cmds

from .._core.commandResult import CommandResult
from .._core.flags import flag_aliases
from ..decorator import undoChunk


@flag_aliases("curve")
@undoChunk("hlib.cmds.createCurve")
def createCurve(*args, **kwargs):
    """指定したCV・ノットからカーブを生成する。

    Args:
        *args: Mayaの作成引数。置換・追加・照会・編集は受け付けない。
        **kwargs: Mayaの長名・短名フラグ。point等の数値列もそのまま指定する。

    Returns:
        Transform: 作成したカーブのtransform参照。
    """
    from .._core.object import Object as _InputObject
    if any(kwargs.get(key) for key in ("query", "edit", "replace", "append")):
        raise ValueError("createCurve supports creation only")
    return CommandResult.reference(cmds.curve(*_InputObject._input_names(args), **kwargs))
