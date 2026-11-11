"""om2.MVector を継承した3成分ベクトルと基本演算。"""

import math
from typing import Any, Sequence

import maya.api.OpenMaya as om2

from ..util import (
    _checked_digits,
    _checked_index,
    _checked_tolerance,
    _copy_state,
    _finite,
    _foreign_comparison,
    _instance_state,
    _rethrow_init_error,
    _round_float,
)

_MVector = om2.MVector
_MPoint = om2.MPoint
_MMatrix = om2.MMatrix
_MQuaternion = om2.MQuaternion
_MEuler = om2.MEulerRotation
_NEW = _MVector.__new__
_INIT = _MVector.__init__
_GET = _MVector.__getitem__
_SET = _MVector.__setitem__
#: スカラーとして扱う数値型。bool は int の派生として含まれる(om2 と同じ)。
_NUMBER = (int, float)
#: MVector のコンストラクタへそのまま渡せる om2 の3成分型。
_OM2_POINT_TYPES = (_MPoint, om2.MFloatVector, om2.MFloatPoint)
#: 軸の名前(小文字)から (成分の番号, 向き) への表。
_AXIS_NAMES = {
    "x": (0, 1.0), "+x": (0, 1.0), "-x": (0, -1.0),
    "y": (1, 1.0), "+y": (1, 1.0), "-y": (1, -1.0),
    "z": (2, 1.0), "+z": (2, 1.0), "-z": (2, -1.0),
}


def _resolve_mvector(value):
    """値を om2.MVector として扱える形へ変換する。

    MVector 系(mlib の Vector 派生を含む)はそのまま返す。MPoint などの om2 の
    3成分型は MVector へ変換し(MPoint の w では割らない)、それ以外は
    3要素の反復可能オブジェクトとして展開する。

    Args:
        value (om2.MVector | om2.MPoint | Iterable[float]): 変換元。

    Returns:
        om2.MVector: value 自身、または新しい MVector。

    Raises:
        TypeError: 反復できない値の場合。
        ValueError: 反復可能オブジェクトの要素数が3でない場合。
    """
    if isinstance(value, _MVector):
        return value
    if isinstance(value, _OM2_POINT_TYPES):
        return _MVector(value)
    x, y, z = value
    result = _MVector()
    result.x = x
    result.y = y
    result.z = z
    return result


def _vector_operand(value):
    """加減算・比較の相手を om2.MVector として扱える形へそろえる。

    MVector 系はそのまま返し、3個の数値(int/float。boolを除く)を持つ tuple/list は新しい
    MVector へ変換する。MPoint などそれ以外の型は対応しないため None を返す。

    Args:
        value (object): 演算・比較の相手。

    Returns:
        om2.MVector | None: 相手の値。対応しない型は None。
    """
    if isinstance(value, _MVector):
        return value
    if type(value) in (tuple, list) and len(value) == 3:
        x, y, z = value
        if (isinstance(x, _NUMBER) and isinstance(y, _NUMBER) and isinstance(z, _NUMBER)
                and not isinstance(x, bool) and not isinstance(y, bool) and not isinstance(z, bool)):
            result = _MVector()
            result.x = x
            result.y = y
            result.z = z
            return result
    return None


def _zero(cls):
    """Python の ``__new__`` / ``__init__`` を通さずに cls のゼロベクトルを作る。

    om2 の型は C++ の実体を基底の ``__init__`` で確保するため、``__new__`` の直後に
    必ず基底の ``__init__`` を呼ぶ。演算結果の生成など内部の高速な経路で使う。

    Args:
        cls (type): 生成する Vector 系のクラス。

    Returns:
        Vector: cls のゼロベクトル。
    """
    result = _NEW(cls)
    _INIT(result)
    return result


def _vector_of(cls, value):
    """om2 の MVector または3要素の列から cls のインスタンスを作る。

    引数付きコンストラクタは om2 の多重定義の解決が遅いため、引数なしで確保した
    インスタンスへ成分を代入する。

    Args:
        cls (type): 生成する Vector 系のクラス。
        value (om2.MVector | Sequence[float]): 値の取得元。

    Returns:
        Vector: cls の新しいインスタンス。
    """
    result = _NEW(cls)
    _INIT(result)
    if isinstance(value, _MVector):
        result.x = value.x
        result.y = value.y
        result.z = value.z
    else:
        result.x = value[0]
        result.y = value[1]
        result.z = value[2]
    return result


def _vectors_of_points(points):
    """om2 の MPoint の列から、XYZを写した Vector のリストを作る。

    MPoint の w では割らない。引数付きコンストラクタの多重定義の解決を通さず、
    引数なしで確保したインスタンスへ成分を代入する(:func:`_vector_of` と同じ理由)。

    Args:
        points (Iterable[om2.MPoint]): 変換元の点列(MPointArray など)。

    Returns:
        list[Vector]: 入力順の新しい Vector。
    """
    result = []
    append = result.append
    for point in points:
        vector = _NEW(Vector)
        _INIT(vector)
        vector.x = point.x
        vector.y = point.y
        vector.z = point.z
        append(vector)
    return result


def _vector_keywords(x=0.0, y=0.0, z=0.0):
    """キーワード引数付きの Vector の生成引数を (x, y, z) へまとめる。

    Args:
        x (float): X 成分。
        y (float): Y 成分。
        z (float): Z 成分。

    Returns:
        tuple: (x, y, z)。
    """
    return x, y, z


