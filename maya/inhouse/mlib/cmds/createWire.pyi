# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
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
from typing import Iterable
from mlib.components.component import Component
from mlib.nodes.geometryFilter import GeometryFilter
from mlib.nodes.node import Node


def createWire(targets: str | Node | Component | Iterable, curves: str | Node | Iterable[str | Node], name: str | None = ..., dropoffDistance: float | None = ..., *, n: str | None = ..., dds: float | None = ...) -> GeometryFilter:
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
    ...
