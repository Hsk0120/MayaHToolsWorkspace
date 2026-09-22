"""3成分を保持する汎用ベクトルと基本演算。"""


class Vector:
    """3成分のベクトル値。

    3要素入力では各値をそのまま保持し、個別の成分指定では float に変換する。
    加減算・スカラー乗算の結果は、派生クラスでも常に Vector となる。"""

    __slots__ = ("x", "y", "z")

    def __init__(self, x, y=None, z=None):
        """3 成分または 3 要素シーケンスからベクトルを初期化する。

        3要素入力は各成分をそのまま保持する。x、y、z を個別に指定した場合のみ float に変換する。

        Args:
            x (float | Iterable[float]): X 成分、または3成分の反復可能オブジェクト。
            y (float | None): Y 成分。3成分入力の場合は省略する。
            z (float | None): Z 成分。3成分入力の場合は省略する。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 反復可能入力が3要素でない場合、または数値変換に失敗した場合。
            TypeError: 3成分指定で y または z だけを省略した場合など、float 変換できない場合。
        """
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
        """X、Y、Z の順で成分を反復する。

        Yields:
            object: X、Y、Z 順の保持値。通常は数値。3要素入力では元の型を維持する。
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

    def __eq__(self, other):
        """同じ Vector 系オブジェクトとの成分一致を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: Vector 同士の成分の完全一致。異なる型では NotImplemented。許容誤差は使わない。
        """
        if not isinstance(other, Vector):
            return NotImplemented
        return tuple(self) == tuple(other)

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
