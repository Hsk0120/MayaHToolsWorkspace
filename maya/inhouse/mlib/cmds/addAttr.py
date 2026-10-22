"""アトリビュートを追加する。照会・編集はPlugのメソッドを使用する。"""

from .._core.flags import flag_aliases
from ..common._fast import fast_edit, is_fast
from ..decorator import undoChunk


@flag_aliases("addAttr")
@fast_edit
@undoChunk("mlib.cmds.addAttr")
def addAttr(target, *, fast=False, **kwargs):
    """アトリビュートを追加する。照会・編集はPlugのメソッドを使用する。

    Args:
        fast (bool): TrueはOpenMaya直接更新でUndoなし。既定FalseはMaya標準コマンドを使用する。
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
