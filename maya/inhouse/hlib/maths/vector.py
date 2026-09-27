"""om2.MVector を継承した3成分ベクトルと基本演算。"""

import copy
import copyreg
import math
from operator import index as _as_index

import maya.api.OpenMaya as om2

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


def _as_mvector(value):
    """値を om2.MVector として扱える形へ変換する。

    MVector 系(hlib の Vector 派生を含む)はそのまま返す。MPoint などの om2 の
    3成分型は MVector へ変換し(MPoint の w では割らない)、それ以外は
    3要素の反復可能オブジェクトとして展開する。

    Args:
        value (om2.MVector | om2.MPoint | Iterable[float]): 変換元。

    Returns:
        om2.MVector: value 自身、または新しい MVector。

    Raises:
        ValueError: 反復可能オブジェクトの要素数が3でない場合。
        TypeError: 反復できない値の場合。
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


def _checked_index(index, size, name):
    """添字を検査し、0〜size-1 へ正規化する。

    om2 の添字は負の範囲外の値を検査しない(Python が長さを1回だけ足して渡すため、
    MVector の ``v[-4]`` が最後の成分を返し、MMatrix の -17 以下は範囲外のメモリを
    読み書きする)ため、om2 へ渡す前に必ずここで検査する。

    Args:
        index (int): 添字。負の値は末尾から数える。
        size (int): 要素数。
        name (str): 例外メッセージに使う型名。

    Returns:
        int: 0〜size-1 の添字。

    Raises:
        IndexError: 範囲外の場合。
        TypeError: 整数として扱えない場合。
    """
    try:
        position = _as_index(index)
    except TypeError:
        raise TypeError("{} indices must be integers or slices, not {}".format(
            name, type(index).__name__)) from None
    if position < 0:
        position += size
    if not 0 <= position < size:
        raise IndexError("{} index out of range".format(name))
    return position


#: 型ごとの判定結果のキャッシュ。動的に作られた型が溜まり続けないよう上限を設ける。
_TYPE_CACHE_LIMIT = 256
_OM2_TYPES = {}
_STATEFUL_TYPES = {}


def _is_om2_type(cls):
    """cls が OpenMaya の型(API 1.0 / 2.0。派生クラスを含む)か判定する。

    Args:
        cls (type): 判定する型。

    Returns:
        bool: MRO に OpenMaya のモジュールで定義された型を含めば True。
    """
    found = _OM2_TYPES.get(cls)
    if found is None:
        found = False
        for base in cls.__mro__:
            module = getattr(base, "__module__", None) or ""
            if module.startswith(("OpenMaya", "maya.OpenMaya", "maya.api.")):
                found = True
                break
        if len(_OM2_TYPES) >= _TYPE_CACHE_LIMIT:
            _OM2_TYPES.clear()
        _OM2_TYPES[cls] = found
    return found


def _foreign_comparison(other, result):
    """om2 の同じ系統に属さない値との ``==`` / ``!=`` の結果を返す。

    om2 の型(MPoint や MObject など。OpenMaya API 1.0 の型を含む)は、相手の型を
    知らない比較で TypeError を送出するため、反射側へ回さずに result で確定する。
    それ以外の型には NotImplemented を返し、相手の ``__eq__`` (反射側の比較)に
    判断を委ねる。どちらも判断しなければ Python の既定の比較(同一性)になるため、
    ``None`` や文字列との比較は例外にならない(``None`` は同じ結果を直接返す)。

    Args:
        other (object): 比較対象。
        result (bool): om2 の型だった場合の結果(``==`` なら False、``!=`` なら True)。

    Returns:
        bool | types.NotImplementedType: om2 の型か None なら result、それ以外は NotImplemented。
    """
    if other is None or _is_om2_type(type(other)):
        return result
    return NotImplemented


def _instance_state(value):
    """利用者の派生クラスのインスタンスが持つ追加の属性を取り出す。

    hlib 自身の型のように ``__dict__`` も ``__slots__`` の属性も持たない型は、
    型ごとの判定をキャッシュしてすぐに返す。

    Args:
        value (object): hlib の値。

    Returns:
        tuple: (``__dict__`` の浅いコピー、または None, ``__slots__`` の値の辞書、または None)。
    """
    cls = type(value)
    stateful = _STATEFUL_TYPES.get(cls)
    if stateful is None:
        stateful = bool(cls.__dictoffset__) or bool(copyreg._slotnames(cls))
        if len(_STATEFUL_TYPES) >= _TYPE_CACHE_LIMIT:
            _STATEFUL_TYPES.clear()
        _STATEFUL_TYPES[cls] = stateful
    if not stateful:
        return None, None
    state = getattr(value, "__dict__", None)
    state = dict(state) if state else None
    slots = None
    for name in copyreg._slotnames(type(value)):
        try:
            item = getattr(value, name)
        except AttributeError:
            continue
        if slots is None:
            slots = {}
        slots[name] = item
    return state, slots


def _restore_state(target, state, slots):
    """_instance_state で取り出した属性を target へ設定する。

    Args:
        target (object): 設定先。
        state (dict | None): ``__dict__`` へ追加する属性。
        slots (dict | None): ``__slots__`` へ設定する属性。

    Returns:
        object: target。
    """
    if state:
        target.__dict__.update(state)
    if slots:
        for name, item in slots.items():
            setattr(target, name, item)
    return target


def _copy_state(source, target, memo=None):
    """利用者の派生クラスが持つ追加の属性(``__dict__`` と ``__slots__``)を複製先へ写す。

    Args:
        source (object): 複製元。
        target (object): 複製先。source と同じクラスのインスタンス。
        memo (dict | None): ``copy.deepcopy`` の memo。None なら浅い複製。

    Returns:
        object: target。
    """
    if memo is not None:
        memo[id(source)] = target
    state, slots = _instance_state(source)
    if state is None and slots is None:
        return target
    if memo is not None:
        if state:
            state = copy.deepcopy(state, memo)
        if slots:
            slots = copy.deepcopy(slots, memo)
    return _restore_state(target, state, slots)


def _rebuild(cls, values):
    """copy / pickle の再構築関数。cls の ``__init__`` を呼ばずに値を復元する。

    om2 の型は C++ の実体を基底の ``__init__`` で確保するため、基底の ``__new__`` と
    ``__init__`` で確保してから成分を設定する。利用者の派生クラスが独自の引数の
    ``__init__`` を持っていても呼ばない。追加の属性(``__dict__`` / ``__slots__``)は
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
        raise TypeError("Cannot rebuild {}".format(cls.__name__))
    return result


