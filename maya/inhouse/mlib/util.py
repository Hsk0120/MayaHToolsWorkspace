"""クラスに属さない汎用関数と、数学値・空間指定の内部補助を提供する。

公開関数は名前の整形・操作の計測・ミラー入力の検証を扱う。
型の番号・比較・派生状態の複製と空間指定の検証は、先頭 ``_`` の内部関数へ分ける。
"""

import copy
import copyreg
import math
import numbers
import string
import time
from operator import index as _as_index

__all__ = ["legalizeName", "measure", "mirrorArguments"]

# 長短のどちらを省略したかを区別する。値として渡すための定数ではない。
_UNSET = ...

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

#: 角度の単位名と正規化した名前。シーン操作の数値の角度は既定で度(``"deg"``)。
_ANGLE_UNITS = {
    "deg": "deg", "degree": "deg", "degrees": "deg",
    "rad": "rad", "radian": "rad", "radians": "rad",
}

#: 反転する軸の番号(0=x, 1=y, 2=z)の順に並べたミラー面の名前。x を反転するミラーは YZ 面のミラー。
_MIRROR_PLANES = ("YZ", "XZ", "XY")

#: ミラーの axis に指定できる書き方の案内(例外の文言用)。
_MIRROR_AXIS_CHOICES = "a flip axis 'x', 'y', 'z' (or 0, 1, 2) or a mirror plane 'YZ', 'XZ', 'XY'"


class _ArgumentError(TypeError):
    """長短引数の競合・必須値の欠落を、複数形でもTypeErrorとして伝える。"""


def legalizeName(name):
    """Mayaノード名用の文字列を整形する。ノードや名前空間は作成しない。

    コロンを名前空間区切りとして残し、各区間の前後の空白を除く。
    ASCII英数字・_以外の連続範囲は一つの_に変え、数字で始まる区間には_を付ける。
    空区間は捨て、先頭のコロンは一つ残す。有効な区間がなければ_を返す。

    Args:
        name (str): 整形する文字列。

    Returns:
        str: 整形後の名前。既存ノード名との重複は検査しない。

    Raises:
        TypeError: nameがstr以外の場合。

    Examples:
        >>> legalizeName("rig:2nd joint")
        'rig:_2nd_joint'
    """
    if not isinstance(name, str):
        raise TypeError(f"name must be a str, not {type(name).__name__}")
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
    # statisticsはfractions・decimalも読むため、import mlibの時間を増やさないよう計測前に読む。
    import statistics

    for _ in range(warmup):
        operation()
    values = []
    for _ in range(samples):
        start = time.perf_counter()
        operation()
        values.append(time.perf_counter() - start)
    return {"samples": samples, "median_seconds": statistics.median(values),
            "min_seconds": min(values), "max_seconds": max(values)}


def _mirror_axis(axis):
    """ミラーの指定を、反転する軸の番号(0=x, 1=y, 2=z)にする。

    反転する軸(``"x"``)とミラー面(``"YZ"``)のどちらの書き方も受け付ける。
    対応は x⇔YZ、y⇔XZ、z⇔XY で、面の文字の順序(``"ZX"`` など)と大文字小文字は問わない。
    ミラー面の名前は ``_MIRROR_PLANES[番号]`` で得られる。

    Args:
        axis (str | int): ``"x"``・``"y"``・``"z"``、``"YZ"``・``"XZ"``・``"XY"``、または0/1/2。

    Returns:
        int: 反転する軸の番号。

    Raises:
        TypeError: axis が文字列・int 以外(bool を含む)の場合。
        ValueError: axis が上記のどれにも当たらない場合。
    """
    if type(axis) is int:
        if axis in (0, 1, 2):
            return axis
        raise ValueError(f"axis must be {_MIRROR_AXIS_CHOICES}: {axis!r}")
    if not isinstance(axis, str):
        raise TypeError(f"axis must be a str or an int, got {type(axis).__name__}")
    letters = axis.lower()
    if letters in ("x", "y", "z"):
        return "xyz".index(letters)
    if len(letters) == 2 and letters[0] != letters[1] and all(letter in "xyz" for letter in letters):
        # ミラー面に含まれない残りの1軸が、反転する軸になる。
        return next(index for index, letter in enumerate("xyz") if letter not in letters)
    raise ValueError(f"axis must be {_MIRROR_AXIS_CHOICES}: {axis!r}")


