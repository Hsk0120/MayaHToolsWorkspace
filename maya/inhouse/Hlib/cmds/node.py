"""Mayaノードを操作するHlibコマンド。"""

import maya.cmds as maya_cmds


def create_node(type, **kwargs):
    """Mayaノードを作成し、対応するHlib wrapperとして返す。"""
    from ..nodes import Node

    return Node.create(type, **kwargs)


def ls(*args, **kwargs):
    """Mayaノードを検索し、対応するHlib wrapperとして返す。"""
    from ..nodes import Joints, Node, SkinClusters

    names = maya_cmds.ls(*args, **kwargs) or []
    node_type = kwargs.get("type")
    if node_type == "joint":
        return Joints(names)
    if node_type == "skinCluster":
        return SkinClusters(names)
    return [Node(name) for name in names]
