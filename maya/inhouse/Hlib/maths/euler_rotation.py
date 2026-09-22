"""回転順序を保持するラジアンのオイラー回転値。"""

import math

from .quaternion import Quaternion
from .rotate import Rotate


class EulerRotation(Rotate):
    """ラジアンの3成分と回転順序を保持するオイラー回転値。

    表示用の文字列は度に変換する。Vector から継承した等値比較では
    回転順序は比較せず、XYZ 成分のみを比較する。"""

    __slots__ = ("order",)
    _VALID_ORDERS = {"xyz", "yzx", "zxy", "xzy", "yxz", "zyx"}

    def __init__(self, x, y=None, z=None, order="xyz"):
        """回転成分と Maya 回転順序から EulerRotation を初期化する。

        回転成分はラジアンで保持する。Vector と同じ入力形式で初期化する。

        Args:
            x (float | Iterable[float]): X 成分、または3成分の反復可能オブジェクト。
            y (float | None): Y 成分。3成分入力の場合は省略する。
            z (float | None): Z 成分。3成分入力の場合は省略する。
            order (str): xyz、yzx、zxy、xzy、yxz、zyx のいずれか。小文字に正規化する。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 未対応の回転順序、3要素でない入力、または数値変換に失敗した場合。
        """
        super().__init__(x, y, z)
        normalized_order = order.lower()
        if normalized_order not in self._VALID_ORDERS:
            raise ValueError(f"Unsupported rotation order: {order}")
        self.order = normalized_order

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