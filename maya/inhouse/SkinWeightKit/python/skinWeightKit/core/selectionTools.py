"""頂点の選択を広げる・狭める(隣接する頂点をたどる)、エッジのループ・リングを選ぶ(計算は mlib の Vertices・Edges)。"""

import mlib
from mlib.common import Selection
from mlib.components import Edges

from . import target as target_module


def selectedEdges(selection=None):
    """選んでいるエッジを、最初のメッシュについて返す。

    Args:
        selection (Selection | None): 使う選択。Noneは今の選択。

    Returns:
        tuple[mlib.Mesh, list[int]]: メッシュとエッジの番号。

    Raises:
        ValueError: メッシュのエッジを選んでいない場合。
    """
    selection = Selection.capture() if selection is None else selection
    mesh = None
    edges = []
    for components in selection.getComponents():
        if isinstance(components, Edges) and isinstance(components.shape, mlib.Mesh):
            if mesh is None:
                mesh = components.shape
            if components.shape == mesh:
                edges.extend(index for index in components.indices if index not in edges)
    if mesh is None:
        raise ValueError("Select edges of a mesh")
    return mesh, edges


def _select_edges(mesh, edges):
    """メッシュのエッジを選ぶ。"""
    edges = sorted(edges)
    Selection([mesh.getEdges(edges)]).select()
    return len(edges)


def selectLoop(selection=None):
    """選んだエッジのループを選ぶ。

    Args:
        selection (Selection | None): 使う選択。Noneは今の選択。

    Returns:
        int: 選んだエッジの数。
    """
    mesh, edges = selectedEdges(selection)
    return _select_edges(mesh, mesh.getEdges(edges).getLoop().indices)


def selectRing(selection=None):
    """選んだエッジのリングを選ぶ。

    Args:
        selection (Selection | None): 使う選択。Noneは今の選択。

    Returns:
        int: 選んだエッジの数。
    """
    mesh, edges = selectedEdges(selection)
    return _select_edges(mesh, mesh.getEdges(edges).getRing().indices)


def grownVertices(target):
    """選んだ頂点に、隣の頂点を足した番号を返す。

    Args:
        target (Target): 対象。

    Returns:
        list[int]: 頂点の番号(昇順)。
    """
    return sorted(target.mesh.getVertices(target.requireVertices()).grow().indices)


def shrunkVertices(target):
    """選んだ頂点から、選んでいない頂点に隣接する頂点(縁)を除いた番号を返す。

    Args:
        target (Target): 対象。

    Returns:
        list[int]: 頂点の番号(昇順)。
    """
    return sorted(target.mesh.getVertices(target.requireVertices()).shrink().indices)


def grow(target):
    """選んだ頂点の選択を、隣の頂点まで広げる。

    Args:
        target (Target): 対象。

    Returns:
        int: 選んだ頂点の数。
    """
    return target_module.selectVertices(target.mesh, grownVertices(target))


def shrink(target):
    """選んだ頂点の選択から、縁の頂点を外す。

    Args:
        target (Target): 対象。

    Returns:
        int: 選んだ頂点の数。
    """
    return target_module.selectVertices(target.mesh, shrunkVertices(target))
