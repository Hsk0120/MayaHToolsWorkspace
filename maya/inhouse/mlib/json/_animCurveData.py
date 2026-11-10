"""アニメカーブ1本の内容を辞書へ読み出し、同じ内容のカーブを書き戻す(mlib.jsonの内部補助)。

:class:`~mlib.json.animationSnapshot.AnimationSnapshot` と
:class:`~mlib.json.drivenKeysSnapshot.DrivenKeysSnapshot` が共有する。カーブの辞書は次の形::

    {"curveType": "animCurveTL", "weighted": False, "preInfinity": "constant", "postInfinity": "constant",
     "keys": [{"input": 1.0, "value": 2.5, "inType": "auto", "outType": "auto",
               "inAngle": 0.0, "inWeight": 1.0, "outAngle": 0.0, "outWeight": 1.0,
               "lock": True, "weightLock": True, "breakdown": False}, ...]}

単位はmlibの既定に合わせ、UI単位に左右されない。

- ``input``: 時間入力(animCurveT*)は保存時のUI時間単位のフレーム。単位なし入力(animCurveU*)は
  呼び出し側が決める単位(ドリブンキーではドライバーのmlib単位)。
- ``value``: 角度出力は度、距離はcm、時間出力はフレーム、その他は無次元。
- 接線の角度・ウェイトは、横軸を ``input`` の単位、縦軸を ``value`` の単位とした平面での向き(度)と、
  Mayaと同じ長さの1/3(ウェイト付き接線のカーブではGraph Editorの表示と同じ値)。単位なし入力・
  ウェイトなしのカーブでは、ウェイトはMayaの表示(1.0)と一致しない場合があるが、往復では同じ形になる。

固定(fixed)以外の接線の角度・ウェイトは記録するが、書き戻しではMayaが接線の型から計算し直す。
"""

import math

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

from ..core.attributeType import _convert_units, _from_seconds, _to_seconds
from ..nodes.animCurve import _TANGENT_NAMES, _TANGENT_TYPES, AnimCurve

#: 外挿方法の名前(AnimCurve.getInfinity・setInfinityと同じ)。
_INFINITY_TYPES = ("constant", "linear", "cycle", "cycleRelative", "oscillate")
#: キーの辞書が持つ項目と、受け付ける値の型。
_KEY_FIELDS = {
    "input": (int, float), "value": (int, float),
    "inType": (str,), "outType": (str,),
    "inAngle": (int, float), "inWeight": (int, float), "outAngle": (int, float), "outWeight": (int, float),
    "lock": (bool,), "weightLock": (bool,), "breakdown": (bool,),
}
#: 入力接線に指定できない型(Mayaのコマンドが拒否する)。
_OUT_ONLY_TANGENTS = ("step", "stepnext")
#: 時刻が同じとみなす差(フレームまたは単位なし入力)。
_TIME_TOLERANCE = 1e-6


def _is_time_input(curve_type):
    """カーブ型の入力が時間かを返す。

    Args:
        curve_type (str): ``"animCurveTL"`` 等。

    Returns:
        bool: animCurveT*ならTrue。
    """
    return curve_type[9:10] == "T"


def _output_kind(curve_type):
    """カーブ型の出力の種類を返す。

    Args:
        curve_type (str): ``"animCurveTL"`` 等。

    Returns:
        str: ``"A"`` (角度)・``"L"`` (距離)・``"T"`` (時間)・``"U"`` (無次元)。
    """
    return curve_type[-1]


def _check_curve(data):
    """カーブの辞書の形を確かめる。

    Args:
        data (object): :func:`_read_curve` の形の辞書。

    Raises:
        ValueError: 形・型・値が違う場合。
    """
    if not isinstance(data, dict):
        raise ValueError(f"Invalid curve data: {data!r}")
    curve_type = data.get("curveType")
    if not isinstance(curve_type, str) or not curve_type.startswith("animCurve") or len(curve_type) != 11 \
            or curve_type[9] not in "TU" or curve_type[10] not in "ALTU":
        raise ValueError(f"Invalid curveType in curve data: {curve_type!r}")
    if not isinstance(data.get("weighted"), bool):
        raise ValueError("Curve data 'weighted' must be a bool")
    for side in ("preInfinity", "postInfinity"):
        if data.get(side) not in _INFINITY_TYPES:
            raise ValueError(f"Invalid {side} in curve data: {data.get(side)!r}")
    keys = data.get("keys")
    if not isinstance(keys, list):
        raise ValueError("Curve data must have a 'keys' list")
    for key in keys:
        if not isinstance(key, dict) or set(key) != set(_KEY_FIELDS):
            raise ValueError(f"Invalid key in curve data: {key!r}")
        for name, kinds in _KEY_FIELDS.items():
            value = key[name]
            if not isinstance(value, kinds) or (bool not in kinds and isinstance(value, bool)):
                raise ValueError(f"Invalid {name} in curve key: {value!r}")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"Curve key {name} must be finite: {value!r}")
        for name in ("inType", "outType"):
            if key[name] and key[name] not in _TANGENT_TYPES:
                raise ValueError(f"Unknown tangent type in curve key: {key[name]!r}")
        if key["inWeight"] < 0 or key["outWeight"] < 0:
            raise ValueError("Curve key weights must not be negative")


