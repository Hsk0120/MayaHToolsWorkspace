# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
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
from typing import Iterable
from mlib.nodes.node import Node
from mlib.nodes.skinCluster import SkinCluster

_DEFAULT_FLAGS: tuple
_REJECTED_FLAGS: frozenset

def bindSkin(joints: Node | str | Iterable[Node | str], geometry: Node | str, maximumInfluences: int = ..., **kwargs: object) -> SkinCluster:
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
    ...
