# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
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
from typing import Any, Callable, Iterable, NoReturn
import types

__all__ = ['legalizeName', 'measure', 'mirrorArguments']
_UNSET: ellipsis
_SEPARATOR: str
_FILLER: str
_PERMITTED: frozenset
_NOT_AT_HEAD: frozenset
_TYPE_CACHE_LIMIT: int
_OM2_TYPES: dict
_STATEFUL_TYPES: dict
_ANGLE_UNITS: dict


class _ArgumentError(TypeError):
    """長短引数の競合・必須値の欠落を、複数形でもTypeErrorとして伝える。"""

def legalizeName(name: str) -> str:
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
    ...

def measure(operation: Callable[..., Any], samples: int = ..., warmup: int = ...) -> dict:
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
    ...

def mirrorArguments(axis: str | int, pivot: Iterable[float]) -> tuple:
    """反転軸と有限な中心座標を検証する。

    Args:
        axis (str | int): 重複のないxyz文字列、または0/1/2。
        pivot (Iterable[float]): 3成分の中心座標。

    Returns:
        tuple: 軸番号のtupleと中心座標のtuple。

    Raises:
        ValueError: 軸や中心が不正な場合。
    """
    ...

def _clean_segment(segment: str) -> str:
    """コロンで区切られた1区間を、単独で有効な識別子へ整える。

    前後の空白を落とし、使えない文字が連続する箇所は1文字の ``_`` に
    まとめる。入力にもともと含まれる ``_`` はそのまま残す。整えた結果が
    数字で始まる場合は先頭に ``_`` を足す。

    Args:
        segment (str): コロンを含まない1区間。

    Returns:
        str: 整えた区間。空白だけ、または空の区間なら空文字。
    """
    ...

def _checked_index(index: int, size: int, name: str) -> int:
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
    ...

def _is_om2_type(cls) -> bool:
    """cls が OpenMaya の型(API 1.0 / 2.0。派生クラスを含む)か判定する。

    Args:
        cls (type): 判定する型。

    Returns:
        bool: MRO に OpenMaya のモジュールで定義された型を含めば True。
    """
    ...

def _foreign_comparison(other: object, result: bool) -> bool | types.NotImplementedType:
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
    ...

def _instance_state(value: object) -> tuple:
    """利用者の派生クラスのインスタンスが持つ追加のアトリビュートを取り出す。

    mlib 自身の型のように ``__dict__`` も ``__slots__`` のアトリビュートも持たない型は、
    型ごとの判定をキャッシュしてすぐに返す。

    Args:
        value (object): mlib の値。

    Returns:
        tuple: (``__dict__`` の浅いコピー、または None, ``__slots__`` の値の辞書、または None)。
    """
    ...

def _restore_state(target: object, state: dict | None, slots: dict | None) -> Any:
    """_instance_state で取り出したアトリビュートを target へ設定する。

    Args:
        target (object): 設定先。
        state (dict | None): ``__dict__`` へ追加するアトリビュート。
        slots (dict | None): ``__slots__`` へ設定するアトリビュート。

    Returns:
        object: target。
    """
    ...

def _copy_state(source: object, target: object, memo: dict | None = ...) -> Any:
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
    ...

def _angle_unit(unit: str | None, default: str | None = ...) -> str | None:
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
    ...

def _to_radians(value: float, unit: str) -> float:
    """正規化済みの単位の数値をラジアンへ変換する。

    Args:
        value (float): 角度。
        unit (str): ``"deg"`` または ``"rad"``。

    Returns:
        float: ラジアンの値。radはそのまま返す。
    """
    ...

def _from_radians(value: float, unit: str) -> float:
    """ラジアンの数値を正規化済みの単位へ変換する。

    Args:
        value (float): ラジアンの角度。
        unit (str): ``"deg"`` または ``"rad"``。

    Returns:
        float: 指定単位の値。radはそのまま返す。
    """
    ...

def _world_space(value: bool) -> bool:
    """boolの空間指定を検証する。

    Args:
        value (bool): Trueはワールド空間、Falseはローカル空間。

    Returns:
        bool: 検証済みの指定。

    Raises:
        TypeError: bool以外を指定した場合。
    """
    ...

def _finite(value: numbers.Real, name: str) -> float:
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
    ...

def _finite_vector(value: Iterable[numbers.Real], size: int, name: str) -> tuple[float, ...]:
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
    ...

def _checked_tolerance(value: numbers.Real, *, positive: bool = ...) -> float:
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
    ...

def _unique_ordered(items: Iterable[object], key: Callable[..., Any] | None = ...) -> list:
    """最初の出現順を保ったまま重複を除く。

    Args:
        items (Iterable[object]): 要素列。keyを省略する場合はハッシュ可能な要素。
        key (callable | None): 重複判定に使うキーを返す関数。Noneは要素自身。

    Returns:
        list: 最初の出現順を維持した要素。
    """
    ...

def _rethrow_init_error(cls, error: TypeError) -> NoReturn:
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
    ...
