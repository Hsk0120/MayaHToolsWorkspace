"""シーン上の単体コンポーネントと同一シェイプの要素群。"""

import math
import operator


class Component:
    """シェイプと番号を保持する単体コンポーネントへの参照。"""

    shape_type = None
    component_type = None
    count_attribute = None

    def __init__(self, shape, index):
        """シェイプと実際のコンポーネント番号を保持する。

        Args:
            shape (Shape): 対応する Mesh または NurbsCurve ラッパー。
            index (int): ゼロ始まりの番号。負の番号は不可。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: シェイプ型または番号の型が不正な場合。
            IndexError: 番号が範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        self._shape = shape
        if isinstance(index, bool):
            raise TypeError("Component index must be an integer, not bool")
        self._index = operator.index(index)
        self._validate()

    @property
    def shape(self):
        """所有シェイプを取得する。

        Returns:
            Shape: 保持しているラッパー。
        """
        return self._shape

    @property
    def index(self):
        """コンポーネントの実番号を取得する。

        Returns:
            int: ゼロ始まりの番号。
        """
        return self._index

    def _validate(self):
        """現在のシェイプ型と番号を再検査する。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 対応しないシェイプ型の場合。
            IndexError: 番号が現在の要素数の範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        if not callable(getattr(self._shape, "is_valid", None)):
            raise TypeError("shape must be an hlib shape wrapper")
        if not self._shape.is_valid():
            raise RuntimeError("Component shape is invalid")
        if self._shape.type() != self.shape_type:
            raise TypeError(f"Expected a {self.shape_type} shape")
        if not 0 <= self._index < getattr(self._shape, self.count_attribute):
            raise IndexError(f"Component index out of range: {self._index}")

    @property
    def full_name(self):
        """現在の DAG パスを使ってコンポーネント名を取得する。

        Returns:
            str: シェイプの完全パスとコンポーネントの種類・番号を含む名前。
        """
        self._validate()
        return f"{self._shape.full_name}.{self.component_type}[{self._index}]"

    def __str__(self):
        """コンポーネント名を返す。

        Returns:
            str: 現在の完全パス付きコンポーネント名。
        """
        return self.full_name


    @staticmethod
    def _finite_coordinates(value, size):
        """有限な座標列に変換する。

        Args:
            value (Iterable[float]): 入力座標。
            size (int): 必要な成分数。

        Returns:
            tuple[float, ...]: 検証済み座標。

        Raises:
            ValueError: 成分数や数値が不正な場合。
        """
        try:
            result = tuple(float(item) for item in value)
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid coordinates") from error
        if len(result) != size or not all(math.isfinite(item) for item in result):
            raise ValueError(f"Expected {size} finite coordinates")
        return result


class Components:
    """同一シェイプ内の番号を作成時に固定して保持するコレクション。

    同じ種類の要素を保持する基底クラス。トポロジー変更後の番号の同一性は保証しない。
    """

    component_class = Component

    def __init__(self, shape, indices=None):
        """番号の順序を維持し、重複を除いて保持する。

        Args:
            shape (Shape): 対応するシェイプラッパー。
            indices (Iterable[int] | None): 実番号。None は作成時の全要素、空列は空集合。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: シェイプまたは番号の型が不正な場合。
            IndexError: 番号が範囲外の場合。
            RuntimeError: シェイプが無効な場合。
        """
        self._shape = shape
        if not callable(getattr(shape, "is_valid", None)):
            raise TypeError("shape must be an hlib shape wrapper")
        if not shape.is_valid():
            raise RuntimeError("Component shape is invalid")
        if shape.type() != self.component_class.shape_type:
            raise TypeError(f"Expected a {self.component_class.shape_type} shape")
        selected = range(getattr(shape, self.component_class.count_attribute)) if indices is None else indices
        self._indices = tuple(dict.fromkeys(self.component_class(shape, index).index for index in selected))

    @property
    def shape(self):
        """所有シェイプを取得する。

        Returns:
            Shape: 保持しているシェイプ。
        """
        return self._shape

    @property
    def indices(self):
        """保持している実番号を取得する。

        Returns:
            tuple[int, ...]: 順序を維持した重複なしの番号列。
        """
        return self._indices

    def __len__(self):
        """保持要素数を取得する。

        Returns:
            int: コレクションの要素数。
        """
        return len(self._indices)

    @property
    def full_names(self):
        """list[str]: 保持順の完全コンポーネント名。全要素を再検証する。"""
        return [item.full_name for item in self]

    def _coordinate_rows(self, values, size):
        """要素別座標を全件検証する。個数・座標不正はValueError。

        Args:
            values (Iterable[Iterable[float]]): 保持順の座標列。
            size (int): 1座標の成分数。
        Returns:
            list[tuple[float, ...]]: 検証済みの座標列。
        """
        rows = [Component._finite_coordinates(value, size) for value in values]
        if len(rows) != len(self):
            raise ValueError("Coordinate count must match component count")
        return rows

    def _axis_rows(self, positions, axis, value):
        """軸の一括設定用座標を作る。スカラーは全要素、列は保持順に対応する。

        Args:
            positions (Iterable[Iterable[float]]): 現在座標。
            axis (int): 成分番号。
            value (float | Iterable[float]): 軸の値。
        Returns:
            list[list[float]]: 更新後の座標列。シーンは変更しない。
        """
        try:
            values = list(value)
        except TypeError:
            values = [value] * len(self)
        if len(values) != len(self):
            raise ValueError("Axis value count must match component count")
        rows = [list(position) for position in positions]
        for row, item in zip(rows, values):
            row[axis] = item
        return rows

    def __iter__(self):
        """保持順に単体ラッパーを返す。

        Yields:
            Component: 現在のシェイプと番号を参照するラッパー。
        """
        for index in self._indices:
            yield self.component_class(self._shape, index)

    def __getitem__(self, index):
        """コレクション内の位置で要素を取得する。

        Args:
            index (int | slice): 実番号ではなく保持列内の位置。負の添字にも対応する。

        Returns:
            Component | Components: 単体、または同じ型の部分コレクション。

        Raises:
            IndexError: 添字が範囲外の場合。
        """
        if isinstance(index, slice):
            return type(self)(self._shape, self._indices[index])
        return self.component_class(self._shape, self._indices[index])
