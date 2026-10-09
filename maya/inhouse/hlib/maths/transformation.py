"""Mayaの変換成分と補助情報を保持する、シーン非依存の値型。"""

import math
from typing import TYPE_CHECKING

import maya.api.OpenMaya as om2

from .._core.getterAlias import _is_alias
from .eulerRotate import EulerRotate
from .matrix import Matrix
from .quaternion import Quaternion
from .scale import Scale
from .shear import Shear
from .translate import Translate


class Transformation:
    """TRS・回転順序・ピボット・補助回転・SSCを保持する可変の値。

    各数学値は所有するコピーであり、取得した成分を直接編集できる。
    matrixは毎回合成するため、成分編集後も古いキャッシュを返さない。
    元のEuler回転・スケール符号は行列へ変換しない限り保持する。
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
        """変換情報・行列・成分から独立した値を作る。

        Args:
            value (Transformation | Matrix | om2.MTransformationMatrix | None): コピー元。
                行列からは元のピボット等を復元できないため既定値を使う。
            **kwargs: Mayaの成分名または短縮名。角度はradian、距離はcm。
                matrixと同時指定した補助成分は分解の条件として使う。
        """
        object.__setattr__(self, "_values", {})
        for name, cls in self._types.items():
            self._values[name] = cls((1, 1, 1)) if name in ("scale", "inverseScale") else cls()
        self._values["segmentScaleCompensate"] = True
        if isinstance(value, Transformation):
            for name, val in value._values.items():
                self._values[name] = self._types[name](val) if name in self._types else val
        elif isinstance(value, om2.MTransformationMatrix):
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
                raise TypeError("Duplicate transformation component: " + name)
            normalized[name] = val
        # rotateの入力は指定した順序で解釈し、matrixは全ての補助成分が確定してから分解する。
        for name in ["rotateOrder"] + [n for n in normalized if n not in ("rotateOrder", "matrix")] + ["matrix"]:
            if name in normalized:
                setattr(self, name, normalized[name])
        if "rotateOrder" in normalized and isinstance(normalized.get("rotate"), om2.MEulerRotation):
            self.rotateOrder = normalized["rotateOrder"]

    def __getattr__(self, name):
        """保持した成分または計算済みの行列・クォータニオンを返す。

        Args:
            name: 参照・作成・照会する対象の名前。
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
        """検証・コピーして成分を設定する。シーンは更新しない。

        Args:
            name: 参照・作成・照会する対象の名前。
            value: 変換・設定する入力値。
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
            if not isinstance(value, bool):
                raise TypeError("segmentScaleCompensate must be bool")
            self._values[name] = value
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
            converted = EulerRotate(value) if isinstance(value, om2.MEulerRotation) else EulerRotate(value, order=self.rotateOrder)
        else:
            converted = self._types[name](value)
        if not all(math.isfinite(v) for v in converted):
            raise ValueError("Transformation components must be finite")
        self._values[name] = converted

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

    def copy(self):
        """成分を共有しない独立したコピー。

        Returns:
            Transformation: 成分を共有しない独立したコピー。
        """
        return type(self)(self)

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

    def _compensation(self):
        """有効な逆スケール補正行列を返す。"""
        if not self.segmentScaleCompensate:
            return Matrix()
        if any(abs(v) <= 1e-15 for v in self.inverseScale):
            raise ValueError("inverseScale must be nonzero while SSC is enabled")
        return Matrix(scale=tuple(1.0 / v for v in self.inverseScale))

    def _compose(self):
        """Mayaの順序でピボット・回転・SSCを含む行列を合成する。"""
        if any(not math.isfinite(value) for name in self._types for value in self._values[name]):
            raise ValueError("Transformation components must be finite")
        sp, rp = self.scalePivot, self.rotatePivot
        rotation = self.rotateAxis * self.quaternion * self.jointOrient
        return (Matrix(translate=-sp) * Matrix(scale=self.scale, shear=self.shear)
                * Matrix(translate=sp + self.scalePivotTranslate - rp)
                * Matrix(rotate=rotation) * Matrix(translate=rp + self.rotatePivotTranslate)
                * self._compensation() * Matrix(translate=self.translate))

    def _set_matrix(self, value):
        """補助成分を保持し、行列からTRSとシアーを求める。失敗時は変更しない。

        Args:
            value: 変換・設定する入力値。
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

    def __mul__(self, other):
        """行列を後乗算し、translateと回転ピボットの位置を追従させたコピーを返す。

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
        """後乗算した結果で自身を更新する。

        Args:
            other: 比較・演算の相手。
        """
        result = self * other
        self._values.update(result._values)
        return self

    def isEquivalent(self, other, tolerance=1e-10):
        """補助情報を含む全成分を比較する。

        Args:
            other (Transformation): 比較対象。
            tolerance (float): 成分差の許容値。
        Returns:
            bool: 同値ならTrue。行列だけの比較はmatrix.isEquivalentを使う。
        """
        if not isinstance(other, Transformation) or self.rotateOrder != other.rotateOrder or self.ssc != other.ssc:
            return False
        return all(all(abs(a - b) <= tolerance for a, b in zip(self._values[n], other._values[n])) for n in self._types)

    @_is_alias(isEquivalent)
    def equivalent(self, *args, **kwargs):
        """isEquivalentへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isEquivalent(*args, **kwargs)

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
