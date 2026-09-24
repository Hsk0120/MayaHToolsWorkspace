"""Maya の行ベクトル規約を使う4行4列の変換行列。"""

import math

from .eulerRotation import EulerRotation
from .quaternion import Quaternion
from .scale import Scale
from .shear import Shear
from .translate import Translate
from .vector import Vector


class Matrix:
    """Maya の行ベクトル規約を使う4行4列の変換行列。

    行優先順で16要素を保持し、平行移動は添字12、13、14に配置する。
    成分からの合成と分解はアフィン変換を想定する。"""

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
        """入力行列または TRS/shear 成分から 4x4 行列を初期化する。

        Args:
            values (Matrix | Iterable[float] | Iterable[Iterable[float]] | om2.MMatrix | None): 16要素または4行4列の行列。指定時は他の変換引数をすべて無視する。
            translate (Iterable[float]): XYZ の平行移動成分。
            rotate (Iterable[float] | Quaternion): XYZ 順のラジアン3成分、または四元数。EulerRotation の order は引き継がない。
            scale (Iterable[float]): XYZ のスケール成分。
            shear (Iterable[float]): XY、XZ、YZ のシアー成分。
            rotation (Iterable[float] | Quaternion | None): rotate の互換引数。None 以外なら rotate より優先する。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 行列入力が16要素に変換できない場合、または回転四元数がゼロの場合。
        """
        if values is not None:
            self._values = self._coerce_values(values)
            return
        if rotation is not None:
            rotate = rotation
        self._values = self._compose_values(translate, rotate, scale, shear)

    @classmethod
    def identity(cls):
        """単位行列を生成する。

        引数なしの ``Matrix()`` と同じ結果だが、意図を明示できる。

        Returns:
            Matrix: 呼び出したクラスの単位行列。
        """
        return cls()

    @classmethod
    def compose(cls, translate=(0.0, 0.0, 0.0), rotate=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0), shear=(0.0, 0.0, 0.0)):
        """TRS/shear 成分から Matrix を合成する。

        Args:
            translate (Iterable[float]): XYZ の平行移動成分。
            rotate (Iterable[float] | Quaternion): XYZ 順のラジアン3成分、または四元数。EulerRotation の order は引き継がない。
            scale (Iterable[float]): XYZ のスケール成分。
            shear (Iterable[float]): XY、XZ、YZ のシアー成分。

        Returns:
            Matrix: 呼び出したクラスの新しい4行4列行列。

        Raises:
            ValueError: 回転四元数がゼロの場合。
        """
        return cls(translate=translate, rotate=rotate, scale=scale, shear=shear)

    @classmethod
    def from_mmatrix(cls, matrix):
        """Maya API 2.0 の行列を hlib の行列へ変換する。

        Args:
            matrix (om2.MMatrix): コピー元の行列。

        Returns:
            Matrix: 呼び出したクラスの新しい行列。
        """
        return cls(matrix)

    @classmethod
    def from_transformation(cls, transformation):
        """Maya API 2.0 の変換行列から hlib の行列を生成する。

        Args:
            transformation (om2.MTransformationMatrix): asMatrix() で値を取得する変換行列。

        Returns:
            Matrix: 呼び出したクラスの新しい行列。
        """
        return cls(transformation.asMatrix())

    def to_mmatrix(self):
        """Maya API 2.0 の行列オブジェクトへ変換する。

        このメソッドの呼び出し時にだけ Maya API を読み込む。

        Returns:
            om2.MMatrix: 現在の成分から作成した新しいオブジェクト。

        Raises:
            ImportError: Maya API 2.0 を利用できない環境の場合。
        """
        import maya.api.OpenMaya as om2

        return om2.MMatrix(self.rows)

    def to_transformation(self):
        """Maya API 2.0 の行列オブジェクトへ変換する。

        このメソッドの呼び出し時にだけ Maya API を読み込む。

        Returns:
            om2.MTransformationMatrix: 現在の成分から作成した新しいオブジェクト。

        Raises:
            ImportError: Maya API 2.0 を利用できない環境の場合。
        """
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

        設定時は3成分の反復可能オブジェクトを受け取り、現在の行列を
        分解して平行移動を置き換える。ゼロスケールなどで分解できなければ
        ValueError を送出する。

        Returns:
            Translate: 行列の平行移動成分。
        """
        return Translate(self._values[12], self._values[13], self._values[14])

    @translate.setter
    def translate(self, value):
        """Translate 成分を置き換えて行列を再合成する。

        現在の行列を分解してから指定成分を置換し、再合成して自身を更新する。

        Args:
            value (Iterable[float]): 新しい平行移動。3成分。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 現在の行列を分解できない場合。
        """
        self._recompose(translate=value)

    @property
    def scale(self):
        """Scale 成分を取得または設定する。

        設定時は XYZ の3成分を受け取り、既存の分解値のスケールを置換する。
        取得・設定とも、行列を分解できない場合は ValueError を送出する。

        Returns:
            Scale: 分解したスケール成分。
        """
        return self.decompose()["scale"]

    @scale.setter
    def scale(self, value):
        """Scale 成分を置き換えて行列を再合成する。

        現在の行列を分解してから指定成分を置換し、再合成して自身を更新する。

        Args:
            value (Iterable[float]): 新しいスケール。3成分。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 現在の行列を分解できない場合。
        """
        self._recompose(scale=value)

    @property
    def shear(self):
        """Shear 成分を取得または設定する。

        設定時は XY、XZ、YZ の3成分を受け取り、既存の分解値のシアーを置換する。
        取得・設定とも、行列を分解できない場合は ValueError を送出する。

        Returns:
            Shear: 分解した shear 成分。
        """
        return self.decompose()["shear"]

    @shear.setter
    def shear(self, value):
        """Shear 成分を置き換えて行列を再合成する。

        現在の行列を分解してから指定成分を置換し、再合成して自身を更新する。

        Args:
            value (Iterable[float]): 新しいシアー。3成分。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 現在の行列を分解できない場合。
        """
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

        設定時は XYZ のラジアン3成分または Quaternion を受け取る。
        EulerRotation を渡した場合も order は引き継がず、XYZ 順で解釈する。
        取得・設定とも、行列を分解できない場合は ValueError を送出する。

        Returns:
            EulerRotation: 分解した Euler 回転成分（radian）。
        """
        return self.euler

    @rotation.setter
    def rotation(self, value):
        """回転成分を置き換えて行列を再合成する。

        現在の行列を分解してから指定成分を置換し、再合成して自身を更新する。

        Args:
            value (Iterable[float] | Quaternion): 新しい回転。ラジアンの XYZ 3成分または四元数。EulerRotation の order は引き継がない。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 現在の行列を分解できない場合。
        """
        self._recompose(rotate=value)

    @property
    def rotate(self):
        """``rotation`` の Maya 風別名を取得または設定する。

        設定値はラジアンの XYZ 3成分または Quaternion。
        変換規約と例外は rotation と同じ。

        Returns:
            EulerRotation: 分解した Euler 回転成分（radian）。
        """
        return self.rotation

    @rotate.setter
    def rotate(self, value):
        """``rotation`` の Maya 風別名として回転成分を設定する。

        現在の行列を分解してから指定成分を置換し、再合成して自身を更新する。

        Args:
            value (Iterable[float] | Quaternion): 新しい回転。ラジアンの XYZ 3成分または四元数。EulerRotation の order は引き継がない。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 現在の行列を分解できない場合。
        """
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

    def determinant(self):
        """行列式を返す。

        1行目に沿った余因子展開で計算する。

        Returns:
            float: 4x4 行列式。
        """
        rows = self.rows
        sign = 1.0
        total = 0.0
        for column in range(4):
            minor = [[rows[row][c] for c in range(4) if c != column] for row in range(1, 4)]
            total += sign * rows[0][column] * self._determinant3x3(minor)
            sign = -sign
        return total

    @staticmethod
    def _determinant3x3(rows):
        """3x3 行列式を返す。

        Args:
            rows (Sequence[Sequence[float]]): 3行3列の値。

        Returns:
            float: 3x3 行列式。
        """
        (a, b, c), (d, e, f), (g, h, i) = rows
        return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)

    def is_equivalent(self, other, tolerance=1e-10):
        """許容誤差付きで別の Matrix とほぼ等しいか判定する。

        ``__eq__`` は完全一致のみを判定するため、浮動小数点誤差を許容した
        比較にはこちらを使う。

        Args:
            other (Matrix): 比較対象。
            tolerance (float): 各成分の差の許容誤差。

        Returns:
            bool: 全16成分の差が tolerance 以下なら True。
        """
        return all(abs(a - b) <= tolerance for a, b in zip(self, other))

    def inverse(self):
        """逆行列を新しいインスタンスとして返す。

        Returns:
            Matrix: 自身と同じクラスの逆行列。

        Raises:
            ValueError: 消去法のピボットの絶対値が 1e-12 未満の場合。
        """
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
        """転置した行列のコピーを返す。

        Returns:
            Matrix: 自身と同じクラスの転置行列。
        """
        return type(self)([self._values[column * 4 + row] for row in range(4) for column in range(4)])

    def transform_point(self, value):
        """行ベクトル規約で位置を変換する。

        同次座標の w を 1 として扱う。

        Args:
            value (Iterable[float]): XYZ の3成分。

        Returns:
            Translate: 平行移動を含む変換結果。射影除算は行わない。
        """
        x, y, z = value
        return Translate(
            x * self._values[0] + y * self._values[4] + z * self._values[8] + self._values[12],
            x * self._values[1] + y * self._values[5] + z * self._values[9] + self._values[13],
            x * self._values[2] + y * self._values[6] + z * self._values[10] + self._values[14],
        )

    def transform_vector(self, value):
        """行ベクトル規約で方向を変換する。

        同次座標の w を 0 として扱う。

        Args:
            value (Iterable[float]): XYZ の3成分。

        Returns:
            Vector: 平行移動を含まない変換結果。
        """
        x, y, z = value
        return Vector(
            x * self._values[0] + y * self._values[4] + z * self._values[8],
            x * self._values[1] + y * self._values[5] + z * self._values[9],
            x * self._values[2] + y * self._values[6] + z * self._values[10],
        )

    def mirrored(self, axis=0):
        """指定したワールド軸に対する「ビヘイビア」ミラー行列を返す。

        平行移動は axis 成分を反転し、回転行列の各行(ローカル軸)は axis 以外の
        2成分を反転する。Maya の ``mirrorJoint -mirrorBehavior`` と同じ規約で、
        軸そのものは反転せず 180 度回転した姿勢になるため、行列式の符号は保存される
        (幾何学的な鏡像とは異なり、対になったノードを同じローカル操作で
        対称に動かせる)。スケール・シアーは変更しない。

        Args:
            axis (int): 鏡映面の法線となる軸。0 で X、1 で Y、2 で Z。

        Returns:
            Matrix: 呼び出したクラスのミラー後の行列。

        Raises:
            ValueError: axis が 0/1/2 以外、またはいずれかのスケール軸がゼロで
                分解できない場合。
        """
        if axis not in (0, 1, 2):
            raise ValueError("axis must be 0, 1, or 2")
        components = self.decompose()
        translate = list(components["translate"])
        translate[axis] = -translate[axis]
        rows = [list(row) for row in self._row_rotation_matrix(components["quaternion"].normalized())]
        for row in rows:
            for other in range(3):
                if other != axis:
                    row[other] = -row[other]
        quaternion = self._quaternion_from_row_axes(*rows)
        return type(self).compose(
            translate=translate,
            rotate=quaternion,
            scale=components["scale"],
            shear=components["shear"],
        )

    def __iter__(self):
        """row-major 順の 16 行列要素を反復する。

        Returns:
            Iterator[float]: 行優先順の16要素を走査するイテレータ。
        """
        return iter(self._values)

    def __len__(self):
        """4x4 行列の要素数である 16 を返す。

        Returns:
            int: 常に16。
        """
        return 16

    def __getitem__(self, index):
        """行列要素を取得する。

        行・列を個別に範囲検査しない。負の添字は内部リストの規約に従う。

        Args:
            index (int | slice | tuple[int, int]): 平坦な添字、スライス、または (行, 列)。タプルは 行 * 4 + 列 に変換する。

        Returns:
            float | list[float]: 指定要素。スライスでは新しいリスト。

        Raises:
            IndexError: 変換後の平坦な添字が範囲外の場合。
        """
        if isinstance(index, tuple):
            row, column = index
            return self._values[row * 4 + column]
        return self._values[index]

    def __eq__(self, other):
        """別の Matrix との全要素一致を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: Matrix 同士の成分の完全一致。異なる型では NotImplemented。許容誤差は使わない。
        """
        if not isinstance(other, Matrix):
            return NotImplemented
        return self.values == other.values

    def __repr__(self):
        """4 行の値を含むデバッグ表現を返す。

        Returns:
            str: 型名と現在の成分を含む文字列表現。
        """
        return f"Matrix({self.rows!r})"

    def __mul__(self, other):
        """Matrix 積、または Vector を位置として変換した値を返す。

        Args:
            other (object): 右側の Matrix、または位置として扱う Vector。

        Returns:
            Matrix | Translate | types.NotImplementedType: 行列同士は自身と同じクラスの積。Vector は平行移動を含む位置変換。未対応型は NotImplemented。
        """
        if isinstance(other, Matrix):
            return type(self)([
                sum(self[row, inner] * other[inner, column] for inner in range(4))
                for row in range(4)
                for column in range(4)
            ])
        if isinstance(other, Vector):
            return self.transform_point(other)
        return NotImplemented

    def __matmul__(self, other):
        """``@`` 演算子による行列積、または Vector の位置変換を行う。

        ``__mul__`` と同じ処理に委譲する(numpy 等に倣った ``@`` 演算子対応)。

        Args:
            other (object): 右側の Matrix、または位置として扱う Vector。

        Returns:
            Matrix | Translate | types.NotImplementedType: ``__mul__`` と同じ。
        """
        return self.__mul__(other)

    def _recompose(self, *, translate=None, rotate=None, scale=None, shear=None):
        """既存分解値の一部を置換して内部 4x4 値を再合成する。

        Args:
            translate (Iterable[float] | None): XYZ の平行移動成分。None なら現在の分解値を使う。
            rotate (Iterable[float] | Quaternion | None): XYZ 順のラジアン3成分、または四元数。None なら現在の分解値を使う。EulerRotation の order は引き継がない。
            scale (Iterable[float] | None): XYZ のスケール成分。None なら現在の分解値を使う。
            shear (Iterable[float] | None): XY、XZ、YZ のシアー成分。None なら現在の分解値を使う。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 現在の行列を分解できない場合、または回転四元数がゼロの場合。
        """
        components = self.decompose()
        self._values = self._compose_values(
            components["translate"] if translate is None else translate,
            components["euler"] if rotate is None else rotate,
            components["scale"] if scale is None else scale,
            components["shear"] if shear is None else shear,
        )

    @classmethod
    def _compose_values(cls, translate, rotate, scale, shear):
        """TRS/shear 成分を Maya row-vector 規約の 16 要素へ変換する。

        Args:
            translate (Iterable[float]): XYZ の平行移動成分。
            rotate (Iterable[float] | Quaternion): XYZ 順のラジアン3成分、または四元数。EulerRotation の order は引き継がない。
            scale (Iterable[float]): XYZ のスケール成分。
            shear (Iterable[float]): XY、XZ、YZ のシアー成分。

        Returns:
            list[float]: 行優先順の16要素。平行移動は添字12〜14。

        Raises:
            ValueError: 回転四元数がゼロの場合。
        """
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
        """MMatrix、4x4 行、または 16 要素入力を平坦な float 配列へ正規化する。

        Args:
            values (Iterable): 16要素、4行4列の入力、または MMatrix。

        Returns:
            list[float]: float に変換した行優先順の16要素。

        Raises:
            ValueError: 16要素として解釈できない場合、または float 変換に失敗した場合。
            TypeError: 入力が反復不可能、または要素が float 変換できない型の場合。
        """
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
        """四元数から row-vector 規約の 3x3 回転行列を生成する。

        Args:
            quaternion (Quaternion): 正規化済みの四元数。このメソッド内では正規化しない。

        Returns:
            tuple[tuple[float, float, float], ...]: 行ベクトル規約の3行3列回転行列。
        """
        x, y, z, w = quaternion
        return (
            (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y + z * w), 2.0 * (x * z - y * w)),
            (2.0 * (x * y - z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z + x * w)),
            (2.0 * (x * z + y * w), 2.0 * (y * z - x * w), 1.0 - 2.0 * (x * x + y * y)),
        )

    @classmethod
    def _quaternion_from_row_axes(cls, axis_x, axis_y, axis_z):
        """直交化済み行軸から Quaternion を復元する。

        Args:
            axis_x (Sequence[float]): 直交化済みの X 行軸の3成分。
            axis_y (Sequence[float]): 直交化済みの Y 行軸の3成分。
            axis_z (Sequence[float]): 直交化済みの Z 行軸の3成分。

        Returns:
            Quaternion: 行軸から復元した四元数。追加の正規化は行わない。
        """
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
        """対応する成分の内積を計算する。

        zip を使うため、長さが異なる場合は短い方の要素数まで計算する。

        Args:
            left (Sequence[float]): 左側の成分列。
            right (Sequence[float]): 右側の成分列。

        Returns:
            float: 対応する成分の積の和。
        """
        return sum(a * b for a, b in zip(left, right))

    @classmethod
    def _length(cls, value):
        """数列のユークリッド長を返す。

        Args:
            value (Sequence[float]): 長さを求める成分列。

        Returns:
            float: 二乗和の平方根。
        """
        return math.sqrt(cls._dot(value, value))

    @staticmethod
    def _multiply(value, scalar):
        """数列の各成分へスカラーを乗算する。

        Args:
            value (Iterable[float]): 演算対象の成分列。
            scalar (float): 各成分に適用するスカラー。

        Returns:
            list[float]: 演算後の成分を格納した新しいリスト。
        """
        return [component * scalar for component in value]

    @staticmethod
    def _divide(value, scalar):
        """数列の各成分をスカラーで除算する。

        Args:
            value (Iterable[float]): 演算対象の成分列。
            scalar (float): 各成分に適用するスカラー。

        Returns:
            list[float]: 演算後の成分を格納した新しいリスト。

        Raises:
            ZeroDivisionError: scalar がゼロで、演算対象の成分がある場合。
        """
        return [component / scalar for component in value]

    @staticmethod
    def _subtract(left, right):
        """対応する成分同士を減算する。

        zip を使うため、長さが異なる場合は短い方の要素数まで計算する。

        Args:
            left (Sequence[float]): 左側の成分列。
            right (Sequence[float]): 右側の成分列。

        Returns:
            list[float]: 左から右を引いた成分列。
        """
        return [a - b for a, b in zip(left, right)]

    @staticmethod
    def _cross(left, right):
        """3次元ベクトルの外積を計算する。

        先頭3成分を使用する。

        Args:
            left (Sequence[float]): 左側の成分列。
            right (Sequence[float]): 右側の成分列。

        Returns:
            list[float]: 外積の XYZ 3成分。
        """
        return [
            left[1] * right[2] - left[2] * right[1],
            left[2] * right[0] - left[0] * right[2],
            left[0] * right[1] - left[1] * right[0],
        ]
