"""ミラー操作に共通する軸と中心の入力検証。"""

import math


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


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ('mirror_arguments',):
    globals().pop(_obsolete_name, None)