def _rebuild(cls, values):
    """copy / pickle の再構築関数。cls の ``__init__`` を呼ばずに値を復元する。

    om2 の型は C++ の実体を基底の ``__init__`` で確保するため、基底の ``__new__`` と
    ``__init__`` で確保してから成分を設定する。利用者の派生クラスが独自の引数の
    ``__init__`` を持っていても呼ばない。追加のアトリビュート(``__dict__`` / ``__slots__``)は
    pickle の標準の手順(``__reduce__`` の3番目の要素)で後から復元される。

    Args:
        cls (type): 復元するクラス。om2.MVector / MQuaternion / MEulerRotation /
            MMatrix のいずれかの派生。
        values (tuple): 成分。MVector 系は (x, y, z)、MQuaternion 系は (x, y, z, w)、
            MEulerRotation 系は (x, y, z, order)、MMatrix 系は行優先の16要素。

    Returns:
        object: 復元した cls のインスタンス。

    Raises:
        TypeError: cls が対応する om2 の型の派生でない場合。
        ValueError: values の要素数が型と合わない場合。
    """
    if issubclass(cls, _MVector):
        result = _NEW(cls)
        _INIT(result)
        result.x, result.y, result.z = values
    elif issubclass(cls, _MQuaternion):
        result = _MQuaternion.__new__(cls)
        _MQuaternion.__init__(result)
        result.x, result.y, result.z, result.w = values
    elif issubclass(cls, _MEuler):
        result = _MEuler.__new__(cls)
        _MEuler.__init__(result)
        result.x, result.y, result.z, result.order = values
    elif issubclass(cls, _MMatrix):
        values = tuple(values)
        if len(values) != 16:
            raise ValueError("Matrix expects 16 values")
        result = _MMatrix.__new__(cls)
        _MMatrix.__init__(result)
        for position, item in enumerate(values):
            _MMatrix.__setitem__(result, position, item)
    else:
        raise TypeError(f"Cannot rebuild {cls.__name__}")
    return result


def _reduce_value(value, values):
    """copy / pickle 用に、:func:`_rebuild` で再構築する情報を返す。

    利用者の派生クラスが持つ追加のアトリビュートは、pickle の標準形式の state(``__dict__`` の
    辞書、``__slots__`` もあれば ``(辞書, slots の辞書)``)として3番目の要素に置く。
    インスタンスの生成後に設定されるため、自身を参照するアトリビュートも復元できる。

    Args:
        value (object): 複製・保存する mlib の値。
        values (tuple): :func:`_rebuild` へ渡す成分。

    Returns:
        tuple: ``(_rebuild, (type(value), values))``、または state を加えた3要素の tuple。
    """
    state, slots = _instance_state(value)
    if slots:
        return (_rebuild, (type(value), values), (state, slots))
    if state:
        return (_rebuild, (type(value), values), state)
    return (_rebuild, (type(value), values))


def _iterable(value, name):
    """点列の引数を list へ変換する。

    Args:
        value (Iterable): 点列。文字列・単独のベクトルは点列として受け付けない。
        name (str): 例外メッセージに使う引数名。

    Returns:
        list: 点のリスト。

    Raises:
        TypeError: 反復できない値、文字列、または単独のom2ベクトル・点の場合。
    """
    if isinstance(value, (str, bytes, _MVector, _MPoint)):
        raise TypeError(f"{name} must be an iterable of points")
    try:
        return list(value)
    except TypeError:
        raise TypeError(f"{name} must be an iterable of points") from None


def _axis_name(axis, name):
    """軸の名前を (成分の番号, 向き) へ変換する。

    Args:
        axis (str): ``"x"``・``"-y"``・``"+Z"`` などの軸の名前。大文字小文字は問わない。
        name (str): 例外メッセージに使う引数名。

    Returns:
        tuple[int, float]: 成分の番号(0〜2)と向き(1.0 または -1.0)。

    Raises:
        TypeError: axisが文字列でない場合。
        ValueError: axisが軸の名前でない場合。
    """
    if not isinstance(axis, str):
        raise TypeError(f"{name} must be a str such as 'x' or '-y'")
    result = _AXIS_NAMES.get(axis.lower())
    if result is None:
        raise ValueError(f"{name} must be one of 'x', 'y', 'z', '-x', '-y', '-z' (got {axis!r})")
    return result


