# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya のデフォーマー(geometryFilter)の共通部分を扱う。"""

import json
import math
from pathlib import Path
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
from ..core.fastWrite import require_range, require_writable, set_attr
from ..core.object import Object
from ..decorator import _edit_context, _require_bool
from .node import Node
from typing import Iterable
from mlib.components.component import Component
from mlib.components.component import Components

_DEFORMER_WEIGHTS_VERSION: int


class GeometryFilter(Node):
    """デフォーマー(cluster・deltaMush・softMod・skinCluster 等)の共通ラッパー。

    Maya の抽象型 ``geometryFilter`` に対応する。頂点ごとの効き具合(デフォーマーのウェイト、
    ``weightList[形状の番号].weights``)の読み書きを提供する。skinCluster では同じアトリビュートが
    インフルエンスのウェイトの置き場なので、:meth:`getDeformerWeights` 等は使えない
    (:meth:`SkinCluster.getWeights <mlib.nodes.skinCluster.SkinCluster.getWeights>` を使う)。
    """
    def getGeometry(self) -> list[Node]:
        """このデフォーマーが変形する形状(出力ジオメトリ)を取得する。

        ``outputGeometry`` の接続先の形状を、``input`` の番号順に返す(``cmds.deformer(query=True, geometry=True)``
        相当)。skinCluster・cluster・deltaMush 等、すべてのデフォーマーで使える。

        Returns:
            list[Node]: 変形する形状。無ければ空リスト。
        """
        ...
    def getDeformerWeights(self, geometryIndex: int = ...) -> list[float]:
        """頂点ごとのデフォーマーのウェイトを取得する。

        値が書かれていない頂点は、Maya の既定どおり 1.0(全部効く)として返す。

        Args:
            geometryIndex (int): 変形する形状の番号(``input``・``weightList`` の論理番号)。既定0。

        Returns:
            list[float]: 形状の頂点(CV・ラティスの点)の番号順の値。長さは形状の点の数。

        Raises:
            TypeError: geometryIndex が int でない、またはデフォーマーのウェイトを持たない型の場合。
            IndexError: geometryIndex の形状が無い場合。
        """
        ...
    def setDeformerWeights(self, weights: Iterable[float], *, vertices: Component | Components | Iterable[int] | None = ..., geometryIndex: int = ..., fast: bool = ...) -> GeometryFilter:
        """頂点ごとのデフォーマーのウェイトを設定する。

        通常は ``cmds.setAttr`` で書き、番号が1ずつ増える頂点は範囲指定の1回の setAttr にまとめる。

        Args:
            weights (Iterable[float]): 書き込む値。vertices と同じ数(None なら形状の点の数)の有限な数値。
            vertices (Component | Components | Iterable[int] | None): 書き込む頂点(点)の番号。None は全頂点。
                重複は不可。指定した順に weights と対応する。
            geometryIndex (int): 変形する形状の番号(``input``・``weightList`` の論理番号)。既定0。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            GeometryFilter: 自身。

        Raises:
            TypeError: fastがbool以外、geometryIndex・値・頂点の型が不正、またはデフォーマーのウェイトを持たない型の場合。
            ValueError: 値の数が頂点の数と合わない、値が有限でない、または頂点が重複している場合。
            IndexError: geometryIndex の形状が無い、または頂点番号が範囲外の場合。
            RuntimeError: アトリビュートがロック・入力接続されている、または Maya が書込みを拒否した場合。
        """
        ...
    def dumpDeformerWeights(self, path: str | Path, geometryIndex: int | None = ...) -> None:
        """頂点ごとのデフォーマーのウェイトを JSON ファイルへ書き出す。

        単純な JSON(UTF-8)で、``version``(形式の版、現在1)・``deformer``(ノード名)・``geometries``(形状ごとの
        ``index``・``numVertices``・``weights``)を書く。値の無い頂点は :meth:`getDeformerWeights` と同じく1.0で書く。

        Args:
            path (str | Path): 書き出し先のファイルパス。
            geometryIndex (int | None): 書き出す形状の番号。Noneは変形する全形状(番号順)。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: geometryIndex が int・None 以外、またはデフォーマーのウェイトを持たない型の場合。
            IndexError: geometryIndex の形状が無い場合。
        """
        ...
    def loadDeformerWeights(self, path: str | Path, *, fast: bool = ...) -> None:
        """:meth:`dumpDeformerWeights` が書き出した JSON ファイルからデフォーマーのウェイトを設定する。

        ファイルの各形状を、形状の番号(``weightList`` の論理番号)と頂点数で照合して書き込む。
        デフォーマー名は照合しない(別のデフォーマーへも読み込める)。全形状を書込みの前に照合し、
        合わなければ何も変更せず ValueError にする。通常は全形状を1回のUndoにまとめる。

        Args:
            path (str | Path): 読み込むファイルパス。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: fastがbool以外、ファイルの値が数値でない、またはデフォーマーのウェイトを持たない型の場合。
            ValueError: ファイルの形式・版が違う、形状の番号がこのデフォーマーに無い、または頂点数が違う場合。
            RuntimeError: アトリビュートがロック・入力接続されている、または Maya が書込みを拒否した場合。
        """
        ...
    def copyDeformerWeightsTo(self, other: GeometryFilter | str, *, geometryIndex: int = ..., otherGeometryIndex: int = ..., fast: bool = ...) -> GeometryFilter:
        """デフォーマーのウェイトを、頂点数が同じ別のデフォーマー(または同じデフォーマーの別の形状)へ写す。

        頂点番号で対応させ、位置での照合はしない。通常は1回のUndoで戻せる。

        Args:
            other (GeometryFilter | str): 写す先のデフォーマー。
            geometryIndex (int): 写す元(自身)の形状の番号。既定0。
            otherGeometryIndex (int): 写す先の形状の番号。既定0。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            GeometryFilter: 写す先のデフォーマー。

        Raises:
            TypeError: fastがbool以外、other がデフォーマーでない、geometryIndex が int でない、
                またはどちらかがデフォーマーのウェイトを持たない型(skinCluster 等)の場合。
            ValueError: 頂点数が違う場合。
            IndexError: 形状の番号の形状が無い場合。
            RuntimeError: other の名前が存在しない、アトリビュートがロック・入力接続されている、
                または Maya が書込みを拒否した場合。
        """
        ...
    def _geometry_indices(self) -> list[int]:
        """変形する形状の番号(``input``・``weightList`` の論理番号)を昇順で返す。

        Returns:
            list[int]: 番号。

        Raises:
            TypeError: デフォーマーのウェイトを持たない型の場合。
        """
        ...
    def _deformer_weight_plug(self, geometry_index: int) -> tuple[om2.MPlug, int]:
        """``weightList[geometry_index].weights`` の Plug と、形状の点の数を返す。

        Args:
            geometry_index (int): 変形する形状の番号。

        Returns:
            tuple[om2.MPlug, int]: weights のマルチアトリビュートの Plug と点の数。

        Raises:
            TypeError: geometry_index が int でない、またはデフォーマーのウェイトを持たない型の場合。
            IndexError: 形状が無い場合。
        """
        ...
    @staticmethod
    def _resolve_point_indices(vertices: Component | Components | Iterable[int], count: int) -> list[int]:
        """頂点の指定を、範囲内で重複の無い番号の list にする。

        Args:
            vertices (Component | Components | Iterable[int]): 頂点・点の参照または番号。
            count (int): 形状の点の数。

        Returns:
            list[int]: 指定順の番号。

        Raises:
            TypeError: 番号に変換できない型の場合。
            ValueError: 番号が重複している場合。
            IndexError: 番号が範囲外の場合。
        """
        ...
    @staticmethod
    def _resolve_weight_values(weights: Iterable[float], count: int) -> list[float]:
        """書き込む値を、有限な float の list にする。

        Args:
            weights (Iterable[float]): 値。
            count (int): 必要な数。

        Returns:
            list[float]: 値。

        Raises:
            TypeError: 数値でない値がある場合。
            ValueError: 数が合わない、または有限でない値がある場合。
        """
        ...
    def _set_deformer_weights_fast(self, plug: om2.MPlug, indices: list[int], values: list[float]) -> None:
        """全要素の書込み可否と範囲を先に調べてから、OpenMaya で書き込む。

        Args:
            plug (om2.MPlug): ``weightList[g].weights`` の Plug。
            indices (list[int]): 頂点番号。
            values (list[float]): 値。

        Returns:
            None: 値を返さない。
        """
        ...
    def _set_deformer_weights_cmds(self, geometry_index: int, indices: list[int], values: list[float]) -> None:
        """番号が1ずつ増える頂点を範囲にまとめ、cmds で書き込む。

        Args:
            geometry_index (int): 変形する形状の番号。
            indices (list[int]): 頂点番号。
            values (list[float]): 値。

        Returns:
            None: 値を返さない。
        """
        ...
