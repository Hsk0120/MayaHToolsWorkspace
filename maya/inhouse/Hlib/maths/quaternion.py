"""四元数の保持・演算とオイラー回転への変換。"""

import math
from dataclasses import dataclass


@dataclass(frozen=True, repr=False)
class Quaternion:
    """XYZW 成分で保持する不変な四元数。

    四元数成分自体は角度ではない。生成時や積の計算時に正規化は行わない。
    オイラー回転との変換に用いる角度はラジアン。
    等価比較・ハッシュは dataclass が生成する。"""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0

    def __post_init__(self):
        """各成分を float へ正規化する。

        既定値 (0, 0, 0, 1) は単位四元数。入力時には正規化しない。frozen のため
        通常の属性代入はできず、object.__setattr__ で書き換える。

        Returns:
            None: 値を返さない。
        """
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))
        object.__setattr__(self, "z", float(self.z))
        object.__setattr__(self, "w", float(self.w))

    def __iter__(self):
        """X、Y、Z、W の順で成分を反復する。

        Yields:
            float: X、Y、Z、W 順の成分。
        """
        yield self.x
        yield self.y
        yield self.z
        yield self.w

    def __repr__(self):
        """クラス名と 4 成分を含むデバッグ表現を返す。

        Returns:
            str: 型名と現在の成分を含む文字列表現。
        """
        return f"Quaternion({self.x}, {self.y}, {self.z}, {self.w})"

    def __mul__(self, other):
        """別の Quaternion との Hamilton 積を返す。

        Args:
            other (object): 右側から乗算する Quaternion。

        Returns:
            Quaternion | types.NotImplementedType: Hamilton 積。結果は正規化しない。相手が Quaternion でなければ NotImplemented。
        """
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
            ValueError: order が大文字小文字を無視して xyz 以外の場合、またはゼロ四元数の場合。
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
