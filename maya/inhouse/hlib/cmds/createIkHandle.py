"""IKハンドルとエフェクターを生成する。"""

from maya import cmds
from .._core.flags import flag_aliases
from .._core.coerce import to_names
from ..decorators.undo import undo_chunk
from .._core.commandResult import CommandResult


@flag_aliases("ikHandle")
@undo_chunk("hlib.cmds.createIkHandle")
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
    if kwargs.get("query") or kwargs.get("edit"):
        raise ValueError("createIkHandle supports creation only")
    options = CommandResult.node_flags(kwargs, ("startJoint", "endEffector", "curve"))
    result = cmds.ikHandle(*to_names(args), **options)
    return CommandResult.references(result if isinstance(result, list) else [result])
