"""Mayaの変換成分と補助情報を保持する、シーン非依存の値型。"""

import math
from typing import TYPE_CHECKING

import maya.api.OpenMaya as om2

from ..decorator import _require_bool
from .eulerRotate import EulerRotate
from .matrix import Matrix, _compose_into, _new, _rotate_matrix, _xyz
from .quaternion import Quaternion
from .scale import Scale
from .shear import Shear
from .translate import Translate
from .vector import _vector_of

_MQuaternion = om2.MQuaternion
_isfinite = math.isfinite
#: 成分のコピーで、Python の ``__init__`` を通さずに同じ値を写す型と関数。
#: いずれも ``cls(値)`` と同じ成分の代入(``setValue``)で、値はビット単位で一致する。
_VECTOR_TYPES = (Translate, Scale, Shear)
_WRAPPED_TYPES = (Quaternion, EulerRotate)


def _copy_component(cls, value):
    """保持成分を ``cls(value)`` と同じ値の独立したインスタンスへコピーする。

    Args:
        cls (type): 成分の型。
        value (object): コピー元の保持成分。

    Returns:
        object: cls の新しいインスタンス。
    """
    if cls in _VECTOR_TYPES:
        return _vector_of(cls, value)
    if cls in _WRAPPED_TYPES:
        return cls._wrap(value)
    return cls(value)


def _translation_matrix(value):
    """``Matrix(translate=value)`` と同じ要素の平行移動マトリクスを作る。

    Matrix のコンストラクタの引数の解析を通さず、同じ書込み(:func:`~mlib.maths.matrix._compose_into`)を行う。

    Args:
        value (om2.MVector | Iterable[float]): 平行移動。

    Returns:
        Matrix: 新しいマトリクス。
    """
    return _compose_into(_new(Matrix), _xyz(value), None, None, None)


def _rotation_matrix(rotation):
    """``Matrix(rotate=rotation)`` と同じ要素の回転マトリクスを作る。

    回転の変換は ``Matrix(rotate=...)`` と同じ :func:`mlib.maths.matrix._rotate_matrix` を使う。

    Args:
        rotation (om2.MQuaternion): 回転。

    Returns:
        Matrix: 新しいマトリクス。

    Raises:
        ValueError: ゼロクォータニオンの場合。
    """
    return _compose_into(_new(Matrix), None, _rotate_matrix(rotation), None, None)


