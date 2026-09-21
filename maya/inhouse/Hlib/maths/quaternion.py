"""Quaternion rotation value."""

import math


class Quaternion:
    """Maya の radian 規約を使う四元数回転値。

    Args:
        x (float): X 成分。
        y (float): Y 成分。
        z (float): Z 成分。
        w (float): スカラー成分。
    """

    __slots__ = ("x", "y", "z", "w")

    def __init__(self, x=0.0, y=0.0, z=0.0, w=1.0):
        """4 成分から四元数を初期化する。"""
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
        self.w = float(w)

    def __iter__(self):
        """X、Y、Z、W の順で成分を反復する。"""
        yield self.x
        yield self.y
        yield self.z
        yield self.w

    def __repr__(self):
        """クラス名と 4 成分を含むデバッグ表現を返す。"""
        return f"Quaternion({self.x}, {self.y}, {self.z}, {self.w})"

    def __eq__(self, other):
        """別の Quaternion との成分一致を判定する。"""
        if not isinstance(other, Quaternion):
            return NotImplemented
        return tuple(self) == tuple(other)

    def __mul__(self, other):
        """別の Quaternion との Hamilton 積を返す。"""
        if not isinstance(other, Quaternion):
            return NotImplemented
        return Quaternion(
            self.w * other.x + self.x * other.w + self.y * other.z - self.z * other.y,
            self.w * other.y - self.x * other.z + self.y * other.w + self.z * other.x,
            self.w * other.z + self.x * other.y - self.y * other.x + self.z * other.w,
            self.w * other.w - self.x * other.x - self.y * other.y - self.z * other.z,
        )

    def normalized(self):
        """正規化済み四元数を返す。

        Returns:
            Quaternion: 長さ 1 の四元数。

        Raises:
            ValueError: ゼロ四元数の場合。
        """
        length = math.sqrt(sum(component * component for component in self))
        if length == 0.0:
            raise ValueError("Cannot normalize a zero quaternion")
        return Quaternion(*(component / length for component in self))

    def to_euler(self, order="xyz"):
        """EulerRotation へ変換する。

        Args:
            order (str): 回転順序。現時点では ``"xyz"`` のみ対応。

        Returns:
            EulerRotation: radian の Euler 回転値。

        Raises:
            ValueError: 未対応の回転順序を指定した場合。
        """
        if order.lower() != "xyz":
            raise ValueError("Only xyz Euler conversion is currently supported")
        from .euler_rotation import EulerRotation

        quaternion = self.normalized()
        x = math.atan2(
            2.0 * (quaternion.w * quaternion.x + quaternion.y * quaternion.z),
            1.0 - 2.0 * (quaternion.x ** 2 + quaternion.y ** 2),
        )
        sin_y = 2.0 * (quaternion.w * quaternion.y - quaternion.z * quaternion.x)
        y = math.copysign(math.pi / 2.0, sin_y) if abs(sin_y) >= 1.0 else math.asin(sin_y)
        z = math.atan2(
            2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
            1.0 - 2.0 * (quaternion.y ** 2 + quaternion.z ** 2),
        )
        return EulerRotation(x, y, z, order)