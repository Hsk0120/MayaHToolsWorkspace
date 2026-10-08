"""Bind Skinメニュー相当のスムーズバインド。内部ではskinClusterを使用する。

Mayaの同名bindSkinコマンド（リジッドバインド）を転送する関数ではない。
"""

import maya.cmds as cmds

from .._core.flags import flag_aliases
from ..decorator import undoChunk


@flag_aliases("skinCluster")
@undoChunk("hlibCreateSkinCluster")
def bindSkin(geometry, influences, **kwargs):
    """明示した形状とインフルエンスをバインドする。

    Args:
        geometry (Node | str | Iterable): 形状またはそのTransform。複数指定可能。
        influences (Node | str | Iterable): インフルエンス。各入力列は名前だけ/Nodeだけ。
        **kwargs (object): skinClusterの作成フラグ。bindMethod(bm)、skinMethod(sm)、
            maximumInfluences(mi)、normalizeWeights(nw)、toSelectedBones(tsb)等。
            省略時はMaya標準値。照会・編集・解除は不可。

    Returns:
        SkinCluster | SkinClusters: 1件なら単体、複数なら入力形状順のコレクション。

    Raises:
        ValueError: 空入力、重複形状、または作成以外の操作を指定した場合。
        TypeError: 入力型・長短フラグの重複が不正な場合。
        RuntimeError: Mayaがバインドを拒否した場合。

    各形状に同じフラグを渡す。全体を一回のUndoで戻せる。途中の失敗は例外とし、
    完了済み作成は自動で戻さない。bindMethod=3は標準コマンドと同様、作成後に
    別途geomBindが必要。選択から対象を推測しない。
    """
    from ..nodes.node import Node as _InputNode
    from ..nodes.node import Nodes as _InputNodes
    from ..nodes.skinCluster import SkinCluster, SkinClusters
    operations = {"query", "edit", "unbind", "unbindKeepHistory", "remove", "removeInfluence",
                  "addInfluence", "geometry", "influence", "selectInfluenceVerts"}
    if operations.intersection(kwargs):
        raise ValueError("bindSkin accepts creation flags only")
    geometries = [_InputNode._resolve_input(value) for value in _InputNodes._resolve_inputs(geometry)]
    joints = [_InputNode._resolve_input(value) for value in _InputNodes._resolve_inputs(influences)]
    if not geometries or not joints:
        raise ValueError("Geometry and influences must not be empty")
    if len(set(geometries)) != len(geometries):
        raise ValueError("Duplicate geometry")
    names = [node.getFullName() for node in joints]
    geometry_names = [node.getFullName() for node in geometries]
    result = []
    for name in geometry_names:
        created = cmds.skinCluster(*names, name, **kwargs)
        result.append(SkinCluster(created[0] if isinstance(created, (list, tuple)) else created))
    return result[0] if len(result) == 1 else SkinClusters(result)