class Transformation:
    """TRS・回転順序・ピボット・補助回転・SSCを保持する可変の値。

    入力の数学値はコピーして所有し、translateやrotate等の取得はその保持値を返す。
    保持値を直接編集すると自身も変わるが、matrixとquaternionは計算した独立値を返す。
    matrix代入・``*=`` は成分を置き換えるため、以前取得した成分参照は再取得が必要。
    matrixは毎回合成するため、成分編集後も古いキャッシュを返さない。
    元のEuler回転・スケール符号はマトリクスへ変換しない限り保持する。
    """

    __slots__ = ("_values",)
    __hash__ = None
    _aliases = {"t": "translate", "r": "rotate", "q": "quaternion", "s": "scale",
                "sh": "shear", "ro": "rotateOrder", "ra": "rotateAxis", "jo": "jointOrient",
                "rp": "rotatePivot", "rpt": "rotatePivotTranslate", "sp": "scalePivot",
                "spt": "scalePivotTranslate", "ssc": "segmentScaleCompensate",
                "is": "inverseScale", "is_": "inverseScale", "m": "matrix"}
    _types = {"translate": Translate, "rotate": EulerRotate, "scale": Scale,
              "shear": Shear, "rotateAxis": Quaternion, "jointOrient": Quaternion,
              "rotatePivot": Translate, "rotatePivotTranslate": Translate,
              "scalePivot": Translate, "scalePivotTranslate": Translate, "inverseScale": Scale}

    if TYPE_CHECKING:
        translate: Translate
        rotate: EulerRotate
        quaternion: Quaternion
        scale: Scale
        shear: Shear
        rotateOrder: int
        rotateAxis: Quaternion
        jointOrient: Quaternion
        rotatePivot: Translate
        rotatePivotTranslate: Translate
        scalePivot: Translate
        scalePivotTranslate: Translate
        inverseScale: Scale
        segmentScaleCompensate: bool
        matrix: Matrix
        t: Translate
        r: EulerRotate
        q: Quaternion
        s: Scale
        sh: Shear
        ro: int
        ra: Quaternion
        jo: Quaternion
        rp: Translate
        rpt: Translate
        sp: Translate
        spt: Translate
        is_: Scale
        ssc: bool
        m: Matrix

    def __init__(self, value=None, **kwargs):
        """変換情報・マトリクス・成分から独立した値を作る。

        Args:
            value (Transformation | Matrix | om2.MTransformationMatrix | None): コピー元。
                マトリクスからは元のピボット等を復元できないため既定値を使う。
            **kwargs: Mayaの成分名または短縮名。角度はradian、距離はcm。
                matrixと同時指定した補助成分は分解の条件として使う。
        """
        values = {}
        object.__setattr__(self, "_values", values)
        if isinstance(value, Transformation):
            # コピー元は全成分を持つため、既定値を作らずに同じ並びでコピーする。
            source = value._values
            for name, cls in self._types.items():
                if name in source:
                    values[name] = _copy_component(cls, source[name])
                else:
                    values[name] = self._default(name, cls)
            values["segmentScaleCompensate"] = source.get("segmentScaleCompensate", True)
            for name, val in source.items():
                if name not in values:
                    values[name] = val
        else:
            for name, cls in self._types.items():
                values[name] = self._default(name, cls)
            values["segmentScaleCompensate"] = True
            if isinstance(value, om2.MTransformationMatrix):
                space = om2.MSpace.kTransform
                components = dict(translate=value.translation(space), rotate=value.rotation(),
                                  scale=value.scale(space), shear=value.shear(space),
                                  rotateAxis=value.rotationOrientation(),
                                  rotatePivot=tuple(value.rotatePivot(space))[:3],
                                  rotatePivotTranslate=value.rotatePivotTranslation(space),
                                  scalePivot=tuple(value.scalePivot(space))[:3],
                                  scalePivotTranslate=value.scalePivotTranslation(space))
                for name, item in components.items():
                    setattr(self, name, item)
            elif value is not None:
                kwargs = dict(kwargs)
                if "matrix" in kwargs or "m" in kwargs:
                    raise TypeError("Matrix input was specified twice")
                kwargs["matrix"] = value
        normalized = {}
        for name, val in kwargs.items():
            name = self._aliases.get(name, name)
            if name in normalized:
                raise TypeError(f"Duplicate transformation component: {name}")
            normalized[name] = val
        # rotateの入力は指定した順序で解釈し、matrixは全ての補助成分が確定してから分解する。
        for name in ["rotateOrder"] + [n for n in normalized if n not in ("rotateOrder", "matrix")] + ["matrix"]:
            if name in normalized:
                setattr(self, name, normalized[name])
        if "rotateOrder" in normalized and isinstance(normalized.get("rotate"), om2.MEulerRotation):
            self.rotateOrder = normalized["rotateOrder"]

    def __getattr__(self, name):
        """保持成分、または計算した独立値を返す。

        Args:
            name (str): 成分名または短縮名。

        Returns:
            object: 数学成分は保持参照。matrixは全成分の合成、quaternionはrotateだけの独立値。

        Raises:
            AttributeError: 未対応の名前の場合。
            ValueError: マトリクス合成で非有限値・無効なSSC補正を検出した場合。
        """
        name = self._aliases.get(name, name)
        if name == "matrix":
            return self._compose()
        if name == "quaternion":
            return Quaternion(self._values["rotate"].asQuaternion())
        if name == "rotateOrder":
            return self._values["rotate"].order
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        """成分を置き換える。シーンは更新しない。

        rotateOrderだけは保持rotateを姿勢維持で更新する。
        quaternionは現在の順序と近いEuler解へ変換し、rotateを置き換える。

        Args:
            name (str): 成分名または短縮名。
            value (object): 成分値。rotateOrderは整数0～5、SSCはbool。

        Raises:
            AttributeError: 未対応の名前の場合。
            TypeError: SSCがbool以外、または値が未対応型の場合。
            ValueError: 回転順序・数値・回転・マトリクスが不正な場合。
        """
        name = self._aliases.get(name, name)
        if name == "matrix":
            self._set_matrix(value)
            return
        if name == "rotateOrder":
            if isinstance(value, bool) or not isinstance(value, int) or value not in range(6):
                raise ValueError("rotateOrder must be an integer from 0 through 5")
            self._values["rotate"].reorderIt(value)
            return
        if name == "segmentScaleCompensate":
            self._values[name] = _require_bool(value, "segmentScaleCompensate")
            return
        if name == "quaternion":
            rotation = self._quaternion(value).asEulerRotate()
            rotation.reorderIt(self.rotateOrder)
            self._values["rotate"] = EulerRotate(rotation.closestSolution(self.rotate))
            return
        if name not in self._types:
            raise AttributeError(name)
        if name in ("rotateAxis", "jointOrient"):
            converted = self._quaternion(value)
        elif name == "rotate":
            if isinstance(value, om2.MEulerRotation):
                converted = EulerRotate(value)
            else:
                converted = EulerRotate(value, order=self.rotateOrder)
        else:
            converted = self._types[name](value)
        if not all(math.isfinite(v) for v in converted):
            raise ValueError("Transformation components must be finite")
        self._values[name] = converted

    def __copy__(self):
        """copy.copyによる独立コピーを返す。"""
        return self.copy()

    def __deepcopy__(self, memo):
        """copy.deepcopyによる独立コピーを返す。

        Args:
            memo: deepcopyが共有する複製済みオブジェクトの辞書。
        """
        result = self.copy()
        memo[id(self)] = result
        return result

    def __mul__(self, other):
        """マトリクスを後乗算し、translateと回転ピボットの位置を追従させたコピーを返す。

        Args:
            other: 比較・演算の相手。
        """
        matrix = other.matrix if isinstance(other, Transformation) else Matrix(other)
        result = self.copy()
        if matrix == Matrix():
            return result
        target = self.matrix * matrix
        translation = matrix.transformPoint(self.translate)
        pivot = matrix.transformPoint(self.translate + (self.rotatePivot + self.rotatePivotTranslate) * self._compensation())
        result.matrix = target
        current = result.translate + (result.rotatePivot + result.rotatePivotTranslate) * result._compensation()
        orient = Matrix(rotate=result.rotateAxis * result.quaternion * result.jointOrient) * result._compensation()
        result.scalePivotTranslate -= (pivot - current) * orient.inverse()
        result.matrix = target
        result.rotatePivotTranslate -= (translation - result.translate) * result._compensation().inverse()
        result.matrix = target
        return result

    def __imul__(self, other):
        """後乗算した結果で自身の成分を置き換える。

        容器の同一性は保つが、以前取得した成分参照は旧値を指す。

        Args:
            other: 比較・演算の相手。
        """
        result = self * other
        self._values.update(result._values)
        return self

    def __eq__(self, other):
        """保持した全成分の完全一致を比較する。

        Args:
            other: 比較・演算の相手。
        """
        if not isinstance(other, Transformation):
            return NotImplemented
        return self.isEquivalent(other, tolerance=0.0)

    def __repr__(self):
        """成分の内容を確認できる文字列表現を返す。"""
        return "Transformation(" + ", ".join(name + "=" + repr(value) for name, value in self._values.items()) + ")"

    def copy(self):
        """成分を共有しない独立したコピー。

        Returns:
            Transformation: 成分を共有しない独立したコピー。
        """
        return type(self)(self)

    def isEquivalent(self, other, tolerance=1e-10):
        """補助情報を含む全成分を比較する。

        Args:
            other (Transformation): 比較対象。
            tolerance (float): 成分差の許容値。

        Returns:
            bool: 同値ならTrue。マトリクスだけの比較はmatrix.isEquivalentを使う。
        """
        if not isinstance(other, Transformation) or self.rotateOrder != other.rotateOrder or self.ssc != other.ssc:
            return False
        return all(all(abs(a - b) <= tolerance for a, b in zip(self._values[n], other._values[n])) for n in self._types)

    @staticmethod
    def _default(name, cls):
        """成分の既定値を返す。

        Args:
            name (str): 成分名。
            cls (type): 成分の型。

        Returns:
            object: scale・inverseScaleは(1, 1, 1)、それ以外はゼロ・単位の新しい値。
        """
        if cls in _VECTOR_TYPES or cls in _WRAPPED_TYPES:
            # 各型の __new__ は om2 の既定値(ゼロ・単位・XYZ順)を確保する。cls() と同じ値。
            value = cls.__new__(cls)
            if name in ("scale", "inverseScale"):
                value.x = value.y = value.z = 1.0
            return value
        return cls((1, 1, 1)) if name in ("scale", "inverseScale") else cls()

    @staticmethod
    def _quaternion(value):
        """EulerまたはQuaternionを有限な単位Quaternionへコピーする。

        Args:
            value: EulerRotateまたはQuaternionとして解釈できる回転値。
        """
        q = Quaternion(value.asQuaternion() if isinstance(value, om2.MEulerRotation) else value)
        length = sum(v * v for v in q)
        if not math.isfinite(length) or length <= 1e-30:
            raise ValueError("A finite nonzero quaternion is required")
        q.normalizeIt()
        return q

    def _compensation(self):
        """有効な逆スケール補正マトリクスを返す。"""
        values = self._values
        if not values["segmentScaleCompensate"]:
            return _new(Matrix)
        x, y, z = values["inverseScale"]
        if abs(x) <= 1e-15 or abs(y) <= 1e-15 or abs(z) <= 1e-15:
            raise ValueError("inverseScale must be nonzero while SSC is enabled")
        # Matrix(scale=...) と同じ書込み(引数の解析だけを省く)。
        return _compose_into(_new(Matrix), None, None, (1.0 / x, 1.0 / y, 1.0 / z), None)

    def _require_finite(self):
        """保持する数学成分がすべて有限か確かめる。

        Raises:
            ValueError: 非有限の成分がある場合。
        """
        values = self._values
        for name in self._types:
            value = values[name]
            if not (_isfinite(value.x) and _isfinite(value.y) and _isfinite(value.z)
                    and (not isinstance(value, _MQuaternion) or _isfinite(value.w))):
                raise ValueError("Transformation components must be finite")

    def _compose(self):
        """Mayaの順序でピボット・回転・SSCを含むマトリクスを合成する。

        各マトリクスは ``Matrix(translate=...)`` 等と同じ書込み、回転は
        ``rotateAxis * quaternion * jointOrient`` と同じ om2 の積で作る(値は同じ)。
        """
        self._require_finite()
        values = self._values
        sp, rp = values["scalePivot"], values["rotatePivot"]
        # Quaternion.__mul__ と同じく、左辺のコピーへ右辺を順に掛ける。
        quaternion = Quaternion._wrap(values["rotate"])
        rotation = Quaternion._wrap(values["rotateAxis"])
        _MQuaternion.__imul__(rotation, quaternion)
        _MQuaternion.__imul__(rotation, values["jointOrient"])
        return (_translation_matrix(-sp)
                * _compose_into(_new(Matrix), None, None, _xyz(values["scale"]), _xyz(values["shear"]))
                * _translation_matrix(sp + values["scalePivotTranslate"] - rp)
                * _rotation_matrix(rotation) * _translation_matrix(rp + values["rotatePivotTranslate"])
                * self._compensation() * _translation_matrix(values["translate"]))

    def _set_matrix(self, value):
        """補助成分を条件にマトリクスからTRS・シアーを求める。

        成功時は補助成分もコピーへ置換し、旧成分参照は追従しない。失敗時は変更しない。

        Args:
            value (object): Matrixで解釈する有限なアフィンマトリクス。

        Returns:
            None: 値を返さない。
        """
        matrix = Matrix(value)
        if not all(math.isfinite(v) for v in matrix):
            raise ValueError("Matrix must be finite")
        if any(abs(matrix[i, 3]) > 1e-10 for i in range(3)) or abs(matrix[3, 3] - 1) > 1e-10:
            raise ValueError("An affine matrix is required")
        corrected = matrix * self._compensation().inverse()
        corrected.translate = matrix.translate
        parts = corrected.decompose()
        q, scale, shear = parts["quaternion"], tuple(parts["scale"]), tuple(parts["shear"])
        signs = tuple(-1 if (v < 0) != (ref < 0) else 1 for v, ref in zip(scale, self.scale))
        if signs.count(-1) == 2:
            axis = [0., 0., 0.]
            axis[signs.index(1)] = 1.
            q = Quaternion(*axis, 0.) * q
            scale = tuple(v * sign for v, sign in zip(scale, signs))
            shear = (shear[0] * signs[0] * signs[1], shear[1] * signs[0] * signs[2], shear[2] * signs[1] * signs[2])
        q = self.rotateAxis.inverse() * q * self.jointOrient.inverse()
        rotation = q.asEulerRotate()
        rotation.reorderIt(self.rotateOrder)
        rotation = rotation.closestSolution(self.rotate)
        trial = self.copy()
        trial.scale, trial.shear, trial.rotate = scale, shear, rotation
        trial.translate = (0, 0, 0)
        trial.translate = matrix.translate - trial.matrix.translate
        self._values.update(trial._values)
