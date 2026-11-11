"""om2.MEulerRotation を継承した、回転順序を持つラジアンのオイラー回転値。"""

import math
import operator

import maya.api.OpenMaya as om2

from ..util import (
    _angle_unit,
    _checked_digits,
    _checked_index,
    _checked_tolerance,
    _copy_state,
    _finite_vector,
    _foreign_comparison,
    _from_radians,
    _rethrow_init_error,
    _round_float,
    _to_radians,
)
from .quaternion import Quaternion
from .vector import _reduce_value

_MEuler = om2.MEulerRotation
_MQuaternion = om2.MQuaternion
_NEW = _MEuler.__new__
_INIT = _MEuler.__init__
_GET = _MEuler.__getitem__
_SET = _MEuler.__setitem__
_NUMBER = (int, float)

#: 回転順序の名前。添字が om2 の ``MEulerRotation.kXYZ`` (0)〜``kZYX`` (5)と、
#: Maya の rotateOrder アトリビュートの番号に対応する。
ORDER_NAMES = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")
_ORDER_INDEX = {name: index for index, name in enumerate(ORDER_NAMES)}


def orderIndex(order):
    """回転順序の名前または番号を om2 の番号(0〜5)へ変換する。

    Args:
        order (str | int): ``"xyz"`` などの名前(大文字小文字を問わない)、または
            om2 の ``MEulerRotation.kXYZ``〜``kZYX`` (Maya の rotateOrder と同じ番号)。

    Returns:
        int: om2 の回転順序の番号。

    Raises:
        ValueError: 未対応の名前・番号、または bool などの不正な型の場合。
    """
    if isinstance(order, str):
        index = _ORDER_INDEX.get(order.lower())
        if index is None:
            raise ValueError(f"Unsupported rotation order: {order!r}")
        return index
    if isinstance(order, bool):
        raise ValueError(f"Unsupported rotation order: {order!r}")
    try:
        index = operator.index(order)
    except TypeError:
        raise ValueError(f"Unsupported rotation order: {order!r}") from None
    if not 0 <= index < 6:
        raise ValueError(f"Unsupported rotation order: {order!r}")
    return index


def _euler_keywords(x=0.0, y=0.0, z=0.0, order=None):
    """キーワード引数付きの EulerRotate の生成引数を (x, y, z, order) へまとめる。

    Args:
        x (float): X 回転(ラジアン)。
        y (float): Y 回転(ラジアン)。
        z (float): Z 回転(ラジアン)。
        order (str | int | None): 回転順序。None は xyz。

    Returns:
        tuple: (x, y, z, order)。
    """
    return x, y, z, order


