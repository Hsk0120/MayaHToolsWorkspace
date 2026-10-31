"""ポリゴンの円柱を作成し、シェイプを返す(``cmds.polyCylinder(constructionHistory=False)`` 相当)。

大きさはMaya APIの内部単位(cm)で、現在のUI単位に依存しない。構築履歴は作らない。
作成・親子付けを1回のUndoにまとめ、現在の選択は変更しない。

.. code-block:: python

    import mlib

    shape = mlib.createPolyCylinder(radius=0.5, height=4.0, axis=(1, 0, 0), name="bone")
    transform = shape.getTransform()
"""

import maya.cmds as cmds

from ..core.shapeBuild import create_poly, positive_size, require_name, resolve_parent, subdivision_counts
from ..util import _finite_vector


def createPolyCylinder(radius=1.0, height=2.0, subdivisions=(20, 1, 1), axis=(0, 1, 0), name=None, parent=None):
    """原点を中心とするポリゴンの円柱を作成し、そのシェイプを返す。

    fast引数は持たない(Mayaのコマンドと同じUV・法線のメッシュをOpenMayaで組み立て直すことになり、同じ結果を保つのが難しいため)。

    Args:
        radius (float): 半径(cm)。既定1。
        height (float): 高さ(cm)。既定2。
        subdivisions (Sequence[int]): 軸のまわり・高さ方向・ふたの分割数(``subdivisionsX/Y/Z``)。既定(20, 1, 1)。
        axis (Sequence[float]): 円柱の軸の方向。0でない有限な3成分。既定(0, 1, 0)。
        name (str | None): Transformの希望名。シェイプは ``<名前>Shape``。NoneはMayaの既定名。
        parent (Node | str | None): Transformの親。Noneはワールド直下。親のローカル空間に単位マトリクスで置く。

    Returns:
        Mesh: 作成したメッシュのシェイプ。Transformは ``getTransform()`` で取得する。

    Raises:
        TypeError: 引数の型が不正な場合。
        ValueError: 大きさが0以下・有限でない、分割数・軸が不正な場合。
        RuntimeError: 親が無効な場合、またはMayaが作成を拒否した場合。
    """
    sx, sy, sz = subdivision_counts(subdivisions, 3)
    flags = {"radius": positive_size(radius, "radius"), "height": positive_size(height, "height"),
             "subdivisionsX": sx, "subdivisionsY": sy, "subdivisionsZ": sz, "axis": _axis(axis)}
    return create_poly(cmds.polyCylinder, flags, require_name(name), resolve_parent(parent))


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
