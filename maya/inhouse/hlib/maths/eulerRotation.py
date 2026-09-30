"""om2.MEulerRotation を継承した、回転順序を持つラジアンのオイラー回転値。"""

import math
import operator

import maya.api.OpenMaya as om2

from .quaternion import Quaternion
from .vector import _checked_index, _copy_state, _foreign_comparison, _reduce_value

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


def order_index(order):
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
            raise ValueError("Unsupported rotation order: {!r}".format(order))
        return index
    if isinstance(order, bool):
        raise ValueError("Unsupported rotation order: {!r}".format(order))
    try:
        index = operator.index(order)
    except TypeError:
        raise ValueError("Unsupported rotation order: {!r}".format(order)) from None
    if not 0 <= index < 6:
        raise ValueError("Unsupported rotation order: {!r}".format(order))
    return index


def _euler_keywords(x=0.0, y=0.0, z=0.0, order=None):
    """キーワード引数付きの EulerRotation の生成引数を (x, y, z, order) へまとめる。

    Args:
        x (float): X 回転(ラジアン)。
        y (float): Y 回転(ラジアン)。
        z (float): Z 回転(ラジアン)。
        order (str | int | None): 回転順序。None は xyz。

    Returns:
        tuple: (x, y, z, order)。
    """
    return x, y, z, order


