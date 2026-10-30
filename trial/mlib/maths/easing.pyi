# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""進行度 0〜1 を、両端でゆるやかに変化する値へ写す対称イージング曲線。

公開するのは曲線名を指定して評価する :func:`ease` と、指定可能な曲線名の
一覧 :data:`CURVES` だけである。どの曲線も次の性質をそろえている。

- 入力は区間 [0, 1] に切り詰めてから評価する。
- 0 と 1 では誤差なく ``0.0`` と ``1.0`` を返す。
- 点 (0.5, 0.5) について点対称で、丸め誤差の範囲で
  ``ease(1 - t) == 1 - ease(t)`` が成り立つ。中央では正確に ``0.5`` を返す。
- 区間全体で単調に増加する。

多くの曲線は「立ち上がり側の半分」だけを 0→1 の関数として定め、
区間の前半ではそれを縦横 1/2 に縮めて使い、後半ではその点対称な写しを使う。
標準ライブラリの ``math`` 以外には依存しない(Maya 非依存)。

Examples:
    >>> from mlib.maths import easing
    >>> easing.ease(0.25)
    0.0625
    >>> easing.ease(0.5, "sine")
    0.5
    >>> "exponential" in easing.CURVES
    True
"""

import math
from typing import Callable

__all__ = ['CURVES', 'ease']
_EXPONENTIAL_STEEPNESS: float

def _rising_power(degree: int) -> Callable[[float], float]:
    """u を degree 乗する立ち上がり側の半曲線を作る。

    Args:
        degree (int): 多項式の次数。

    Returns:
        Callable[[float], float]: [0, 1] を [0, 1] へ写す単調増加関数。
    """
    ...

def _rising_exponential(u: float) -> float:
    """指数関数を 0→0、1→1 になるよう正規化した立ち上がり側の半曲線。

    ``(e^(k*u) - 1) / (e^k - 1)`` を ``math.expm1`` で求めるため、0 付近でも
    桁落ちせず、両端は正規化によって厳密に 0 と 1 になる。

    Args:
        u (float): [0, 1] の値。

    Returns:
        float: [0, 1] の値。
    """
    ...

def _rising_circular(u: float) -> float:
    """中心 (0, 1)・半径 1 の円のうち、(0, 0) から (1, 1) へ至る 1/4 弧。

    u = 0 で接線が水平、u = 1 で接線が垂直(傾きが無限大)になる。

    Args:
        u (float): [0, 1] の値。

    Returns:
        float: [0, 1] の値。
    """
    ...

def _symmetric(rising: Callable[[float], float]) -> Callable[[float], float]:
    """立ち上がり側の半曲線から、点 (0.5, 0.5) について対称な曲線を組み立てる。

    前半 [0, 0.5] は半曲線を縦横 1/2 に縮めたもの、後半 [0.5, 1] は前半を
    点 (0.5, 0.5) のまわりに 180 度回したものになる。

    Args:
        rising (Callable[[float], float]): f(0) == 0、f(1) == 1 の単調増加関数。

    Returns:
        Callable[[float], float]: [0, 1] で定義された対称曲線。
    """
    ...

def _linear(t: float) -> float:
    """入力をそのまま返す恒等曲線。比較や、強弱を付けない指定に使う。

    Args:
        t (float): (0, 1) の値。

    Returns:
        float: t と同じ値。
    """
    ...

def _smoothstep(t: float) -> float:
    """両端の傾きが 0 になる 3 次エルミート補間 ``3t^2 - 2t^3``。

    Args:
        t (float): (0, 1) の値。

    Returns:
        float: (0, 1) の値。
    """
    ...

def _sine(t: float) -> float:
    """正弦の -90〜90 度を 0〜1 へ写した曲線 ``(1 + sin(pi * (t - 0.5))) / 2``。

    中央 t = 0.5 で sin(0) を評価するため、中央の値が丸め誤差なく 0.5 になる。

    Args:
        t (float): (0, 1) の値。

    Returns:
        float: (0, 1) の値。
    """
    ...
_SHAPES: dict
CURVES: tuple

def _to_progress(t: float) -> float:
    """進行度として渡された値を float に変換する。

    int・float のほか ``float()`` で数値化できる実数型(``fractions.Fraction``
    など)を受け付ける。文字列と組み込みの bool は、誤って渡されたものが数値として
    通ってしまわないよう、数値化できる内容でも受け付けない。float で表せないほど
    大きな値は、符号に応じて ``inf`` / ``-inf`` として扱う(呼び出し側で切り詰める)。

    Args:
        t (float): 進行度として渡された値。

    Returns:
        float: 変換した値。範囲の切り詰めはしない。

    Raises:
        TypeError: t が文字列・bool、または ``float()`` で数値化できない値の場合。
        ValueError: t が NaN の場合。
    """
    ...

def ease(t: float, curve: str = ...) -> float:
    """進行度 t を、指定した対称イージング曲線で写した値を返す。

    t は [0, 1] に切り詰めてから評価するため、範囲外の値を渡しても
    戻り値は常に [0, 1] に収まる。どの曲線でも ``ease(0) == 0.0``、
    ``ease(1) == 1.0`` で、点 (0.5, 0.5) について対称かつ単調増加である。

    曲線ごとの形:

    - ``"linear"``: 変化なし(t をそのまま返す)。
    - ``"smoothstep"``: 3 次エルミート補間。両端の傾きが 0。
    - ``"sine"``: 正弦の半周期。smoothstep に近いなだらかな形。
    - ``"circular"``: 1/4 円弧を 2 つつないだ形。中央 t = 0.5 で接線が
      垂直になる(傾きが無限大)。
    - ``"quadratic"`` / ``"cubic"`` / ``"quartic"`` / ``"quintic"``:
      2〜5 次のべき乗を対称につないだ形。次数が高いほど両端が平らになる。
    - ``"exponential"``: 正規化した指数関数を対称につないだ形。

    Args:
        t (float): 進行度。int・float などの実数を受け付ける。文字列と組み込みの
            bool は数値として扱わない。
        curve (str): 曲線名。:data:`CURVES` のいずれか。既定は ``"cubic"``。

    Returns:
        float: [0, 1] の値。

    Raises:
        TypeError: curve が文字列でない場合。または t が文字列・bool・None
            など、実数として扱えない値の場合。
        ValueError: curve が未対応の名前の場合。または t が NaN の場合。

    Examples:
        >>> ease(0.25, "quadratic")
        0.125
        >>> ease(-3.0, "quintic")
        0.0
        >>> ease(0.5, "circular")
        0.5
    """
    ...
