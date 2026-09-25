"""Mesh の現在の UV セットを参照する UV 型。"""

from ..decorators._fast import fast_edit, is_fast
from .._core import fast_geometry
import maya.cmds as cmds
from .component import Component, Components
from ..decorators.undo import undo_chunk


class UV(Component):
    """現在の UV セットの単一 UV。UV セット切替後は切替先を参照する。"""
    shape_type = "mesh"
    component_type = "map"
    count_attribute = "num_uvs"

    def get_position(self):
        """UV 座標を取得する。

        Returns:
            tuple[float, float]: 単位を持たない U、V 座標。
        """
        self._validate()
        mesh_fn = self.shape.mesh_fn()
        return tuple(mesh_fn.getUV(self._index, uvSet=mesh_fn.currentUVSetName()))

    @fast_edit
    @undo_chunk("hlibUVPosition")
    def set_position(self, value, *, fast=False):
        """UV 座標を設定する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Iterable[float]): 有限な U、V の2成分。

        Returns:
            UV: 編集した自身。

        Raises:
            ValueError: 座標が不正な場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状を編集するとNotImplementedError。
        """
        u, v = self._finite_coordinates(value, 2)
        if is_fast():
            self._validate()
            fast_geometry.set_uvs(self.shape, [self.index], [(u, v)])
            return self
        cmds.polyEditUV(self.full_name(), relative=False, uValue=u, vValue=v,
                        uvSetName=self.shape.mesh_fn().currentUVSetName())
        return self

    def get_u(self):
        """U 座標を取得する。

        Returns:
            float: 現在の UV 座標。
        """
        return self.get_position()[0]

    def set_u(self, value):
        """U 座標だけを設定する。

        Args:
            value (float): 有限な座標。

        Returns:
            None: 値を返さない。
        """
        position = list(self.get_position())
        position[0] = value
        self.set_position(position)

    def get_v(self):
        """V 座標を取得する。

        Returns:
            float: 現在の UV 座標。
        """
        return self.get_position()[1]

    def set_v(self, value):
        """V 座標だけを設定する。

        Args:
            value (float): 有限な座標。

        Returns:
            None: 値を返さない。
        """
        position = list(self.get_position())
        position[1] = value
        self.set_position(position)


class UVs(Components):
    """同一 Mesh の現在の UV セットの UV 群。"""
    component_class = UV

    def get_position(self):
        """list[tuple[float, float]]: 保持順のUV座標列。"""
        return self.get_positions()

    @fast_edit
    def set_position(self, value, *, fast=False):
        """全UVを同じ座標へ設定する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Iterable[float]): 有限のU、V座標。
        Returns:
            UVs: 自身。要素別の指定にはset_positionsを使う。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状を編集するとNotImplementedError。
        """
        point = Component._finite_coordinates(value, 2)
        return self.set_positions([point] * len(self))

    @fast_edit
    @undo_chunk("hlibUVsSetPositions")
    def set_positions(self, values, *, fast=False):
        """保持順にUV座標を設定する。全件の座標・対象を先に検証する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            values (Iterable[Iterable[float]]): 要素数と同じ数のU、V座標。
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
        components = list(self)
        if is_fast():
            fast_geometry.set_uvs(self._shape, [c.index for c in components], rows)
            return self
        for item, point in zip(components, rows):
            item.set_position(point)
        return self

    def get_u(self):
        """list[float]: 保持順のU座標。"""
        return [p[0] for p in self.get_positions()]

    def set_u(self, value):
        """Uだけを更新する。スカラーは全要素、数値列は保持順へ適用する。"""
        self.set_positions(self._axis_rows(self.get_positions(), 0, value))

    def get_v(self):
        """list[float]: 保持順のV座標。"""
        return [p[1] for p in self.get_positions()]

    def set_v(self, value):
        """Vだけを更新する。スカラーは全要素、数値列は保持順へ適用する。"""
        self.set_positions(self._axis_rows(self.get_positions(), 1, value))

    def get_positions(self):
        """保持順の UV 座標を取得する。

        Returns:
            list[tuple[float, float]]: U、V 座標列。
        """
        return [item.get_position() for item in self]
