"""Mesh の現在の UV セットを参照する UV 型。"""

import numbers

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorator import _edit_context, _require_bool
from ..util import _finite, _finite_vector
from .component import Component, Components


class UV(Component):
    """Mesh参照とUV番号を保持し、現在のUVセットのU/V座標を照会・編集する。

    UVセット名は固定して保持しない。切替後は同じ番号で切替先のセットを参照する。
    U/Vは無次元で、0〜1に制限しない。書込みは通常 ``cmds.polyEditUV`` で1回のUndoにまとめ、
    ``fast=True`` は ``MFnMesh.setUV`` / ``setUVs`` で書き込んでUndoに記録しない。
    """

    shape_type = "mesh"
    component_type = "map"
    count_attribute = "getNumUVs"

    def getPosition(self):
        """現在のUVセットから、保持番号のU/V座標を取得する。

        Returns:
            tuple[float, float]: 新しい無次元の(U, V)値。UI距離単位やobject/ワールド空間とは無関係。

        Raises:
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshまたは現在のUVセットを参照できない場合。
        """
        self._require_valid()
        mesh_fn = self.shape._geometry_fn()
        return tuple(mesh_fn.getUV(self._index, uvSet=mesh_fn.currentUVSetName()))

    def setPosition(self, value, *, fast=False):
        """現在のUVセットの保持番号へ、絶対U/V座標を設定する。移動量ではない。

        通常は ``cmds.polyEditUV(relative=False)`` で書き込み、1回のUndoにまとめる。
        ``fast=True`` は ``MFnMesh.setUV`` で書き込み、Undoに記録しない(1点で約5倍速い)。

        Args:
            value (Iterable[float]): 有限なU/Vの2成分。無次元で0〜1に限定しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UV: 自身。UVセットや割当ては作成しない。

        Raises:
            TypeError: fastがbool以外、または座標の型が不正な場合。
            ValueError: 座標が2成分の有限値でない場合。
            IndexError: 番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力(コンストラクションヒストリ)がある場合。
        """
        _require_bool(fast, "fast")
        row = _uv_value(value)
        self._require_valid()
        _write_uvs(self.shape, [self._index], [row], fast, "setPosition", "mlibUVSetPosition")
        return self

    def getU(self):
        """U成分の現在値を取得する。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(0)

    def setU(self, value, *, fast=False):
        """U成分だけを設定し、Vは現在値を保つ。

        Args:
            value (float): 有限なU。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UV: 自身。

        Raises:
            TypeError: fastがbool以外、またはvalueが数値でない場合。
            ValueError: valueが有限でない場合。
            IndexError: 番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力がある場合。
        """
        return self._set_coordinate(0, value, fast, "setU", "mlibUVSetU")

    def getV(self):
        """V成分の現在値を取得する。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(1)

    def setV(self, value, *, fast=False):
        """V成分だけを設定し、Uは現在値を保つ。

        Args:
            value (float): 有限なV。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UV: 自身。

        Raises:
            TypeError: fastがbool以外、またはvalueが数値でない場合。
            ValueError: valueが有限でない場合。
            IndexError: 番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力がある場合。
        """
        return self._set_coordinate(1, value, fast, "setV", "mlibUVSetV")

    def getVertex(self):
        """このUVが割り当てられた頂点を取得する(現在のUVセット)。

        Returns:
            Vertex | None: 頂点。どのフェースにも割り当てられていないUVはNone。

        Raises:
            IndexError: 番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshまたは現在のUVセットを参照できない場合。
        """
        # vertex.py が uv.py を import するため、循環を避けて呼出し時に読む。
        from .vertex import Vertex
        self._require_valid()
        mesh_fn = self.shape._geometry_fn()
        uv_counts, uv_ids = mesh_fn.getAssignedUVs(mesh_fn.currentUVSetName())
        counts, vertices = mesh_fn.getVertices()
        uv_offset = vertex_offset = 0
        for uv_count, count in zip(uv_counts, counts):
            # UVの無いフェースは uv_count が0で、uv_ids に項目を持たない。
            for local in range(uv_count):
                if uv_ids[uv_offset + local] == self._index:
                    return Vertex(self.shape, vertices[vertex_offset + local])
            uv_offset += uv_count
            vertex_offset += count
        return None

    def _set_coordinate(self, axis, value, fast, method, chunk):
        """1成分だけを書き換えたU/Vを書き込む。

        Args:
            axis (int): 成分番号(0=U、1=V)。
            value (float): 設定する値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
            method (str): 例外の文言に使う公開メソッド名。
            chunk (str): Undoチャンク名。

        Returns:
            UV: 自身。
        """
        _require_bool(fast, "fast")
        number = _finite(value, "value")
        row = list(self.getPosition())
        row[axis] = number
        _write_uvs(self.shape, [self._index], [tuple(row)], fast, method, chunk)
        return self


_UV_GET_POSITION = UV.getPosition


