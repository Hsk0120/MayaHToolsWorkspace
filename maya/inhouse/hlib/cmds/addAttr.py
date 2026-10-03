"""アトリビュートを追加する。照会・編集はPlugのメソッドを使用する。"""

from .._core.flags import flag_aliases
from ..decorators.undo import undoChunk


@flag_aliases("addAttr")
@undoChunk("hlib.cmds.addAttr")
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
    from ..nodes.node import Node
    return Node._add_attribute(target, **kwargs)