def _read_curve(curve, input_scale=1.0, input_range=None):
    """カーブの全キー(または範囲内のキー)と設定を辞書へ読み出す。

    Args:
        curve (str): animCurveノードの名前。
        input_scale (float): 単位なし入力のカーブで、Mayaの入力値に掛けて ``input`` にする倍率。
            時間入力では使わない。
        input_range (tuple[float, float] | None): ``input`` の単位で両端を含む範囲。Noneは全キー。

    Returns:
        dict: モジュールの説明の形の新しい辞書。
    """
    node = AnimCurve(curve)
    curve_type = node.getType()
    time_input = _is_time_input(curve_type)
    kind = _output_kind(curve_type)
    fn = oma2.MFnAnimCurve(node.mnode())
    scale = 1.0 if time_input else input_scale
    inputs = [value * scale for value in node.getKeyInputs()]
    values = node.getKeyValues()
    infinity = node.getInfinity()
    keys = []
    for index, (position, value) in enumerate(zip(inputs, values)):
        if input_range is not None and not (input_range[0] - _TIME_TOLERANCE <= position
                                            <= input_range[1] + _TIME_TOLERANCE):
            continue
        key = {"input": position, "value": value,
               "inType": _TANGENT_NAMES.get(fn.inTangentType(index), ""),
               "outType": _TANGENT_NAMES.get(fn.outTangentType(index), ""),
               "lock": bool(fn.tangentsLocked(index)), "weightLock": bool(fn.weightsLocked(index)),
               "breakdown": bool(fn.isBreakdown(index))}
        for side, incoming in (("in", True), ("out", False)):
            x, y = fn.getTangentXY(index, incoming)
            x = _from_seconds(x, "frame") if time_input else x * scale
            angle, weight = _angle_weight(x, _from_internal(kind, y))
            key[side + "Angle"], key[side + "Weight"] = angle, weight
        keys.append(key)
    return {"curveType": curve_type, "weighted": bool(fn.isWeighted),
            "preInfinity": infinity["pre"], "postInfinity": infinity["post"], "keys": keys}


def _transform_keys(keys, scale=1.0, offset=0.0, value_scale=1.0):
    """キーの入力を ``input * scale + offset`` へ動かし、接線も同じ倍率で伸ばした新しいlistを返す。

    Args:
        keys (list[dict]): キーの辞書の並び。変更しない。
        scale (float): 入力の倍率(fpsの換算)。
        offset (float): 入力へ足す量。
        value_scale (float): 値の倍率(時間出力のカーブのfps換算)。

    Returns:
        list[dict]: 新しいキーの辞書の並び。
    """
    result = []
    for key in keys:
        key = dict(key)
        key["input"] = key["input"] * scale + offset
        key["value"] = key["value"] * value_scale
        if scale != 1.0 or value_scale != 1.0:
            for side in ("in", "out"):
                x, y = _tangent_xy(key[side + "Angle"], key[side + "Weight"])
                key[side + "Angle"], key[side + "Weight"] = _angle_weight(x * scale, y * value_scale)
        result.append(key)
    return result


def _merge_keys(existing, incoming, mode, input_range=None):
    """既存のキーと読み込んだキーを、適用の方法に従って1つの並びにする。

    Args:
        existing (list[dict]): カーブにあるキー。
        incoming (list[dict]): 読み込んだキー(移動済み)。
        mode (str): ``"replace"``・``"insert"``・``"merge"``。
        input_range (tuple[float, float] | None): insertで置き換える範囲。Noneは読み込んだキーの範囲。

    Returns:
        list[dict]: 入力の昇順の並び。同じ時刻では読み込んだキーを使う。
    """
    if mode == "replace" or not existing:
        kept = []
    elif mode == "insert":
        if input_range is None:
            inputs = [key["input"] for key in incoming]
            input_range = (min(inputs), max(inputs)) if inputs else None
        kept = existing if input_range is None else [
            key for key in existing
            if not input_range[0] - _TIME_TOLERANCE <= key["input"] <= input_range[1] + _TIME_TOLERANCE]
    else:
        kept = [key for key in existing
                if not any(abs(key["input"] - other["input"]) <= _TIME_TOLERANCE for other in incoming)]
    return sorted(kept + list(incoming), key=lambda key: key["input"])


