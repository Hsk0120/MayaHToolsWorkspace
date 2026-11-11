"""NURBSの円を作成し、シェイプを返す(``cmds.circle(constructionHistory=False)`` 相当)。

半径はMaya APIの内部単位(cm)で、現在のUI単位に依存しない。構築履歴は作らない。
作成・親子付けを1回のUndoにまとめ、現在の選択は変更しない。

.. code-block:: python

    import mlib

    shape = mlib.createCircle(radius=2.0, normal=(0, 1, 0), name="ring")
    shape = mlib.createCircle(r=2.0, nr=(0, 1, 0), n="ring")  # cmds.circle と同じ短縮名
"""

import maya.cmds as cmds

from ..core.shapeBuild import finish_shape, require_name, resolve_parent
from ..decorator import _pick_alias, nativeUnits, preservedSelection, undoTransaction
from ..util import _UNSET, _finite, _finite_vector


def createCircle(radius=_UNSET, normal=_UNSET, sections=_UNSET, degree=_UNSET, name=_UNSET, parent=None, *,
        r=_UNSET, nr=_UNSET, s=_UNSET, d=_UNSET, n=_UNSET):
    """原点を中心とするNURBSの円を作成し、そのシェイプを返す。

    fast引数は持たない(OpenMayaに円の作成の同等機能が無いため)。
    parent以外は ``cmds.circle`` と同じ短縮名でも受ける(長名と短縮名の同時指定はできない)。

    Args:
        radius (float): 半径(cm)。正の有限値。既定1。
        normal (Sequence[float]): 円の面の法線。0でない有限な3成分。既定(0, 0, 1)。
        sections (int): 区間数。degree=1は3以上、degree=3は4以上。既定8。
        degree (int): 1(直線)または3(曲線)。既定3。
        name (str | None): Transformの希望名。シェイプは ``<名前>Shape``。NoneはMayaの既定名(``nurbsCircle1`` 等)。
            既定None。
        parent (Node | str | None): Transformの親。Noneはワールド直下。親のローカル空間に単位マトリクスで置く。
        r (float): radiusの短縮名。同時指定はできない。
        nr (Sequence[float]): normalの短縮名。同時指定はできない。
        s (int): sectionsの短縮名。同時指定はできない。
        d (int): degreeの短縮名。同時指定はできない。
        n (str | None): nameの短縮名。同時指定はできない。

    Returns:
        NurbsCurve: 作成した円のシェイプ。Transformは ``getTransform()`` で取得する。

    Raises:
        TypeError: 長名と短縮名を同時に指定した場合、または引数の型が不正な場合。
        ValueError: 半径・法線・区間数・次数が不正な場合。
        RuntimeError: 親が無効な場合、またはMayaが作成を拒否した場合。
    """
    radius = _pick_alias(radius, r, "radius", "r", default=1.0)
    normal = _pick_alias(normal, nr, "normal", "nr", default=(0, 0, 1))
    sections = _pick_alias(sections, s, "sections", "s", default=8)
    degree = _pick_alias(degree, d, "degree", "d", default=3)
    name = _pick_alias(name, n, "name", "n", default=None)
    radius = _finite(radius, "radius")
    if radius <= 0:
        raise ValueError("radius must be positive")
    normal = _finite_vector(normal, 3, "normal")
    if not any(normal):
        raise ValueError("normal must not be zero")
    if isinstance(degree, bool) or degree not in (1, 3):
        raise ValueError("degree must be 1 or 3")
    if isinstance(sections, bool) or not isinstance(sections, int):
        raise TypeError("sections must be an int")
    if sections < (3 if degree == 1 else 4):
        raise ValueError(f"sections must be at least {3 if degree == 1 else 4} for degree {degree}")
    name = require_name(name)
    parent_node = resolve_parent(parent)
    flags = {"radius": radius, "normal": tuple(normal), "sections": sections, "degree": degree,
             "constructionHistory": False}
    if name:
        flags["name"] = name
    with undoTransaction("mlibCreateCircle"), preservedSelection():
        with nativeUnits():
            transform = cmds.circle(**flags)[0]
        return finish_shape(transform, "nurbsCurve", name, parent_node)
