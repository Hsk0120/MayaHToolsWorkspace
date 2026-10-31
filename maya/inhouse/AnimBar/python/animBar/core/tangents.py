"""選んだキーの接線を、Mayaの接線型または計算した向き(flow・bounce)にする。

- Mayaの接線型(auto・spline・linear・flat・step・clamped・plateau)はそのまま設定する。
- ``flow``: 前後のキーを結ぶ向きの接線(キーを通る滑らかな流れ)。両端のキーは flat。
- ``bounce``: 山・谷(前後より大きい・小さい)のキーは flat、それ以外は flow。
"""

import math

from mlib.decorator import undoChunk

from . import keys

#: Mayaの接線型。
MAYA_TYPES = ("auto", "spline", "linear", "flat", "step", "clamped", "plateau")

#: 計算して決める接線。
COMPUTED_TYPES = ("flow", "bounce")


@undoChunk("animBarSetTangent")
def setTangent(kind, side="both"):
    """選んだキー(無ければ現在時刻のキー)の接線を設定する。

    Args:
        kind (str): :data:`MAYA_TYPES` または :data:`COMPUTED_TYPES` の名前。
        side (str): ``"both"``・``"in"``・``"out"``。stepは出力側だけに効く。

    Returns:
        int: 設定したキーの数。
    """
    if kind not in MAYA_TYPES + COMPUTED_TYPES:
        raise ValueError("Unknown tangent type: " + str(kind))
    if side not in ("both", "in", "out"):
        raise ValueError("side must be 'both', 'in' or 'out'")
    count = 0
    for target in keys.targets():
        for index in target.indices:
            if kind in MAYA_TYPES:
                _set_type(target.curve, index, kind, side)
            else:
                _set_computed(target.curve, index, kind, side)
            count += 1
    return count


def flowAngle(curve, index):
    """前後のキーを結ぶ向きの接線の角度(度)を返す。両端のキーは0。

    Args:
        curve (AnimCurve): カーブ。
        index (int): キーの番号。

    Returns:
        float: 接線の角度(度)。グラフの横軸は秒、縦軸は値。
    """
    inputs, values = curve.getKeyInputs(timeUnit="sec"), curve.getKeyValues()
    if index <= 0 or index >= len(inputs) - 1:
        return 0.0
    dt = inputs[index + 1] - inputs[index - 1]
    if dt <= 0:
        return 0.0
    return math.degrees(math.atan((values[index + 1] - values[index - 1]) / dt))


def isExtreme(curve, index):
    """キーが山・谷(前後より大きい・小さい)か、両端かを返す。

    Args:
        curve (AnimCurve): カーブ。
        index (int): キーの番号。

    Returns:
        bool: 山・谷・両端ならTrue。
    """
    values = curve.getKeyValues()
    if index <= 0 or index >= len(values) - 1:
        return True
    before, value, after = values[index - 1], values[index], values[index + 1]
    return (value >= before and value >= after) or (value <= before and value <= after)


def _set_type(curve, index, kind, side):
    """Mayaの接線型を設定する。

    Args:
        curve (AnimCurve): カーブ。
        index (int): キーの番号。
        kind (str): 接線型。
        side (str): 設定する側。

    Returns:
        None: 値を返さない。
    """
    flags = {}
    if side in ("both", "in") and kind != "step":
        flags["inTangentType"] = kind
    if side in ("both", "out") or kind == "step":
        flags["outTangentType"] = kind
    curve.setTangent(index, **flags)


def _set_computed(curve, index, kind, side):
    """flow・bounce の接線を、固定の角度で設定する。

    Args:
        curve (AnimCurve): カーブ。
        index (int): キーの番号。
        kind (str): ``"flow"`` または ``"bounce"``。
        side (str): 設定する側。

    Returns:
        None: 値を返さない。
    """
    if kind == "bounce" and isExtreme(curve, index):
        _set_type(curve, index, "flat", side)
        return
    angle = flowAngle(curve, index)
    flags = {"lock": False}
    if side in ("both", "in"):
        flags.update(inTangentType="fixed", inAngle=angle)
    if side in ("both", "out"):
        flags.update(outTangentType="fixed", outAngle=angle)
    curve.setTangent(index, **flags)
