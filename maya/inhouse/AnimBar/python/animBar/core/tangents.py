"""選んだキーの接線を、Mayaの接線型または計算した向き(flow・bounce)にする。

- Mayaの接線型(auto・spline・linear・flat・step・clamped・plateau)はそのまま設定する。
- ``flow``: 前後のキーを結ぶ向きの接線(キーを通る滑らかな流れ)。両端のキーは flat。
- ``bounce``: 山・谷(前後より大きい・小さい)のキーは flat、それ以外は flow。

対象のキーは scope で選ぶ。``"selected"`` は選んだキー(:func:`keys.targets` の順。タイムスライダーの範囲も含む)、
``"first"``・``"last"`` は選んだノードの各カーブの最初・最後のキー(範囲を選んでいればその中の最初・最後)、
``"all"`` は全キー(範囲を選んでいればその中の全キー)。
"""

import math

import maya.cmds as cmds

from mlib.decorator import undoChunk

from . import keys

#: Mayaの接線型。
MAYA_TYPES = ("auto", "spline", "linear", "flat", "step", "clamped", "plateau")

#: 計算して決める接線。
COMPUTED_TYPES = ("flow", "bounce")

#: 対象のキーの選び方。
SCOPES = ("selected", "first", "last", "all")


@undoChunk("animBarSetTangent")
def setTangent(kind, side="both", scope="selected"):
    """選んだキー(無ければ現在時刻のキー)の接線を設定する。

    Args:
        kind (str): :data:`MAYA_TYPES` または :data:`COMPUTED_TYPES` の名前。
        side (str): ``"both"``・``"in"``・``"out"``。stepは出力側だけに効く。
        scope (str): :data:`SCOPES` の名前(対象のキーの選び方)。

    Returns:
        int: 設定したキーの数。
    """
    if kind not in MAYA_TYPES + COMPUTED_TYPES:
        raise ValueError("Unknown tangent type: " + str(kind))
    if side not in ("both", "in", "out"):
        raise ValueError("side must be 'both', 'in' or 'out'")
    if scope not in SCOPES:
        raise ValueError("scope must be one of " + ", ".join(SCOPES))
    count = 0
    for target in _scoped_targets(scope):
        for index in target.indices:
            if kind in MAYA_TYPES:
                _set_type(target.curve, index, kind, side)
            else:
                _set_computed(target.curve, index, kind, side)
            count += 1
    return count


def _scoped_targets(scope):
    """scope に合わせて対象のカーブとキーを返す。

    Args:
        scope (str): :data:`SCOPES` の名前。

    Returns:
        list[Target]: 対象。
    """
    if scope == "selected":
        return keys.targets()
    span = keys.timelineRange()
    result = []
    for node in keys.selectedNodes():
        for plug in keys.animatedPlugs(node):
            curve = keys.animCurveOf(plug)
            indices = [index for index, time in enumerate(curve.getKeyInputs())
                       if span is None or span[0] - keys.TIME_EPSILON <= time <= span[1] + keys.TIME_EPSILON]
            if not indices:
                continue
            if scope == "first":
                indices = indices[:1]
            elif scope == "last":
                indices = indices[-1:]
            result.append(keys.Target(curve, indices, plug))
    return result


def flowAngle(curve, index):
    """前後のキーを結ぶ向きの接線の角度(度)を返す。両端のキーは0。

    Args:
        curve (AnimCurve): カーブ。
        index (int): キーの番号。

    Returns:
        float: 接線の角度(度)。Mayaの接線の角度と同じく、Graph Editor の目盛り(横軸は現在のUI時間単位のフレーム、
        縦軸はUI単位の値)で測る。
    """
    # 接線の角度は Graph Editor の目盛りで決まるため、UI単位の値を cmds.keyframe で読む(mlib の値は度・cm)。
    inputs = curve.getKeyInputs()
    values = cmds.keyframe(curve.getFullName(), query=True, valueChange=True) or []
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