def _write_curve(curve, data, keys, input_scale=1.0, fast=False):
    """カーブの全キーを消し、指定したキーと設定で書き直す。

    通常はcmds(setKeyframe・keyTangent)で書くので、呼び出し側のUndoにまとまる。fastはOpenMayaで書く
    (時間出力のカーブはfastでもcmdsで書く)。

    Args:
        curve (str): animCurveノードの名前。
        data (dict): ``weighted``・``preInfinity``・``postInfinity`` を持つカーブの辞書。
        keys (list[dict]): 書くキー(入力の昇順)。
        input_scale (float): 単位なし入力で ``input`` をMayaの入力値へ戻すときに割る倍率。
        fast (bool): TrueはOpenMayaで書く。
    """
    node = AnimCurve(curve)
    curve_type = node.getType()
    time_input = _is_time_input(curve_type)
    kind = _output_kind(curve_type)
    scale = 1.0 if time_input else input_scale
    entries = []
    for key in keys:
        raw = {"key": key, "value": _to_internal(kind, key["value"]),
               "input": key["input"] if time_input else key["input"] / scale}
        for side in ("in", "out"):
            x, y = _tangent_xy(key[side + "Angle"], key[side + "Weight"])
            raw[side] = (_to_seconds(x, "frame") if time_input else x / scale, _to_internal(kind, y))
        entries.append(raw)
    if fast and kind != "T":
        _write_fast(node, time_input, data["weighted"], entries)
    else:
        _write_cmds(node, time_input, data["weighted"], entries)
    node.setInfinity(pre=data["preInfinity"], post=data["postInfinity"], fast=fast)
    if not fast:
        cmds.dgdirty(node.getFullName())


def _write_cmds(node, time_input, weighted, entries):
    """cmdsでキーを書き直す(Undo可能)。

    Args:
        node (AnimCurve): 書き込むカーブ。
        time_input (bool): 入力が時間か。
        weighted (bool): ウェイト付き接線にするか。
        entries (list[dict]): :func:`_write_curve` が内部単位へ直したキー。
    """
    name = node.getFullName()
    count = node.getKeyCount()
    if count:
        # 全キーを消すとMayaがカーブを削除するため、その間だけノードをロックする。
        locked = cmds.lockNode(name, query=True, lock=True)[0]
        if not locked:
            cmds.lockNode(name, lock=True)
        try:
            cmds.cutKey(name, index=(0, count - 1), clear=True, animation="objects")
        finally:
            if not locked:
                cmds.lockNode(name, lock=False)
    if not entries:
        return
    output = node.getPlug("output").mplug()
    position_flag = "time" if time_input else "float"
    for entry in entries:
        key = entry["key"]
        flags = {position_flag: entry["input"], "value": _convert_units(output, entry["value"]),
                 "breakdown": key["breakdown"]}
        if key["inType"] and key["inType"] != "fixed" and key["inType"] not in _OUT_ONLY_TANGENTS:
            flags["inTangentType"] = key["inType"]
        if key["outType"] and key["outType"] != "fixed":
            flags["outTangentType"] = key["outType"]
        cmds.setKeyframe(name, **flags)
    last = len(entries) - 1
    cmds.keyTangent(name, edit=True, weightedTangents=weighted)
    # ロックしたままでは片側の接線・ウェイトを書けないため、外してから書き、最後に戻す。
    # ウェイトなしのカーブはウェイトのロックを持たない(keyTangentが拒否する)。
    unlock = {"lock": False, "weightLock": False} if weighted else {"lock": False}
    cmds.keyTangent(name, edit=True, index=(0, last), animation="objects", **unlock)
    for index, entry in enumerate(entries):
        key = entry["key"]
        flags = {}
        if key["inType"] == "fixed":
            flags.update(ix=entry["in"][0], iy=entry["in"][1])
        if key["outType"] == "fixed":
            flags.update(ox=entry["out"][0], oy=entry["out"][1])
        if flags:
            cmds.keyTangent(name, edit=True, index=(index, index), animation="objects", **flags)
    for flag in ("lock", "weightLock") if weighted else ("lock",):
        ranges = _ranges(index for index, entry in enumerate(entries) if entry["key"][flag])
        # keyTangentのindexフラグは複数の範囲のlistを正しく受け付けないため、範囲ごとに呼ぶ。
        for item in ranges:
            cmds.keyTangent(name, edit=True, index=item, animation="objects", **{flag: True})