class EulerRotation(om2.MEulerRotation):
    """om2.MEulerRotation を継承した、ラジアンの3成分と回転順序を持つ可変な回転値。

    ``om2.MEulerRotation`` の派生クラスなので、そのまま OpenMaya API 2.0 の関数へ
    渡せる。:class:`~hlib.maths.vector.Vector` の派生ではない。

    受け付ける引数は次のとおり。

    * ``EulerRotation()``: (0, 0, 0)、順序 xyz。
    * ``EulerRotation(x, y, z[, order])``、または ``order=`` キーワード。
    * ``EulerRotation(x=..., y=..., z=..., order=...)``: キーワード引数(省略した成分は 0)。
    * ``EulerRotation(values[, order])``: values は3要素の列や MVector。
      order を指定しても成分の並べ替えはしない(並べ替えは om2 の ``reorder()``)。
    * ``EulerRotation(MEulerRotation)``: 順序を含めて複製する。

    成分は数値だけで、文字列などは om2 と同じく ValueError になる。
    ``order`` は om2 と同じ int(``kXYZ`` = 0、``kYZX`` = 1、``kZXY`` = 2、``kXZY`` = 3、
    ``kYXZ`` = 4、``kZYX`` = 5。Maya の rotateOrder アトリビュートの番号と同じ並び)で、
    名前は :attr:`order_name` で取得・設定する。コンストラクタの order には
    名前(``"zyx"`` など。大文字小文字を問わない)と番号のどちらも使える。

    演算子は om2 の意味論に従い、結果を hlib の :class:`EulerRotation` で返す。
    ``+`` / ``-`` は順序が同じなら成分ごと、違えば右辺を左辺の順序へ変換して計算する。
    ``*`` は数値なら成分のスケール、EulerRotation / Quaternion なら回転の合成。
    om2 に無い ``数値 * e`` と ``e / 数値`` (成分ごとの除算)は hlib の拡張として使える。
    ``+=`` / ``-=`` / ``*=`` / ``/=`` は自身を書き換える。

    値は可変でハッシュは不可。添字(-3〜2。範囲外は IndexError。スライスは成分の
    tuple)と反復は X、Y、Z の順。``==`` は om2 と同じく順序を含めた成分の完全一致で、
    MEulerRotation 系以外との比較は :class:`~hlib.maths.vector.Vector` と同じく
    例外にしない。表示は度に変換するが、内部値はラジアン。

    snake_case のメソッドは hlib の型を返す。om2 から継承した camelCase のメソッド
    (``asQuaternion``、``asMatrix``、``reorder``、``bound``、``closestSolution`` など)は
    om2 の基底型を返す。
    """

    __slots__ = ()
    __hash__ = None

    def __new__(cls, *args, **kwargs):
        """C++ の実体を確保した cls のインスタンス(0 回転、順序 xyz)を作る。

        理由は :meth:`hlib.maths.vector.Vector.__new__` と同じ。:meth:`__init__` で
        引数を検証する前に確保しておくため、検証の例外を握りつぶす派生クラスでも
        アクセス時に落ちない。

        Args:
            *args: コンストラクタの引数。ここでは使わない。
            **kwargs: コンストラクタのキーワード引数。ここでは使わない。

        Returns:
            EulerRotation: cls の 0 回転。
        """
        self = _NEW(cls)
        _INIT(self)
        return self

    def __init__(self, *args, **kwargs):
        """成分と回転順序を設定する。

        引数をすべて検証してから書き込むため、例外時に値は変わらない。

        Args:
            *args: ``()``、``(x, y, z)``、``(x, y, z, order)``、``(values)``、
                ``(values, order)``、または ``(MEulerRotation)``。角度はラジアン。
            **kwargs: ``order``、または ``x`` / ``y`` / ``z`` / ``order`` のキーワード引数。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 未対応の回転順序、または成分が数値でない場合。
            TypeError: 引数の数や型が不正な場合、または同じ引数を二重に指定した場合。
        """
        if not kwargs:
            # よく使う ()、(x, y, z)、(x, y, z, order) は解析を省く。
            count = len(args)
            if count == 3 or count == 4:
                x, y, z = args[0], args[1], args[2]
                if isinstance(x, _NUMBER) and isinstance(y, _NUMBER) and isinstance(z, _NUMBER):
                    index = order_index(args[3]) if count == 4 else 0
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
                raise TypeError("{}() {}".format(type(self).__name__, str(error).split("() ", 1)[-1])) from None
        else:
            order = kwargs.pop("order", None)
            if kwargs:
                raise TypeError("EulerRotation got unexpected keyword arguments: " + ", ".join(sorted(kwargs)))
            count = len(args)
            if count == 1 and order is None and isinstance(args[0], _MEuler):
                self.setValue(args[0])
                return
            if count in (1, 2) and not isinstance(args[0], _NUMBER):
                if count == 2:
                    if order is not None:
                        raise TypeError("EulerRotation got multiple values for 'order'")
                    order = args[1]
                x, y, z = args[0]
            elif count in (3, 4):
                x, y, z = args[0], args[1], args[2]
                if count == 4:
                    if order is not None:
                        raise TypeError("EulerRotation got multiple values for 'order'")
                    order = args[3]
            elif count == 0:
                x = y = z = 0.0
            else:
                raise TypeError("EulerRotation expects (), (x, y, z[, order]), (values[, order]) or (EulerRotation)")
        index = 0 if order is None else order_index(order)
        if not (isinstance(x, _NUMBER) and isinstance(y, _NUMBER) and isinstance(z, _NUMBER)):
            # 数値以外は om2 の変換規則に任せる(文字列などは om2 と同じ ValueError)。
            source = _MEuler(x, y, z)
            x, y, z = source.x, source.y, source.z
        self.x = x
        self.y = y
        self.z = z
        self.order = index

    @classmethod
    def _wrap(cls, value):
        """om2 の値を複製した cls のインスタンスを返す。

        Python の ``__new__`` / ``__init__`` を通さず(利用者の派生クラスの ``__init__`` も
        呼ばない)、基底の ``__init__`` で C++ の実体を確保する。

        Args:
            value (om2.MEulerRotation | om2.MQuaternion | om2.MMatrix): 複製元。
                ``setValue`` が受け付ける値。MEulerRotation なら順序も写す。

        Returns:
            EulerRotation: cls の新しいインスタンス。
        """
        result = _NEW(cls)
        _INIT(result)
        result.setValue(value)
        return result

    @classmethod
    def from_iterable(cls, values, order="xyz"):
        """3要素の反復可能オブジェクトから生成する。

        Args:
            values (Iterable[float]): ラジアンの3成分。
            order (str | int): 回転順序。既定は ``"xyz"``。

        Returns:
            EulerRotation: 呼び出したクラスの新しいインスタンス。

        Raises:
            ValueError: 要素数が3でない場合、または未対応の回転順序の場合。
        """
        values = tuple(values)
        if len(values) != 3:
            raise ValueError("{} expects 3 values".format(cls.__name__))
        return cls(values[0], values[1], values[2], order)

    @classmethod
    def from_degrees(cls, x, y, z, order="xyz"):
        """度数法の3成分から生成する。

        Args:
            x (float): X 回転角度(度)。
            y (float): Y 回転角度(度)。
            z (float): Z 回転角度(度)。
            order (str | int): 回転順序。既定は ``"xyz"``。

        Returns:
            EulerRotation: ラジアンに変換した回転値。

        Raises:
            ValueError: 未対応の回転順序の場合。
        """
        return cls(math.radians(x), math.radians(y), math.radians(z), order)

    # ------------------------------------------------------------------ 値
    @property
    def order_name(self):
        """回転順序の名前(``"xyz"`` など)を取得または設定する。

        設定時は名前(大文字小文字を問わない)と om2 の番号のどちらも受け付け、
        成分は並べ替えない。未対応の値は ValueError。

        Returns:
            str: 小文字の回転順序名。
        """
        return ORDER_NAMES[self.order]

    @order_name.setter
    def order_name(self, value):
        """回転順序を名前または番号で設定する。

        Args:
            value (str | int): 回転順序。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 未対応の回転順序の場合。
        """
        self.order = order_index(value)

    def as_degrees(self):
        """回転成分を度数法の3要素 tuple として取得する。

        Returns:
            tuple[float, float, float]: XYZ の回転角度(度)。
        """
        return (math.degrees(self.x), math.degrees(self.y), math.degrees(self.z))

    def to_quaternion(self):
        """回転順序を反映した Quaternion へ変換する。

        Returns:
            Quaternion: 単位四元数。
        """
        return Quaternion._wrap(self)

    def mirrored(self, axis="x"):
        """Matrixと同じ規約で向きをビヘイビアミラーした複製を返す。

        Args:
            axis (str | int): x/y/z/xy/xz/yz/xyz、または0/1/2。

        Returns:
            EulerRotation: 同型の新しい回転。Eulerの回転順序は維持する。
        """
        matrix = self.to_matrix().mirrored(axis)
        rotation = matrix.quaternion.asEulerRotation()
        rotation.reorderIt(self.order)
        result = type(self)._wrap(rotation)
        return result

    def mirror(self, axis="x"):
        """自身の向きをビヘイビアミラーする。

        Args:
            axis (str | int): mirroredと同じ反転軸。

        Returns:
            EulerRotation: 更新した自身。
        """
        self.setValue(self.mirrored(axis))
        return self

    def to_matrix(self):
        """回転順序を反映した回転行列を返す。

        Returns:
            Matrix: 回転だけを持つ4行4列行列。
        """
        from .matrix import Matrix

        return Matrix._wrap(self.asMatrix())

    def is_equivalent(self, other, tolerance=1e-10):
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
            other = EulerRotation(other)
        return _MEuler.isEquivalent(self, other, tolerance)

    # ------------------------------------------------------------------ 添字・反復
    def __getitem__(self, index):
        """回転成分を取得する。

        Args:
            index (int | slice): -3〜2 の添字(X、Y、Z の順)、またはスライス。

        Returns:
            float | tuple[float, ...]: 指定成分(ラジアン)。スライスでは成分の tuple。

        Raises:
            IndexError: 添字が範囲外の場合。
            TypeError: 添字が整数・スライス以外の場合。
        """
        if index.__class__ is int and -3 <= index < 3:
            return _GET(self, index)
        if isinstance(index, slice):
            return (self.x, self.y, self.z)[index]
        return _GET(self, _checked_index(index, 3, "EulerRotation"))

    def __setitem__(self, index, value):
        """回転成分を設定する。

        Args:
            index (int): -3〜2 の添字。
            value (float): 設定する値(ラジアン)。

        Returns:
            None: 値を返さない。

        Raises:
            IndexError: 添字が範囲外の場合。
            TypeError: 添字が整数以外の場合。
        """
        if index.__class__ is not int or not -3 <= index < 3:
            index = _checked_index(index, 3, "EulerRotation")
        _SET(self, index, value)

    def __iter__(self):
        """X、Y、Z の順に回転成分を反復する。

        Returns:
            Iterator[float]: 3成分(ラジアン)のイテレータ。
        """
        return iter((self.x, self.y, self.z))

    # ------------------------------------------------------------------ 複製・表示・比較
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
            EulerRotation: 自身と同じクラスの新しいインスタンス。
        """
        return _copy_state(self, type(self)._wrap(self))

    def __deepcopy__(self, memo):
        """同じ型・同じ成分と順序の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートは深く複製する。

        Args:
            memo (dict): copy.deepcopy の memo。

        Returns:
            EulerRotation: 自身と同じクラスの新しいインスタンス。
        """
        return _copy_state(self, type(self)._wrap(self), memo)

    def __repr__(self):
        """度数法の回転成分と回転順序名を含むデバッグ表現を返す。

        Returns:
            str: ``EulerRotation(degrees=(90, 0, -45), order='xyz')`` の形式の文字列。
            内部値はラジアンのまま。
        """
        values = ", ".join("{:.15g}".format(value) for value in self.as_degrees())
        return "{}(degrees=({}), order={!r})".format(type(self).__name__, values, self.order_name)

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

    # ------------------------------------------------------------------ 演算
    def __add__(self, other):
        """om2 の ``+`` の結果を EulerRotation で返す。

        Args:
            other (object): MEulerRotation 系。順序が違えば自身の順序へ変換して加算する。

        Returns:
            EulerRotation | types.NotImplementedType: 和。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MEuler):
            return NotImplemented
        return EulerRotation._wrap(_MEuler.__add__(self, other))

    def __radd__(self, other):
        """左辺の MEulerRotation 系との和を返す。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotation | types.NotImplementedType: 和。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MEuler):
            return NotImplemented
        return EulerRotation._wrap(_MEuler.__add__(other, self))

    def __sub__(self, other):
        """om2 の ``-`` の結果を EulerRotation で返す。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotation | types.NotImplementedType: 差。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MEuler):
            return NotImplemented
        return EulerRotation._wrap(_MEuler.__sub__(self, other))

    def __rsub__(self, other):
        """左辺の MEulerRotation 系から自身を引いた値を返す。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotation | types.NotImplementedType: 差。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MEuler):
            return NotImplemented
        return EulerRotation._wrap(_MEuler.__sub__(other, self))

    def __mul__(self, other):
        """om2 の ``*`` の結果を EulerRotation で返す。

        Args:
            other (object): 数値(成分のスケール)、または MEulerRotation 系 /
                MQuaternion 系(自身を先に適用する回転の合成)。

        Returns:
            EulerRotation | types.NotImplementedType: 結果。対応しない型は NotImplemented。
        """
        if not isinstance(other, (int, float, _MEuler, _MQuaternion)):
            return NotImplemented
        return EulerRotation._wrap(_MEuler.__mul__(self, other))

    def __rmul__(self, other):
        """左辺からの乗算を om2 の意味論で行う。

        Args:
            other (object): 数値、または左辺の MEulerRotation 系。

        Returns:
            EulerRotation | types.NotImplementedType: 結果。対応しない型は NotImplemented。
        """
        if isinstance(other, _NUMBER):
            return EulerRotation._wrap(_MEuler.__mul__(self, other))
        if isinstance(other, _MEuler):
            return EulerRotation._wrap(_MEuler.__mul__(other, self))
        return NotImplemented

    def __truediv__(self, other):
        """数値による成分ごとの除算を返す(om2 には無い hlib の拡張)。

        順序は保持し、各成分を other で割る。

        Args:
            other (object): 除数の int または float。

        Returns:
            EulerRotation | types.NotImplementedType: 新しい回転値。対応しない型は NotImplemented。

        Raises:
            ZeroDivisionError: other が 0 の場合。
        """
        if not isinstance(other, _NUMBER):
            return NotImplemented
        if other == 0:
            raise ZeroDivisionError("EulerRotation division by zero")
        result = EulerRotation._wrap(self)
        result.x = self.x / other
        result.y = self.y / other
        result.z = self.z / other
        return result

    def __neg__(self):
        """om2 の単項 ``-`` (逆回転の成分)を EulerRotation で返す。

        Returns:
            EulerRotation: 新しい回転値。
        """
        return EulerRotation._wrap(_MEuler.__neg__(self))

    def __iadd__(self, other):
        """MEulerRotation 系を自身へ加算する。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotation | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MEuler):
            return NotImplemented
        return _MEuler.__iadd__(self, other)

    def __isub__(self, other):
        """MEulerRotation 系を自身から減算する。

        Args:
            other (object): MEulerRotation 系。

        Returns:
            EulerRotation | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MEuler):
            return NotImplemented
        return _MEuler.__isub__(self, other)

    def __imul__(self, other):
        """数値倍、または回転の合成を自身へ適用する。

        Args:
            other (object): 数値、MEulerRotation 系、または MQuaternion 系。

        Returns:
            EulerRotation | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, (int, float, _MEuler, _MQuaternion)):
            return NotImplemented
        return _MEuler.__imul__(self, other)

    def __itruediv__(self, other):
        """数値で自身の各成分を除算する(hlib の拡張。順序は変えない)。

        Args:
            other (object): 除数の int または float。

        Returns:
            EulerRotation | types.NotImplementedType: 自身。対応しない型は NotImplemented。

        Raises:
            ZeroDivisionError: other が 0 の場合。
        """
        if not isinstance(other, _NUMBER):
            return NotImplemented
        if other == 0:
            raise ZeroDivisionError("EulerRotation division by zero")
        self.x = self.x / other
        self.y = self.y / other
        self.z = self.z / other
        return self
