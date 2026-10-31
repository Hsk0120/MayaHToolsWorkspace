# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""点列からNURBSカーブを作成し、シェイプを返す(``cmds.curve`` 相当)。

点をそのままCVにする(通過点の補間ではない)。距離はMaya APIの内部単位(cm)で、現在のUI単位に
依存しない。作成・親子付けを1回のUndoにまとめ、現在の選択は変更しない。

.. code-block:: python

    import mlib

    shape = mlib.createCurve([(0, 0, 0), (1, 0, 0), (1, 1, 0)], degree=1, name="line")
    transform = shape.getTransform()
    loop = mlib.createCurve([(1, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0)], degree=3, closed=True)
"""

import math
from typing import Any, Dict
import maya.cmds as cmds
from ..core import geometryEdit as geometry_edit
from ..core.shapeBuild import finish_shape, require_name, resolve_parent
from ..decorator import _require_bool, nativeUnits, preservedSelection, undoTransaction
from typing import Iterable, Sequence
from mlib.nodes.node import Node
from mlib.nodes.nurbsCurve import NurbsCurve
import maya.api.OpenMaya as om2


def createCurve(points: Iterable[Sequence[float] | om2.MPoint | om2.MVector], degree: int = ..., closed: bool = ..., knots: Sequence[float] | None = ..., name: str | None = ..., parent: Node | str | None = ...) -> NurbsCurve:
    """点列からNURBSカーブを作成し、そのシェイプを返す。

    開いたカーブは ``knots`` を省略すると ``cmds.curve`` の既定ノット、``closed=True`` は先頭 ``degree`` 個の
    CVを末尾へ重ねた周期カーブ(``getForm()`` が ``om2.MFnNurbsCurve.kPeriodic``)にする。
    fast引数は持たない(OpenMayaで作っても約1.4倍で、効果がほぼ無いため)。

    Args:
        points (Iterable[Sequence[float] | om2.MPoint | om2.MVector]): CVの位置。各点は3個の
            有限な数値(boolを除く)。MPointはwで割らずにXYZを使う。カーブのTransform(作成時は単位
            マトリクス)のローカル座標で、単位はcm。
        degree (int): 次数。1・2・3のいずれか。既定1。
        closed (bool): Trueなら閉じたカーブにする。既定False。
        knots (Sequence[float] | None): 開いたカーブのノット列(``cmds.curve`` の ``knot``)。
            個数は ``CV数 + degree - 1``。Noneは既定のノット。``closed=True`` とは併用できない。
        name (str | None): Transformの希望名。シェイプは ``<名前>Shape``。NoneはMayaの既定名(``curve1`` 等)。
        parent (Node | str | None): Transformの親。Noneはワールド直下。親のローカル空間に
            単位マトリクスで置くため、点は親の空間の座標になる。

    Returns:
        NurbsCurve: 作成したカーブのシェイプ。Transformは ``getTransform()`` で取得する。

    Raises:
        TypeError: points・degree・closed・knots・name・parentの型が不正な場合。
        ValueError: degreeが1〜3でない、点の成分数が3でない・有限でない、点の数が不足する
            (開いたカーブはdegree+1点以上、閉じたカーブは3点以上かつdegree点以上)、
            knotsの個数・値が不正、またはclosedとknotsを併用した場合。
        RuntimeError: 親が無効な場合、またはMayaが作成を拒否した場合。
    """
    ...

def _knot_list(knots: Sequence[float], count: int) -> list[float]:
    """ノット列を検証してfloatのリストにする。

    Args:
        knots (Sequence[float]): ノット列。
        count (int): 必要な個数。

    Returns:
        list[float]: 検証したノット列。

    Raises:
        TypeError: 反復できない、または数値以外を含む場合。
        ValueError: 個数が違う、有限でない、または減少する場合。
    """
    ...
