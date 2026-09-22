"""Mayaコンストレイントを操作するHlibコマンド。"""

def constraint(sources, target, type="parent", maintainOffset=False):
    """ソースノードからターゲットノードへのコンストレイントを作成する。"""
    from ..nodes import Node

    target_node = target if isinstance(target, Node) else Node(target)
    return target_node.add_constraint(
        sources,
        type=type,
        maintainOffset=maintainOffset,
    )
