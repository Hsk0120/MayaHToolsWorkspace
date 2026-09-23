"""Mesh の現在の UV セットを参照する UV 型。"""
import maya.cmds as cmds
from .component import Component, Components
from ..decorators.undo import undo_chunk


class UV(Component):
    """現在の UV セットの単一 UV。UV セット切替後は切替先を参照する。"""
    shape_type = "mesh"
    component_type = "map"
    count_attribute = "num_uvs"

    def position(self):
        """UV 座標を取得する。

        Returns:
            tuple[float, float]: 単位を持たない U、V 座標。
        """
        self._validate()
        mesh_fn = self.shape.mesh_fn()
        return tuple(mesh_fn.getUV(self._index, uvSet=mesh_fn.currentUVSetName()))

    @undo_chunk("hlibUVPosition")
    def set_position(self, value):
        """UV 座標を設定する。

        Args:
            value (Iterable[float]): 有限な U、V の2成分。

        Returns:
            UV: 編集した自身。

        Raises:
            ValueError: 座標が不正な場合。
        """
        u, v = self._finite_coordinates(value, 2)
        cmds.polyEditUV(self.full_name, relative=False, uValue=u, vValue=v,
                        uvSetName=self.shape.mesh_fn().currentUVSetName())
        return self

    @property
    def u(self):
        """U 座標を取得する。

        Returns:
            float: 現在の UV 座標。
        """
        return self.position()[0]

    @u.setter
    def u(self, value):
        """U 座標だけを設定する。

        Args:
            value (float): 有限な座標。

        Returns:
            None: 値を返さない。
        """
        position = list(self.position())
        position[0] = value
        self.set_position(position)

    @property
    def v(self):
        """V 座標を取得する。

        Returns:
            float: 現在の UV 座標。
        """
        return self.position()[1]

    @v.setter
    def v(self, value):
        """V 座標だけを設定する。

        Args:
            value (float): 有限な座標。

        Returns:
            None: 値を返さない。
        """
        position = list(self.position())
        position[1] = value
        self.set_position(position)


class UVs(Components):
    """同一 Mesh の現在の UV セットの UV 群。"""
    component_class = UV

    def positions(self):
        """保持順の UV 座標を取得する。

        Returns:
            list[tuple[float, float]]: U、V 座標列。
        """
        return [item.position() for item in self]