def mirrorArguments(axis, pivot):
    """ミラーの軸と有限な中心座標を検証する。

    axis は反転する軸(``"x"``)とミラー面(``"YZ"``)のどちらの書き方でもよい。
    対応は x⇔YZ、y⇔XZ(``"ZX"`` も可)、z⇔XY で、文字の順序と大文字小文字は問わない。

    Args:
        axis (str | int): ``"x"``・``"y"``・``"z"``、``"YZ"``・``"XZ"``・``"XY"``、または0/1/2。
        pivot (Iterable[float]): 3成分の中心座標。

    Returns:
        tuple: 反転する軸の番号1つのtuple(例 ``(0,)``)と、中心座標のtuple。

    Raises:
        TypeError: axis が文字列・int 以外の場合。
        ValueError: axis が未対応の値、または中心が有限の3成分でない場合。
    """
    flip = _mirror_axis(axis)
    try:
        center = tuple(float(value) for value in pivot)
    except (TypeError, ValueError):
        raise ValueError("pivot must contain three finite numbers") from None
    if len(center) != 3 or not all(math.isfinite(value) for value in center):
        raise ValueError("pivot must contain three finite numbers")
    return (flip,), center


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
    """番号を検査し、0〜size-1 へ正規化する。

    om2 の番号は負の範囲外の値を検査しない(Python が長さを1回だけ足して渡すため、
    MVector の ``v[-4]`` が最後の成分を返し、MMatrix の -17 以下は範囲外のメモリを
    読み書きする)ため、om2 へ渡す前に必ずここで検査する。

    Args:
        index (int): 番号。負の値は末尾から数える。
        size (int): 要素数。
        name (str): 例外メッセージに使う型名。

    Returns:
        int: 0〜size-1 の番号。

    Raises:
        TypeError: 整数として扱えない場合。
        IndexError: 範囲外の場合。
    """
    try:
        position = _as_index(index)
    except TypeError:
        raise TypeError(f"{name} indices must be integers or slices, not {type(index).__name__}") from None
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
    """数学成分を作成済みの複製先へ、派生クラスの追加Python状態だけを写す。

    数学成分の確保・コピーは呼出し側が担当する。この関数は__dict__/__slots__を
    取り出して設定し、memo=Noneでは追加値の参照を浅く写す。memo指定時は
    source→targetを先に登録してから深くコピーし、自己参照を複製先へ対応付ける。
    通常の演算や型変換へ暗黙に追加状態を伝播する仕組みではない。

    Args:
        source (object): コピー元の数学値。
        target (object): 数学成分を独立確保した同型のコピー先。
        memo (dict | None): copy.deepcopyの共有辞書。Noneは浅いコピー。

    Returns:
        object: 渡されたtarget自身。sourceの数学成分は変更しない。
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


def _angle_unit(unit, default="deg"):
    """角度の単位名を ``"deg"`` / ``"rad"`` へ正規化する。

    Args:
        unit (str | None): ``"deg"``・``"degree"``・``"degrees"``・``"rad"``・``"radian"``・
            ``"radians"`` のいずれか。Noneはdefaultを使う。
        default (str | None): unitがNoneの場合に返す値。

    Returns:
        str | None: ``"deg"`` または ``"rad"``。unitとdefaultがNoneならNone。

    Raises:
        TypeError: unitが文字列・None以外の場合。
        ValueError: 未対応の単位名の場合。
    """
    if unit is None:
        return default
    if not isinstance(unit, str):
        raise TypeError(f"Angle unit must be a string: {unit!r}")
    try:
        return _ANGLE_UNITS[unit]
    except KeyError:
        raise ValueError(f"Unsupported angle unit: {unit!r} (use 'deg' or 'rad')") from None


def _to_radians(value, unit):
    """正規化済みの単位の数値をラジアンへ変換する。

    Args:
        value (float): 角度。
        unit (str): ``"deg"`` または ``"rad"``。

    Returns:
        float: ラジアンの値。radはそのまま返す。
    """
    return math.radians(value) if unit == "deg" else value


def _from_radians(value, unit):
    """ラジアンの数値を正規化済みの単位へ変換する。

    Args:
        value (float): ラジアンの角度。
        unit (str): ``"deg"`` または ``"rad"``。

    Returns:
        float: 指定単位の値。radはそのまま返す。
    """
    return math.degrees(value) if unit == "deg" else value


def _world_space(value):
    """boolの空間指定を検証する。

    Args:
        value (bool): Trueはワールド空間、Falseはローカル空間。

    Returns:
        bool: 検証済みの指定。

    Raises:
        TypeError: bool以外を指定した場合。
    """
    if type(value) is not bool:
        raise TypeError("worldSpace (ws) must be a bool")
    return value


def _finite(value, name):
    """有限な実数を検証し、floatへ変換する。

    Args:
        value (numbers.Real): 検証する値。boolは数値として受け付けない。
        name (str): 例外メッセージに使う引数名。

    Returns:
        float: 変換済みの値。

    Raises:
        TypeError: 実数以外(boolを含む)の場合。
        ValueError: 無限大・NaNの場合。
    """
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise TypeError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _finite_vector(value, size, name):
    """成分数の決まった有限な実数列を検証し、floatのtupleへ変換する。

    Args:
        value (Iterable[numbers.Real]): 検証する成分列。
        size (int): 期待する成分数。
        name (str): 例外メッセージに使う引数名。

    Returns:
        tuple[float, ...]: 変換済みの成分。

    Raises:
        TypeError: 反復できない値、または成分に実数以外(boolを含む)がある場合。
        ValueError: 成分数が異なる、または無限大・NaNの成分がある場合。
    """
    try:
        items = tuple(value)
    except TypeError:
        raise TypeError(f"{name} must be a sequence of {size} numbers") from None
    if len(items) != size:
        raise ValueError(f"{name} must have {size} components")
    return tuple(_finite(item, name) for item in items)


def _checked_tolerance(value, *, positive=False):
    """許容誤差を検証し、floatへ変換する。

    Args:
        value (numbers.Real): 許容誤差。
        positive (bool): Trueなら0を拒否し、正の値だけを受け付ける。既定は0以上。

    Returns:
        float: 変換済みの許容誤差。

    Raises:
        TypeError: 実数以外(boolを含む)の場合。
        ValueError: 無限大・NaN・負、またはpositive=Trueで0の場合。
    """
    result = _finite(value, "tolerance")
    if positive and result <= 0:
        raise ValueError("tolerance must be positive")
    if result < 0:
        raise ValueError("tolerance must be non-negative")
    return result


def _unique_ordered(items, key=None):
    """最初の出現順を保ったまま重複を除く。

    Args:
        items (Iterable[object]): 要素列。keyを省略する場合はハッシュ可能な要素。
        key (callable | None): 重複判定に使うキーを返す関数。Noneは要素自身。

    Returns:
        list: 最初の出現順を維持した要素。
    """
    seen = set()
    result = []
    for item in items:
        marker = item if key is None else key(item)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def _rethrow_init_error(cls, error):
    """キーワード解析のTypeErrorを、構築中のクラス名を先頭にした文言で送り直す。

    maths の ``__init__`` が ``_vector_keywords`` 等の補助関数から受けた
    ``"<helper>() <理由>"`` 形式のメッセージを、``"<Class>() <理由>"`` に書き換える。

    Args:
        cls (type): 構築中のクラス。
        error (TypeError): 補助関数が送出した例外。

    Returns:
        NoReturn: 正常には戻らない。

    Raises:
        TypeError: 書き換えたメッセージの例外。元の例外は連鎖しない。
    """
    raise TypeError(f"{cls.__name__}() {str(error).split('() ', 1)[-1]}") from None