class UVs(Components):
    """同一MeshのUV番号列を保持し、現在のUVセットの座標を保持順に照会・一括編集する。

    セット名や座標値は保持せず、セット切替後は切替先の同じ番号を使う。
    setPositionは同じU/Vを全要素へ、setPositionsは保持番号ごとに異なる行を設定する。
    書込みは入力をすべて検証してから行う。通常は ``cmds.polyEditUV`` をUVごとに呼んで1回のUndoに
    まとめ(Mayaが途中で拒否した場合は先に書いたUVを戻す)、``fast=True`` は ``MFnMesh.setUVs`` で
    全UVを1回で書き込んでUndoに記録しない。
    """

    component_class = UV

    def getU(self):
        """U成分の現在値を取得する。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(0)

    def setU(self, value, *, fast=False):
        """U成分だけを設定し、Vは現在値を保つ。

        Args:
            value (float | Iterable[float]): 全要素に共通の値、または保持順の値列。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UVs: 自身。

        Raises:
            TypeError: fastがbool以外、または値の型が不正な場合。
            ValueError: 値が有限でない、または値列の件数が保持数と違う場合。
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力がある場合。
        """
        return self._set_coordinates(0, value, fast, "setU", "mlibUVsSetU")

    def getV(self):
        """V成分の現在値を取得する。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(1)

    def setV(self, value, *, fast=False):
        """V成分だけを設定し、Uは現在値を保つ。

        Args:
            value (float | Iterable[float]): 全要素に共通の値、または保持順の値列。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UVs: 自身。

        Raises:
            TypeError: fastがbool以外、または値の型が不正な場合。
            ValueError: 値が有限でない、または値列の件数が保持数と違う場合。
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力がある場合。
        """
        return self._set_coordinates(1, value, fast, "setV", "mlibUVsSetV")

    def getPosition(self):
        """現在のUVセットのU/V座標を、保持番号の順に取得する。

        標準実装は同じMFnMeshと現在UVセット名を使って各番号を問い合わせる。
        単数参照や反復が拡張されている場合は、各要素のgetPositionへ委譲する。

        Returns:
            list[tuple[float, float]]: 新しい無次元のU/V値リスト。座標への書換え可能な参照ではない。
                標準実装の空集合は、Shapeを再照会せず空リストを返す。

        Raises:
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshまたは現在のUVセットを参照できない場合。
        """
        if not (self._uses_standard_iteration(UV) and UV.getPosition is _UV_GET_POSITION):
            return [item.getPosition() for item in self]
        if not self._indices:
            return []
        Component._validate_shape(self._shape, UV.shape_type)
        mesh_fn = self._shape._geometry_fn()
        count = mesh_fn.numUVs()
        uv_set = mesh_fn.currentUVSetName()
        result = []
        for index in self._indices:
            Component._require_index_range(index, count)
            result.append(tuple(mesh_fn.getUV(index, uvSet=uv_set)))
        return result

    def setPosition(self, value, *, fast=False):
        """保持する全UVを、現在のUVセットで同じ絶対U/V座標へ集める。

        要素ごとに違う座標は :meth:`setPositions` を使う。

        Args:
            value (Iterable[float]): 全要素に共通の有限なU/V。無次元。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UVs: 自身。空集合は入力だけを検証して何もしない。

        Raises:
            TypeError: fastがbool以外、または座標の型が不正な場合。
            ValueError: 座標が2成分の有限値でない場合。
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力がある場合。
        """
        _require_bool(fast, "fast")
        row = _uv_value(value)
        return self._write([row] * len(self._indices), fast, "setPosition", "mlibUVsSetPosition")

    def setPositions(self, values, *, fast=False):
        """現在のUVセットへ、保持番号の順に絶対(U, V)を設定する。

        件数・有限値・現在の番号範囲を先にすべて検証し、問題があればシーンを変更しない。
        通常は ``cmds.polyEditUV`` をUVごとに呼ぶ(目安は1UVあたり約1ms)。``fast=True`` は
        ``MFnMesh.setUVs`` で全UVを1回で書き込む。

        Args:
            values (Iterable[Iterable[float]]): 保持番号と同じ件数の有限な(U, V)。無次元。
                :meth:`getPosition` の結果をそのまま受け付ける。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UVs: 自身。空集合と空列はShapeを再照会せず何もしない。

        Raises:
            TypeError: fastがbool以外、または座標の型が不正な場合。
            ValueError: 件数が保持数と違う、または座標が2成分の有限値でない場合。
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshが無効・ロックされている、またはMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力がある場合。

        Note:
            UVセット・割当ての作成は行わない。
        """
        _require_bool(fast, "fast")
        if isinstance(values, (str, bytes)):
            raise TypeError("values must be an iterable of (u, v) pairs")
        try:
            items = list(values)
        except TypeError:
            raise TypeError("values must be an iterable of (u, v) pairs") from None
        rows = [_uv_value(item) for item in items]
        if len(rows) != len(self._indices):
            raise ValueError(f"Expected {len(self._indices)} UVs, got {len(rows)}")
        return self._write(rows, fast, "setPositions", "mlibUVsSetPositions")

    def _set_coordinates(self, axis, value, fast, method, chunk):
        """保持順の1成分だけを書き換えたU/Vを書き込む。

        Args:
            axis (int): 成分番号(0=U、1=V)。
            value (float | Iterable[float]): 共通の値または保持順の値列。
            fast (bool): TrueはUndoなしのOpenMaya更新。
            method (str): 例外の文言に使う公開メソッド名。
            chunk (str): Undoチャンク名。

        Returns:
            UVs: 自身。
        """
        _require_bool(fast, "fast")
        values = _axis_values(value, len(self._indices))
        if not self._indices:
            return self
        rows = []
        for row, number in zip(self.getPosition(), values):
            row = list(row)
            row[axis] = number
            rows.append(tuple(row))
        return self._write(rows, fast, method, chunk)

    def _write(self, rows, fast, method, chunk):
        """検証済みのU/V行を、番号範囲を確かめてから書き込む。

        Args:
            rows (list[tuple[float, float]]): 保持順のU/V。
            fast (bool): TrueはUndoなしのOpenMaya更新。
            method (str): 例外の文言に使う公開メソッド名。
            chunk (str): Undoチャンク名。

        Returns:
            UVs: 自身。
        """
        if not self._indices:
            return self
        self._require_valid()
        _write_uvs(self._shape, list(self._indices), rows, fast, method, chunk)
        return self


