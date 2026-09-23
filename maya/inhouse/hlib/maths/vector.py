"""3成分を保持する汎用ベクトルと基本演算。"""

import math
from dataclasses import dataclass


@dataclass(frozen=True, repr=False)
class Vector:
    """3成分の不変なベクトル値。

    加減算・スカラー乗算の結果は、派生クラスでも常に Vector となる。
    等価比較・ハッシュは dataclass が生成し、同一クラス同士でのみ成分比較する。"""

    x: float
    y: float
    z: float

    def __post_init__(self):
        """各成分を float へ正規化する。

        frozen のため通常の属性代入はできず、object.__setattr__ で書き換える。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: float へ変換できない値を指定した場合。
        """
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))
        object.__setattr__(self, "z", float(self.z))

    @classmethod
    def from_iterable(cls, values):
        """3要素の反復可能オブジェクトから生成する。

        Args:
            values (Iterable[float]): 3要素の反復可能オブジェクト。

        Returns:
            Vector: 呼び出したクラスの新しいインスタンス。

        Raises:
            ValueError: 要素数が3でない場合。
        """
        values = tuple(values)
        if len(values) != 3:
            raise ValueError(f"{cls.__name__} expects 3 values")
        return cls(*values)

    def __iter__(self):
        """X、Y、Z の順で成分を反復する。

        Yields:
            float: X、Y、Z 順の成分。
        """
        yield self.x
        yield self.y
        yield self.z

    def __len__(self):
        """ベクトル成分数の 3 を返す。

        Returns:
            int: 常に3。
        """
        return 3

    def __getitem__(self, index):
        """指定インデックスのベクトル成分を返す。

        Args:
            index (int | slice): XYZ 順の添字またはスライス。負の添字も使用できる。

        Returns:
            float | tuple[float, ...]: 単一成分、またはスライスに対応する成分のタプル。

        Raises:
            IndexError: 整数の添字が範囲外の場合。
        """
        return (self.x, self.y, self.z)[index]

    def __repr__(self):
        """クラス名と 3 成分を含むデバッグ表現を返す。

        Returns:
            str: 型名と現在の成分を含む文字列表現。
        """
        return f"{type(self).__name__}({self.x}, {self.y}, {self.z})"

    def __str__(self):
        """デバッグ表現と同じ文字列表現を返す。

        Returns:
            str: __repr__ と同じ文字列。
        """
        return repr(self)

    def __add__(self, other):
        """別の Vector 系オブジェクトとの成分ごとの加算を行う。

        Args:
            other (object): 成分ごとの加算に使う Vector。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。派生クラスの型は保持しない。相手が Vector でなければ NotImplemented。
        """
        if not isinstance(other, Vector):
            return NotImplemented
        return Vector(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other):
        """別の Vector 系オブジェクトとの成分ごとの減算を行う。

        Args:
            other (object): 成分ごとの減算に使う Vector。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。派生クラスの型は保持しない。相手が Vector でなければ NotImplemented。
        """
        if not isinstance(other, Vector):
            return NotImplemented
        return Vector(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar):
        """数値スカラーによる成分ごとの乗算を行う。

        Args:
            scalar (object): 乗算する int または float。

        Returns:
            Vector | types.NotImplementedType: 成分ごとの積を持つ新しい Vector。未対応型では NotImplemented。
        """
        if isinstance(scalar, (int, float)):
            return Vector(self.x * scalar, self.y * scalar, self.z * scalar)
        return NotImplemented

    __rmul__ = __mul__

    def __truediv__(self, scalar):
        """数値スカラーによる成分ごとの除算を行う。

        Args:
            scalar (object): 除算する int または float。

        Returns:
            Vector | types.NotImplementedType: 成分ごとの商を持つ新しい Vector。未対応型では NotImplemented。

        Raises:
            ZeroDivisionError: scalar が 0 の場合。
        """
        if isinstance(scalar, (int, float)):
            return Vector(self.x / scalar, self.y / scalar, self.z / scalar)
        return NotImplemented

    def __neg__(self):
        """各成分の符号を反転したベクトルを返す。

        Returns:
            Vector: 符号反転後の新しい Vector。派生クラスの型は保持しない。
        """
        return Vector(-self.x, -self.y, -self.z)

    def dot(self, other):
        """別の Vector 系オブジェクトとの内積を返す。

        Args:
            other (Vector): 内積の相手となる Vector。

        Returns:
            float: 内積。
        """
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other):
        """別の Vector 系オブジェクトとの外積を返す。

        Args:
            other (Vector): 外積の相手となる Vector。

        Returns:
            Vector: 外積。派生クラスの型は保持しない。
        """
        return Vector(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length_squared(self):
        """ベクトルの長さの2乗を返す。

        平方根を計算しないため、長さそのものが不要な比較などでは length() より
        高速。

        Returns:
            float: 長さの2乗(自身との内積)。
        """
        return self.dot(self)

    def length(self):
        """ベクトルの長さ(ユークリッドノルム)を返す。

        Returns:
            float: 長さ。
        """
        return math.sqrt(self.length_squared())

    def normalized(self):
        """正規化済みベクトルを返す。

        Returns:
            Vector: 長さ 1 のベクトル。派生クラスの型は保持しない。

        Raises:
            ValueError: ゼロベクトルの場合。
        """
        length = self.length()
        if length == 0.0:
            raise ValueError("Cannot normalize a zero vector")
        return Vector(self.x / length, self.y / length, self.z / length)

    def distance_to(self, other):
        """別の Vector 系オブジェクトとの距離を返す。

        Args:
            other (Vector): 距離を測る相手。

        Returns:
            float: 2点間のユークリッド距離。
        """
        return (self - other).length()

    def angle_to(self, other):
        """別の Vector 系オブジェクトとの成す角度をラジアンで返す。

        Args:
            other (Vector): 角度を測る相手。

        Returns:
            float: 0 から pi の範囲のラジアン角度。

        Raises:
            ValueError: 自身または other がゼロベクトルの場合。
        """
        self_length = self.length()
        other_length = other.length()
        if self_length == 0.0 or other_length == 0.0:
            raise ValueError("Cannot measure the angle to or from a zero vector")
        cosine = self.dot(other) / (self_length * other_length)
        cosine = max(-1.0, min(1.0, cosine))
        return math.acos(cosine)

    def is_equivalent(self, other, tolerance=1e-10):
        """許容誤差付きで別の Vector 系オブジェクトとほぼ等しいか判定する。

        dataclass が生成する ``==`` は完全一致かつ同一クラス同士でしか
        True にならないため、浮動小数点誤差を許容した比較にはこちらを使う。

        Args:
            other (Vector): 比較対象。
            tolerance (float): 各成分の差の許容誤差。

        Returns:
            bool: 全成分の差が tolerance 以下なら True。
        """
        return (
            abs(self.x - other.x) <= tolerance
            and abs(self.y - other.y) <= tolerance
            and abs(self.z - other.z) <= tolerance
        )

    def lerp(self, other, t):
        """別の Vector 系オブジェクトとの線形補間を返す。

        Args:
            other (Vector): 補間先。
            t (float): 補間係数。0 で自身、1 で other。範囲外の値は外挿になる。

        Returns:
            Vector: 補間結果。派生クラスの型は保持しない。
        """
        return self + (other - self) * t