def _write_fast(node, time_input, weighted, entries):
    """OpenMayaでキーを書き直す(Undoなし)。

    Args:
        node (AnimCurve): 書き込むカーブ。時間出力でないもの。
        time_input (bool): 入力が時間か。
        weighted (bool): ウェイト付き接線にするか。
        entries (list[dict]): :func:`_write_curve` が内部単位へ直したキー。
    """
    fn = oma2.MFnAnimCurve(node.mnode())
    for index in range(fn.numKeys - 1, -1, -1):
        fn.remove(index)
    fn.setIsWeighted(weighted)
    if not entries:
        return
    auto = oma2.MFnAnimCurve.kTangentAuto
    if time_input:
        unit = om2.MTime.uiUnit()
        times = om2.MTimeArray([om2.MTime(entry["input"], unit) for entry in entries])
        fn.addKeys(times, [entry["value"] for entry in entries], auto, auto)
    else:
        for entry in entries:
            fn.addKey(entry["input"], entry["value"], auto, auto)
    fixed = oma2.MFnAnimCurve.kTangentFixed
    for index, entry in enumerate(entries):
        key = entry["key"]
        fn.setTangentsLocked(index, False)
        fn.setWeightsLocked(index, False)
        fn.setIsBreakdown(index, key["breakdown"])
        for side, incoming, setter in (("in", True, fn.setInTangentType), ("out", False, fn.setOutTangentType)):
            name = key[side + "Type"]
            if name == "fixed":
                setter(index, fixed)
                fn.setTangent(index, entry[side][0], entry[side][1], incoming, convertUnits=False)
            elif name and not (incoming and name in _OUT_ONLY_TANGENTS):
                setter(index, _TANGENT_TYPES[name])
    for index, entry in enumerate(entries):
        fn.setTangentsLocked(index, entry["key"]["lock"])
        fn.setWeightsLocked(index, entry["key"]["weightLock"])


def _ranges(indices):
    """番号の並びを、連続した ``(最初, 最後)`` の並びにする。

    Args:
        indices (Iterable[int]): 昇順の番号。

    Returns:
        list[tuple[int, int]]: keyTangentのindexフラグへ渡す範囲。
    """
    ranges = []
    for index in indices:
        if ranges and ranges[-1][1] + 1 == index:
            ranges[-1] = (ranges[-1][0], index)
        else:
            ranges.append((index, index))
    return ranges


def _angle_weight(x, y):
    """接線のベクトルを角度(度)とウェイトにする。

    Args:
        x (float): 横軸の成分。
        y (float): 縦軸の成分。

    Returns:
        tuple[float, float]: 角度(度)と、ベクトルの長さの1/3。
    """
    return math.degrees(math.atan2(y, x)), math.hypot(x, y) / 3.0


def _tangent_xy(angle, weight):
    """角度(度)とウェイトを接線のベクトルへ戻す。

    Args:
        angle (float): 角度(度)。
        weight (float): ウェイト。

    Returns:
        tuple[float, float]: 横軸・縦軸の成分。
    """
    radians = math.radians(angle)
    return 3.0 * weight * math.cos(radians), 3.0 * weight * math.sin(radians)


def _to_internal(kind, value):
    """mlibの単位の値を、Mayaの内部単位(rad・cm・秒)へ直す。

    Args:
        kind (str): :func:`_output_kind` の種類。
        value (float): 度・cm・フレーム・無次元の値。

    Returns:
        float: 内部単位の値。
    """
    if kind == "A":
        return math.radians(value)
    if kind == "T":
        return _to_seconds(value, "frame")
    return value


def _from_internal(kind, value):
    """Mayaの内部単位の値を、mlibの単位(度・cm・フレーム)へ直す。

    Args:
        kind (str): :func:`_output_kind` の種類。
        value (float): 内部単位の値。

    Returns:
        float: mlibの単位の値。
    """
    if kind == "A":
        return math.degrees(value)
    if kind == "T":
        return _from_seconds(value, "frame")
    return value
