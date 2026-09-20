"""Euler rotation value."""

import math

from .quaternion import Quaternion
from .rotation import Rotation


class EulerRotation(Rotation):
    """Maya の回転順序を保持する Euler 回転値。

    Args:
        x (float): X 軸回転（radian）。
        y (float | None): Y 軸回転（radian）。
        z (float | None): Z 軸回転（radian）。
        order (str): Maya 回転順序。
    """

    __slots__ = ("order",)
    _VALID_ORDERS = {"xyz", "yzx", "zxy", "xzy", "yxz", "zyx"}

    def __init__(self, x, y=None, z=None, order="xyz"):
        """回転成分と Maya 回転順序から EulerRotation を初期化する。"""
        super().__init__(x, y, z)
        normalized_order = order.lower()
        if normalized_order not in self._VALID_ORDERS:
            raise ValueError(f"Unsupported rotation order: {order}")
        self.order = normalized_order

    def __repr__(self):
        """回転成分と回転順序を含むデバッグ表現を返す。"""
        return f"EulerRotation({self.x}, {self.y}, {self.z}, order={self.order!r})"

    def to_quaternion(self):
        """Quaternion へ変換する。

        Returns:
            Quaternion: 正規化済みの四元数。
        """
        if self.order == "xyz":
            half_x = self.x / 2.0
            half_y = self.y / 2.0
            half_z = self.z / 2.0
            sin_x, cos_x = math.sin(half_x), math.cos(half_x)
            sin_y, cos_y = math.sin(half_y), math.cos(half_y)
            sin_z, cos_z = math.sin(half_z), math.cos(half_z)
            return Quaternion(
                sin_x * cos_y * cos_z - cos_x * sin_y * sin_z,
                cos_x * sin_y * cos_z + sin_x * cos_y * sin_z,
                cos_x * cos_y * sin_z - sin_x * sin_y * cos_z,
                cos_x * cos_y * cos_z + sin_x * sin_y * sin_z,
            ).normalized()
        half_angles = {"x": self.x / 2.0, "y": self.y / 2.0, "z": self.z / 2.0}
        axis_quaternions = {
            "x": Quaternion(math.sin(half_angles["x"]), 0.0, 0.0, math.cos(half_angles["x"])),
            "y": Quaternion(0.0, math.sin(half_angles["y"]), 0.0, math.cos(half_angles["y"])),
            "z": Quaternion(0.0, 0.0, math.sin(half_angles["z"]), math.cos(half_angles["z"])),
        }
        quaternion = Quaternion()
        for axis in self.order:
            quaternion = quaternion * axis_quaternions[axis]
        return quaternion.normalized()