"""IKハンドルとエフェクターを生成する。"""

from maya import cmds
from .._core.flags import flag_aliases
from ..decorators.undo import undoChunk
from .._core.commandResult import CommandResult


@flag_aliases("ikHandle")
@undoChunk("hlib.cmds.createIkHandle")
def createIkHandle(*args, **kwargs):
    """IKハンドルとエフェクターを生成する。

    Args:
        *args: 対象の名前またはhlib参照。省略時の扱いはMayaに従う。照会・編集は受け付けない。
        **kwargs: Mayaの長名・短名フラグ。重複指定は拒否する。

    Returns:
        list[Node]: 作成したIkHandle/IkEffector等。

    Raises:
        TypeError: 入力型やフラグの重複が不正な場合。
        RuntimeError: Mayaが操作を拒否した場合。


    """
    from hlib.object import Object as _InputObject
    if kwargs.get("query") or kwargs.get("edit"):
        raise ValueError("createIkHandle supports creation only")
    options = CommandResult.node_flags(kwargs, ("startJoint", "endEffector", "curve"))
    result = cmds.ikHandle(*_InputObject._input_names(args), **options)
    return CommandResult.references(result if isinstance(result, list) else [result])
