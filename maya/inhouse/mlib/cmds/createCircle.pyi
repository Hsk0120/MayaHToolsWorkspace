# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""NURBSの円を作成し、シェイプを返す(``cmds.circle(constructionHistory=False)`` 相当)。

半径はMaya APIの内部単位(cm)で、現在のUI単位に依存しない。構築履歴は作らない。
作成・親子付けを1回のUndoにまとめ、現在の選択は変更しない。

.. code-block:: python

    import mlib

    shape = mlib.createCircle(radius=2.0, normal=(0, 1, 0), name="ring")
"""

import maya.cmds as cmds
from ..core.shapeBuild import finish_shape, require_name, resolve_parent
from ..decorator import nativeUnits, preservedSelection, undoTransaction
from ..util import _finite, _finite_vector
from typing import Sequence
from mlib.nodes.node import Node
from mlib.nodes.nurbsCurve import NurbsCurve


def createCircle(radius: float = ..., normal: Sequence[float] = ..., sections: int = ..., degree: int = ..., name: str | None = ..., parent: Node | str | None = ...) -> NurbsCurve:
    """原点を中心とするNURBSの円を作成し、そのシェイプを返す。

    fast引数は持たない(OpenMayaに円の作成の同等機能が無いため)。

    Args:
        radius (float): 半径(cm)。正の有限値。既定1。
        normal (Sequence[float]): 円の面の法線。0でない有限な3成分。既定(0, 0, 1)。
        sections (int): 区間数。degree=1は3以上、degree=3は4以上。既定8。
        degree (int): 1(直線)または3(曲線)。既定3。
        name (str | None): Transformの希望名。シェイプは ``<名前>Shape``。NoneはMayaの既定名(``nurbsCircle1`` 等)。
        parent (Node | str | None): Transformの親。Noneはワールド直下。親のローカル空間に単位マトリクスで置く。

    Returns:
        NurbsCurve: 作成した円のシェイプ。Transformは ``getTransform()`` で取得する。

    Raises:
        TypeError: 引数の型が不正な場合。
        ValueError: 半径・法線・区間数・次数が不正な場合。
        RuntimeError: 親が無効な場合、またはMayaが作成を拒否した場合。
    """
    ...
