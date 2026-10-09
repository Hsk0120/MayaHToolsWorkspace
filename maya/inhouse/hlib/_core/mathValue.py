"""数学値の添字・比較・派生インスタンス状態を扱う内部共通処理。"""

import copy
import copyreg
from operator import index as _as_index

# 型を動的に作る利用側でも保持し続けないよう、判定キャッシュに上限を設ける。
_TYPE_CACHE_LIMIT = 256
_OM2_TYPES = {}
_STATEFUL_TYPES = {}


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
    """利用者の派生クラスのインスタンスが持つ追加のアトリビュートを取り出す。

    hlib 自身の型のように ``__dict__`` も ``__slots__`` のアトリビュートも持たない型は、
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
    """_instance_state で取り出したアトリビュートを target へ設定する。

    Args:
        target (object): 設定先。
        state (dict | None): ``__dict__`` へ追加するアトリビュート。
        slots (dict | None): ``__slots__`` へ設定するアトリビュート。

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
    """利用者の派生クラスが持つ追加のアトリビュート(``__dict__`` と ``__slots__``)を複製先へ写す。

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
