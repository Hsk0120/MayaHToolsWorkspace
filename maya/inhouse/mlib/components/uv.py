"""Mesh の現在の UV セットを参照する UV 型。"""

import maya.cmds as cmds

from ..core import geometryEdit as geometry_edit
from ..decorator import _fast_edit, _is_fast, undoChunk
from .component import Component, Components


class UV(Component):
    """現在の UV セットの単一 UV。UV セット切替後は切替先を参照する。"""

    shape_type = "mesh"
    component_type = "map"
    count_attribute = "getNumUVs"

    def getPosition(self):
        """UV 座標を取得する。

        Returns:
            tuple[float, float]: 単位を持たない U、V 座標。
        """
        self._validate()
        mesh_fn = self.shape.meshFn()
        return tuple(mesh_fn.getUV(self._index, uvSet=mesh_fn.currentUVSetName()))

    @_fast_edit
    @undoChunk("mlibUVPosition")
    def setPosition(self, value, *, fast=False):
        """UV 座標を設定する。

        Args:
            value (Iterable[float]): 有限な U、V の2成分。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            UV: 編集した自身。

        Raises:
            ValueError: 座標が不正な場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状を編集するとNotImplementedError。
        """
        u, v = self._finite_coordinates(value, 2)
        if _is_fast():
            self._validate()
            geometry_edit.set_uvs(self.shape, [self.index], [(u, v)])
            return self
        cmds.polyEditUV(self.getFullName(), relative=False, uValue=u, vValue=v,
                        uvSetName=self.shape.meshFn().currentUVSetName())
        return self

    def getU(self):
        """U成分の現在値を取得する。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(0)

    @_fast_edit
    def setU(self, value, *, fast=False):
        """U成分だけを設定し、他の成分を維持する。

        Args:
            value (float): 有限な座標。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            UV: 更新した自身。

        Raises:
            ValueError: 座標または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        return self._set_coordinate(0, value)

    def getV(self):
        """V成分の現在値を取得する。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(1)

    @_fast_edit
    def setV(self, value, *, fast=False):
        """V成分だけを設定し、他の成分を維持する。

        Args:
            value (float): 有限な座標。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            UV: 更新した自身。

        Raises:
            ValueError: 座標または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        return self._set_coordinate(1, value)


_UV_GET_POSITION = UV.getPosition


class UVs(Components):
    """同一 Mesh の現在の UV セットの UV 群。"""

    component_class = UV

    @_fast_edit
    @undoChunk("mlibUVsSetPositions")
    def setPositions(self, values, *, fast=False):
        """保持順にUV座標を設定する。全件の座標・対象を先に検証する。

        Args:
            values (Iterable[Iterable[float]]): 要素数と同じ数のU、V座標。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            UVs: 自身。空集合と空列は何もしない。

        Raises:
            ValueError: 件数・座標が不正な場合。
            RuntimeError: Mayaが拒否した場合。完了済み変更は自動で戻さない。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状を編集するとNotImplementedError。
        """
        rows = self._coordinate_rows(values, 2)
        if _is_fast() and self._uses_standard_iteration(UV):
            if self._indices:
                Component._validate_shape(self._shape, UV.shape_type)
                count = self._shape.getNumUVs()
                for index in self._indices:
                    Component._validate_index(index, count)
            geometry_edit.set_uvs(self._shape, self._indices, rows)
            return self
        components = list(self)
        if _is_fast():
            geometry_edit.set_uvs(self._shape, [c.index for c in components], rows)
            return self
        for item, point in zip(components, rows):
            item.setPosition(point)
        return self

    def getU(self):
        """U成分の現在値を取得する。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(0)

    @_fast_edit
    def setU(self, value, *, fast=False):
        """U成分だけを設定し、他の成分を維持する。

        Args:
            value (float | Iterable[float]): 同値スカラーまたは保持順の値列。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            UVs: 更新した自身。

        Raises:
            ValueError: 座標または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        return self._set_coordinate(0, value)

    def getV(self):
        """V成分の現在値を取得する。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(1)

    @_fast_edit
    def setV(self, value, *, fast=False):
        """V成分だけを設定し、他の成分を維持する。

        Args:
            value (float | Iterable[float]): 同値スカラーまたは保持順の値列。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            UVs: 更新した自身。

        Raises:
            ValueError: 座標または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        return self._set_coordinate(1, value)

    def getPosition(self):
        """保持順の UV 座標を取得する。

        Returns:
            list[tuple[float, float]]: U、V 座標列。
        """
        if not (self._uses_standard_iteration(UV) and UV.getPosition is _UV_GET_POSITION):
            return [item.getPosition() for item in self]
        if not self._indices:
            return []
        Component._validate_shape(self._shape, UV.shape_type)
        mesh_fn = self._shape.meshFn()
        count = mesh_fn.numUVs()
        uv_set = mesh_fn.currentUVSetName()
        result = []
        for index in self._indices:
            Component._validate_index(index, count)
            result.append(tuple(mesh_fn.getUV(index, uvSet=uv_set)))
        return result

    @_fast_edit
    def setPosition(self, value, *, fast=False):
        """全UVを同じ座標へ設定する。

        Args:
            value (Iterable[float]): 有限のU、V座標。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            UVs: 自身。要素別の指定にはsetPositionsを使う。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状を編集するとNotImplementedError。
        """
        point = Component._finite_coordinates(value, 2)
        return self.setPositions([point] * len(self))
