"""Mesh の現在の UV セットを参照する UV 型。"""

from contextlib import nullcontext

import maya.cmds as cmds

from ..core import geometryEdit as geometry_edit
from ..decorator import _require_bool, undoChunk
from .component import Component, Components


class UV(Component):
    """Mesh参照とUV番号を保持し、現在のUVセットのU/V座標を照会・編集する。

    UVセット名は固定して保持しない。切替後は同じ番号で切替先のセットを参照する。
    U/Vは無次元で、0〜1に制限しない。
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
        """現在のUVセットの保持番号へ、絶対U/V座標を設定する。

        通常はpolyEditUV(relative=False)で更新する。fastはinMesh入力とShapeロックを検査して
        UV配列を直接設定するが、個々のUV-set Plugの書込み可否は全件検査しない。

        Args:
            value (Iterable[float]): 有限なU/Vの2成分。無次元で0〜1に限定しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UV: 自身。UVセットや割当ては作成しない。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 座標が不正な場合。
            IndexError: 番号が現在のUVセットの範囲外の場合。
            RuntimeError: 対象を参照できない、またはMayaが更新を拒否した場合。
            NotImplementedError: fastでinMesh入力付きShapeを編集する場合。

        Note:
            API更新中の失敗で完了済みの変更は自動で戻さない。
        """
        _require_bool(fast, "fast")
        with nullcontext() if fast else undoChunk("mlibUVSetPosition"):
            u, v = self._finite_coordinates(value, 2)
            if fast:
                self._require_valid()
                geometry_edit.set_uvs(self.shape, [self.index], [(u, v)])
                return self
            cmds.polyEditUV(self.getFullName(), relative=False, uValue=u, vValue=v,
                            uvSetName=self.shape._geometry_fn().currentUVSetName())
            return self

    def getU(self):
        """U成分の現在値を取得する。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(0)

    def setU(self, value, *, fast=False):
        """U成分だけを設定し、他の成分を維持する。

        Args:
            value (float): 有限な座標。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UV: 更新した自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 座標または要素数が不正な場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        _require_bool(fast, "fast")
        return self._set_coordinate(0, value, fast=fast)

    def getV(self):
        """V成分の現在値を取得する。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(1)

    def setV(self, value, *, fast=False):
        """V成分だけを設定し、他の成分を維持する。

        Args:
            value (float): 有限な座標。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UV: 更新した自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 座標または要素数が不正な場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        _require_bool(fast, "fast")
        return self._set_coordinate(1, value, fast=fast)


_UV_GET_POSITION = UV.getPosition


class UVs(Components):
    """同一MeshのUV番号列を保持し、現在のUVセットの座標を保持順に扱う。

    セット名や座標値は保持せず、セット切替後は切替先の同じ番号を使う。
    setPositionは同じU/Vを全要素へ、setPositionsは保持番号ごとに異なる行を設定する。
    """

    component_class = UV

    def setPositions(self, values, *, fast=False):
        """現在のUVセットへ、保持番号に対応する絶対(U,V)行を設定する。

        件数・有限値・現在の番号範囲を検証する。通常は保持順にpolyEditUVを呼び、
        fastはinMesh入力とShapeロックを検査してUV配列を一括設定する。

        Args:
            values (Iterable[Iterable[float]]): 保持番号と同じ件数の有限な(U,V)行。無次元。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UVs: 自身。標準実装の空集合と空列はShapeを再照会せず何もしない。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 件数または座標が不正な場合。
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fastでinMesh入力付きShapeを編集する場合。

        Note:
            UVセット/割当ての作成、全UV-set Plugの書込み検査、自動ロールバックは行わない。
        """
        _require_bool(fast, "fast")
        with nullcontext() if fast else undoChunk("mlibUVsSetPositions"):
            rows = self._coordinate_rows(values, 2)
            if fast and self._uses_standard_iteration(UV):
                if self._indices:
                    Component._validate_shape(self._shape, UV.shape_type)
                    count = self._shape.getNumUVs()
                    for index in self._indices:
                        Component._require_index_range(index, count)
                geometry_edit.set_uvs(self._shape, self._indices, rows)
                return self
            components = list(self)
            if fast:
                geometry_edit.set_uvs(self._shape, [c.index for c in components], rows)
                return self
            for item, point in zip(components, rows):
                item.setPosition(point, fast=fast)
            return self

    def getU(self):
        """U成分の現在値を取得する。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(0)

    def setU(self, value, *, fast=False):
        """U成分だけを設定し、他の成分を維持する。

        Args:
            value (float | Iterable[float]): 同値スカラーまたは保持順の値列。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UVs: 更新した自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 座標または要素数が不正な場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        _require_bool(fast, "fast")
        return self._set_coordinate(0, value, fast=fast)

    def getV(self):
        """V成分の現在値を取得する。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(1)

    def setV(self, value, *, fast=False):
        """V成分だけを設定し、他の成分を維持する。

        Args:
            value (float | Iterable[float]): 同値スカラーまたは保持順の値列。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            UVs: 更新した自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 座標または要素数が不正な場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        _require_bool(fast, "fast")
        return self._set_coordinate(1, value, fast=fast)

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

        一つのU/Vを各保持番号へ対応させ、setPositionsへ委譲する。

        Args:
            value (Iterable[float]): 全要素に共通の有限なU/V。無次元。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。setPositionsと同じ制限に従う。

        Returns:
            UVs: 自身。要素ごとに異なる座標を指定する場合はsetPositionsを使う。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: U/Vが不正な場合。空集合でも入力値を検証する。
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fastでinMesh入力のあるShapeを編集する場合。
        """
        _require_bool(fast, "fast")
        point = Component._finite_coordinates(value, 2)
        return self.setPositions([point] * len(self), fast=fast)
