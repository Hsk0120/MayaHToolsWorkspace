# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
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
from ..decorator import _pick_alias
from ..util import _UNSET, _finite_vector
from typing import Sequence
from mlib.nodes.mesh import Mesh
from mlib.nodes.node import Node


def createPolyCylinder(radius: float = ..., height: float = ..., subdivisions: Sequence[int] = ..., axis: Sequence[float] = ..., name: str | None = ..., parent: Node | str | None = ..., *, r: float = ..., h: float = ..., ax: Sequence[float] = ..., n: str | None = ...) -> Mesh:
    """原点を中心とするポリゴンの円柱を作成し、そのシェイプを返す。

    fast引数は持たない(Mayaのコマンドと同じUV・法線のメッシュをOpenMayaで組み立て直すことになり、同じ結果を保つのが難しいため)。
    radius・height・axis・nameは ``cmds.polyCylinder`` と同じ短縮名でも受ける(長名と短縮名の同時指定はできない)。
    subdivisionsは ``subdivisionsX/Y/Z`` をまとめた独自の引数のため短縮名は無い。

    Args:
        radius (float): 半径(cm)。既定1。
        height (float): 高さ(cm)。既定2。
        subdivisions (Sequence[int]): 軸のまわり・高さ方向・ふたの分割数(``subdivisionsX/Y/Z``)。既定(20, 1, 1)。
        axis (Sequence[float]): 円柱の軸の方向。0でない有限な3成分。既定(0, 1, 0)。
        name (str | None): Transformの希望名。シェイプは ``<名前>Shape``。NoneはMayaの既定名。既定None。
        parent (Node | str | None): Transformの親。Noneはワールド直下。親のローカル空間に単位マトリクスで置く。
        r (float): radiusの短縮名。同時指定はできない。
        h (float): heightの短縮名。同時指定はできない。
        ax (Sequence[float]): axisの短縮名。同時指定はできない。
        n (str | None): nameの短縮名。同時指定はできない。

    Returns:
        Mesh: 作成したメッシュのシェイプ。Transformは ``getTransform()`` で取得する。

    Raises:
        TypeError: 長名と短縮名を同時に指定した場合、または引数の型が不正な場合。
        ValueError: 大きさが0以下・有限でない、分割数・軸が不正な場合。
        RuntimeError: 親が無効な場合、またはMayaが作成を拒否した場合。
    """
    ...

def _axis(value: Sequence[float]) -> tuple[float, float, float]:
    """軸の方向を検証する。

    Args:
        value (Sequence[float]): 方向。

    Returns:
        tuple[float, float, float]: 検証した方向。

    Raises:
        TypeError: 数値の列でない場合。
        ValueError: 成分数が3でない、有限でない、または0の場合。
    """
    ...