def _uv_value(value):
    """1つのU/Vを検証し、floatのtupleへ変換する。

    Args:
        value (Iterable[float]): U/Vの2成分。

    Returns:
        tuple[float, float]: 変換済みのU/V。

    Raises:
        TypeError: 反復できない、文字列、または成分が数値でない場合。
        ValueError: 2成分でない、または有限でない場合。
    """
    if isinstance(value, (str, bytes)):
        raise TypeError("uv must be a sequence of 2 numbers")
    return _finite_vector(value, 2, "uv")


def _axis_values(value, count):
    """1成分の値を、共通のスカラーまたは保持順の値列として検証する。

    Args:
        value (float | Iterable[float]): 共通の値、または件数countの値列。
        count (int): 保持している要素数。

    Returns:
        list[float]: 件数countの有限な値。

    Raises:
        TypeError: 数値・数値の列でない場合(文字列を含む)。
        ValueError: 有限でない、または値列の件数がcountと違う場合。
    """
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return [_finite(value, "value")] * count
    if isinstance(value, (str, bytes)):
        raise TypeError("value must be a number or a sequence of numbers")
    try:
        items = list(value)
    except TypeError:
        raise TypeError("value must be a number or a sequence of numbers") from None
    if len(items) != count:
        raise ValueError(f"Expected {count} values, got {len(items)}")
    return [_finite(item, "value") for item in items]


def _write_uvs(shape, indices, rows, fast, method, chunk):
    """検証済みのU/Vを、現在のUVセットへ書き込む。

    Args:
        shape (Mesh): 対象のMesh。番号は検証済み。
        indices (list[int]): UV番号。
        rows (list[tuple[float, float]]): 番号と同じ件数のU/V。
        fast (bool): TrueはUndoなしのOpenMaya更新。
        method (str): 例外の文言に使う公開メソッド名。
        chunk (str): 通常経路のUndoチャンク名。

    Raises:
        RuntimeError: Meshがロックされている、またはMayaが書込みを拒否した場合。
        NotImplementedError: fastで、inMeshへの入力がある場合。
    """
    path = shape.mpath()
    dependency = om2.MFnDependencyNode(path.node())
    if dependency.isLocked:
        raise RuntimeError(f"Mesh is locked: {shape.getFullName()}")
    if fast and dependency.findPlug("inMesh", False).isDestination:
        # 入力履歴のあるMeshはinMeshの再評価でUVが上書きされるため、直接は書かない。
        raise NotImplementedError(f"fast {method} does not support a mesh with input history: {shape.getFullName()}")
    mesh_fn = om2.MFnMesh(path)
    uv_set = mesh_fn.currentUVSetName()
    # polyEditUVの途中でMayaが書込みを拒否した場合に、先に書いたUVを戻すためundoTransactionを使う。
    with _edit_context(chunk, fast, transaction=True):
        if fast:
            _write_uvs_fast(mesh_fn, uv_set, indices, rows)
            return
        name = shape.getFullName()
        for index, (u, v) in zip(indices, rows):
            cmds.polyEditUV(f"{name}.map[{index}]", relative=False, uValue=u, vValue=v, uvSetName=uv_set)


def _write_uvs_fast(mesh_fn, uv_set, indices, rows):
    """U/VをOpenMayaで書き込む。1点は ``setUV``、複数は全UVを ``setUVs`` で1回に書く。

    Args:
        mesh_fn (om2.MFnMesh): 対象のMeshの関数セット。
        uv_set (str): 書き込むUVセット名。
        indices (list[int]): UV番号。重複は後の値を優先する。
        rows (list[tuple[float, float]]): 番号と同じ件数のU/V。
    """
    if len(indices) == 1:
        mesh_fn.setUV(indices[0], rows[0][0], rows[0][1], uv_set)
        return
    us, vs = mesh_fn.getUVs(uv_set)
    for index, (u, v) in zip(indices, rows):
        us[index] = u
        vs[index] = v
    mesh_fn.setUVs(us, vs, uv_set)
