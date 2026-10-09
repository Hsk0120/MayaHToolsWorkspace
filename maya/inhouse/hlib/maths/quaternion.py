"""om2.MQuaternion を継承した四元数と、回転の補間・分解。"""

import math

import maya.api.OpenMaya as om2

from .vector import (
    Vector,
    _as_mvector,
    _checked_index,
    _copy_state,
    _foreign_comparison,
    _reduce_value,
    _zero,
)

_MQuaternion = om2.MQuaternion
_MVector = om2.MVector
_NEW = _MQuaternion.__new__
_INIT = _MQuaternion.__init__
_GET = _MQuaternion.__getitem__
_SET = _MQuaternion.__setitem__
_NUMBER = (int, float)


def _quaternion_keywords(x=0.0, y=0.0, z=0.0, w=1.0):
    """キーワード引数付きの Quaternion の生成引数を (x, y, z, w) へまとめる。

    Args:
        x (float): X 成分。
        y (float): Y 成分。
        z (float): Z 成分。
        w (float): W 成分。

    Returns:
        tuple: (x, y, z, w)。
    """
    return x, y, z, w


def _unit_copy(value):
    """MQuaternion 系を正規化した新しい Quaternion を返す。

    Args:
        value (om2.MQuaternion): 正規化元。hlib の Quaternion 以外の MQuaternion も受け付ける。

    Returns:
        Quaternion: 長さ 1 の新しい四元数。

    Raises:
        ValueError: ゼロ四元数の場合。
    """
    x, y, z, w = value.x, value.y, value.z, value.w
    if x * x + y * y + z * z + w * w == 0.0:
        raise ValueError("Cannot normalize a zero quaternion")
    result = _NEW(Quaternion)
    _INIT(result)
    result.setValue(value)
    result.normalizeIt()
    return result


