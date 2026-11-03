"""Maya のデフォーマー(geometryFilter)の共通部分を扱う。"""

import math

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2

from ..core.fastWrite import require_range, require_writable, set_attr
from ..decorator import _edit_context, _require_bool
from .node import Node


class GeometryFilter(Node):
    """デフォーマー(cluster・deltaMush・softMod・skinCluster 等)の共通ラッパー。

    Maya の抽象型 ``geometryFilter`` に対応する。頂点ごとの効き具合(デフォーマーのウェイト、
    ``weightList[形状の番号].weights``)の読み書きを提供する。skinCluster では同じアトリビュートが
    インフルエンスのウェイトの置き場なので、:meth:`getDeformerWeights` 等は使えない
    (:meth:`SkinCluster.getWeights <mlib.nodes.skinCluster.SkinCluster.getWeights>` を使う)。
    """

    def getDeformerWeights(self, geometryIndex=0):
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
        plug, count = self._deformer_weight_plug(geometryIndex)
        values = [1.0] * count
        for index in plug.getExistingArrayAttributeIndices():
            if index < count:
                values[index] = plug.elementByLogicalIndex(index).asFloat()
        return values

    def setDeformerWeights(self, weights, *, vertices=None, geometryIndex=0, fast=False):
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
        with _edit_context("mlibGeometryFilterSetDeformerWeights", fast):
            plug, count = self._deformer_weight_plug(geometryIndex)
            indices = list(range(count)) if vertices is None else self._resolve_point_indices(vertices, count)
            values = self._resolve_weight_values(weights, len(indices))
            if fast:
                self._set_deformer_weights_fast(plug, indices, values)
            else:
                self._set_deformer_weights_cmds(geometryIndex, indices, values)
            return self

    def _deformer_weight_plug(self, geometry_index):
        """``weightList[geometry_index].weights`` の Plug と、形状の点の数を返す。

        Args:
            geometry_index (int): 変形する形状の番号。

        Returns:
            tuple[om2.MPlug, int]: weights のマルチアトリビュートの Plug と点の数。

        Raises:
            TypeError: geometry_index が int でない、またはデフォーマーのウェイトを持たない型の場合。
            IndexError: 形状が無い場合。
        """
        if isinstance(geometry_index, bool) or not isinstance(geometry_index, int):
            raise TypeError(f"geometryIndex must be an int, got {type(geometry_index).__name__}")
        if self.isType("skinCluster") or not self.hasAttr("weightList"):
            raise TypeError(f"{self.getType()} has no deformer weights: {self.getFullName()}")
        try:
            shape = oma2.MFnGeometryFilter(self.mnode()).outputShapeAtIndex(geometry_index)
        except RuntimeError:
            raise IndexError(f"No geometry at index {geometry_index}: {self.getFullName()}") from None
        count = om2.MItGeometry(om2.MDagPath.getAPathTo(shape)).exactCount()
        weight_list = self._dependency_fn().findPlug("weightList", False)
        return weight_list.elementByLogicalIndex(geometry_index).child(0), count

    @staticmethod
    def _resolve_point_indices(vertices, count):
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
        if hasattr(vertices, "indices"):
            vertices = vertices.indices
        elif isinstance(getattr(vertices, "index", None), int):
            vertices = [vertices.index]
        indices = []
        for value in vertices:
            if not isinstance(value, int) and isinstance(getattr(value, "index", None), int):
                value = value.index
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"vertex must be an int, got {type(value).__name__}")
            if not 0 <= value < count:
                raise IndexError(f"Vertex index out of range: {value}")
            indices.append(value)
        if len(set(indices)) != len(indices):
            raise ValueError("vertices must not contain duplicates")
        return indices

    @staticmethod
    def _resolve_weight_values(weights, count):
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
        values = []
        for value in weights:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"weight must be a number, got {type(value).__name__}")
            if not math.isfinite(value):
                raise ValueError(f"weight must be finite, got {value}")
            values.append(float(value))
        if len(values) != count:
            raise ValueError(f"Expected {count} weights, got {len(values)}")
        return values

    def _set_deformer_weights_fast(self, plug, indices, values):
        """全要素の書込み可否と範囲を先に調べてから、OpenMaya で書き込む。

        Args:
            plug (om2.MPlug): ``weightList[g].weights`` の Plug。
            indices (list[int]): 頂点番号。
            values (list[float]): 値。

        Returns:
            None: 値を返さない。
        """
        edits = []
        for index, value in zip(indices, values):
            element = plug.elementByLogicalIndex(index)
            require_writable(element)
            require_range(element, value)
            edits.append((element, value))
        for element, value in edits:
            element.setFloat(value)

    def _set_deformer_weights_cmds(self, geometry_index, indices, values):
        """番号が1ずつ増える頂点を範囲にまとめ、cmds で書き込む。

        Args:
            geometry_index (int): 変形する形状の番号。
            indices (list[int]): 頂点番号。
            values (list[float]): 値。

        Returns:
            None: 値を返さない。
        """
        prefix = f"{self.getFullName()}.weightList[{geometry_index}].weights"
        start = 0
        while start < len(indices):
            end = start + 1
            while end < len(indices) and indices[end] == indices[end - 1] + 1:
                end += 1
            if end - start == 1:
                set_attr(f"{prefix}[{indices[start]}]", values[start])
            else:
                set_attr(f"{prefix}[{indices[start]}:{indices[end - 1]}]", *values[start:end])
            start = end