class EulerRotate(om2.MEulerRotation):
    """om2.MEulerRotationを継承した、radのXYZ成分と回転順序を持つ可変値。

    Vectorの派生ではなく、OpenMaya APIへそのまま渡せる。
    生成形式は ``__init__`` に従い、MEulerRotation入力は順序を含めてコピーする。
    コンストラクタのorder指定は成分を並べ替えない。姿勢を保った順序変更には ``reorder()`` を使う。
    orderはMayaのrotateOrderと同じ0〜5。コンストラクタは順序名も受理し、
    :attr:`orderName` でも名前を取得・設定できる。

    演算はOM2に従い、結果はEulerRotateを返す。
    ``+`` / ``-`` は同順序なら成分ごと、異なる順序なら右辺を左辺の順序へ変換する。
    ``*`` は数値なら成分のスケール、EulerRotate/Quaternionなら回転合成。
    ``数値 * e`` と ``e / 数値`` はmlibの拡張。``+=`` / ``-=`` / ``*=`` / ``/=`` は自身更新。
    数学値を返す継承メソッドも対応するmlib型を返し、コピー操作とIt付きの自身更新を区別する。

    ハッシュ不可。番号は-3〜2、範囲外はIndexError。スライスは成分tuple、反復はXYZ順。
    ``==`` は順序を含む成分の完全一致。異種型との比較は :class:`~mlib.maths.vector.Vector` と同じ扱い。
    表示は度、内部値はrad。
    """

    __slots__ = ()
    __hash__ = None

    def __new__(cls, *args, **kwargs):
        """基底初期化でC++実体を確保し、clsの0回転(xyz順)を作る。

        ``__init__`` を省略・失敗しても実体へアクセスできるよう、先に確保する。
        詳細は :meth:`mlib.maths.vector.Vector.__new__` を参照。

        Args:
            *args: ここでは使わない生成引数。
            **kwargs: ここでは使わないキーワード引数。

        Returns:
            EulerRotate: clsの0回転。
        """
        self = _NEW(cls)
        _INIT(self)
        return self

    def __init__(self, *args, **kwargs):
        """成分と回転順序を設定する。

        引数をすべて検証してから書き込むため、例外時に値は変わらない。

        Args:
            *args: ``()``、``(x, y, z)``、``(x, y, z, order)``、``(values)``、
                ``(values, order)``、または ``(MEulerRotation)``。角度は既定でラジアン。
            **kwargs: ``order``、または ``x`` / ``y`` / ``z`` / ``order`` のキーワード引数。
                ``unit`` は数値成分の単位で、既定 ``"rad"`` (om2と同じ)、``"deg"`` は度
                (``"degree"`` / ``"radians"`` 等の別名も可)。内部値は常にラジアンで保持する。
                MEulerRotationのコピーでは ``"rad"`` 以外を指定できない。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 引数の数や型が不正な場合、同じ引数を二重に指定した場合、またはunitが文字列・None以外の場合。
            ValueError: 未対応の回転順序・単位、成分が数値でない場合、またはMEulerRotationへ度を指定した場合。
        """
        unit = "rad"
        if "unit" in kwargs:
            kwargs = dict(kwargs)
            unit = _angle_unit(kwargs.pop("unit"))
        if not kwargs and unit == "rad":
            # よく使う ()、(x, y, z)、(x, y, z, order) は解析を省く。
            count = len(args)
            if count == 3 or count == 4:
                x, y, z = args[0], args[1], args[2]
                if isinstance(x, _NUMBER) and isinstance(y, _NUMBER) and isinstance(z, _NUMBER):
                    index = orderIndex(args[3]) if count == 4 else 0
                    self.x = x
                    self.y = y
                    self.z = z
                    self.order = index
                    return
            elif count == 0:
                self.x = 0.0
                self.y = 0.0
                self.z = 0.0
                self.order = 0
                return
        if "x" in kwargs or "y" in kwargs or "z" in kwargs:
            try:
                x, y, z, order = _euler_keywords(*args, **kwargs)
            except TypeError as error:
                _rethrow_init_error(type(self), error)
        else:
            order = kwargs.pop("order", None)
            if kwargs:
                raise TypeError(f"EulerRotate got unexpected keyword arguments: {', '.join(sorted(kwargs))}")
            count = len(args)
            if count == 1 and order is None and isinstance(args[0], _MEuler):
                if unit != "rad":
                    raise ValueError("unit cannot convert an existing rotation; it already holds radians")
                self.setValue(args[0])
                return
            if count in (1, 2) and not isinstance(args[0], _NUMBER):
                if count == 2:
                    if order is not None:
                        raise TypeError("EulerRotate got multiple values for 'order'")
                    order = args[1]
                x, y, z = args[0]
            elif count in (3, 4):
                x, y, z = args[0], args[1], args[2]
                if count == 4:
                    if order is not None:
                        raise TypeError("EulerRotate got multiple values for 'order'")
                    order = args[3]
            elif count == 0:
                x = y = z = 0.0
            else:
                raise TypeError("EulerRotate expects (), (x, y, z[, order]), (values[, order]) or (EulerRotate)")
        index = 0 if order is None else orderIndex(order)
        if not (isinstance(x, _NUMBER) and isinstance(y, _NUMBER) and isinstance(z, _NUMBER)):
            # 数値以外は om2 の変換規則に任せる(文字列などは om2 と同じ ValueError)。
            source = _MEuler(x, y, z)
            x, y, z = source.x, source.y, source.z
        if unit == "deg":
            x, y, z = math.radians(x), math.radians(y), math.radians(z)
        self.x = x
        self.y = y
        self.z = z
        self.order = index

    def __getitem__(self, index):
        """回転成分を取得する。

        Args:
            index (int | slice): -3〜2 の番号(X、Y、Z の順)、またはスライス。

        Returns:
            float | tuple[float, ...]: 指定成分(ラジアン)。スライスでは成分の tuple。

        Raises:
            TypeError: 番号が整数・スライス以外の場合。
            IndexError: 番号が範囲外の場合。
        """
        if index.__class__ is int and -3 <= index < 3:
            return _GET(self, index)
        if isinstance(index, slice):
            return (self.x, self.y, self.z)[index]
        return _GET(self, _checked_index(index, 3, "EulerRotate"))

    def __setitem__(self, index, value):
        """回転成分を設定する。

        Args:
            index (int): -3〜2 の番号。
            value (float): 設定する値(ラジアン)。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 番号が整数以外の場合。
            IndexError: 番号が範囲外の場合。
        """
        if index.__class__ is not int or not -3 <= index < 3:
            index = _checked_index(index, 3, "EulerRotate")
        _SET(self, index, value)

    def __iter__(self):
        """X、Y、Z の順に回転成分を反復する。

        Returns:
            Iterator[float]: 3成分(ラジアン)のイテレータ。
        """
        return iter((self.x, self.y, self.z))

    def __reduce__(self):
        """copy / pickle 用に、コンストラクタを通さずに再構築する情報を返す。

        Returns:
            tuple: ``(_rebuild, (type(self), (x, y, z, order))[, state])``。
            利用者の派生クラスの ``__init__`` は呼ばず、``__dict__`` と ``__slots__`` の
            アトリビュートは再構築時に復元する。
        """
        return _reduce_value(self, (self.x, self.y, self.z, self.order))

    def __reduce_ex__(self, protocol):
        """pickle のプロトコルにかかわらず __reduce__ と同じ情報を返す。

        Args:
            protocol (int): pickle のプロトコル番号。使用しない。

        Returns:
            tuple: ``__reduce__()`` の結果。
        """
        return self.__reduce__()

    def __copy__(self):
        """同じ型・同じ成分と順序の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートも浅く写す。

        Returns:
            EulerRotate: 自身と同じクラスの新しいインスタンス。
        """
        return _copy_state(self, type(self)._wrap(self))

    def __deepcopy__(self, memo):
        """同じ型・同じ成分と順序の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートは深く複製する。

        Args:
            memo (dict): copy.deepcopy の memo。

        Returns:
            EulerRotate: 自身と同じクラスの新しいインスタンス。
        """
        return _copy_state(self, type(self)._wrap(self), memo)

    def __repr__(self):
        """度数法の回転成分と回転順序名を含むデバッグ表現を返す。

        Returns:
            str: ``EulerRotate(degrees=(90, 0, -45), order='xyz')`` の形式の文字列。
            内部値はラジアンのまま。
        """
        values = ", ".join(f"{value:.15g}" for value in self.asDegrees())
        return "{}(degrees=({}), order={!r})".format(type(self).__name__, values, self.orderName)

    __str__ = __repr__

    def __eq__(self, other):
        """MEulerRotation 系との比較を om2 と同じ規則(順序を含む完全一致)で行う。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MEulerRotation 系なら om2 の比較結果。
            その他の om2 の型は False。それ以外の型は NotImplemented(相手の比較に委ね、
            どちらも判断しなければ False になる)。
        """
        if isinstance(other, _MEuler):
            return _MEuler.__eq__(self, other)
        return _foreign_comparison(other, False)

    def __ne__(self, other):
        """``__eq__`` の否定を返す。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MEulerRotation 系なら om2 の比較結果。
            その他の om2 の型は True。それ以外の型は NotImplemented。
        """
        if isinstance(other, _MEuler):
            return _MEuler.__ne__(self, other)
        return _foreign_comparison(other, True)

    def __add__(self, other):
        """om2 の ``+`` の結果を EulerRotate で返す。

        Args:
            other (object): MEulerRotation 系。順序が違えば自身の順序へ変換して加算する。

        Returns:
            EulerRotate | types.NotImplementedType: 和。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MEuler):
            return NotImplemented
        return EulerRotate._wrap(_MEuler.__add__(self, other))

    def __radd__(self, other):
        """左辺の MEulerRotation 系との和を返す。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotate | types.NotImplementedType: 和。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MEuler):
            return NotImplemented
        return EulerRotate._wrap(_MEuler.__add__(other, self))

    def __iadd__(self, other):
        """MEulerRotation 系を自身へ加算する。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotate | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MEuler):
            return NotImplemented
        return _MEuler.__iadd__(self, other)

    def __sub__(self, other):
        """om2 の ``-`` の結果を EulerRotate で返す。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotate | types.NotImplementedType: 差。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MEuler):
            return NotImplemented
        return EulerRotate._wrap(_MEuler.__sub__(self, other))

    def __rsub__(self, other):
        """左辺の MEulerRotation 系から自身を引いた値を返す。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotate | types.NotImplementedType: 差。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MEuler):
            return NotImplemented
        return EulerRotate._wrap(_MEuler.__sub__(other, self))

    def __isub__(self, other):
        """MEulerRotation 系を自身から減算する。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotate | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MEuler):
            return NotImplemented
        return _MEuler.__isub__(self, other)

    def __mul__(self, other):
        """om2 の ``*`` の結果を EulerRotate で返す。

        Args:
            other (object): 数値(成分のスケール)、または MEulerRotation 系 /
                MQuaternion 系(自身を先に適用する回転の合成)。

        Returns:
            EulerRotate | types.NotImplementedType: 結果。対応しない型は NotImplemented。
        """
        if not isinstance(other, (int, float, _MEuler, _MQuaternion)):
            return NotImplemented
        return EulerRotate._wrap(_MEuler.__mul__(self, other))

    def __rmul__(self, other):
        """左辺からの乗算を om2 の意味論で行う。

        Args:
            other (object): 数値、または左辺の MEulerRotation 系。

        Returns:
            EulerRotate | types.NotImplementedType: 結果。対応しない型は NotImplemented。
        """
        if isinstance(other, _NUMBER):
            return EulerRotate._wrap(_MEuler.__mul__(self, other))
        if isinstance(other, _MEuler):
            return EulerRotate._wrap(_MEuler.__mul__(other, self))
        return NotImplemented

    def __imul__(self, other):
        """数値倍、または回転の合成を自身へ適用する。

        Args:
            other (object): 数値、MEulerRotation 系、または MQuaternion 系。

        Returns:
            EulerRotate | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, (int, float, _MEuler, _MQuaternion)):
            return NotImplemented
        return _MEuler.__imul__(self, other)

    def __truediv__(self, other):
        """数値による成分ごとの除算を返す(om2 には無い mlib の拡張)。

        順序は保持し、各成分を other で割る。

        Args:
            other (object): 除数の int または float。

        Returns:
            EulerRotate | types.NotImplementedType: 新しい回転値。対応しない型は NotImplemented。

        Raises:
            ZeroDivisionError: other が 0 の場合。
        """
        if not isinstance(other, _NUMBER):
            return NotImplemented
        if other == 0:
            raise ZeroDivisionError("EulerRotate division by zero")
        result = EulerRotate._wrap(self)
        result.x = self.x / other
        result.y = self.y / other
        result.z = self.z / other
        return result

    def __itruediv__(self, other):
        """数値で自身の各成分を除算する(mlib の拡張。順序は変えない)。

        Args:
            other (object): 除数の int または float。

        Returns:
            EulerRotate | types.NotImplementedType: 自身。対応しない型は NotImplemented。

        Raises:
            ZeroDivisionError: other が 0 の場合。
        """
        if not isinstance(other, _NUMBER):
            return NotImplemented
        if other == 0:
            raise ZeroDivisionError("EulerRotate division by zero")
        self.x = self.x / other
        self.y = self.y / other
        self.z = self.z / other
        return self

    def __neg__(self):
        """om2 の単項 ``-`` (逆回転の成分)を EulerRotate で返す。

        Returns:
            EulerRotate: 新しい回転値。
        """
        return EulerRotate._wrap(_MEuler.__neg__(self))

    def __round__(self, ndigits=None):
        """組み込みの ``round`` から度で丸める :meth:`round` を呼ぶ。

        Args:
            ndigits (int | None): roundと同じ桁数。

        Returns:
            EulerRotate: 同型の新しい回転。
        """
        return self.round(ndigits)

    @classmethod
    def fromIterable(cls, values, order="xyz"):
        """3要素の反復可能オブジェクトから生成する。

        Args:
            values (Iterable[float]): ラジアンの3成分。
            order (str | int): 回転順序。既定は ``"xyz"``。

        Returns:
            EulerRotate: 呼び出したクラスの新しいインスタンス。

        Raises:
            ValueError: 要素数が3でない場合、または未対応の回転順序の場合。
        """
        values = tuple(values)
        if len(values) != 3:
            raise ValueError(f"{cls.__name__} expects 3 values")
        return cls(values[0], values[1], values[2], order)

    @classmethod
    def fromDegrees(cls, x, y, z, order="xyz"):
        """度数法の3成分から生成する。

        Args:
            x (float): X 回転角度(度)。
            y (float): Y 回転角度(度)。
            z (float): Z 回転角度(度)。
            order (str | int): 回転順序。既定は ``"xyz"``。

        Returns:
            EulerRotate: ラジアンに変換した回転値。

        Raises:
            ValueError: 未対応の回転順序の場合。
        """
        return cls(math.radians(x), math.radians(y), math.radians(z), order)

    @classmethod
    def fromYawPitch(cls, direction, order="xyz"):
        """回転順序の最初の軸(基準軸)を、指定方向へ向ける2軸の回転(ピッチとヨー)を生成する。

        回転順序の文字が「基準軸・ピッチの軸・ヨーの軸」を表す(``"xyz"`` はX軸を、Y軸周りのピッチの後に
        Z軸周りのヨーで向ける)。基準軸の成分は常に0で、ロール(基準軸周りの捻り)は含まない。
        ピッチは -90〜90 度、ヨーは -180〜180 度の範囲になる。真上・真下(ヨーの軸の方向)ではヨーを0にする。

        Args:
            direction (om2.MVector | om2.MPoint | Iterable[float]): 向ける方向。長さは問わない。
            order (str | int): 回転順序。既定は ``"xyz"``。

        Returns:
            EulerRotate: 呼び出したクラスの新しいラジアンの回転。``asMatrix()`` の基準軸の行が direction の向きになる。

        Raises:
            TypeError: directionが3成分の数値でない場合。
            ValueError: directionがゼロベクトルまたは有限でない場合、または未対応の回転順序の場合。
        """
        index = orderIndex(order)
        if isinstance(direction, (om2.MVector, om2.MPoint, om2.MFloatVector, om2.MFloatPoint)):
            direction = (direction.x, direction.y, direction.z)
        vector = _finite_vector(direction, 3, "direction")
        length = math.sqrt(sum(value * value for value in vector))
        if length == 0.0:
            raise ValueError("direction must not be a zero vector")
        name = ORDER_NAMES[index]
        base, pitch_axis, yaw_axis = ("xyz".index(letter) for letter in name)
        # 巡回順(xyz・yzx・zxy)とそれ以外では、ピッチの軸周りに回した基準軸の向きの符号が変わる。
        sign = 1.0 if name in ("xyz", "yzx", "zxy") else -1.0
        along, side, up = vector[base] / length, vector[pitch_axis] / length, vector[yaw_axis] / length
        values = [0.0, 0.0, 0.0]
        values[pitch_axis] = math.atan2(-sign * up, math.hypot(along, side))
        values[yaw_axis] = math.atan2(sign * side, along) if (along or side) else 0.0
        return cls(values[0], values[1], values[2], index)

    @staticmethod
    def computeAlternateSolution(*args):
        """同じ向きを表す、単純な一周加算とは異なるオイラー回転を計算する。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 回転rotを1個指定する。角度はrad。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        return EulerRotate._wrap(_MEuler.computeAlternateSolution(*args))

    @staticmethod
    def computeBound(*args):
        """各角度を±πの範囲へ収めた、等価なオイラー回転を計算する。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 回転rotを1個指定する。角度はrad。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        return EulerRotate._wrap(_MEuler.computeBound(*args))

    @staticmethod
    def computeClosestCut(*args):
        """各軸へ一周の整数倍を加え、基準に近い等価な回転を計算する。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 元の回転srcと基準targetを指定する。角度はrad。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        return EulerRotate._wrap(_MEuler.computeClosestCut(*args))

    @staticmethod
    def computeClosestSolution(*args):
        """基準に最も近い、等価なオイラー回転を計算する。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 元の回転srcと基準targetを指定する。角度はrad。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        return EulerRotate._wrap(_MEuler.computeClosestSolution(*args))

    @staticmethod
    def decompose(*args):
        """マトリクスと回転順序からオイラー回転を分解する。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: MMatrix系のmatrixとOpenMayaの回転順序定数orderを指定する。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        return EulerRotate._wrap(_MEuler.decompose(*args))

    @property
    def orderName(self):
        """回転順序の名前(``"xyz"`` など)を取得または設定する。

        設定時は名前(大文字小文字を問わない)と om2 の番号のどちらも受け付け、
        成分は並べ替えない。未対応の値は ValueError。

        Returns:
            str: 小文字の回転順序名。
        """
        return ORDER_NAMES[self.order]

    @orderName.setter
    def orderName(self, value):
        """回転順序を名前または番号で設定する。

        Args:
            value (str | int): 回転順序。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 未対応の回転順序の場合。
        """
        self.order = orderIndex(value)

    def asDegrees(self):
        """保持するXYZのEuler角を、radから度へ換算したtupleで取得する。

        現在のMaya UI角度単位は参照しない。回転順序は変更せず、
        等価な別解や一定の角度範囲へ正規化する処理も行わない。

        Returns:
            tuple[float, float, float]: XYZ角度の独立した値列(度)。自身は変化しない。
        """
        return (math.degrees(self.x), math.degrees(self.y), math.degrees(self.z))

    def asQuaternion(self):
        """保持するEuler角と回転順序から、独立したQuaternionを作る。

        自身は変更しない。Quaternionは回転の向きを表し、元のEuler角の回転周期や
        回転順序番号、利用者の追加Python状態を保存する容器ではない。

        Returns:
            Quaternion: 新しい単位Quaternion。
        """
        return Quaternion._wrap(self)

    def mirror(self, axis="x"):
        """Matrixと同じ規約で向きをビヘイビアミラーした複製を返す。

        Args:
            axis (str | int): 反転する軸 ``"x"``・``"y"``・``"z"``、またはミラー面 ``"YZ"``・``"XZ"``・``"XY"``
                (x⇔YZ、y⇔XZ、z⇔XY。文字の順序・大文字小文字は問わない)、または0/1/2。

        Returns:
            EulerRotate: 同型の新しい回転。Eulerの回転順序は維持する。

        Raises:
            TypeError: axisが文字列・int以外の場合。
            ValueError: axisが不正な場合。
        """
        matrix = self.asMatrix().mirror(axis)
        rotation = matrix.quaternion.asEulerRotate()
        rotation.reorderIt(self.order)
        result = type(self)._wrap(rotation)
        return result

    def mirrorIt(self, axis="x"):
        """自身の向きをビヘイビアミラーする。

        Args:
            axis (str | int): mirrorと同じ反転軸。

        Returns:
            EulerRotate: 更新した自身。
        """
        self.setValue(self.mirror(axis))
        return self

    def round(self, ndigits=None, *, unit="deg"):
        """XYZの角度をunitの単位で小数点以下ndigits桁へ丸めた同型の複製を返す。

        既定では度へ換算して丸め、ラジアンへ戻して保持する(``89.99999`` 度は ``90`` 度になる)。
        内部値はラジアンなので、丸めた後の :meth:`asDegrees` には浮動小数点のわずかな誤差が残ることがある。
        各成分に組み込みの ``round`` を使い(端数がちょうど半分なら偶数側)、-0.0 は 0.0 にそろえる。
        回転順序は維持し、等価な別解への変換や角度範囲の正規化は行わない。
        組み込みの ``round(value, ndigits)`` は度で丸める。

        Args:
            ndigits (int | None): 小数点以下の桁数。負の値は整数部を丸める。Noneは整数へ丸める。
            unit (str): 丸める単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
                (``"degree"`` / ``"radians"`` 等の別名も可)。

        Returns:
            EulerRotate: 同型の新しい回転。

        Raises:
            TypeError: ndigitsがint・None以外(boolを含む)、またはunitが文字列・None以外の場合。
            ValueError: unitが未対応の場合。
        """
        ndigits = _checked_digits(ndigits)
        unit = _angle_unit(unit)
        values = [_to_radians(_round_float(_from_radians(value, unit), ndigits), unit) for value in self]
        return type(self)(values[0], values[1], values[2], self.order)

    def roundIt(self, ndigits=None, *, unit="deg"):
        """自身のXYZの角度を丸める。

        Args:
            ndigits (int | None): roundと同じ桁数。
            unit (str): roundと同じ丸める単位。

        Returns:
            EulerRotate: 更新した自身。

        Raises:
            TypeError: ndigitsがint・None以外(boolを含む)、またはunitが文字列・None以外の場合。自身は変更しない。
            ValueError: unitが未対応の場合。自身は変更しない。
        """
        self.setValue(self.round(ndigits, unit=unit))
        return self

    def asMatrix(self):
        """回転順序を反映した回転マトリクスを返す。

        Returns:
            Matrix: 回転だけを持つ4行4列のマトリクス。
        """
        from .matrix import Matrix

        return Matrix._wrap(_MEuler.asMatrix(self))

    def isEquivalent(self, other, tolerance=1e-10):
        """許容誤差付きでほぼ等しいか判定する。

        om2 の ``isEquivalent`` に委譲するため、回転順序が一致し、各成分の差が
        tolerance 以内のときだけ True になる。

        Args:
            other (om2.MEulerRotation | Iterable[float]): 比較対象。列は xyz 順序の
                ラジアンとして扱う。
            tolerance (float): 各成分の許容誤差。

        Returns:
            bool: ほぼ等しければ True。
        """
        if not isinstance(other, _MEuler):
            other = EulerRotate(other)
        return _MEuler.isEquivalent(self, other, tolerance)

    def alternateSolution(self, *args):
        """同じ向き・回転順序を持つ、別解のオイラー回転を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        return EulerRotate._wrap(_MEuler.alternateSolution(self, *args))

    def bound(self, *args):
        """各角度を±πの範囲へ収めた、等価な回転の複製を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        return EulerRotate._wrap(_MEuler.bound(self, *args))

    def closestCut(self, *args):
        """各軸へ一周の整数倍を加え、基準に近い等価な回転を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 基準となる回転targetを指定する。角度はrad。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        return EulerRotate._wrap(_MEuler.closestCut(self, *args))

    def closestSolution(self, *args):
        """基準に最も近い、等価なオイラー回転を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 基準となる回転targetを指定する。角度はrad。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        return EulerRotate._wrap(_MEuler.closestSolution(self, *args))

    def inverse(self, *args):
        """逆回転を表す新しいオイラー回転を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        return EulerRotate._wrap(_MEuler.inverse(self, *args))

    def reorder(self, *args):
        """指定した回転順序で同じ向きを表す、新しい回転を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの回転順序定数orderを指定する。

        Returns:
            EulerRotate: 演算結果を保持する新しいmlib値。
        """
        return EulerRotate._wrap(_MEuler.reorder(self, *args))

    def asVector(self, *args):
        """回転順序を除いたXYZ角度成分を、radのVectorとして返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            Vector: 演算結果を保持する新しいmlib値。
        """
        from .vector import Vector

        return Vector(_MEuler.asVector(self, *args))

    def isGimbalLocked(self, tolerance=1e-10):
        """中間の軸(回転順序の2文字目)の角度が ±90 度に近い、ジンバルロックの姿勢か判定する。

        このとき最初と最後の軸の回転が同じ向きの回転になり、1軸分の自由度を失う。

        Args:
            tolerance (float): ±90 度からの差の許容誤差(ラジアン)。0以上。

        Returns:
            bool: 中間の軸の角度を -180〜180 度へ収めた絶対値と 90 度の差が tolerance 以下ならTrue。

        Raises:
            TypeError: toleranceが数値でない場合。
            ValueError: toleranceが負・有限でない場合。
        """
        limit = _checked_tolerance(tolerance)
        middle = "xyz".index(ORDER_NAMES[self.order][1])
        angle = math.remainder(self[middle], 2.0 * math.pi)
        return abs(abs(angle) - math.pi / 2.0) <= limit

    def reverseDirection(self):
        """同じ姿勢を逆回りでたどる回転を返す。

        絶対値が最大の成分(同じなら x・y・z の順で先)へ、符号と逆向きに360度を加える
        (``asQuaternion()`` の符号が反転する。マトリクスは変わらない)。
        Eulerのフィルターや、補間の回る向きの調整に使う。

        Returns:
            EulerRotate: 同型・同じ回転順序の新しい回転。
        """
        values = list(self)
        index = max(range(3), key=lambda number: abs(values[number]))
        values[index] += -2.0 * math.pi if values[index] >= 0.0 else 2.0 * math.pi
        return type(self)(values[0], values[1], values[2], self.order)

    def reverseDirectionIt(self):
        """自身を、同じ姿勢を逆回りでたどる回転(:meth:`reverseDirection`)へ置き換える。

        Returns:
            EulerRotate: 更新した自身。
        """
        self.setValue(self.reverseDirection())
        return self

    @classmethod
    def _wrap(cls, value):
        """om2 の値を複製した cls のインスタンスを返す。

        Python の ``__new__`` / ``__init__`` を通さず(利用者の派生クラスの ``__init__`` も
        呼ばない)、基底の ``__init__`` で C++ の実体を確保する。

        Args:
            value (om2.MEulerRotation | om2.MQuaternion | om2.MMatrix): 複製元。
                ``setValue`` が受け付ける値。MEulerRotation なら順序も写す。

        Returns:
            EulerRotate: cls の新しいインスタンス。
        """
        result = _NEW(cls)
        _INIT(result)
        result.setValue(value)
        return result


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ("order_index",):
    globals().pop(_obsolete_name, None)
