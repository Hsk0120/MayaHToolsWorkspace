"""クラスに属さない汎用関数と、数学値・空間指定の内部補助を提供する。

公開関数は名前の整形・操作の計測・ミラー入力の検証を扱う。
型の添字・比較・派生状態の複製と空間指定の検証は、先頭_の内部関数へ分ける。
"""

import copy
import copyreg
import math
import statistics
import string
import time
from operator import index as _as_index

__all__ = ["legalizeName", "measure", "mirrorArguments"]

#: 名前空間の区切り文字。区切りとして残し、区間ごとに検査する。
_SEPARATOR = ":"

#: 使えない文字の代わりに入れる文字。
_FILLER = "_"

#: 区間内で使ってよい文字。``str.isalnum`` は非ASCII文字も真になるため使わない。
_PERMITTED = frozenset(string.ascii_letters + string.digits + _FILLER)

#: 区間の先頭に置けない文字。``str.isdigit`` は上付き数字なども真になるため使わない。
_NOT_AT_HEAD = frozenset(string.digits)

# 型を動的に作る利用側でも保持し続けないよう、判定キャッシュに上限を設ける。
_TYPE_CACHE_LIMIT = 256
_OM2_TYPES = {}
_STATEFUL_TYPES = {}


def legalizeName(name):
    """文字列を Maya のノード名として受け付けられる形へ変換する。

    コロン ``:`` を名前空間の区切りとして残し、区切られた各区間(名前空間名と
    末尾のノード名)に同じ規則を当てる。

    - 各区間の前後の空白は取り除く。
    - ASCII 英字・数字・``_`` 以外の文字(途中の空白、記号、``|``、``.``、
      非ASCII文字など)は、連続している範囲ごとに1つの ``_`` へ置き換える。
    - 数字で始まる区間には先頭に ``_`` を足す(``"ns:1abc"`` は ``"ns:_1abc"``)。
    - 空になった区間は捨てる(``"a::b"`` は ``"a:b"``、``"ns:"`` は ``"ns"``)。
    - 先頭のコロンはルート名前空間からの指定とみなし、1つだけ残す。
    - 有効な区間が1つも残らない場合は ``"_"`` を返す。

    Args:
        name (str): 変換したい文字列。

    Returns:
        str: Maya のノード名として有効な文字列。

    Raises:
        TypeError: name が str でない場合。

    Examples:
        >>> legalizeName("  arm L.001 ")
        'arm_L_001'
        >>> legalizeName("rig:2nd joint")
        'rig:_2nd_joint'
    """
    if not isinstance(name, str):
        raise TypeError(
            f"name には str を指定してください(受け取った型: {type(name).__name__})"
        )
    text = name.strip()
    segments = []
    for part in text.split(_SEPARATOR):
        cleaned = _clean_segment(part)
        if cleaned:
            segments.append(cleaned)
    if not segments:
        return _FILLER
    joined = _SEPARATOR.join(segments)
    if text.startswith(_SEPARATOR):
        return _SEPARATOR + joined
    return joined


def measure(operation, samples=30, warmup=3):
    """操作の所要時間を秒単位で返す。

    Args:
        operation (callable): 入力更新と評価を含む操作。各回で呼ぶ。
        samples (int): 記録する回数。
        warmup (int): 記録前の実行回数。

    Returns:
        dict: samples、median_seconds、min_seconds、max_seconds。

    Note:
        同じ値を読むだけではキャッシュの速度になる。必要なdirty化は
        呼び出し側で行う。処理の副作用や時間位置も呼び出し側が管理する。
    """
    if not callable(operation):
        raise TypeError("operation must be callable")
    if type(samples) is not int or samples <= 0 or type(warmup) is not int or warmup < 0:
        raise ValueError("Invalid sample count")
    for _ in range(warmup):
        operation()
    values = []
    for _ in range(samples):
        start = time.perf_counter()
        operation()
        values.append(time.perf_counter() - start)
    return {"samples": samples, "median_seconds": statistics.median(values),
            "min_seconds": min(values), "max_seconds": max(values)}


def mirrorArguments(axis, pivot):
    """反転軸と有限な中心座標を検証する。

    Args:
        axis (str | int): 重複のないxyz文字列、または0/1/2。
        pivot (Iterable[float]): 3成分の中心座標。

    Returns:
        tuple: 軸番号のtupleと中心座標のtuple。

    Raises:
        ValueError: 軸や中心が不正な場合。
    """
    if type(axis) is int and axis in (0, 1, 2):
        axis = "xyz"[axis]
    if not isinstance(axis, str) or not axis:
        raise ValueError("axis must contain x, y, or z")
    axis = axis.lower()
    if any(value not in "xyz" for value in axis) or len(set(axis)) != len(axis):
        raise ValueError("axis must contain unique x, y, z characters")
    try:
        center = tuple(float(value) for value in pivot)
    except (TypeError, ValueError):
        raise ValueError("pivot must contain three finite numbers") from None
    if len(center) != 3 or not all(math.isfinite(value) for value in center):
        raise ValueError("pivot must contain three finite numbers")
    return tuple("xyz".index(value) for value in axis), center


def _clean_segment(segment):
    """コロンで区切られた1区間を、単独で有効な識別子へ整える。

    前後の空白を落とし、使えない文字が連続する箇所は1文字の ``_`` に
    まとめる。入力にもともと含まれる ``_`` はそのまま残す。整えた結果が
    数字で始まる場合は先頭に ``_`` を足す。

    Args:
        segment (str): コロンを含まない1区間。

    Returns:
        str: 整えた区間。空白だけ、または空の区間なら空文字。
    """
    out = []
    in_bad_run = False
    for char in segment.strip():
        if char in _PERMITTED:
            out.append(char)
            in_bad_run = False
            continue
        if not in_bad_run:
            out.append(_FILLER)
            in_bad_run = True
    cleaned = "".join(out)
    if cleaned[:1] in _NOT_AT_HEAD:
        cleaned = _FILLER + cleaned
    return cleaned


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
        raise IndexError(f"{name} index out of range")
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

    mlib 自身の型のように ``__dict__`` も ``__slots__`` のアトリビュートも持たない型は、
    型ごとの判定をキャッシュしてすぐに返す。

    Args:
        value (object): mlib の値。

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


def _world_space(value):
    """boolの空間指定を検証する。

    Args:
        value (bool): Trueはワールド空間、Falseはローカル空間。

    Returns:
        bool: 検証済みの指定。

    Raises:
        ValueError: bool以外を指定した場合。
    """
    if type(value) is not bool:
        raise ValueError("worldSpace (ws) must be a bool")
    return value