class Vector(om2.MVector):
    """om2.MVectorを継承した、可変・ハッシュ不可のXYZベクトル値。

    OpenMaya APIへそのまま渡せる。生成時は成分をコピーし、引数形式は ``__init__`` に従う。
    MPointからもwで割らずXYZを写す。

    演算はOM2に従い、ベクトル結果は派生型によらず基底Vectorを返す。
    ``om2.MVector`` が左辺の ``+`` / ``-`` / ``^`` もVectorになる。

    * ``+`` / ``-`` はMVector系、または3個の数値のtuple/listとの成分ごとの加減算
      (``v + (1, 1, 1)``・``(1, 1, 1) + v``・``v - [0, 1, 0]``)。結果はVector。
    * ``v * 数値`` / ``数値 * v`` / ``v / 数値`` はスカラー演算。0除算はZeroDivisionError。
    * ``v * w`` は内積(float)、``v ^ w`` は外積。
    * ``v * m`` は平行移動を含まない行ベクトルの方向変換。
      ``m * v`` は列ベクトルの積(``v * mᵀ``)。

    ``+=`` / ``-=`` / ``*=`` / ``/=`` / ``^=`` は自身を更新し派生型を保つ。
    ただし ``v *= w`` は内積のfloatへ束ね直す。コピーを返す操作と自身更新を区別し、
    数学値を返す継承メソッドも対応するmlib型を使う。OpenMayaの共有クラス定数は変更しない。

    成分・番号へ代入可能。番号は-3〜2、範囲外はIndexError。スライスは代入不可のtuple、反復はXYZ順。
    ``==`` はMVector系、または3個の数値のtuple/listとの成分の完全一致で、派生型が違っても等しくなり得る。
    MPointなどそれ以外のOM2型はFalse、他は相手の比較へ委ね、未判定ならFalse。
    OM2型が左辺の比較はOM2側でTypeErrorになり得る。
    """

    __slots__ = ()
    __hash__ = None

    def __new__(cls, *args, **kwargs):
        """基底初期化でC++実体を確保し、clsのゼロベクトルを作る。

        ``__init__`` を省略・失敗した派生クラスでも未確保実体へアクセスしないため、ここで確保する。
        mlibの ``__init__`` は成分だけを設定する。基底初期化の再実行はMaya 2022で実体をリークする。

        Args:
            *args: ここでは使わない生成引数。
            **kwargs: ここでは使わないキーワード引数。

        Returns:
            Vector: clsのゼロベクトル。
        """
        self = _NEW(cls)
        _INIT(self)
        return self

    def __init__(self, *args, **kwargs):
        """成分を設定する。

        Args:
            *args: ``()``、``(x, y, z)``、``(x, y)``、``(values)``、または
                ``(MVector | MPoint | MFloatVector | MFloatPoint)`` など om2 の
                MVector のコンストラクタが受け付ける引数。
            **kwargs: ``x``、``y``、``z``。位置引数と合わせて使える。省略した成分は 0。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 未知のキーワード引数、または同じ成分を二重に指定した場合。
            ValueError: om2 のコンストラクタが受け付けない引数(文字列の成分など)の場合。
        """
        if kwargs:
            try:
                args = _vector_keywords(*args, **kwargs)
            except TypeError as error:
                _rethrow_init_error(type(self), error)
        count = len(args)
        # 成分の形はom2のコンストラクタと同じく実行時に判定するため、任意の値として扱う。
        values: Sequence[Any] = args
        if count == 1:
            source: Any = args[0]
            if isinstance(source, _MVector):
                self.x = source.x
                self.y = source.y
                self.z = source.z
                return
            if type(source) in (tuple, list) and len(source) == 3:
                values = source
        elif count == 0:
            self.x = 0.0
            self.y = 0.0
            self.z = 0.0
            return
        if len(values) == 3:
            x, y, z = values
            if isinstance(x, _NUMBER) and isinstance(y, _NUMBER) and isinstance(z, _NUMBER):
                self.x = x
                self.y = y
                self.z = z
                return
        # その他の形(MPoint など)は om2 の多重定義の解決に任せる(不正な引数も om2 と同じ ValueError)。
        source = _MVector(*args)
        self.x = source.x
        self.y = source.y
        self.z = source.z

    def __getitem__(self, index):
        """成分を取得する。

        Args:
            index (int | slice): -3〜2 の番号、またはスライス。

        Returns:
            float | tuple[float, ...]: 指定成分。スライスでは成分の tuple。

        Raises:
            TypeError: 番号が整数・スライス以外の場合。
            IndexError: 番号が範囲外の場合。
        """
        if index.__class__ is int and -3 <= index < 3:
            return _GET(self, index)
        if isinstance(index, slice):
            return (self.x, self.y, self.z)[index]
        return _GET(self, _checked_index(index, 3, "Vector"))

    def __setitem__(self, index, value):
        """成分を設定する。

        Args:
            index (int): -3〜2 の番号。
            value (float): 設定する値。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 番号が整数以外の場合。
            IndexError: 番号が範囲外の場合。
        """
        if index.__class__ is not int or not -3 <= index < 3:
            index = _checked_index(index, 3, "Vector")
        _SET(self, index, value)

    def __iter__(self):
        """X、Y、Z の順に成分を反復する。

        Returns:
            Iterator[float]: 3成分のイテレータ。
        """
        return iter((self.x, self.y, self.z))

    def __reduce__(self):
        """copy / pickle 用に、コンストラクタを通さずに再構築する情報を返す。

        om2 の型は C++ の実体を基底の ``__init__`` で確保するため、再構築関数で
        確保してから成分を設定する。利用者の派生クラスの ``__init__`` は呼ばず、
        ``__dict__`` と ``__slots__`` のアトリビュートは再構築時に復元する。

        Returns:
            tuple: ``(_rebuild, (type(self), (x, y, z))[, state])``。
        """
        return _reduce_value(self, (self.x, self.y, self.z))

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
            Vector: 自身と同じクラスの新しいインスタンス。
        """
        return _copy_state(self, type(self)._wrap(self))

    def __deepcopy__(self, memo):
        """同じ型・同じ成分の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つアトリビュートは深く複製する。

        Args:
            memo (dict): copy.deepcopy の memo。

        Returns:
            Vector: 自身と同じクラスの新しいインスタンス。
        """
        return _copy_state(self, type(self)._wrap(self), memo)

    def __repr__(self):
        """クラス名と3成分を含むデバッグ表現を返す。

        Returns:
            str: ``Translate(1.0, 2.0, 3.0)`` の形式の文字列。
        """
        return "{}({!r}, {!r}, {!r})".format(type(self).__name__, self.x, self.y, self.z)

    __str__ = __repr__

    def __eq__(self, other):
        """MVector 系との成分の完全一致を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MVector 系と3個の数値の tuple/list は成分比較の結果。
            その他の om2 の型は False。それ以外の型は NotImplemented(相手の比較に委ね、
            どちらも判断しなければ False になる)。
        """
        operand = _vector_operand(other)
        if operand is not None:
            return _MVector.__eq__(self, operand)
        return _foreign_comparison(other, False)

    def __ne__(self, other):
        """``__eq__`` の否定を返す。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MVector 系と3個の数値の tuple/list は成分比較の結果。
            その他の om2 の型は True。それ以外の型は NotImplemented。
        """
        operand = _vector_operand(other)
        if operand is not None:
            return _MVector.__ne__(self, operand)
        return _foreign_comparison(other, True)

    def __add__(self, other):
        """MVector 系との成分ごとの加算を返す。

        Args:
            other (object): 加算する MVector 系、または3個の数値の tuple/list。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        other = _vector_operand(other)
        if other is None:
            return NotImplemented
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, self)
        _MVector.__iadd__(result, other)
        return result

    def __radd__(self, other):
        """左辺の MVector 系との成分ごとの加算を返す。

        Args:
            other (object): 左辺の MVector 系、または3個の数値の tuple/list。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        other = _vector_operand(other)
        if other is None:
            return NotImplemented
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, other)
        _MVector.__iadd__(result, self)
        return result

    def __iadd__(self, other):
        """MVector 系を自身へ加算する。

        om2 の MVector を継承した型では、対応しない型との ``+=`` が例外にならず
        NotImplemented が代入されてしまうため、型を検査してから委譲する。

        Args:
            other (object): 加算する MVector 系、または3個の数値の tuple/list。

        Returns:
            Vector | types.NotImplementedType: 自身。対応しない型は NotImplemented(TypeError になる)。
        """
        other = _vector_operand(other)
        if other is None:
            return NotImplemented
        return _MVector.__iadd__(self, other)

    def __sub__(self, other):
        """MVector 系との成分ごとの減算を返す。

        Args:
            other (object): 減算する MVector 系、または3個の数値の tuple/list。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        other = _vector_operand(other)
        if other is None:
            return NotImplemented
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, self)
        _MVector.__isub__(result, other)
        return result

    def __rsub__(self, other):
        """左辺の MVector 系から自身を引いた値を返す。

        Args:
            other (object): 左辺の MVector 系、または3個の数値の tuple/list。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        other = _vector_operand(other)
        if other is None:
            return NotImplemented
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, other)
        _MVector.__isub__(result, self)
        return result

    def __isub__(self, other):
        """MVector 系を自身から減算する。

        Args:
            other (object): 減算する MVector 系、または3個の数値の tuple/list。

        Returns:
            Vector | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        other = _vector_operand(other)
        if other is None:
            return NotImplemented
        return _MVector.__isub__(self, other)

    def __mul__(self, other):
        """om2 の意味論で乗算する。

        Args:
            other (object): 数値、MVector 系、または MMatrix 系。

        Returns:
            Vector | float | types.NotImplementedType: 数値ならスカラー倍の Vector、
            MVector 系なら内積の float、MMatrix 系なら行ベクトル規約で方向変換した
            Vector(平行移動を含まない)。対応しない型は NotImplemented。
        """
        if isinstance(other, _NUMBER):
            result = _NEW(Vector)
            _INIT(result)
            _MVector.__iadd__(result, self)
            _MVector.__imul__(result, other)
            return result
        if isinstance(other, _MVector):
            return _MVector.__mul__(self, other)
        if isinstance(other, _MMatrix):
            result = _NEW(Vector)
            _INIT(result)
            _MVector.__iadd__(result, self)
            _MVector.__imul__(result, other)
            return result
        return NotImplemented

    def __rmul__(self, other):
        """左辺からの乗算を om2 の意味論で行う。

        ``m * v`` (m は MMatrix 系)は om2 と同じく列ベクトルとしての積
        (``v * mᵀ``)になる。位置をマトリクスで変換する場合は
        :meth:`mlib.maths.matrix.Matrix.transformPoint`、方向は ``v * m`` を使う。

        Args:
            other (object): 数値または MMatrix 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        if isinstance(other, _NUMBER):
            result = _NEW(Vector)
            _INIT(result)
            _MVector.__iadd__(result, self)
            _MVector.__imul__(result, other)
            return result
        if isinstance(other, _MMatrix):
            value = _MVector.__rmul__(self, other)
            if value is NotImplemented:
                return value
            result = _NEW(Vector)
            _INIT(result)
            _MVector.__iadd__(result, value)
            return result
        return NotImplemented

    def __imul__(self, other):
        """数値倍、または MMatrix 系による行ベクトル規約の方向変換を自身へ適用する。

        Args:
            other (object): 数値または MMatrix 系。

        Returns:
            Vector | types.NotImplementedType: 自身。対応しない型は NotImplemented
            (MVector 系を渡した場合は om2 と同じく内積へ戻り、名前が float に再束縛される)。
        """
        if not isinstance(other, (int, float, _MMatrix)):
            return NotImplemented
        return _MVector.__imul__(self, other)

    def __truediv__(self, other):
        """数値による成分ごとの除算を返す。

        Args:
            other (object): 除数の int または float。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。

        Raises:
            ZeroDivisionError: other が 0 の場合(Maya のバージョンにかかわらない)。
        """
        if not isinstance(other, _NUMBER):
            return NotImplemented
        if other == 0:
            raise ZeroDivisionError("Vector division by zero")
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, self)
        _MVector.__itruediv__(result, other)
        return result

    def __itruediv__(self, other):
        """数値で自身を除算する。

        Args:
            other (object): 除数の int または float。

        Returns:
            Vector | types.NotImplementedType: 自身。対応しない型は NotImplemented。

        Raises:
            ZeroDivisionError: other が 0 の場合。
        """
        if not isinstance(other, _NUMBER):
            return NotImplemented
        if other == 0:
            raise ZeroDivisionError("Vector division by zero")
        return _MVector.__itruediv__(self, other)

    def __xor__(self, other):
        """MVector 系との外積を返す(om2 の ``^``)。

        Args:
            other (object): 外積の相手となる MVector 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MVector):
            return NotImplemented
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, _MVector.__xor__(self, other))
        return result

    def __rxor__(self, other):
        """左辺の MVector 系と自身の外積 ``other ^ self`` を返す。

        Vector は om2.MVector の派生なので、``om2.MVector ^ Vector`` では Python が
        このメソッドを先に呼ぶ(定義しないと om2 の結果の ``om2.MVector`` になる)。

        Args:
            other (object): 左辺の MVector 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MVector):
            return NotImplemented
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, _MVector.__xor__(other, self))
        return result

    def __ixor__(self, other):
        """MVector 系との外積で自身を書き換える(om2 の MVector には無い in-place 版)。

        Args:
            other (object): 外積の相手となる MVector 系。

        Returns:
            Vector | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MVector):
            return NotImplemented
        result = _MVector.__xor__(self, other)
        self.x = result.x
        self.y = result.y
        self.z = result.z
        return self

    def __neg__(self):
        """各成分の符号を反転した値を返す。

        Returns:
            Vector: 新しい Vector。派生クラスの型は保持しない。
        """
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, self)
        _MVector.__imul__(result, -1.0)
        return result

    def __round__(self, ndigits=None):
        """組み込みの ``round`` から :meth:`round` を呼ぶ。

        Args:
            ndigits (int | None): roundと同じ桁数。

        Returns:
            Vector: 同型の新しい値。
        """
        return self.round(ndigits)

    @classmethod
    def fromIterable(cls, values):
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
        return cls(values[0], values[1], values[2])

    @classmethod
    def fromAxis(cls, axis):
        """軸の名前から長さ1の軸方向のベクトルを生成する。

        ``"x"``・``"y"``・``"z"`` は正の向き、``"-x"``・``"-y"``・``"-z"`` は負の向き。
        ``"+x"`` のような明示的な正の符号と、大文字(``"X"``・``"-Y"``)も受け付ける。
        前後の空白は受け付けない。

        Args:
            axis (str): 軸の名前。

        Returns:
            Vector: 呼び出したクラスの新しいインスタンス(``Translate.fromAxis("y")`` はTranslate)。

        Raises:
            TypeError: axisが文字列でない場合。
            ValueError: axisが軸の名前でない場合。
        """
        index, sign = _axis_name(axis, "axis")
        values = [0.0, 0.0, 0.0]
        values[index] = sign
        return cls(values[0], values[1], values[2])

    @classmethod
    def getCenter(cls, points):
        """点列の重心(位置の平均)を返す。

        Args:
            points (Iterable[om2.MVector | om2.MPoint | Iterable[float]]): 1点以上の点列。

        Returns:
            Vector: 呼び出したクラスの新しい値(``Translate.getCenter(...)`` はTranslate)。

        Raises:
            TypeError: 点列が反復できない場合。
            ValueError: 点列が空の場合。
        """
        vectors = [_resolve_mvector(point) for point in _iterable(points, "points")]
        if not vectors:
            raise ValueError("Cannot compute the center of no points")
        total = _MVector()
        for vector in vectors:
            _MVector.__iadd__(total, vector)
        _MVector.__itruediv__(total, float(len(vectors)))
        return cls._wrap(total)

    @classmethod
    def isPlanar(cls, points, tolerance=1e-10):
        """点列がすべて同一平面上にあるか判定する。

        一直線上にない最初の3点で平面を決め、全点の平面からの距離が tolerance 以下ならTrue。
        3点以下、または全点が一直線上なら常にTrue。

        Args:
            points (Iterable[om2.MVector | om2.MPoint | Iterable[float]]): 点列。
            tolerance (float): 平面からの距離の許容誤差(点と同じ単位)。0以上。

        Returns:
            bool: 同一平面上ならTrue。

        Raises:
            TypeError: 点列が反復できない、またはtoleranceが数値でない場合。
            ValueError: toleranceが負・有限でない場合。
        """
        limit = _checked_tolerance(tolerance)
        vectors = [_resolve_mvector(point) for point in _iterable(points, "points")]
        if len(vectors) <= 3:
            return True
        origin = vectors[0]
        normal = None
        for index in range(1, len(vectors)):
            first = _MVector.__sub__(vectors[index], origin)
            for other in vectors[index + 1:]:
                cross = _MVector.__xor__(first, _MVector.__sub__(other, origin))
                if cross.length() > 1e-12:
                    normal = cross.normal()
                    break
            if normal is not None:
                break
        if normal is None:
            return True
        return all(abs(_MVector.__mul__(_MVector.__sub__(vector, origin), normal)) <= limit for vector in vectors)

    def mirror(self, axis="x", pivot=(0.0, 0.0, 0.0)):
        """指定中心から成分を反転した同型の複製を返す。

        Translate・Scale・Shearでも数値反転として使用できる。
        Scale・Shearのマトリクスとしての鏡映にはMatrix.mirrorを使う。

        Args:
            axis (str | int): 反転する軸 ``"x"``・``"y"``・``"z"``、またはミラー面 ``"YZ"``・``"XZ"``・``"XY"``
                (x⇔YZ、y⇔XZ、z⇔XY。文字の順序・大文字小文字は問わない)、または0/1/2。
            pivot (Iterable[float]): 値と同じ単位の中心。方向には原点を使う。

        Returns:
            Vector: 同型の新しい値。

        Raises:
            TypeError: axisが文字列・int以外の場合。
            ValueError: axisが不正、またはpivotが有限の3成分でない場合。
        """
        from ..util import mirrorArguments
        axes, center = mirrorArguments(axis, pivot)
        values = list(self)
        for index in axes:
            values[index] = 2 * center[index] - values[index]
        return type(self)(values)

    def mirrorIt(self, axis="x", pivot=(0.0, 0.0, 0.0)):
        """自身の3成分を反転する。

        Args:
            axis (str | int): mirrorと同じ反転軸。
            pivot (Iterable[float]): 値と同じ単位の中心。

        Returns:
            Vector: 更新した自身。
        """
        self.x, self.y, self.z = self.mirror(axis, pivot)
        return self

    def round(self, ndigits=None):
        """各成分を小数点以下ndigits桁へ丸めた同型の複製を返す。

        各成分に組み込みの ``round`` を使う(端数がちょうど半分なら偶数側へ丸める)。
        丸めた結果の -0.0 は 0.0 にそろえる。組み込みの ``round(value, ndigits)`` でも同じ結果になる。

        Args:
            ndigits (int | None): 小数点以下の桁数。負の値は整数部を丸める。Noneは整数値へ丸める
                (成分はfloatのまま)。

        Returns:
            Vector: 同型の新しい値。

        Raises:
            TypeError: ndigitsがint・None以外(boolを含む)の場合。
        """
        ndigits = _checked_digits(ndigits)
        return type(self)([_round_float(value, ndigits) for value in self])

    def roundIt(self, ndigits=None):
        """自身の3成分を丸める。

        Args:
            ndigits (int | None): roundと同じ桁数。

        Returns:
            Vector: 更新した自身。

        Raises:
            TypeError: ndigitsがint・None以外(boolを含む)の場合。自身は変更しない。
        """
        self.x, self.y, self.z = self.round(ndigits)
        return self

    def dot(self, other):
        """内積を返す。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 内積の相手。

        Returns:
            float: 内積。
        """
        return _MVector.__mul__(self, _resolve_mvector(other))

    def cross(self, other):
        """外積を返す。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 外積の相手。

        Returns:
            Vector: 外積。派生クラスの型は保持しない。
        """
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, _MVector.__xor__(self, _resolve_mvector(other)))
        return result

    def lengthSq(self):
        """長さの2乗(自身との内積)を返す。

        平方根を計算しないため、長さの比較だけが目的なら length() より速い。

        Returns:
            float: 長さの2乗。
        """
        return _MVector.__mul__(self, self)

    def normal(self, *args):
        """OpenMayaの規則で正規化したVectorの複製を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: OpenMayaの同名メソッドへ渡す位置引数。通常は指定しない。

        Returns:
            Vector: 演算結果を保持する新しいmlib値。
        """
        return _vector_of(Vector, _MVector.normal(self, *args))

    def rotateBy(self, *args):
        """OpenMayaの回転規則でXYZベクトルを回し、独立したVectorを返す。

        MVector.rotateBy()へ引数をそのまま渡し、自身や回転引数は変更しない。
        Quaternionの事前正規化やゼロ拒否を独自に加えないため、
        Quaternion.rotateVector()の正規化コピーによる回転とは入力条件が異なる。

        Args:
            *args: Quaternion/EulerRotateなどの回転、またはOpenMayaの軸定数とrad角度。
                多重定義の受理型はMVector.rotateBy()に従う。

        Returns:
            Vector: 基底Vectorの新しい値。派生型や追加Python状態は引き継がない。
        """
        return _vector_of(Vector, _MVector.rotateBy(self, *args))

    def rotateTo(self, *args):
        """自身の方向から指定した方向へ向けるQuaternionを返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 目標方向となるMVector系のtargetを指定する。

        Returns:
            Quaternion: 演算結果を保持する新しいmlib値。
        """
        from .quaternion import Quaternion

        return Quaternion._wrap(_MVector.rotateTo(self, *args))

    def transformAsNormal(self, *args):
        """マトリクスの逆転置で法線変換し、正規化したVectorの複製を返す。

        自身や入力値は変更しない。引数・ゼロ値の扱いはOpenMayaに従う。

        Args:
            *args: 変換に使うMMatrix系のmatrixを指定する。

        Returns:
            Vector: 演算結果を保持する新しいmlib値。
        """
        return _vector_of(Vector, _MVector.transformAsNormal(self, *args))

    def unitIt(self):
        """ゼロ値を拒否して自身を正規化する。

        Returns:
            Vector: 更新した自身。

        Raises:
            ValueError: ゼロ値の場合。自身は変更しない。
        """
        value = self.unit()
        self.x, self.y, self.z = value
        return self

    def unit(self):
        """正規化した新しいベクトルを返す。

        om2 の ``normal()`` はゼロベクトルでも例外にならず ``om2.MVector`` を返すが、
        このメソッドは mlib の Vector を返し、ゼロベクトルを拒否する。

        Returns:
            Vector: 長さ 1 のベクトル。派生クラスの型は保持しない。

        Raises:
            ValueError: ゼロベクトルの場合。
        """
        length = self.length()
        if length == 0.0:
            raise ValueError("Cannot normalize a zero vector")
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, self)
        _MVector.__itruediv__(result, length)
        return result

    def distanceTo(self, other):
        """2点間のユークリッド距離を返す。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 距離を測る相手。

        Returns:
            float: 距離。
        """
        return _MVector.__sub__(self, _resolve_mvector(other)).length()

    def angleTo(self, other):
        """別のベクトルとの成す角度をラジアンで返す。

        ``atan2(|a × b|, a · b)`` で計算するため、ほぼ平行・反平行な場合も精度を
        保つ(om2 の ``angle()`` は約 1e-5 rad 未満の角度を 0 として返す)。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 角度を測る相手。

        Returns:
            float: 0 から pi の範囲のラジアン角度。

        Raises:
            ValueError: 自身または other がゼロベクトルの場合。
        """
        other = _resolve_mvector(other)
        if _MVector.__mul__(self, self) == 0.0 or _MVector.__mul__(other, other) == 0.0:
            raise ValueError("Cannot measure the angle to or from a zero vector")
        return math.atan2(_MVector.__xor__(self, other).length(), _MVector.__mul__(self, other))

    def isEquivalent(self, other, tolerance=1e-10):
        """許容誤差付きでほぼ等しいか判定する。

        om2 の ``isEquivalent`` に委譲するため、2点間のユークリッド距離が
        tolerance 以下かどうかで判定する。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 比較対象。
            tolerance (float): 距離の許容誤差。

        Returns:
            bool: ほぼ等しければ True。
        """
        return _MVector.isEquivalent(self, _resolve_mvector(other), tolerance)

    def lerp(self, other, t):
        """別のベクトルとの線形補間 ``self + (other - self) * t`` を返す。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 補間先。
            t (float): 補間係数。0 で自身、1 で other。範囲外は外挿になる。

        Returns:
            Vector: 補間結果。派生クラスの型は保持しない。
        """
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, _resolve_mvector(other))
        _MVector.__isub__(result, self)
        _MVector.__imul__(result, t)
        _MVector.__iadd__(result, self)
        return result

    def projected(self, axis):
        """指定した軸の方向の成分(軸への正射影)を返す。

        Args:
            axis (om2.MVector | om2.MPoint | Iterable[float]): 射影する軸。長さは問わない。

        Returns:
            Vector: ``axis`` と平行な成分。派生クラスの型は保持しない。

        Raises:
            ValueError: axisがゼロベクトルの場合。
        """
        axis = _resolve_mvector(axis)
        length_sq = _MVector.__mul__(axis, axis)
        if length_sq == 0.0:
            raise ValueError("Cannot project onto a zero vector")
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, axis)
        _MVector.__imul__(result, _MVector.__mul__(self, axis) / length_sq)
        return result

    def orthogonal(self, axis):
        """指定した軸に直交する成分(軸の方向の成分を取り除いた値)を返す。

        ポールベクター・アップベクターを主軸に直交させるときなどに使う(グラム・シュミットの1段)。

        Args:
            axis (om2.MVector | om2.MPoint | Iterable[float]): 直交させる軸。長さは問わない。

        Returns:
            Vector: ``axis`` に直交する成分。派生クラスの型は保持しない。自身が軸と平行ならゼロベクトル。

        Raises:
            ValueError: axisがゼロベクトルの場合。
        """
        result = self.projected(axis)
        _MVector.__imul__(result, -1.0)
        _MVector.__iadd__(result, self)
        return result

    def orthogonalIt(self, axis):
        """自身を、指定した軸に直交する成分へ置き換える。

        Args:
            axis (om2.MVector | om2.MPoint | Iterable[float]): :meth:`orthogonal` と同じ軸。

        Returns:
            Vector: 更新した自身。

        Raises:
            ValueError: axisがゼロベクトルの場合。自身は変更しない。
        """
        self.x, self.y, self.z = self.orthogonal(axis)
        return self

    def distanceSqTo(self, other):
        """2点間の距離の2乗を返す。

        平方根を計算しないため、距離の比較だけが目的なら :meth:`distanceTo` より速い。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 距離を測る相手。

        Returns:
            float: 距離の2乗。
        """
        difference = _MVector.__sub__(self, _resolve_mvector(other))
        return _MVector.__mul__(difference, difference)

    def isZero(self, tolerance=1e-10):
        """長さが tolerance 以下(ほぼゼロベクトル)か判定する。

        Args:
            tolerance (float): 長さの許容誤差。0以上。

        Returns:
            bool: 長さが tolerance 以下ならTrue。

        Raises:
            TypeError: toleranceが数値でない場合。
            ValueError: toleranceが負・有限でない場合。
        """
        limit = _checked_tolerance(tolerance)
        return _MVector.__mul__(self, self) <= limit * limit

    def abs(self):
        """各成分を絶対値にした同型の複製を返す。

        組み込みの ``abs()`` (長さではない)と混同しないよう、``__abs__`` は定義しない。長さは :meth:`length`。

        Returns:
            Vector: 同型の新しい値。
        """
        return type(self)([math.fabs(value) for value in self])

    def cotan(self, other):
        """別のベクトルとの成す角のコタンジェント(``内積 / |外積|``)を返す。

        メッシュのラプラシアン(コタンジェントの重み)などに使う。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 角度を測る相手。

        Returns:
            float: コタンジェント。鋭角は正、鈍角は負。

        Raises:
            ValueError: 自身または other がゼロベクトル、または2つが平行(角度が0かpi)な場合。
        """
        other = _resolve_mvector(other)
        if _MVector.__mul__(self, self) == 0.0 or _MVector.__mul__(other, other) == 0.0:
            raise ValueError("Cannot compute the cotangent with a zero vector")
        sine = _MVector.__xor__(self, other).length()
        if sine == 0.0:
            raise ValueError("Cannot compute the cotangent of parallel vectors")
        return _MVector.__mul__(self, other) / sine

    def slerp(self, other, t, spin=0):
        """別のベクトルへ向きを球面線形補間し、長さを線形補間したベクトルを返す。

        2つのベクトルが張る平面の中で、自身の向きを other の向きへ角度 ``t`` の割合だけ回す
        (回す角度は ``(成す角 + 2pi * spin) * t``)。長さは ``|自身| + (|other| - |自身|) * t``。
        2つが平行・反平行で平面が決まらない場合は、自身に直交する軸(:meth:`orthogonal` で作る)の周りに回す。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 補間先。
            t (float): 補間係数。0 で自身、1 で other(spin=0 の場合)。範囲外は外挿になる。
            spin (int): 追加で回る周回数。既定 0 は最短経路、-1 は逆回り(長い経路)。

        Returns:
            Vector: 補間結果。派生クラスの型は保持しない。

        Raises:
            TypeError: tが数値でない、またはspinが整数でない場合(boolを含む)。
            ValueError: tが有限でない、または自身・otherがゼロベクトルの場合。
        """
        weight = _finite(t, "t")
        if isinstance(spin, bool) or not isinstance(spin, int):
            raise TypeError("spin must be an int")
        other = _resolve_mvector(other)
        start_length = self.length()
        end_length = other.length()
        if start_length == 0.0 or end_length == 0.0:
            raise ValueError("Cannot interpolate the direction of a zero vector")
        start = _MVector.__truediv__(self, start_length)
        end = _MVector.__truediv__(other, end_length)
        axis = _MVector.__xor__(start, end)
        sine = axis.length()
        angle = math.atan2(sine, _MVector.__mul__(start, end))
        if sine < 1e-12:
            # 平行・反平行は回転の平面が決まらないため、自身に直交する軸を使う。
            index = min(range(3), key=lambda number: abs(start[number]))
            base = _MVector()
            base[index] = 1.0
            axis = _MVector.__xor__(start, base)
        axis = axis.normal()
        turn = (angle + 2.0 * math.pi * spin) * weight
        # ロドリゲスの回転の式(axis は start に直交する単位ベクトル)。
        direction = start * math.cos(turn) + _MVector.__xor__(axis, start) * math.sin(turn)
        result = _zero(Vector)
        _MVector.__iadd__(result, direction * (start_length + (end_length - start_length) * weight))
        return result

    def getClosestAxis(self, includeNegative=True):
        """ベクトルの向きに最も近い座標軸の名前を返す。

        :meth:`Transform.getClosestAxisToVector <mlib.nodes.transform.Transform.getClosestAxisToVector>` の
        値版で、候補の軸のうち内積が最大のものを選ぶ。同じ値なら x・y・z の順で先のものを選ぶ。

        Args:
            includeNegative (bool): Trueなら負の軸(``"-x"`` 等)も候補にする。Falseは ``"x"``・``"y"``・``"z"`` だけ。

        Returns:
            str: ``"x"``・``"y"``・``"z"``・``"-x"``・``"-y"``・``"-z"`` のいずれか。:meth:`fromAxis` へ渡せる。

        Raises:
            TypeError: includeNegativeがbool以外の場合。
            ValueError: ゼロベクトルの場合。
        """
        if type(includeNegative) is not bool:
            raise TypeError("includeNegative must be a bool")
        if _MVector.__mul__(self, self) == 0.0:
            raise ValueError("Cannot find the closest axis of a zero vector")
        best_name = None
        best_value = None
        for index, name in enumerate(("x", "y", "z")):
            value = self[index]
            candidates = [(name, value)]
            if includeNegative:
                candidates.append(("-" + name, -value))
            for candidate, dot in candidates:
                if best_value is None or dot > best_value:
                    best_name, best_value = candidate, dot
        return best_name

    def getBarycentricWeights(self, *points):
        """自身の位置を、2点(線分)または3点(三角形)の重心座標の重みに分解する。

        重みの合計は1で、``points[0] * w0 + points[1] * w1 (+ points[2] * w2)`` が自身(線分では直線上、三角形
        では平面上へ射影した位置)になる。範囲の外では負の重みになる。

        Args:
            *points (om2.MVector | om2.MPoint | Iterable[float]): 2点または3点。

        Returns:
            tuple[float, ...]: 点と同じ数の重み。

        Raises:
            TypeError: 点の数が2・3以外の場合。
            ValueError: 線分の長さが0、または三角形の面積が0(3点が一直線上)の場合。
        """
        if len(points) not in (2, 3):
            raise TypeError(f"getBarycentricWeights expects 2 or 3 points, got {len(points)}")
        vectors = [_resolve_mvector(point) for point in points]
        offset = _MVector.__sub__(self, vectors[0])
        if len(vectors) == 2:
            edge = _MVector.__sub__(vectors[1], vectors[0])
            length_sq = _MVector.__mul__(edge, edge)
            if length_sq == 0.0:
                raise ValueError("Cannot compute weights on a zero-length segment")
            weight = _MVector.__mul__(offset, edge) / length_sq
            return 1.0 - weight, weight
        first = _MVector.__sub__(vectors[1], vectors[0])
        second = _MVector.__sub__(vectors[2], vectors[0])
        normal = _MVector.__xor__(first, second)
        area_sq = _MVector.__mul__(normal, normal)
        if area_sq == 0.0:
            raise ValueError("Cannot compute weights on a degenerate triangle")
        weight1 = _MVector.__mul__(_MVector.__xor__(offset, second), normal) / area_sq
        weight2 = _MVector.__mul__(_MVector.__xor__(first, offset), normal) / area_sq
        return 1.0 - weight1 - weight2, weight1, weight2

    @classmethod
    def _wrap(cls, value):
        """3成分の値を複製した cls のインスタンスを返す(追加のアトリビュートは写さない)。

        Python の ``__new__`` / ``__init__`` を通さない(利用者の派生クラスの
        ``__init__`` も呼ばない)。

        Args:
            value (om2.MVector): 複製元。x・y・zを持つ値。

        Returns:
            Vector: cls の新しいインスタンス。
        """
        result = _NEW(cls)
        _INIT(result)
        result.x = value.x
        result.y = value.y
        result.z = value.z
        return result