def _reduce_value(value, values):
    """copy / pickle 用に、:func:`_rebuild` で再構築する情報を返す。

    利用者の派生クラスが持つ追加の属性は、pickle の標準形式の state(``__dict__`` の
    辞書、``__slots__`` もあれば ``(辞書, slots の辞書)``)として3番目の要素に置く。
    インスタンスの生成後に設定されるため、自身を参照する属性も復元できる。

    Args:
        value (object): 複製・保存する hlib の値。
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


class Vector(_MVector):
    """om2.MVector を継承した3成分の可変なベクトル値。

    ``om2.MVector`` の派生クラスなので、hlib の Vector をそのまま OpenMaya API 2.0 の
    関数・コンストラクタへ渡せる。コンストラクタは ``Vector()`` (ゼロ)、
    ``Vector(x, y, z)``、``Vector(x, y)`` (z=0)、``Vector([x, y, z])``、
    ``Vector(MVector | MPoint)`` など om2 と同じ形を受け付け、加えて
    ``Vector(x=1, y=2, z=3)`` のキーワード引数(省略した成分は 0)も使える。
    成分は数値だけで、文字列などの不正な引数は om2 と同じく ValueError になる。

    演算子は om2 の意味論に従い、結果を常に基底の :class:`Vector` として返す
    (Translation などの派生型は保持しない)。

    * ``+`` / ``-``: MVector 系同士の成分ごとの加減算。
    * ``v * 数値`` / ``数値 * v`` / ``v / 数値``: スカラー倍。0 での除算は
      Maya のバージョンにかかわらず ZeroDivisionError。
    * ``v * w``: 内積(float)。``v ^ w``: 外積。
    * ``v * m`` (m は MMatrix 系): 行ベクトル規約の方向変換(平行移動を含まない)。
    * ``m * v``: om2 と同じく列ベクトルとしての積(``v * mᵀ`` と同じ)。

    ``+=`` / ``-=`` / ``*=`` / ``/=`` / ``^=`` は自身を書き換えて派生型を保つ
    (``v *= w`` だけは om2 と同じく内積の float へ名前を束ね直す)。値は可変で
    ``x``/``y``/``z`` や添字へ代入でき、ハッシュは不可(dict のキーや set には
    使えない)。添字は -3〜2 の整数で、範囲外は IndexError。スライスは成分の tuple を
    返す(代入には使えない)。

    ``==`` は om2 と同じ成分の完全一致で、MVector 系であれば派生型が異なっても
    等しくなり得る。MVector 系以外との比較は例外にしない(om2 の型なら False、
    それ以外は相手の比較に委ね、どちらも判断しなければ False)。ただし om2 の型が
    左辺の比較(``om2.MPoint() == Vector()`` など)は om2 側が TypeError を送出する。

    snake_case のメソッド(``normalized`` や ``cross`` など)は hlib の型を返す。
    om2 から継承した camelCase のメソッド(``normal``、``rotateBy``、``isEquivalent``
    など)と ``kXaxisVector`` などのクラス定数は om2 の基底型 ``om2.MVector`` を
    返す。クラス定数は om2 の共有オブジェクトなので書き換えないこと。
    """

    __slots__ = ()
    __hash__ = None

    def __new__(cls, *args, **kwargs):
        """C++ の実体を確保した cls のインスタンス(ゼロベクトル)を作る。

        om2 の型は C++ の実体を基底の ``__init__`` で確保するため、``__new__`` だけで
        作ったインスタンスや、``__init__`` で基底の初期化まで到達しなかった派生クラスの
        インスタンスは、アクセス時にプロセスごと落ちる。ここで必ず確保し、
        :meth:`__init__` は成分の設定だけを行う(基底の ``__init__`` を再度呼ぶと
        Maya 2022 では確保済みの実体がリークする)。

        Args:
            *args: コンストラクタの引数。ここでは使わない。
            **kwargs: コンストラクタのキーワード引数。ここでは使わない。

        Returns:
            Vector: cls のゼロベクトル。
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
            ValueError: om2 のコンストラクタが受け付けない引数(文字列の成分など)の場合。
            TypeError: 未知のキーワード引数、または同じ成分を二重に指定した場合。
        """
        if kwargs:
            try:
                args = _vector_keywords(*args, **kwargs)
            except TypeError as error:
                raise TypeError("{}() {}".format(type(self).__name__, str(error).split("() ", 1)[-1])) from None
        count = len(args)
        values = args
        if count == 1:
            source = args[0]
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

    @classmethod
    def from_iterable(cls, values):
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
            raise ValueError("{} expects 3 values".format(cls.__name__))
        return cls(values[0], values[1], values[2])

    # ------------------------------------------------------------------ 添字・反復
    def __getitem__(self, index):
        """成分を取得する。

        Args:
            index (int | slice): -3〜2 の添字、またはスライス。

        Returns:
            float | tuple[float, ...]: 指定成分。スライスでは成分の tuple。

        Raises:
            IndexError: 添字が範囲外の場合。
            TypeError: 添字が整数・スライス以外の場合。
        """
        if index.__class__ is int and -3 <= index < 3:
            return _GET(self, index)
        if isinstance(index, slice):
            return (self.x, self.y, self.z)[index]
        return _GET(self, _checked_index(index, 3, "Vector"))

    def __setitem__(self, index, value):
        """成分を設定する。

        Args:
            index (int): -3〜2 の添字。
            value (float): 設定する値。

        Returns:
            None: 値を返さない。

        Raises:
            IndexError: 添字が範囲外の場合。
            TypeError: 添字が整数以外の場合。
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

    # ------------------------------------------------------------------ 複製・表示
    def __reduce__(self):
        """copy / pickle 用に、コンストラクタを通さずに再構築する情報を返す。

        om2 の型は C++ の実体を基底の ``__init__`` で確保するため、再構築関数で
        確保してから成分を設定する。利用者の派生クラスの ``__init__`` は呼ばず、
        ``__dict__`` と ``__slots__`` の属性は再構築時に復元する。

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

    def _duplicate(self):
        """同じ型・同じ成分の新しいインスタンスを返す(追加の属性は写さない)。

        利用者の派生クラスの ``__init__`` は呼ばない。

        Returns:
            Vector: 自身と同じクラスの新しいインスタンス。
        """
        result = _NEW(type(self))
        _INIT(result)
        result.x = self.x
        result.y = self.y
        result.z = self.z
        return result

    def __copy__(self):
        """同じ型・同じ成分の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つ属性も浅く写す。

        Returns:
            Vector: 自身と同じクラスの新しいインスタンス。
        """
        return _copy_state(self, self._duplicate())

    def __deepcopy__(self, memo):
        """同じ型・同じ成分の複製を返す。

        利用者の派生クラスが ``__dict__`` / ``__slots__`` に持つ属性は深く複製する。

        Args:
            memo (dict): copy.deepcopy の memo。

        Returns:
            Vector: 自身と同じクラスの新しいインスタンス。
        """
        return _copy_state(self, self._duplicate(), memo)

    def __repr__(self):
        """クラス名と3成分を含むデバッグ表現を返す。

        Returns:
            str: ``Translation(1.0, 2.0, 3.0)`` の形式の文字列。
        """
        return "{}({!r}, {!r}, {!r})".format(type(self).__name__, self.x, self.y, self.z)

    __str__ = __repr__

    # ------------------------------------------------------------------ 比較
    def __eq__(self, other):
        """MVector 系との成分の完全一致を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MVector 系なら om2 と同じ成分比較の結果。
            その他の om2 の型は False。それ以外の型は NotImplemented(相手の比較に委ね、
            どちらも判断しなければ False になる)。
        """
        if isinstance(other, _MVector):
            return _MVector.__eq__(self, other)
        return _foreign_comparison(other, False)

    def __ne__(self, other):
        """``__eq__`` の否定を返す。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: MVector 系なら om2 と同じ比較の結果。
            その他の om2 の型は True。それ以外の型は NotImplemented。
        """
        if isinstance(other, _MVector):
            return _MVector.__ne__(self, other)
        return _foreign_comparison(other, True)

    # ------------------------------------------------------------------ 演算
    def __add__(self, other):
        """MVector 系との成分ごとの加算を返す。

        Args:
            other (object): 加算する MVector 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MVector):
            return NotImplemented
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, self)
        _MVector.__iadd__(result, other)
        return result

    def __radd__(self, other):
        """左辺の MVector 系との成分ごとの加算を返す。

        Args:
            other (object): 左辺の MVector 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MVector):
            return NotImplemented
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, other)
        _MVector.__iadd__(result, self)
        return result

    def __sub__(self, other):
        """MVector 系との成分ごとの減算を返す。

        Args:
            other (object): 減算する MVector 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MVector):
            return NotImplemented
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, self)
        _MVector.__isub__(result, other)
        return result

    def __rsub__(self, other):
        """左辺の MVector 系から自身を引いた値を返す。

        Args:
            other (object): 左辺の MVector 系。

        Returns:
            Vector | types.NotImplementedType: 新しい Vector。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MVector):
            return NotImplemented
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, other)
        _MVector.__isub__(result, self)
        return result

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
        (``v * mᵀ``)になる。位置を行列で変換する場合は
        :meth:`hlib.maths.matrix.Matrix.transform_point`、方向は ``v * m`` を使う。

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

    def __iadd__(self, other):
        """MVector 系を自身へ加算する。

        om2 の MVector を継承した型では、対応しない型との ``+=`` が例外にならず
        NotImplemented が代入されてしまうため、型を検査してから委譲する。

        Args:
            other (object): 加算する MVector 系。

        Returns:
            Vector | types.NotImplementedType: 自身。対応しない型は NotImplemented(TypeError になる)。
        """
        if not isinstance(other, _MVector):
            return NotImplemented
        return _MVector.__iadd__(self, other)

    def __isub__(self, other):
        """MVector 系を自身から減算する。

        Args:
            other (object): 減算する MVector 系。

        Returns:
            Vector | types.NotImplementedType: 自身。対応しない型は NotImplemented。
        """
        if not isinstance(other, _MVector):
            return NotImplemented
        return _MVector.__isub__(self, other)

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

    # ------------------------------------------------------------------ hlib 名のメソッド
    def dot(self, other):
        """内積を返す。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 内積の相手。

        Returns:
            float: 内積。
        """
        return _MVector.__mul__(self, _as_mvector(other))

    def cross(self, other):
        """外積を返す。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 外積の相手。

        Returns:
            Vector: 外積。派生クラスの型は保持しない。
        """
        result = _NEW(Vector)
        _INIT(result)
        _MVector.__iadd__(result, _MVector.__xor__(self, _as_mvector(other)))
        return result

    def length_squared(self):
        """長さの2乗(自身との内積)を返す。

        平方根を計算しないため、長さの比較だけが目的なら length() より速い。

        Returns:
            float: 長さの2乗。
        """
        return _MVector.__mul__(self, self)

    def normalized(self):
        """正規化した新しいベクトルを返す。

        om2 の ``normal()`` はゼロベクトルでも例外にならず ``om2.MVector`` を返すが、
        このメソッドは hlib の Vector を返し、ゼロベクトルを拒否する。

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

    def distance_to(self, other):
        """2点間のユークリッド距離を返す。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 距離を測る相手。

        Returns:
            float: 距離。
        """
        return _MVector.__sub__(self, _as_mvector(other)).length()

    def angle_to(self, other):
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
        other = _as_mvector(other)
        if _MVector.__mul__(self, self) == 0.0 or _MVector.__mul__(other, other) == 0.0:
            raise ValueError("Cannot measure the angle to or from a zero vector")
        return math.atan2(_MVector.__xor__(self, other).length(), _MVector.__mul__(self, other))

    def is_equivalent(self, other, tolerance=1e-10):
        """許容誤差付きでほぼ等しいか判定する。

        om2 の ``isEquivalent`` に委譲するため、2点間のユークリッド距離が
        tolerance 以下かどうかで判定する。

        Args:
            other (om2.MVector | om2.MPoint | Iterable[float]): 比較対象。
            tolerance (float): 距離の許容誤差。

        Returns:
            bool: ほぼ等しければ True。
        """
        return _MVector.isEquivalent(self, _as_mvector(other), tolerance)

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
        _MVector.__iadd__(result, _as_mvector(other))
        _MVector.__isub__(result, self)
        _MVector.__imul__(result, t)
        _MVector.__iadd__(result, self)
        return result
