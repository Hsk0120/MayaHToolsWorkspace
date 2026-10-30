"""om2.MVector を継承した3成分ベクトルと基本演算。"""

import math
from typing import Any, Sequence

import maya.api.OpenMaya as om2

from ..util import _checked_index, _copy_state, _foreign_comparison, _instance_state, _rethrow_init_error

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


class Vector(om2.MVector):
    """om2.MVectorを継承した、可変・ハッシュ不可のXYZベクトル値。

    OpenMaya APIへそのまま渡せる。生成時は成分をコピーし、引数形式は :meth:`__init__` に従う。
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

    def mirror(self, axis="x", pivot=(0.0, 0.0, 0.0)):
        """指定中心から成分を反転した同型の複製を返す。

        Translate・Scale・Shearでも数値反転として使用できる。
        Scale・Shearのマトリクスとしての鏡映にはMatrix.mirrorを使う。

        Args:
            axis (str | int): x/y/z/xy/xz/yz/xyz、または0/1/2。
            pivot (Iterable[float]): 値と同じ単位の中心。方向には原点を使う。

        Returns:
            Vector: 同型の新しい値。
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
