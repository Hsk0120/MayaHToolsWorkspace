"""Maya標準のNURBSカーブを作成する。"""

from maya import cmds
from .._core.flags import flag_aliases
from .._core.coerce import to_names
from .._core.commandResult import CommandResult
from ..decorators.undo import undo_chunk


@flag_aliases("curve")
@undo_chunk("hlib.cmds.createCurve")
def createCurve(*args, **kwargs):
    """指定したCV・ノットからカーブを生成する。

    Args:
        *args: Mayaの作成引数。置換・追加・照会・編集は受け付けない。
        **kwargs: Mayaの長名・短名フラグ。point等の数値列もそのまま指定する。

    Returns:
        Transform: 作成したカーブのtransform参照。
    """
    if any(kwargs.get(key) for key in ("query", "edit", "replace", "append")):
        raise ValueError("createCurve supports creation only")
    return CommandResult.reference(cmds.curve(*to_names(args), **kwargs))
