"""ポリゴンの平面を作成し、シェイプを返す(``cmds.polyPlane(constructionHistory=False)`` 相当)。

大きさはMaya APIの内部単位(cm)で、現在のUI単位に依存しない。構築履歴は作らない。
作成・親子付けを1回のUndoにまとめ、現在の選択は変更しない。

.. code-block:: python

    import mlib

    shape = mlib.createPolyPlane(width=10.0, height=10.0, subdivisions=(4, 4), name="floor")
    transform = shape.getTransform()
"""

import maya.cmds as cmds

from ..core.shapeBuild import create_poly, positive_size, require_name, resolve_parent, subdivision_counts
from ..util import _finite_vector


def createPolyPlane(width=1.0, height=1.0, subdivisions=(10, 10), axis=(0, 1, 0), name=None, parent=None):
    """原点を中心とするポリゴンの平面を作成し、そのシェイプを返す。

    fast引数は持たない(Mayaのコマンドと同じUV・法線のメッシュをOpenMayaで組み立て直すことになり、同じ結果を保つのが難しいため)。

    Args:
        width (float): 幅(cm)。既定1。
        height (float): 高さ(奥行き方向の長さ、cm)。既定1。
        subdivisions (Sequence[int]): 幅・高さ方向の分割数(``subdivisionsX/Y``)。既定(10, 10)。
        axis (Sequence[float]): 面の法線。0でない有限な3成分。既定(0, 1, 0)。
        name (str | None): Transformの希望名。シェイプは ``<名前>Shape``。NoneはMayaの既定名。
        parent (Node | str | None): Transformの親。Noneはワールド直下。親のローカル空間に単位マトリクスで置く。

    Returns:
        Mesh: 作成したメッシュのシェイプ。Transformは ``getTransform()`` で取得する。

    Raises:
        TypeError: 引数の型が不正な場合。
        ValueError: 大きさが0以下・有限でない、分割数・軸が不正な場合。
        RuntimeError: 親が無効な場合、またはMayaが作成を拒否した場合。
    """
    sx, sy = subdivision_counts(subdivisions, 2)
    flags = {"width": positive_size(width, "width"), "height": positive_size(height, "height"),
             "subdivisionsX": sx, "subdivisionsY": sy, "axis": _axis(axis)}
    return create_poly(cmds.polyPlane, flags, require_name(name), resolve_parent(parent))


def _axis(value):
    """軸の方向を検証する。

    Args:
        value (Sequence[float]): 方向。

    Returns:
        tuple[float, float, float]: 検証した方向。

    Raises:
        TypeError: 数値の列でない場合。
        ValueError: 成分数が3でない、有限でない、または0の場合。
    """
    axis = _finite_vector(value, 3, "axis")
    if not any(axis):
        raise ValueError("axis must not be zero")
    return axis
