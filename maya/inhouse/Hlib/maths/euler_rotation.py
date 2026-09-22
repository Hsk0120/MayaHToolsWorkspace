"""回転順序を保持するラジアンのオイラー回転値。"""

import math
from dataclasses import dataclass, field

from .quaternion import Quaternion
from .rotate import Rotate


@dataclass(frozen=True, repr=False)
class EulerRotation(Rotate):
    """ラジアンの3成分と回転順序を保持する不変なオイラー回転値。

    表示用の文字列は度に変換する。回転順序（order）は等価比較・ハッシュの
    対象から除外し、XYZ 成分のみで比較する（Vector 系と同じ挙動を維持する）。"""

    order: str = field(default="xyz", compare=False)

    _VALID_ORDERS = {"xyz", "yzx", "zxy", "xzy", "yxz", "zyx"}

    def __post_init__(self):
        """XYZ 成分を float 化し、回転順序を検証・正規化する。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 未対応の回転順序、または数値変換に失敗した場合。
        """
        super().__post_init__()
        normalized_order = self.order.lower()
        if normalized_order not in self._VALID_ORDERS:
            raise ValueError(f"Unsupported rotation order: {self.order}")
        object.__setattr__(self, "order", normalized_order)

    def __repr__(self):
        """度数法の回転成分と回転順序を含むデバッグ表現を返す。

        Returns:
            str: 度に変換した成分と回転順序を含む文字列。内部値はラジアンのまま。
        """
        values = ", ".join(f"{value:.15g}" for value in self.as_degrees())
        return f"EulerRotation(degrees=({values}), order={self.order!r})"

    def as_degrees(self):
        """回転成分を度数法の 3 要素 tuple として取得する。

        Returns:
            tuple[float, float, float]: XYZ の回転角度（度）。
        """
        return tuple(math.degrees(value) for value in self)

    asDegrees = as_degrees

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
