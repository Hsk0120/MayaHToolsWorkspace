"""Generic three-dimensional vector value."""


class Vector:
    """3 次元ベクトル値。

    Args:
        x (float | Iterable[float]): X 値、または 3 要素のシーケンス。
        y (float | None): Y 値。
        z (float | None): Z 値。

    Raises:
        ValueError: シーケンスの要素数が 3 でない場合。
    """

    __slots__ = ("x", "y", "z")

    def __init__(self, x, y=None, z=None):
        """3 成分または 3 要素シーケンスからベクトルを初期化する。"""
        if y is None and z is None:
            values = tuple(x)
            if len(values) != 3:
                raise ValueError("Vector expects 3 values")
            self.x, self.y, self.z = values
        else:
            self.x = float(x)
            self.y = float(y)
            self.z = float(z)

    def __iter__(self):
        """X、Y、Z の順で成分を反復する。"""
        yield self.x
        yield self.y
        yield self.z

    def __len__(self):
        """ベクトル成分数の 3 を返す。"""
        return 3

    def __getitem__(self, index):
        """指定インデックスのベクトル成分を返す。"""
        return (self.x, self.y, self.z)[index]

    def __repr__(self):
        """クラス名と 3 成分を含むデバッグ表現を返す。"""
        return f"{type(self).__name__}({self.x}, {self.y}, {self.z})"

    def __str__(self):
        """デバッグ表現と同じ文字列表現を返す。"""
        return repr(self)

    def __eq__(self, other):
        """同じ Vector 系オブジェクトとの成分一致を判定する。"""
        if not isinstance(other, Vector):
            return NotImplemented
        return tuple(self) == tuple(other)

    def __add__(self, other):
        """別の Vector 系オブジェクトとの成分ごとの加算を行う。"""
        if not isinstance(other, Vector):
            return NotImplemented
        return Vector(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other):
        """別の Vector 系オブジェクトとの成分ごとの減算を行う。"""
        if not isinstance(other, Vector):
            return NotImplemented
        return Vector(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar):
        """数値スカラーによる成分ごとの乗算を行う。"""
        if isinstance(scalar, (int, float)):
            return Vector(self.x * scalar, self.y * scalar, self.z * scalar)
        return NotImplemented

    __rmul__ = __mul__