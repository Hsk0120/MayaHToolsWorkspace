"""Mayaのシェーダーノードを作成する。"""
import maya.cmds as cmds
from .._core.flags import flag_aliases
from ..decorators.undo import undo_chunk


@flag_aliases(n="name")
@undo_chunk("hlibCreateShader")
def createShader(type, name=None):
    """シェーダーとしてノードを作成する。割り当てセットは別途作成する。

    Args:
        type (str): lambert、standardSurface等のMayaノード型。
        name (str | None): ノード名。省略時はMayaの自動命名。
    Returns:
        Node: 型に対応したラッパー。
    """
    from ..nodes import Node
    flags = {} if name is None else {"name": name}
    return Node(cmds.shadingNode(type, asShader=True, **flags))
