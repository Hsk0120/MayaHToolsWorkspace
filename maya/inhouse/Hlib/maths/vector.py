"""3成分を保持する汎用ベクトルと基本演算。"""

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
