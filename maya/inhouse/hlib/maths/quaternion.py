"""四元数の保持・演算とオイラー回転への変換。"""

import math
from dataclasses import dataclass

#: 回転順序の文字列と、X/Y/Z(0/1/2)成分インデックスの対応。
_EULER_ORDER_AXES = {
    "xyz": (0, 1, 2), "yzx": (1, 2, 0), "zxy": (2, 0, 1),
    "xzy": (0, 2, 1), "yxz": (1, 0, 2), "zyx": (2, 1, 0),
}

#: (x, y, z) の巡回置換になっている回転順序。行列成分からの角度抽出時の符号を決める。
_EULER_CYCLIC_ORDERS = frozenset(("xyz", "yzx", "zxy"))

#: ジンバルロック時(中間軸が ±90度)に、最初に適用される軸の角度を
#: 行列成分から復元する式。最後に適用される軸の角度は 0 とみなす。
_EULER_GIMBAL_FORMULAS = {
    "xyz": lambda m, branch: math.atan2(branch * m[1][0], m[1][1]),
    "yzx": lambda m, branch: math.atan2(-m[0][2], branch * m[0][1]),
    "zxy": lambda m, branch: math.atan2(branch * m[0][2], m[0][0]),
    "xzy": lambda m, branch: math.atan2(m[1][2], -branch * m[1][0]),
    "yxz": lambda m, branch: math.atan2(branch * m[0][1], m[0][0]),
    "zyx": lambda m, branch: math.atan2(m[0][1], -branch * m[0][2]),
}


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

    def dot(self, other):
        """別の Quaternion との内積を返す。

        Args:
            other (Quaternion): 内積の相手。

        Returns:
            float: 内積。
        """
        return self.x * other.x + self.y * other.y + self.z * other.z + self.w * other.w

    def length(self):
        """四元数の長さ(ノルム)を返す。

        Returns:
            float: 長さ。
        """
        return math.sqrt(self.dot(self))

    def normalized(self):
        """正規化済み四元数を返す。

        Returns:
            Quaternion: 長さ 1 の四元数。

        Raises:
            ValueError: ゼロ四元数の場合。
        """
        length = self.length()
        if length == 0.0:
            raise ValueError("Cannot normalize a zero quaternion")
        return Quaternion(*(component / length for component in self))

    def conjugate(self):
        """共役四元数を返す。

        Returns:
            Quaternion: XYZ 成分の符号を反転した四元数。
        """
        return Quaternion(-self.x, -self.y, -self.z, self.w)

    def inverse(self):
        """逆四元数を返す。

        単位四元数(回転として正規化済み)であれば conjugate() と同じ結果になる。

        Returns:
            Quaternion: 逆四元数。

        Raises:
            ValueError: ゼロ四元数の場合。
        """
        length_squared = self.dot(self)
        if length_squared == 0.0:
            raise ValueError("Cannot invert a zero quaternion")
        return Quaternion(*(component / length_squared for component in self.conjugate()))

    def rotate_vector(self, vector):
        """Vector をこの回転で変換する。

        自身を正規化してから適用するため、正規化していない四元数を渡しても
        結果のスケールには影響しない。

        Args:
            vector (Vector): 回転させる方向・位置ベクトル。

        Returns:
            Vector: 回転後のベクトル。派生クラスの型は保持しない。

        Raises:
            ValueError: 自身がゼロ四元数の場合。
        """
        from .vector import Vector

        rotation = self.normalized()
        axis = Vector(rotation.x, rotation.y, rotation.z)
        uv = axis.cross(vector)
        uuv = axis.cross(uv)
        return vector + uv * (2.0 * rotation.w) + uuv * 2.0

    def angle_to(self, other):
        """別の Quaternion が表す回転との角度差をラジアンで返す。

        自身・other をそれぞれ正規化してから比較する。四元数の二重被覆
        (q と -q が同じ回転を表す)を考慮し、常に 0 から pi の範囲を返す。

        Args:
            other (Quaternion): 角度差を測る相手の回転。

        Returns:
            float: 0 から pi の範囲のラジアン角度。

        Raises:
            ValueError: 自身または other がゼロ四元数の場合。
        """
        cosine = abs(self.normalized().dot(other.normalized()))
        cosine = max(-1.0, min(1.0, cosine))
        return 2.0 * math.acos(cosine)

    def slerp(self, other, t):
        """別の Quaternion との球面線形補間を返す。

        最短経路になるよう二重被覆を補正し、ほぼ同じ回転同士では
        sin(theta) がゼロに近づく数値不安定を避けるため線形補間へ
        フォールバックする。

        Args:
            other (Quaternion): 補間先の回転。
            t (float): 補間係数。0 で自身、1 で other。範囲外の値は外挿になる。

        Returns:
            Quaternion: 補間結果。正規化済み。

        Raises:
            ValueError: 自身または other がゼロ四元数の場合。
        """
        self_q = self.normalized()
        other_q = other.normalized()
        cosine = self_q.dot(other_q)
        if cosine < 0.0:
            other_q = Quaternion(-other_q.x, -other_q.y, -other_q.z, -other_q.w)
            cosine = -cosine
        cosine = max(-1.0, min(1.0, cosine))
        if cosine > 0.9995:
            blended = Quaternion(*(a + (b - a) * t for a, b in zip(self_q, other_q)))
            return blended.normalized()
        theta = math.acos(cosine)
        sine = math.sin(theta)
        self_weight = math.sin((1.0 - t) * theta) / sine
        other_weight = math.sin(t * theta) / sine
        return Quaternion(*(a * self_weight + b * other_weight for a, b in zip(self_q, other_q)))

    @classmethod
    def from_axis_angle(cls, axis, angle):
        """軸と角度から回転四元数を生成する。

        Args:
            axis (Vector | Iterable[float]): 回転軸。内部で正規化する。
            angle (float): 回転角度(ラジアン)。

        Returns:
            Quaternion: axis を中心に angle だけ回転する単位四元数。

        Raises:
            ValueError: axis がゼロベクトルの場合。
        """
        from .vector import Vector

        if not isinstance(axis, Vector):
            axis = Vector(*axis)
        axis = axis.normalized()
        half_angle = angle / 2.0
        sine = math.sin(half_angle)
        return cls(axis.x * sine, axis.y * sine, axis.z * sine, math.cos(half_angle))

    def to_axis_angle(self):
        """軸と角度の組へ分解する。

        Returns:
            tuple[Vector, float]: 正規化した回転軸と、ラジアンの回転角度
                (0 から 2*pi の範囲)。回転がほぼ無い場合、軸は便宜上
                (1, 0, 0) を返す。

        Raises:
            ValueError: 自身がゼロ四元数の場合。
        """
        from .vector import Vector

        rotation = self.normalized()
        if rotation.w < 0.0:
            rotation = Quaternion(-rotation.x, -rotation.y, -rotation.z, -rotation.w)
        angle = 2.0 * math.acos(max(-1.0, min(1.0, rotation.w)))
        sine = math.sqrt(max(0.0, 1.0 - rotation.w * rotation.w))
        if sine < 1e-10:
            return Vector(1.0, 0.0, 0.0), angle
        return Vector(rotation.x / sine, rotation.y / sine, rotation.z / sine), angle

    def to_swing_twist(self, axis=(1.0, 0.0, 0.0)):
        """指定軸まわりの捻り(twist)と、それ以外の曲げ(swing)へ分解する。

        ボーン(joint)の回転を、軸方向の捻り成分とそれに直交する曲げ成分に
        分離する swing-twist 分解。``twist`` は axis 周りのみの回転、
        ``swing`` は axis をそのまま axis 周りに回転させない(twist を
        先に適用した結果を axis 方向に保ったまま残りを回転させる)成分で、
        ``swing * twist`` は自身と同じ回転を表す。

        Args:
            axis (Vector | Iterable[float]): 捻り軸。内部で正規化する。

        Returns:
            tuple[Quaternion, Quaternion]: (swing, twist)。どちらも正規化済み。

        Raises:
            ValueError: axis がゼロベクトルの場合、または自身がゼロ四元数の場合。
        """
        from .vector import Vector

        if not isinstance(axis, Vector):
            axis = Vector(*axis)
        axis = axis.normalized()
        rotation = self.normalized()
        dot = rotation.x * axis.x + rotation.y * axis.y + rotation.z * axis.z
        twist = Quaternion(dot * axis.x, dot * axis.y, dot * axis.z, rotation.w)
        length = twist.length()
        if length < 1e-10:
            # 捻り軸に直交する180度回転など、axis 成分が無い姿勢は捻りなしとみなす。
            twist = Quaternion()
        else:
            twist = Quaternion(*(component / length for component in twist))
        swing = rotation * twist.conjugate()
        return swing, twist

    def to_euler(self, order="xyz"):
        """EulerRotation へ変換する。

        回転行列(行ベクトル規約)を経由し、``EulerRotation.to_quaternion()`` の
        6回転順序すべてに対応する合成規約(最初に適用する軸が右端、最後に
        適用する軸が左端の Hamilton 積)を逆算する。中間軸が ±90度付近の
        ジンバルロックでは、最後に適用される軸の角度を 0 とみなし、最初に
        適用される軸の角度のみを残りの自由度から復元する(一般的な規約)。

        Args:
            order (str): 回転順序。``"xyz"``/``"yzx"``/``"zxy"``/``"xzy"``/
                ``"yxz"``/``"zyx"`` に対応。

        Returns:
            EulerRotation: radian の Euler 回転値。

        Raises:
            ValueError: order が未対応の場合、またはゼロ四元数の場合。
        """
        order = order.lower()
        if order not in _EULER_ORDER_AXES:
            raise ValueError(f"Unsupported rotation order: {order!r}")
        from .eulerRotation import EulerRotation

        quaternion = self.normalized()
        x, y, z, w = quaternion.x, quaternion.y, quaternion.z, quaternion.w
        m = (
            (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y + z * w), 2.0 * (x * z - y * w)),
            (2.0 * (x * y - z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z + x * w)),
            (2.0 * (x * z + y * w), 2.0 * (y * z - x * w), 1.0 - 2.0 * (x * x + y * y)),
        )
        a, b, c = _EULER_ORDER_AXES[order]
        sign = 1.0 if order in _EULER_CYCLIC_ORDERS else -1.0
        gimbal = max(-1.0, min(1.0, -sign * m[a][c]))

        angles = [0.0, 0.0, 0.0]
        if abs(gimbal) >= 1.0 - 1e-9:
            branch = math.copysign(1.0, gimbal)
            angles[b] = branch * math.pi / 2.0
            angles[a] = _EULER_GIMBAL_FORMULAS[order](m, branch)
            angles[c] = 0.0
        else:
            angles[b] = math.asin(gimbal)
            angles[a] = math.atan2(sign * m[b][c], m[c][c])
            angles[c] = math.atan2(sign * m[a][b], m[a][a])
        return EulerRotation(angles[0], angles[1], angles[2], order)
