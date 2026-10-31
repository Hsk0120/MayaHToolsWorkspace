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


def createCurve(points, degree=1, closed=False, knots=None, name=None, parent=None):
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
    values = geometry_edit.point_list(points)
    if isinstance(degree, bool) or not isinstance(degree, int):
        raise TypeError("degree must be an int")
    if degree not in (1, 2, 3):
        raise ValueError(f"degree must be 1, 2 or 3, got {degree}")
    _require_bool(closed, "closed")
    name = require_name(name)
    if closed:
        if knots is not None:
            raise ValueError("knots cannot be combined with closed=True")
        if len(values) < max(3, degree):
            raise ValueError(f"A closed curve of degree {degree} needs at least {max(3, degree)} points")
    elif len(values) < degree + 1:
        raise ValueError(f"An open curve of degree {degree} needs at least {degree + 1} points")
    flags: Dict[str, Any] = {"degree": degree}
    if knots is not None:
        flags["knot"] = _knot_list(knots, len(values) + degree - 1)
    parent_node = resolve_parent(parent)
    if closed:
        count = len(values)
        values = values + values[:degree]
        # 周期カーブのノットは重なるCVの数だけ両端へはみ出す一様な列(CV数 + degree - 1 個)。
        flags["periodic"] = True
        flags["knot"] = [float(knot) for knot in range(-(degree - 1), count + degree)]
    if name:
        flags["name"] = name
    with undoTransaction("mlibCreateCurve"), preservedSelection():
        # cmds.curveの座標は現在のUI単位で解釈されるため、内部単位(cm)へ切り替えて渡す。
        with nativeUnits():
            transform = cmds.curve(point=values, **flags)
        return finish_shape(transform, "nurbsCurve", name, parent_node)


def _knot_list(knots, count):
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
    if isinstance(knots, (str, bytes)):
        raise TypeError("knots must be a sequence of numbers")
    try:
        items = list(knots)
    except TypeError:
        raise TypeError("knots must be a sequence of numbers") from None
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in items):
        raise TypeError("knots must be numbers")
    values = [float(value) for value in items]
    if len(values) != count:
        raise ValueError(f"knots must have {count} values (CV count + degree - 1), got {len(values)}")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("knots must be finite")
    if any(b < a for a, b in zip(values, values[1:])):
        raise ValueError("knots must not decrease")
    return values
