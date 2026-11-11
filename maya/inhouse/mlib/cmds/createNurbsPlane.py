"""NURBSの平面を作成し、シェイプを返す(``cmds.nurbsPlane(constructionHistory=False)`` 相当)。

幅はMaya APIの内部単位(cm)で、現在のUI単位に依存しない。構築履歴は作らない。
作成・親子付けを1回のUndoにまとめ、現在の選択は変更しない。リボンの元の面などに使う。

.. code-block:: python

    import mlib

    shape = mlib.createNurbsPlane(width=10.0, lengthRatio=0.1, patchesU=5, name="ribbon")
    shape = mlib.createNurbsPlane(w=10.0, lr=0.1, u=5, n="ribbon")  # cmds.nurbsPlane と同じ短縮名
"""

import maya.cmds as cmds

from ..core.shapeBuild import finish_shape, positive_size, require_name, resolve_parent
from ..decorator import _pick_alias, nativeUnits, preservedSelection, undoTransaction
from ..util import _UNSET, _finite_vector


def createNurbsPlane(width=_UNSET, lengthRatio=_UNSET, patchesU=_UNSET, patchesV=_UNSET, axis=_UNSET,
        degree=_UNSET, name=_UNSET, parent=None, *, w=_UNSET, lr=_UNSET, u=_UNSET, v=_UNSET, ax=_UNSET,
        d=_UNSET, n=_UNSET):
    """原点を中心とするNURBSの平面を作成し、そのシェイプを返す。

    fast引数は持たない(OpenMayaで同じノット・CVの面を組み立て直すことになり、同じ結果を保つのが難しいため)。
    parent以外は ``cmds.nurbsPlane`` と同じ短縮名でも受ける(長名と短縮名の同時指定はできない)。
    U方向が幅(width)、V方向が長さ(``width * lengthRatio``)になる。

    Args:
        width (float): 幅(cm)。正の有限値。既定1。
        lengthRatio (float): 幅に対する長さの比。正の有限値。既定1。
        patchesU (int): U方向のパッチ(スパン)数。1以上。既定1。
        patchesV (int): V方向のパッチ(スパン)数。1以上。既定1。
        axis (Sequence[float]): 面の法線。0でない有限な3成分。既定(0, 1, 0)(``cmds.nurbsPlane`` の既定と違い、
            :func:`createPolyPlane <mlib.cmds.createPolyPlane.createPolyPlane>` と同じ上向き)。
        degree (int): U・V方向の次数。1(直線)または3(曲線)。既定3。
        name (str | None): Transformの希望名。シェイプは ``<名前>Shape``。NoneはMayaの既定名(``nurbsPlane1`` 等)。
            既定None。
        parent (Node | str | None): Transformの親。Noneはワールド直下。親のローカル空間に単位マトリクスで置く。
        w (float): widthの短縮名。同時指定はできない。
        lr (float): lengthRatioの短縮名。同時指定はできない。
        u (int): patchesUの短縮名。同時指定はできない。
        v (int): patchesVの短縮名。同時指定はできない。
        ax (Sequence[float]): axisの短縮名。同時指定はできない。
        d (int): degreeの短縮名。同時指定はできない。
        n (str | None): nameの短縮名。同時指定はできない。

    Returns:
        NurbsSurface: 作成した平面のシェイプ。Transformは ``getTransform()`` で取得する。

    Raises:
        TypeError: 長名と短縮名を同時に指定した場合、または引数の型が不正な場合。
        ValueError: 幅・比が0以下・有限でない、パッチ数・軸・次数が不正な場合。
        RuntimeError: 親が無効な場合、またはMayaが作成を拒否した場合。
    """
    width = _pick_alias(width, w, "width", "w", default=1.0)
    lengthRatio = _pick_alias(lengthRatio, lr, "lengthRatio", "lr", default=1.0)
    patchesU = _pick_alias(patchesU, u, "patchesU", "u", default=1)
    patchesV = _pick_alias(patchesV, v, "patchesV", "v", default=1)
    axis = _pick_alias(axis, ax, "axis", "ax", default=(0, 1, 0))
    degree = _pick_alias(degree, d, "degree", "d", default=3)
    name = _pick_alias(name, n, "name", "n", default=None)
    width = positive_size(width, "width")
    lengthRatio = positive_size(lengthRatio, "lengthRatio")
    patchesU = _patch_count(patchesU, "patchesU")
    patchesV = _patch_count(patchesV, "patchesV")
    axis = _finite_vector(axis, 3, "axis")
    if not any(axis):
        raise ValueError("axis must not be zero")
    if isinstance(degree, bool) or not isinstance(degree, int):
        raise TypeError("degree must be an int")
    if degree not in (1, 3):
        raise ValueError("degree must be 1 or 3")
    name = require_name(name)
    parent_node = resolve_parent(parent)
    flags = {"width": width, "lengthRatio": lengthRatio, "patchesU": patchesU, "patchesV": patchesV,
             "axis": tuple(axis), "degree": degree, "constructionHistory": False}
    if name:
        flags["name"] = name
    with undoTransaction("mlibCreateNurbsPlane"), preservedSelection():
        # nurbsPlaneの幅は現在のUI単位で解釈されるため、内部単位(cm)へ切り替えて渡す。
        with nativeUnits():
            transform = cmds.nurbsPlane(**flags)[0]
        return finish_shape(transform, "nurbsSurface", name, parent_node)


def _patch_count(value, name):
    """パッチ数を検証する。

    Args:
        value (int): パッチ数。boolは受け付けない。
        name (str): 例外メッセージに使う引数名。

    Returns:
        int: 検証したパッチ数。

    Raises:
        TypeError: int以外の場合。
        ValueError: 1未満の場合。
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 1:
        raise ValueError(f"{name} must be 1 or more")
    return value
