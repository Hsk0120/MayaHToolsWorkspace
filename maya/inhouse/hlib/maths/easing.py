"""0から1の範囲を非線形に補間するイージング関数。Maya非依存の純粋関数。"""

import math

__all__ = (
    "ease_in_out_quadratic",
    "ease_in_out_cubic",
    "ease_in_out_quartic",
    "ease_in_out_quintic",
    "ease_in_out_sinusoidal",
    "ease_in_out_exponential",
    "ease_in_out_circular",
)


def ease_in_out_quadratic(t):
    """2次関数のease-in-outカーブでtを変換する。

    Args:
        t (float): 0から1の入力値。

    Returns:
        float: 変換後の値。t=0で0、t=0.5で0.5、t=1で1。
    """
    t *= 2.0
    if t < 1.0:
        return 0.5 * t ** 2
    t -= 1.0
    return -0.5 * (t * (t - 2.0) - 1.0)


def ease_in_out_cubic(t):
    """3次関数のease-in-outカーブでtを変換する。

    Args:
        t (float): 0から1の入力値。

    Returns:
        float: 変換後の値。t=0で0、t=0.5で0.5、t=1で1。
    """
    t *= 2.0
    if t < 1.0:
        return 0.5 * t ** 3
    t -= 2.0
    return 0.5 * (t ** 3 + 2.0)


def ease_in_out_quartic(t):
    """4次関数のease-in-outカーブでtを変換する。

    Args:
        t (float): 0から1の入力値。

    Returns:
        float: 変換後の値。t=0で0、t=0.5で0.5、t=1で1。
    """
    t *= 2.0
    if t < 1.0:
        return 0.5 * t ** 4
    t -= 2.0
    return -0.5 * (t ** 4 - 2.0)


def ease_in_out_quintic(t):
    """5次関数のease-in-outカーブでtを変換する。

    Args:
        t (float): 0から1の入力値。

    Returns:
        float: 変換後の値。t=0で0、t=0.5で0.5、t=1で1。
    """
    t *= 2.0
    if t < 1.0:
        return 0.5 * t ** 5
    t -= 2.0
    return 0.5 * (t ** 5 + 2.0)


def ease_in_out_sinusoidal(t):
    """正弦関数のease-in-outカーブでtを変換する。

    Args:
        t (float): 0から1の入力値。

    Returns:
        float: 変換後の値。t=0で0、t=0.5で0.5、t=1で1。
    """
    return -0.5 * (math.cos(math.pi * t) - 1.0)


def ease_in_out_exponential(t):
    """指数関数のease-in-outカーブでtを変換する。

    Args:
        t (float): 0から1の入力値。

    Returns:
        float: 変換後の値。t=0.5で0.5、t=1で1。t=0では厳密な0ではなく
            極小値になる(指数関数の漸近的な性質による)。
    """
    t *= 2.0
    if t < 1.0:
        return 0.5 * math.pow(2.0, 10.0 * (t - 1.0))
    t -= 1.0
    return 0.5 * (-math.pow(2.0, -10.0 * t) + 2.0)


def ease_in_out_circular(t):
    """円弧関数のease-in-outカーブでtを変換する。

    Args:
        t (float): 0から1の入力値。

    Returns:
        float: 変換後の値。t=0で0、t=0.5で0.5、t=1で1。
    """
    t *= 2.0
    if t < 1.0:
        return -0.5 * (math.sqrt(1.0 - t ** 2) - 1.0)
    t -= 2.0
    return 0.5 * (math.sqrt(1.0 - t ** 2) + 1.0)
