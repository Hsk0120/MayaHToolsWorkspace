"""アトリビュートを追加する。照会・編集はPlugのメソッドを使用する。"""

from maya import cmds
from .._core.flags import flag_aliases
from .._core.coerce import to_name
from ..decorators.undo import undo_chunk


@flag_aliases("addAttr")
@undo_chunk("hlib.cmds.addAttr")
def addAttr(target, **kwargs):
    """アトリビュートを追加する。照会・編集はPlugのメソッドを使用する。

    Args:
        target (str | Node | Plug): 操作対象。
        **kwargs: Mayaの長名・短名フラグ。重複指定は拒否する。

    Returns:
        Plug: 追加したアトリビュート参照。

    Raises:
        TypeError: 入力型やフラグの重複が不正な場合。
        RuntimeError: Mayaが操作を拒否した場合。


    """
    from .._core.coerce import to_plug, to_node

    if kwargs.get("query") or kwargs.get("edit"):
        raise ValueError("addAttr supports creation only")
    name = to_name(target)
    if (
        not kwargs.get("query")
        and "." not in name
        and not (kwargs.get("longName") or kwargs.get("shortName"))
    ):
        raise ValueError("Specify longName or shortName")
    cmds.addAttr(name, **kwargs)
    if "." in name:
        return to_plug(name)
    attribute = kwargs.get("longName") or kwargs.get("shortName")
    if not attribute:
        raise ValueError("Specify longName or shortName")
    return to_node(target).plug(attribute)
