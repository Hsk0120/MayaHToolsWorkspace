"""形状・コンポーネントにラティス(ffdデフォーマー)を作成し、ffdを返す(``cmds.lattice`` 相当)。

ラティスの形状は ``deformedLatticePoints`` の入力元、基準のラティスは ``baseLatticeMatrix`` の入力元に
つながる。作成を1回のUndoにまとめ、現在の選択は変更しない。

.. code-block:: python

    import mlib

    ffd = mlib.createLattice("head_geo", divisions=(3, 4, 3), name="head_ffd")
    lattice = ffd.getPlug("deformedLatticePoints").getSource().getNode()
"""

import maya.cmds as cmds

from ..core.object import Object
from ..core.shapeBuild import require_name
from ..decorator import _pick_alias, _require_bool, preservedSelection, undoChunk
from ..util import _UNSET


def _divisions(value, name, minimum):
    """3つの整数の分割数を検証する。

    Args:
        value (Sequence[int]): S・T・U方向の分割数。
        name (str): 例外メッセージに使う引数名。
        minimum (int): 各値の下限。

    Returns:
        tuple[int, int, int]: 検証した分割数。

    Raises:
        TypeError: 並びでない、または値がint以外(boolを含む)の場合。
        ValueError: 値の数が3でない、または下限未満の場合。
    """
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be a sequence of 3 ints")
    try:
        values = tuple(value)
    except TypeError:
        raise TypeError(f"{name} must be a sequence of 3 ints, got {type(value).__name__}") from None
    if len(values) != 3:
        raise ValueError(f"{name} must have 3 values, got {len(values)}")
    for item in values:
        if isinstance(item, bool) or not isinstance(item, int):
            raise TypeError(f"{name} must contain ints, got {type(item).__name__}")
        if item < minimum:
            raise ValueError(f"{name} values must be {minimum} or greater, got {item}")
    return values


def createLattice(targets, name=_UNSET, divisions=_UNSET, ldivisions=_UNSET, objectCentered=_UNSET, *, n=_UNSET,
                  dv=_UNSET, ldv=_UNSET, oc=_UNSET):
    """形状またはコンポーネントにラティスを作成し、ffdデフォーマーを返す。

    選択状態は参照しない。ラティスは対象を囲む大きさで作る。fast引数は持たない
    (OpenMayaにデフォーマー作成の同等機能が無い)。Undo有効時は1回で戻せる。
    name・divisions・ldivisions・objectCenteredは ``cmds.lattice`` と同じ短縮名 ``n``・``dv``・``ldv``・``oc``
    でも受ける(長名と短縮名の同時指定はできない)。

    Args:
        targets (str | Node | Component | Iterable): 変形する形状・そのtransform・コンポーネント。
        name (str | None): ffdの作成名。ラティスは ``<名前>Lattice``、基準は ``<名前>Base``。
            NoneはMayaの既定名。既定None。
        divisions (Sequence[int]): ラティスのS・T・U方向の点の数。各2以上。既定(2, 5, 2)。
        ldivisions (Sequence[int]): 変形の計算に使う局所の分割数。各1以上。既定(2, 2, 2)。
        objectCentered (bool): Trueは対象の中心に置く。Falseは原点に置く。既定True。
        n (str | None): nameの短縮名。同時指定はできない。
        dv (Sequence[int]): divisionsの短縮名。同時指定はできない。
        ldv (Sequence[int]): ldivisionsの短縮名。同時指定はできない。
        oc (bool): objectCenteredの短縮名。同時指定はできない。

    Returns:
        GeometryFilter: 作成したffdデフォーマー。実際の型はMayaの ``ffd`` 型に対応する生成クラス(``mlib.nodes.Ffd``)。

    Raises:
        TypeError: 長名と短縮名を同時に指定した場合、または引数の型が不正な場合。
        ValueError: nameが空文字列・``|`` を含む、分割数の数・値が不正、または対象が空・無効な場合。
        RuntimeError: 名前を解決できない、またはMayaが作成を拒否した場合。

    Examples:
        .. code-block:: python

            ffd = mlib.createLattice(["arm_geo", "hand_geo"], dv=(2, 6, 2), oc=True)
            base = ffd.getPlug("baseLatticeMatrix").getSource().getNode()
    """
    # nodes はcmdsを参照するため、循環importを避けて関数内で読み込む。
    from ..nodes.node import Node

    name = require_name(_pick_alias(name, n, "name", "n", default=None))
    divisions = _divisions(_pick_alias(divisions, dv, "divisions", "dv", default=(2, 5, 2)), "divisions", 2)
    ldivisions = _divisions(_pick_alias(ldivisions, ldv, "ldivisions", "ldv", default=(2, 2, 2)), "ldivisions", 1)
    objectCentered = _pick_alias(objectCentered, oc, "objectCentered", "oc", default=True)
    _require_bool(objectCentered, "objectCentered")
    target_names = Object._input_names(targets, allow_plugs=False)
    if not target_names:
        raise ValueError("At least one target is required")
    flags = {"divisions": divisions, "ldivisions": ldivisions, "objectCentered": objectCentered}
    if name is not None:
        flags["name"] = name
    with undoChunk("mlibCreateLattice"), preservedSelection():
        result = cmds.lattice(*target_names, **flags)
        return Node(result[0])