class Quaternion(om2.MQuaternion):
    """om2.MQuaternion を継承した XYZW 成分の可変な四元数。

    ``om2.MQuaternion`` の派生クラスなので、そのまま OpenMaya API 2.0 の関数へ
    渡せる。コンストラクタは ``Quaternion()`` (単位四元数)、
    ``Quaternion(x, y, z, w)``、``Quaternion([x, y, z, w])``、
    ``Quaternion(MQuaternion)``、``Quaternion(angle, axis)`` (軸角。axis は
    MVector 系)、``Quaternion(a, b[, factor])`` (MVector a を b へ回す回転)など
    om2 と同じ形を受け付け、加えて ``Quaternion(x=0, y=0, z=0, w=1)`` の
    キーワード引数(省略した成分は単位四元数の値)も使える。成分は数値だけで、
    不正な引数は om2 と同じく ValueError。生成時や積の計算時に正規化は行わない。

    積 ``q1 * q2`` は om2 と同じ順序で、q1 を先に適用してから q2 を適用する回転
    になる(``(q1 * q2).asMatrix()`` は ``q1.asMatrix() * q2.asMatrix()`` と同じ回転。Hamilton 積の
    ``q2 ⊗ q1`` に等しい)。``+``、``-``、単項の ``-`` は om2 の成分ごとの演算。
    ``数値 * q`` は om2 と同じく4成分のスカラー倍(``q * 数値`` と ``/`` は om2 と
    同じく未対応)。演算結果は hlib の :class:`Quaternion` で返す(``om2.MQuaternion`` が
    左辺でも同じ)。ただし ``om2.MEulerRotation * q`` は om2 側が先に処理するため
    ``om2.MEulerRotation`` になる(``EulerRotate * q`` は EulerRotate)。``*=`` / ``+=`` /
    ``-=`` は自身を書き換える(om2 の MQuaternion に無い ``+=`` / ``-=`` も hlib で
    in-place にしている)。

    値は可変で成分へ代入でき、ハッシュは不可。``len()`` は 4、添字(-4〜3。範囲外は
    IndexError。スライスは成分の tuple)と反復は X、Y、Z、W の順。``==`` は成分の
    完全一致で(``q`` と ``-q`` は同じ回転でも等しくない)、MQuaternion 系以外との
    比較は :class:`~hlib.maths.vector.Vector` と同じく例外にしない。

    数学値を返す継承メソッドも対応するhlib型を返す。コピー操作は新しい値を
    返し、It付きの更新操作は自身を書き換える。OpenMaya標準の演算と引数を維持する。
    """

    __slots__ = ()
    __hash__ = None

    def __new__(cls, *args, **kwargs):
        """C++ の実体を確保した cls のインスタンス(単位四元数)を作る。

        理由は :meth:`hlib.maths.vector.Vector.__new__` と同じ(``__new__`` だけで
        作ったインスタンスがアクセス時に落ちないよう、ここで確保する)。

        Args:
            *args: コンストラクタの引数。ここでは使わない。
            **kwargs: コンストラクタのキーワード引数。ここでは使わない。

        Returns:
            Quaternion: cls の単位四元数。
        """
        self = _NEW(cls)
        _INIT(self)
        return self

    def __init__(self, *args, **kwargs):
        """成分を設定する。

        Args:
            *args: ``()``、``(x, y, z, w)``、``(values)``、``(MQuaternion)``、
                ``(angle, axis)``、``(a, b[, factor])`` など om2 の MQuaternion の
                コンストラクタが受け付ける引数。
            **kwargs: ``x``、``y``、``z``、``w``。位置引数と合わせて使える。
                省略した成分は (0, 0, 0, 1) の値。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: om2 のコンストラクタが受け付けない引数の場合。
            TypeError: 未知のキーワード引数、または同じ成分を二重に指定した場合。
        """
        if kwargs:
            try:
                args = _quaternion_keywords(*args, **kwargs)
            except TypeError as error:
                raise TypeError("{}() {}".format(type(self).__name__, str(error).split("() ", 1)[-1])) from None
        count = len(args)
        values = args
        if count == 1:
            source = args[0]
            if isinstance(source, _MQuaternion):
                self.setValue(source)
                return
            if type(source) in (tuple, list) and len(source) == 4:
                values = source
        elif count == 0:
            self.x = 0.0
            self.y = 0.0
            self.z = 0.0
            self.w = 1.0
            return
        if len(values) == 4:
            x, y, z, w = values
            if (isinstance(x, _NUMBER) and isinstance(y, _NUMBER)
                    and isinstance(z, _NUMBER) and isinstance(w, _NUMBER)):
                self.x = x
                self.y = y
                self.z = z
                self.w = w
                return
        # 軸角などの形は om2 の多重定義の解決に任せる(不正な引数も om2 と同じ ValueError)。
        self.setValue(_MQuaternion(*args))

    def __getitem__(self, index):
        """成分を取得する。

        Args:
            index (int | slice): -4〜3 の添字(X、Y、Z、W の順)、またはスライス。

        Returns:
            float | tuple[float, ...]: 指定成分。スライスでは成分の tuple。

        Raises:
            IndexError: 添字が範囲外の場合。
            TypeError: 添字が整数・スライス以外の場合。
        """
        if index.__class__ is int and -4 <= index < 4:
            return _GET(self, index)
        if isinstance(index, slice):
            return (self.x, self.y, self.z, self.w)[index]
        return _GET(self, _checked_index(index, 4, "Quaternion"))

    def __setitem__(self, index, value):
        """成分を設定する。

        Args:
            index (int): -4〜3 の添字。
            value (float): 設定する値。

        Returns:
            None: 値を返さない。

        Raises:
            IndexError: 添字が範囲外の場合。
            TypeError: 添字が整数以外の場合。
        """
        if index.__class__ is not int or not -4 <= index < 4:
            index = _checked_index(index, 4, "Quaternion")
        _SET(self, index, value)

    def __iter__(self):
        """X、Y、Z、W の順に成分を反復する。

        Returns:
            Iterator[float]: 4成分のイテレータ。
        """
        return iter((self.x, self.y, self.z, self.w))

    def __reduce__(self):
        """copy / pickle 用に、コンストラクタを通さずに再構築する情報を返す。

        Returns:
            tuple: ``(_rebuild, (type(self), (x, y, z, w))[, state])``。
            利用者の派生クラスの ``__init__`` は呼ばず、``__dict__`` と ``__slots__`` の
            アトリビュートは再構築時に復元する。
        """
        return _reduce_value(self, (self.x, self.y, self.z, self.w))

    def __reduce_ex__(self, protocol):
        """pickle のプロトコルにかかわらず __reduce__ と同じ情報を返す。

        Args:
            protocol (int): pickle のプロトコル番号。使用しない。

        Returns:
            tuple: ``__reduce__()`` の結果。
        """
        return self.__reduce__()

    def __copy__(self):
        """同じ型・同じ成分の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートも浅く写す。

        Returns:
            Quaternion: 自身と同じクラスの新しいインスタンス。
        """
        return _copy_state(self, type(self)._wrap(self))

    def __deepcopy__(self, memo):
        """同じ型・同じ成分の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートは深く複製する。

        Args:
            memo (dict): copy.deepcopy の memo。

        Returns:
            Quaternion: 自身と同じクラスの新しいインスタンス。
        """
        return _copy_state(self, type(self)._wrap(self), memo)

    def __repr__(self):
        """クラス名と4成分を含むデバッグ表現を返す。

        Returns:
            str: ``Quaternion(x, y, z, w)`` の形式の文字列。
        """
        return "{}({!r}, {!r}, {!r}, {!r})".format(type(self).__name__, self.x, self.y, self.z, self.w)

    __str__ = __repr__

    def __eq__(self, other):
        """MQuaternion 系との成分の完全一致を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MQuaternion 系なら om2 と同じ比較の結果。
            その他の om2 の型は False。それ以外の型は NotImplemented(相手の比較に委ね、
            どちらも判断しなければ False になる)。
        """
        if isinstance(other, _MQuaternion):
            return _MQuaternion.__eq__(self, other)
        return _foreign_comparison(other, False)

    def __ne__(self, other):
        """``__eq__`` の否定を返す。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MQuaternion 系なら om2 と同じ比較の結果。
            その他の om2 の型は True。それ以外の型は NotImplemented。
        """
        if isinstance(other, _MQuaternion):
            return _MQuaternion.__ne__(self, other)
        return _foreign_comparison(other, True)

    def __mul__(self, other):
        """om2 の順序で四元数の積を返す(自身を先に適用する回転)。

        Args:
            other (object): 右側の MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 積。正規化しない。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MQuaternion):
            return NotImplemented
        result = Quaternion._wrap(self)
        _MQuaternion.__imul__(result, other)
        return result

    def __rmul__(self, other):
        """左辺の MQuaternion 系との積を om2 の順序で返す。数値なら成分をスケールする。

        ``数値 * q`` は om2 と同じく4成分それぞれのスカラー倍(正規化しない)。
        ``q * 数値`` は om2 と同じく対応しない。

        Args:
            other (object): 左側の MQuaternion 系、または int / float。

        Returns:
            Quaternion | types.NotImplementedType: 積。対応しない型は NotImplemented。
        """
        if isinstance(other, _NUMBER):
            return Quaternion._wrap(_MQuaternion.__rmul__(self, other))
        if not isinstance(other, _MQuaternion):
            return NotImplemented
        result = Quaternion._wrap(other)
        _MQuaternion.__imul__(result, self)
        return result

    def __imul__(self, other):
        """自身へ右から MQuaternion 系を掛ける(``self = self * other``)。

        Args:
            other (object): 右側の MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MQuaternion):
            return NotImplemented
        return _MQuaternion.__imul__(self, other)

    def __add__(self, other):
        """成分ごとの和を返す(om2 の ``+``)。

        Args:
            other (object): MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 和。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MQuaternion):
            return NotImplemented
        return Quaternion._wrap(_MQuaternion.__add__(self, other))

    def __radd__(self, other):
        """左辺の MQuaternion 系との成分ごとの和を返す。

        Args:
            other (object): MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 和。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MQuaternion):
            return NotImplemented
        return Quaternion._wrap(_MQuaternion.__add__(other, self))

    def __iadd__(self, other):
        """MQuaternion 系を成分ごとに自身へ加算する(om2 の MQuaternion には無い in-place 版)。

        Args:
            other (object): MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MQuaternion):
            return NotImplemented
        self.setValue(_MQuaternion.__add__(self, other))
        return self

    def __sub__(self, other):
        """成分ごとの差を返す(om2 の ``-``)。

        Args:
            other (object): MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 差。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MQuaternion):
            return NotImplemented
        return Quaternion._wrap(_MQuaternion.__sub__(self, other))

    def __rsub__(self, other):
        """左辺の MQuaternion 系から自身を引いた成分ごとの差を返す。

        Args:
            other (object): MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 差。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MQuaternion):
            return NotImplemented
        return Quaternion._wrap(_MQuaternion.__sub__(other, self))

    def __isub__(self, other):
        """MQuaternion 系を成分ごとに自身から減算する(om2 の MQuaternion には無い in-place 版)。

        Args:
            other (object): MQuaternion 系。

        Returns:
            Quaternion | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MQuaternion):
            return NotImplemented
        self.setValue(_MQuaternion.__sub__(self, other))
        return self

    def __neg__(self):
        """全成分の符号を反転した四元数を返す(同じ回転を表す)。

        Returns:
            Quaternion: 新しい四元数。
        """
        return Quaternion._wrap(_MQuaternion.__neg__(self))

    @classmethod
    def fromAxisAngle(cls, axis, angle):
        """軸と角度から回転四元数を生成する。

        Args:
            axis (om2.MVector | Iterable[float]): 回転軸。内部で正規化する。
            angle (float): 回転角度(ラジアン)。

        Returns:
            Quaternion: axis を中心に angle だけ回転する単位四元数。

        Raises:
            ValueError: axis がゼロベクトルの場合(om2 は単位四元数を返す)。
        """
        axis = _as_mvector(axis)
        length = axis.length()
        if length == 0.0:
            raise ValueError("Cannot normalize a zero vector")
        half = angle / 2.0
        sine = math.sin(half)
        result = _NEW(cls)
        _INIT(result)
        result.x = axis.x / length * sine
        result.y = axis.y / length * sine
        result.z = axis.z / length * sine
        result.w = math.cos(half)
        return result

    @staticmethod
    def squad(*args):
        """OpenMayaと同じ演算でQuaternionの新しい値を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。

        Returns:
            Quaternion: 演算結果を保持する新しいhlib値。
        """
        return Quaternion._wrap(_MQuaternion.squad(*args))

    @staticmethod
    def squadPt(*args):
        """OpenMayaと同じ演算でQuaternionの新しい値を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。

        Returns:
            Quaternion: 演算結果を保持する新しいhlib値。
        """
        return Quaternion._wrap(_MQuaternion.squadPt(*args))

    def dot(self, other):
        """4成分の内積を返す。

        Args:
            other (om2.MQuaternion): 内積の相手。x、y、z、w を持つ値。

        Returns:
            float: 内積。
        """
        return self.x * other.x + self.y * other.y + self.z * other.z + self.w * other.w

    def length(self):
        """四元数の長さ(ノルム)を返す。

        Returns:
            float: 長さ。
        """
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z + self.w * self.w)

    def unitIt(self):
        """ゼロ値を拒否して自身を正規化する。

        Returns:
            Quaternion: 更新した自身。

        Raises:
            ValueError: ゼロ値の場合。自身は変更しない。
        """
        value = self.unit()
        self.setValue(value)
        return self

    def unit(self):
        """正規化した新しい四元数を返す。

        om2 の ``normal()`` はゼロ四元数に単位四元数を返すが、このメソッドは拒否する。

        Returns:
            Quaternion: 長さ 1 の四元数。

        Raises:
            ValueError: ゼロ四元数の場合。
        """
        return _unit_copy(self)

    def conjugate(self):
        """共役四元数を返す(om2 の同名メソッドを hlib の型で返すよう上書き)。

        Returns:
            Quaternion: XYZ 成分の符号を反転した新しい四元数。
        """
        result = Quaternion._wrap(self)
        result.conjugateIt()
        return result

    def inverse(self):
        """逆四元数(共役を長さの2乗で割った値)を返す。

        om2 の同名メソッドを上書きし、hlib の型で返す。om2 はゼロ四元数に NaN を
        返すが、このメソッドは拒否する。単位四元数なら conjugate() と同じ。

        Returns:
            Quaternion: 逆四元数。

        Raises:
            ValueError: ゼロ四元数の場合。
        """
        if self.x * self.x + self.y * self.y + self.z * self.z + self.w * self.w == 0.0:
            raise ValueError("Cannot invert a zero quaternion")
        result = Quaternion._wrap(self)
        result.invertIt()
        return result

    def rotateVector(self, vector):
        """ベクトルをこの回転で変換する。

        自身を正規化してから適用するため、正規化していない四元数でも結果の大きさは
        変わらない(om2 の ``MVector.rotateBy`` は正規化しない四元数だと大きさも変える)。

        Args:
            vector (om2.MVector | Iterable[float]): 回転させる方向・位置。

        Returns:
            Vector: 回転後のベクトル。派生クラスの型は保持しない。

        Raises:
            ValueError: 自身がゼロ四元数の場合。
        """
        result = _zero(Vector)
        _MVector.__iadd__(result, _as_mvector(vector).rotateBy(_unit_copy(self)))
        return result

    def angleTo(self, other):
        """別の四元数が表す回転との角度差をラジアンで返す。

        両方を正規化し、二重被覆(q と -q が同じ回転)を考慮する。acos を使わず
        ``4 * atan2(|p - q|, |p + q|)`` で計算するため、角度差が 0 や pi に近くても
        精度を保つ。

        Args:
            other (om2.MQuaternion): 角度差を測る相手の回転。

        Returns:
            float: 0 から pi の範囲のラジアン角度。

        Raises:
            ValueError: 自身または other がゼロ四元数の場合。
        """
        p = _unit_copy(self)
        q = _unit_copy(other)
        if p.x * q.x + p.y * q.y + p.z * q.z + p.w * q.w < 0.0:
            q.negateIt()
        dx, dy, dz, dw = p.x - q.x, p.y - q.y, p.z - q.z, p.w - q.w
        sx, sy, sz, sw = p.x + q.x, p.y + q.y, p.z + q.z, p.w + q.w
        return 4.0 * math.atan2(math.sqrt(dx * dx + dy * dy + dz * dz + dw * dw),
                                math.sqrt(sx * sx + sy * sy + sz * sz + sw * sw))

    def slerp(self, other, t, spin=0):
        """別の四元数との球面線形補間を返す。

        om2 の静的メソッド ``MQuaternion.slerp(p, q, t, spin=0)`` を上書きする。
        インスタンスメソッドとして ``p.slerp(q, t)`` と呼べるほか、
        ``Quaternion.slerp(p, q, t)`` の静的呼び出しの形でも使える。入力を正規化
        してから om2 の slerp で最短経路を補間する。

        Args:
            other (om2.MQuaternion): 補間先の回転。
            t (float): 補間係数。0 で自身、1 で other。
            spin (int): om2 の slerp に渡す追加回転数。既定は 0。

        Returns:
            Quaternion: 補間結果。

        Raises:
            ValueError: 自身または other がゼロ四元数の場合。
        """
        return Quaternion._wrap(_MQuaternion.slerp(_unit_copy(self), _unit_copy(other), t, spin))

    def asCanonicalAxisAngle(self):
        """軸と角度の組へ分解する。

        om2 の ``asAxisAngle`` と異なり、w が負なら符号を反転して角度を 0 から pi の
        範囲に収め、回転が無い場合の軸は (1, 0, 0) とする。角度は
        ``2 * atan2(|xyz|, w)`` で求めるため、微小な回転でも精度を保つ。

        Returns:
            tuple[Vector, float]: 正規化した回転軸と、ラジアンの回転角度(0 から pi)。

        Raises:
            ValueError: 自身がゼロ四元数の場合。
        """
        rotation = _unit_copy(self)
        if rotation.w < 0.0:
            rotation.negateIt()
        sine = math.sqrt(rotation.x * rotation.x + rotation.y * rotation.y + rotation.z * rotation.z)
        angle = 2.0 * math.atan2(sine, rotation.w)
        result = _zero(Vector)
        if sine == 0.0:
            result.x = 1.0
            return result, angle
        result.x = rotation.x / sine
        result.y = rotation.y / sine
        result.z = rotation.z / sine
        return result, angle

    def asSwingTwist(self, axis=(1.0, 0.0, 0.0)):
        """指定軸まわりの捻り(twist)と、それ以外の曲げ(swing)へ分解する。

        ``twist`` は axis 周りだけの回転、``swing`` は axis の向きを変える残りの
        回転。om2 の積の順序で ``twist * swing`` が自身と同じ回転になる
        (twist を先に適用し、続けて swing を適用する)。

        Args:
            axis (om2.MVector | Iterable[float]): 捻り軸。内部で正規化する。

        Returns:
            tuple[Quaternion, Quaternion]: (swing, twist)。どちらも正規化済み。

        Raises:
            ValueError: axis がゼロベクトルの場合、または自身がゼロ四元数の場合。
        """
        axis = _as_mvector(axis)
        length = axis.length()
        if length == 0.0:
            raise ValueError("Cannot normalize a zero vector")
        ax, ay, az = axis.x / length, axis.y / length, axis.z / length
        rotation = _unit_copy(self)
        dot = rotation.x * ax + rotation.y * ay + rotation.z * az
        twist = _NEW(Quaternion)
        _INIT(twist)
        twist.x = dot * ax
        twist.y = dot * ay
        twist.z = dot * az
        twist.w = rotation.w
        twist_length = twist.length()
        if twist_length < 1e-10:
            # 捻り軸に直交する180度回転など、axis 成分が無い姿勢は捻りなしとみなす。
            twist = _NEW(Quaternion)
            _INIT(twist)
        else:
            twist.x /= twist_length
            twist.y /= twist_length
            twist.z /= twist_length
            twist.w /= twist_length
        swing = twist.conjugate() * rotation
        return swing, twist

    def asDecomposedEulerRotate(self, order="xyz"):
        """EulerRotate へ変換する。

        正規化した回転行列を ``om2.MEulerRotation.decompose`` で分解するため、
        ``Matrix.euler`` と同じ規約の角度になる。中間軸が 90 度を超える等価な角度を
        返すことがある。

        Args:
            order (str | int): 回転順序。``"xyz"``/``"yzx"``/``"zxy"``/``"xzy"``/
                ``"yxz"``/``"zyx"``、または om2 の番号 0〜5。

        Returns:
            EulerRotate: ラジアンの Euler 回転値。

        Raises:
            ValueError: order が未対応の場合、またはゼロ四元数の場合。
        """
        from .eulerRotate import EulerRotate, orderIndex

        index = orderIndex(order)
        return EulerRotate._wrap(om2.MEulerRotation.decompose(_unit_copy(self).asMatrix(), index))

    def mirror(self, axis="x"):
        """Matrixと同じ規約で向きをビヘイビアミラーした複製を返す。

        Args:
            axis (str | int): x/y/z/xy/xz/yz/xyz、または0/1/2。

        Returns:
            Quaternion: 同型の新しい回転。Eulerの回転順序は維持する。
        """
        matrix = self.asUnitMatrix().mirror(axis)
        result = type(self)._wrap(matrix.quaternion)
        return result

    def mirrorIt(self, axis="x"):
        """自身の向きをビヘイビアミラーする。

        Args:
            axis (str | int): mirrorと同じ反転軸。

        Returns:
            Quaternion: 更新した自身。
        """
        self.setValue(self.mirror(axis))
        return self

    def asUnitMatrix(self):
        """正規化した回転を表す Matrix を返す。

        Returns:
            Matrix: 回転だけを持つ4行4列行列。

        Raises:
            ValueError: ゼロ四元数の場合。
        """
        from .matrix import Matrix

        return Matrix._wrap(_MQuaternion.asMatrix(_unit_copy(self)))

    def normal(self, *args):
        """OpenMayaと同じ演算でQuaternionの新しい値を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。

        Returns:
            Quaternion: 演算結果を保持する新しいhlib値。
        """
        return Quaternion._wrap(_MQuaternion.normal(self, *args))

    def exp(self, *args):
        """OpenMayaと同じ演算でQuaternionの新しい値を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。

        Returns:
            Quaternion: 演算結果を保持する新しいhlib値。
        """
        return Quaternion._wrap(_MQuaternion.exp(self, *args))

    def log(self, *args):
        """OpenMayaと同じ演算でQuaternionの新しい値を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。

        Returns:
            Quaternion: 演算結果を保持する新しいhlib値。
        """
        return Quaternion._wrap(_MQuaternion.log(self, *args))

    def asMatrix(self, *args):
        """OpenMayaと同じ演算でMatrixの新しい値を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。

        Returns:
            Matrix: 演算結果を保持する新しいhlib値。
        """
        from .matrix import Matrix

        return Matrix._wrap(_MQuaternion.asMatrix(self, *args))

    def asEulerRotation(self, *args):
        """OpenMayaと同じ演算でEulerRotateの新しい値を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。

        Returns:
            EulerRotate: 演算結果を保持する新しいhlib値。
        """
        from .eulerRotate import EulerRotate

        return EulerRotate._wrap(_MQuaternion.asEulerRotation(self, *args))

    def asEulerRotate(self, *args):
        """標準のasEulerRotationへ委譲し、EulerRotateの新しい値を返す。

        Args:
            *args: OpenMayaの標準メソッドへ渡す位置引数。

        Returns:
            EulerRotate: ラジアンのEuler回転値。元の標準メソッドと同じ演算結果。

        Note:
            OpenMaya標準のasEulerRotationも引き続き使用できる。
            引数・例外・自身を変更しない動作は標準メソッドと同じ。
        """
        return self.asEulerRotation(*args)

    def asAxisAngle(self):
        """OpenMayaの軸角表現をhlibの軸ベクトルで返す。

        Returns:
            tuple[Vector, float]: 軸とラジアン角度。角度範囲はOpenMayaに従う。
        """
        axis, angle = _MQuaternion.asAxisAngle(self)
        return Vector(axis), angle

    @classmethod
    def _wrap(cls, value):
        """om2 の値を複製した cls のインスタンスを返す。

        Python の ``__new__`` / ``__init__`` を通さない(利用者の派生クラスの
        ``__init__`` も呼ばない)。

        Args:
            value (om2.MQuaternion | om2.MEulerRotation | om2.MMatrix): 複製元。
                ``setValue`` が受け付ける値。

        Returns:
            Quaternion: cls の新しいインスタンス。
        """
        result = _NEW(cls)
        _INIT(result)
        result.setValue(value)
        return result
