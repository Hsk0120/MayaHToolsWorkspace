"""形状をカーブで変形するwireデフォーマーを作成し、wireを返す(``cmds.wire`` 相当)。

カーブを動かすと、近くの頂点がカーブに沿って動く。作成を1回のUndoにまとめ、現在の選択は変更しない。

.. code-block:: python

    import mlib

    wire = mlib.createWire("brow_geo", "brow_crv", dropoffDistance=3.0, name="brow_wire")
"""

import math

import maya.cmds as cmds

from ..core.object import Object
from ..core.shapeBuild import require_name
from ..decorator import _pick_alias, preservedSelection, undoChunk
from ..util import _UNSET


def createWire(targets, curves, name=_UNSET, dropoffDistance=_UNSET, *, n=_UNSET, dds=_UNSET):
    """形状またはコンポーネントに、カーブで変形するwireデフォーマーを作成する。

    選択状態は参照しない。カーブごとに基準のカーブ(``<カーブ名>BaseWire``)をMayaが作る。
    fast引数は持たない(OpenMayaにデフォーマー作成の同等機能が無い)。Undo有効時は1回で戻せる。
    name・dropoffDistanceは ``cmds.wire`` と同じ短縮名 ``n``・``dds`` でも受ける(長名と短縮名の同時指定はできない)。

    Args:
        targets (str | Node | Component | Iterable): 変形する形状・そのtransform・コンポーネント。
        curves (str | Node | Iterable[str | Node]): 変形に使うnurbsCurveまたはそのtransform。``cmds.wire`` の
            ``wire`` フラグに渡す。
        name (str | None): wireの作成名。NoneはMayaの既定名。既定None。
        dropoffDistance (float | None): カーブからの影響が届く距離(cm)。0より大きい有限値で、全カーブに
            同じ値を設定する。NoneはMayaの既定。既定None。
        n (str | None): nameの短縮名。同時指定はできない。
        dds (float | None): dropoffDistanceの短縮名。同時指定はできない。

    Returns:
        GeometryFilter: 作成したwireデフォーマー。実際の型はMayaの ``wire`` 型に対応する生成クラス(``mlib.nodes.Wire``)。

    Raises:
        TypeError: 長名と短縮名を同時に指定した場合、dropoffDistanceが数値・None以外、nameが文字列・None以外、
            または対象・カーブが対応しない型の場合。
        ValueError: nameが空文字列・``|`` を含む、dropoffDistanceが0以下・非有限、または対象・カーブが空・無効な場合。
        RuntimeError: 名前を解決できない、またはMayaが作成を拒否した場合。

    Examples:
        .. code-block:: python

            wire = mlib.createWire(face.getVertices(range(40)), ["lip_upper_crv", "lip_lower_crv"], dds=2.0)
    """
    # nodes はcmdsを参照するため、循環importを避けて関数内で読み込む。
    from ..nodes.node import Node

    name = require_name(_pick_alias(name, n, "name", "n", default=None))
    dropoffDistance = _pick_alias(dropoffDistance, dds, "dropoffDistance", "dds", default=None)
    if dropoffDistance is not None:
        if isinstance(dropoffDistance, bool) or not isinstance(dropoffDistance, (int, float)):
            raise TypeError(f"dropoffDistance must be a number or None, got {type(dropoffDistance).__name__}")
        if not math.isfinite(dropoffDistance) or dropoffDistance <= 0.0:
            raise ValueError(f"dropoffDistance must be a finite positive number, got {dropoffDistance}")
    target_names = Object._input_names(targets, allow_plugs=False)
    if not target_names:
        raise ValueError("At least one target is required")
    curve_names = Object._input_names(curves, allow_plugs=False)
    if not curve_names:
        raise ValueError("At least one curve is required")
    flags = {"wire": curve_names}
    if name is not None:
        flags["name"] = name
    if dropoffDistance is not None:
        flags["dropoffDistance"] = [(index, float(dropoffDistance)) for index in range(len(curve_names))]
    with undoChunk("mlibCreateWire"), preservedSelection():
        result = cmds.wire(*target_names, **flags)
        return Node(result[0])
