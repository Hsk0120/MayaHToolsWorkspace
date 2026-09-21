"""Matrix-first transform value using Maya's row-vector convention."""

import math

from .euler_rotation import EulerRotation
from .quaternion import Quaternion
from .scale import Scale
from .shear import Shear
from .translate import Translate
from .vector import Vector


class Matrix:
    """Maya の row-vector 規約を使う実体 4x4 変換行列。

    値は row-major で保持し、translation は index 12、13、14 に配置する。

    Args:
        values (Iterable[float] | om2.MMatrix | None): 16 要素、4x4 行列、または
            Maya MMatrix。省略時は TRS/shear から合成する。
        translate (Iterable[float]): Translate 値。
        rotate (Iterable[float] | Quaternion): Euler 回転値（radian）または四元数。
        rotation (Iterable[float] | None): ``rotate`` の互換別名。
        scale (Iterable[float]): Scale 値。
        shear (Iterable[float]): Shear 値。
    """

    __slots__ = ("_values",)

    def __init__(
        self,
        values=None,
        *,
        translate=(0.0, 0.0, 0.0),
        rotate=(0.0, 0.0, 0.0),
        rotation=None,
        scale=(1.0, 1.0, 1.0),
        shear=(0.0, 0.0, 0.0),
    ):
        """入力行列または TRS/shear 成分から 4x4 行列を初期化する。"""
        if values is not None:
            self._values = self._coerce_values(values)
            return
        if rotation is not None:
            rotate = rotation
        self._values = self._compose_values(translate, rotate, scale, shear)

    @classmethod
    def compose(cls, translate=(0.0, 0.0, 0.0), rotate=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0), shear=(0.0, 0.0, 0.0)):
        """TRS/shear 成分から Matrix を合成する。

        Args:
            translate (Iterable[float]): Translate 値。
            rotate (Iterable[float] | Quaternion): Euler 値または四元数。
            scale (Iterable[float]): Scale 値。
            shear (Iterable[float]): Shear 値。

        Returns:
            Matrix: 合成した 4x4 行列。
        """
        return cls(translate=translate, rotate=rotate, scale=scale, shear=shear)

    @classmethod
    def from_mmatrix(cls, matrix):
        """Create a Matrix from a Maya API 2.0 MMatrix."""
        return cls(matrix)

    @classmethod
    def from_transformation(cls, transformation):
        """Create a Matrix from an API 2.0 MTransformationMatrix."""
        return cls(transformation.asMatrix())

    def to_mmatrix(self):
        """Return an API 2.0 MMatrix for this value.

        Maya is imported lazily so pure-Python math remains usable elsewhere.
        """
        import maya.api.OpenMaya as om2

        return om2.MMatrix(self.rows)

    def to_transformation(self):
        """Return an API 2.0 MTransformationMatrix for this value."""
        import maya.api.OpenMaya as om2

        return om2.MTransformationMatrix(self.to_mmatrix())

    @property
    def values(self):
        """row-major 順の 16 要素を取得する。

        Returns:
            tuple[float, ...]: 4x4 行列の平坦な要素列。
        """
        return tuple(self._values)

    @property
    def rows(self):
        """4x4 行列を行ごとの値として取得する。

        Returns:
            tuple[tuple[float, float, float, float], ...]: 4 行の行列値。
        """
        return tuple(tuple(self._values[row * 4:(row + 1) * 4]) for row in range(4))

    @property
    def translate(self):
        """Translate 成分を取得または設定する。

        Returns:
            Translate: 行列の平行移動成分。
        """
        return Translate(self._values[12], self._values[13], self._values[14])

    @translate.setter
    def translate(self, value):
        """Translate 成分を置き換えて行列を再合成する。"""
        self._recompose(translate=value)

    @property
    def scale(self):
        """Scale 成分を取得または設定する。

        Returns:
            Scale: 分解したスケール成分。
        """
        return self.decompose()["scale"]

    @scale.setter
    def scale(self, value):
        """Scale 成分を置き換えて行列を再合成する。"""
        self._recompose(scale=value)

    @property
    def shear(self):
        """Shear 成分を取得または設定する。

        Returns:
            Shear: 分解した shear 成分。
        """
        return self.decompose()["shear"]

    @shear.setter
    def shear(self, value):
        """Shear 成分を置き換えて行列を再合成する。"""
        self._recompose(shear=value)

    @property
    def quaternion(self):
        """回転成分を Quaternion として取得する。

        Returns:
            Quaternion: 分解した回転値。
        """
        return self.decompose()["quaternion"]

    @property
    def euler(self):
        """回転成分を EulerRotation として取得する。

        Returns:
            EulerRotation: 分解した回転値（radian）。
        """
        return self.quaternion.to_euler()

    @property
    def rotation(self):
        """回転成分を EulerRotation として取得または設定する。

        Returns:
            EulerRotation: 分解した Euler 回転成分（radian）。
        """
        return self.euler

    @rotation.setter
    def rotation(self, value):
        """回転成分を置き換えて行列を再合成する。"""
        self._recompose(rotate=value)

    @property
    def rotate(self):
        """``rotation`` の Maya 風別名を取得または設定する。

        Returns:
            EulerRotation: 分解した Euler 回転成分（radian）。
        """
        return self.rotation

    @rotate.setter
    def rotate(self, value):
        """``rotation`` の Maya 風別名として回転成分を設定する。"""
        self.rotation = value

    def decompose(self):
        """行列を意味付きの変換成分へ分解する。

        Returns:
            dict[str, object]: translate、rotation、quaternion、euler、scale、shear を
            含む辞書。

        Raises:
            ValueError: いずれかのスケール軸がゼロの場合。
        """
        rows = [self._values[index:index + 3] for index in (0, 4, 8)]
        row_x, row_y, row_z = rows

        scale_x = self._length(row_x)
        if scale_x == 0.0:
            raise ValueError("Cannot decompose a matrix with zero X scale")
        axis_x = self._divide(row_x, scale_x)

        shear_xy_raw = self._dot(axis_x, row_y)
        row_y = self._subtract(row_y, self._multiply(axis_x, shear_xy_raw))
        scale_y = self._length(row_y)
        if scale_y == 0.0:
            raise ValueError("Cannot decompose a matrix with zero Y scale")
        axis_y = self._divide(row_y, scale_y)

        shear_xz_raw = self._dot(axis_x, row_z)
        row_z = self._subtract(row_z, self._multiply(axis_x, shear_xz_raw))
        shear_yz_raw = self._dot(axis_y, row_z)
        row_z = self._subtract(row_z, self._multiply(axis_y, shear_yz_raw))
        scale_z = self._length(row_z)
        if scale_z == 0.0:
            raise ValueError("Cannot decompose a matrix with zero Z scale")
        axis_z = self._divide(row_z, scale_z)

        if self._dot(self._cross(axis_x, axis_y), axis_z) < 0.0:
            scale_x = -scale_x
            axis_x = self._multiply(axis_x, -1.0)

        quaternion = self._quaternion_from_row_axes(axis_x, axis_y, axis_z)
        euler = quaternion.to_euler()
        return {
            "translate": self.translate,
            "rotation": euler,
            "quaternion": quaternion,
            "euler": euler,
            "scale": Scale(scale_x, scale_y, scale_z),
            "shear": Shear(shear_xy_raw / scale_y, shear_xz_raw / scale_z, shear_yz_raw / scale_z),
        }

    def inverse(self):
        """Return the inverse matrix, raising ValueError when singular."""
        augmented = [
            self._values[row * 4:(row + 1) * 4] + [1.0 if row == column else 0.0 for column in range(4)]
            for row in range(4)
        ]
        for column in range(4):
            pivot_row = max(range(column, 4), key=lambda row: abs(augmented[row][column]))
            if abs(augmented[pivot_row][column]) < 1e-12:
                raise ValueError("Matrix is singular and cannot be inverted")
            augmented[column], augmented[pivot_row] = augmented[pivot_row], augmented[column]
            pivot = augmented[column][column]
            augmented[column] = [value / pivot for value in augmented[column]]
            for row in range(4):
                if row == column:
                    continue
                factor = augmented[row][column]
                augmented[row] = [value - factor * pivot_value for value, pivot_value in zip(augmented[row], augmented[column])]
        return type(self)([value for row in augmented for value in row[4:]])

    def transpose(self):
        """Return a transposed copy of this matrix."""
        return type(self)([self._values[column * 4 + row] for row in range(4) for column in range(4)])

    def transform_point(self, value):
        """Transform a position using homogeneous coordinate $w = 1$."""
        x, y, z = value
        return Translate(
            x * self._values[0] + y * self._values[4] + z * self._values[8] + self._values[12],
            x * self._values[1] + y * self._values[5] + z * self._values[9] + self._values[13],
            x * self._values[2] + y * self._values[6] + z * self._values[10] + self._values[14],
        )

    def transform_vector(self, value):
        """Transform a direction using homogeneous coordinate $w = 0$."""
        x, y, z = value
        return Vector(
            x * self._values[0] + y * self._values[4] + z * self._values[8],
            x * self._values[1] + y * self._values[5] + z * self._values[9],
            x * self._values[2] + y * self._values[6] + z * self._values[10],
        )

    def __iter__(self):
        """row-major 順の 16 行列要素を反復する。"""
        return iter(self._values)

    def __len__(self):
        """4x4 行列の要素数である 16 を返す。"""
        return 16

    def __getitem__(self, index):
        """行列要素を取得する。

        Args:
            index (int | tuple[int, int]): 平坦な要素インデックス、または ``(row, column)``。

        Returns:
            float: 指定要素。
        """
        if isinstance(index, tuple):
            row, column = index
            return self._values[row * 4 + column]
        return self._values[index]

    def __eq__(self, other):
        """別の Matrix との全要素一致を判定する。"""
        if not isinstance(other, Matrix):
            return NotImplemented
        return self.values == other.values

    def __repr__(self):
        """4 行の値を含むデバッグ表現を返す。"""
        return f"Matrix({self.rows!r})"

    def __mul__(self, other):
        """Matrix 積、または Vector を位置として変換した値を返す。"""
        if isinstance(other, Matrix):
            return type(self)([
                sum(self[row, inner] * other[inner, column] for inner in range(4))
                for row in range(4)
                for column in range(4)
            ])
        if isinstance(other, Vector):
            return self.transform_point(other)
        return NotImplemented

    def _recompose(self, *, translate=None, rotate=None, scale=None, shear=None):
        """既存分解値の一部を置換して内部 4x4 値を再合成する。"""
        components = self.decompose()
        self._values = self._compose_values(
            components["translate"] if translate is None else translate,
            components["euler"] if rotate is None else rotate,
            components["scale"] if scale is None else scale,
            components["shear"] if shear is None else shear,
        )

    @classmethod
    def _compose_values(cls, translate, rotate, scale, shear):
        """TRS/shear 成分を Maya row-vector 規約の 16 要素へ変換する。"""
        translation = Translate(*translate)
        scale = Scale(*scale)
        shear = Shear(*shear)
        quaternion = rotate if isinstance(rotate, Quaternion) else EulerRotation(*rotate).to_quaternion()
        rotation_rows = cls._row_rotation_matrix(quaternion.normalized())
        shear_scale_rows = (
            (scale.x, 0.0, 0.0),
            (scale.y * shear.x, scale.y, 0.0),
            (scale.z * shear.y, scale.z * shear.z, scale.z),
        )
        linear = [
            [sum(shear_scale_rows[row][inner] * rotation_rows[inner][column] for inner in range(3)) for column in range(3)]
            for row in range(3)
        ]
        return [
            linear[0][0], linear[0][1], linear[0][2], 0.0,
            linear[1][0], linear[1][1], linear[1][2], 0.0,
            linear[2][0], linear[2][1], linear[2][2], 0.0,
            translation.x, translation.y, translation.z, 1.0,
        ]

    @staticmethod
    def _coerce_values(values):
        """MMatrix、4x4 行、または 16 要素入力を平坦な float 配列へ正規化する。"""
        try:
            rows = [tuple(values[row]) for row in range(4)]
        except (TypeError, IndexError):
            rows = None
        if rows is not None and all(len(row) == 4 for row in rows):
            return [float(value) for row in rows for value in row]
        flattened = tuple(values)
        if len(flattened) != 16:
            raise ValueError("Matrix expects an MMatrix, 4x4 rows, or 16 values")
        return [float(value) for value in flattened]

    @staticmethod
    def _row_rotation_matrix(quaternion):
        """四元数から row-vector 規約の 3x3 回転行列を生成する。"""
        x, y, z, w = quaternion
        return (
            (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y + z * w), 2.0 * (x * z - y * w)),
            (2.0 * (x * y - z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z + x * w)),
            (2.0 * (x * z + y * w), 2.0 * (y * z - x * w), 1.0 - 2.0 * (x * x + y * y)),
        )

    @classmethod
    def _quaternion_from_row_axes(cls, axis_x, axis_y, axis_z):
        """直交化済み行軸から Quaternion を復元する。"""
        matrix = ((axis_x[0], axis_y[0], axis_z[0]), (axis_x[1], axis_y[1], axis_z[1]), (axis_x[2], axis_y[2], axis_z[2]))
        trace = matrix[0][0] + matrix[1][1] + matrix[2][2]
        if trace > 0.0:
            root = math.sqrt(trace + 1.0) * 2.0
            return Quaternion((matrix[2][1] - matrix[1][2]) / root, (matrix[0][2] - matrix[2][0]) / root, (matrix[1][0] - matrix[0][1]) / root, 0.25 * root)
        if matrix[0][0] > matrix[1][1] and matrix[0][0] > matrix[2][2]:
            root = math.sqrt(1.0 + matrix[0][0] - matrix[1][1] - matrix[2][2]) * 2.0
            return Quaternion(0.25 * root, (matrix[0][1] + matrix[1][0]) / root, (matrix[0][2] + matrix[2][0]) / root, (matrix[2][1] - matrix[1][2]) / root)
        if matrix[1][1] > matrix[2][2]:
            root = math.sqrt(1.0 + matrix[1][1] - matrix[0][0] - matrix[2][2]) * 2.0
            return Quaternion((matrix[0][1] + matrix[1][0]) / root, 0.25 * root, (matrix[1][2] + matrix[2][1]) / root, (matrix[0][2] - matrix[2][0]) / root)
        root = math.sqrt(1.0 + matrix[2][2] - matrix[0][0] - matrix[1][1]) * 2.0
        return Quaternion((matrix[0][2] + matrix[2][0]) / root, (matrix[1][2] + matrix[2][1]) / root, 0.25 * root, (matrix[1][0] - matrix[0][1]) / root)

    @staticmethod
    def _dot(left, right):
        """同じ長さの数列の内積を返す。"""
        return sum(a * b for a, b in zip(left, right))

    @classmethod
    def _length(cls, value):
        """数列のユークリッド長を返す。"""
        return math.sqrt(cls._dot(value, value))

    @staticmethod
    def _multiply(value, scalar):
        """数列の各成分へスカラーを乗算する。"""
        return [component * scalar for component in value]

    @staticmethod
    def _divide(value, scalar):
        """数列の各成分をスカラーで除算する。"""
        return [component / scalar for component in value]

    @staticmethod
    def _subtract(left, right):
        """同じ長さの数列を成分ごとに減算する。"""
        return [a - b for a, b in zip(left, right)]

    @staticmethod
    def _cross(left, right):
        """3 次元数列の外積を返す。"""
        return [
            left[1] * right[2] - left[2] * right[1],
            left[2] * right[0] - left[0] * right[2],
            left[0] * right[1] - left[1] * right[0],
        ]