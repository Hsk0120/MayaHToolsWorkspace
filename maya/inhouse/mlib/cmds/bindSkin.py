"""形状をinfluenceへバインドし、作成したskinClusterを返す(``cmds.skinCluster`` 相当)。

Mayaの Bind Skin と同じく ``cmds.skinCluster`` でバインドする。既定は選択したjointだけをinfluenceにし
(``toSelectedBones=True``)、正規化はInteractive(``normalizeWeights=1``)にする。

.. code-block:: python

    import mlib

    skin = mlib.bindSkin([hip, knee, ankle], "leg_geo", maximumInfluences=3)
"""

import maya.cmds as cmds

from ..core.object import Object
from ..decorator import undoChunk

#: bindSkin が既定値を決めるフラグ(長名, 短名, 既定値)。
_DEFAULT_FLAGS = (
    ("toSelectedBones", "tsb", True),
    ("normalizeWeights", "nw", 1),
)

#: 作成専用のため受け付けないフラグ。
_REJECTED_FLAGS = frozenset(("query", "q", "edit", "e"))


def bindSkin(joints, geometry, maximumInfluences=4, **kwargs):
    """形状を指定したinfluenceへバインドする。

    選択状態は参照しない。形状が既に skinCluster で変形されている場合は何もせず拒否する。
    fast引数は持たない(OpenMayaにバインドの同等機能が無い)。Undo有効時は1回で戻せる。

    Args:
        joints (Node | str | Iterable[Node | str]): influenceにするjoint等のtransform。
        geometry (Node | str): Mayaがバインドできる形状またはそのtransform。
        maximumInfluences (int): 1頂点に割り当てる最大数。正の整数。既定4。
        **kwargs (object): ``cmds.skinCluster`` のその他のフラグ(``bindMethod``・``dropoffRate``・
            ``name`` 等。長名・短名とも可)。``toSelectedBones``・``normalizeWeights`` を指定すると既定値を上書きする。

    Returns:
        SkinCluster: 作成したskinCluster。

    Raises:
        TypeError: query・editフラグ、または ``maximumInfluences`` の短名 ``mi`` を渡した場合。
        ValueError: influenceが空、maximumInfluencesが正の整数でない、または形状が既にスキニングされている場合。
        RuntimeError: 名前を解決できない、またはMayaがバインドを拒否した場合。
    """
    # nodes はcmdsを参照するため、循環importを避けて関数内で読み込む。
    from ..nodes.node import Node, Nodes
    from ..nodes.skinCluster import SkinCluster

    if "mi" in kwargs:
        raise TypeError("Use maximumInfluences instead of mi")
    rejected = sorted(_REJECTED_FLAGS.intersection(kwargs))
    if rejected:
        raise TypeError(f"bindSkin does not accept: {', '.join(rejected)}")
    if isinstance(maximumInfluences, bool) or not isinstance(maximumInfluences, int) or maximumInfluences < 1:
        raise ValueError("maximumInfluences must be a positive int")
    influences = [Node(name) for name in Nodes._resolve_inputs(joints)]
    if not influences:
        raise ValueError("At least one influence is required")
    target = Node(Object._input_name(geometry))
    if SkinCluster._geometry_skin_uuids(target):
        raise ValueError("Geometry already has a skinCluster")
    flags = dict(kwargs, maximumInfluences=maximumInfluences)
    for long, short, default in _DEFAULT_FLAGS:
        if long not in flags and short not in flags:
            flags[long] = default
    with undoChunk("mlibBindSkin"):
        result = cmds.skinCluster([node.getFullName() for node in influences], target.getFullName(), **flags)
        return Node(result[0])
