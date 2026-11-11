"""シーン設定を書き換えずに距離・角度・時間を変換する。"""

import re

import maya.api.OpenMaya as om2

from ..util import _angle_unit, _time_unit


def distanceToUi(centimeters):
    """cm距離を現在のUI距離単位の数値へ変換する。

    Args:
        centimeters (float): cm単位の距離。

    Returns:
        float: 現在のUI距離単位で表した値。
    """
    return om2.MDistance(centimeters).asUnits(om2.MDistance.uiUnit())


def _distance_unit(unit):
    """距離単位名をOpenMayaの単位へ解決する。

    Args:
        unit (str | None): Mayaの長名・短名。Noneは現在のUI単位。

    Returns:
        int: MDistanceの単位定数。

    Raises:
        TypeError: 文字列またはNoneでない場合。
        ValueError: 未対応の単位名の場合。
    """
    if unit is None:
        return om2.MDistance.uiUnit()
    if not isinstance(unit, str):
        raise TypeError("unit must be a string or None")
    names = {
        "mm": om2.MDistance.kMillimeters, "millimeter": om2.MDistance.kMillimeters,
        "cm": om2.MDistance.kCentimeters, "centimeter": om2.MDistance.kCentimeters,
        "m": om2.MDistance.kMeters, "meter": om2.MDistance.kMeters,
        "km": om2.MDistance.kKilometers, "kilometer": om2.MDistance.kKilometers,
        "in": om2.MDistance.kInches, "inch": om2.MDistance.kInches,
        "ft": om2.MDistance.kFeet, "foot": om2.MDistance.kFeet,
        "yd": om2.MDistance.kYards, "yard": om2.MDistance.kYards,
        "mi": om2.MDistance.kMiles, "mile": om2.MDistance.kMiles,
    }
    if unit not in names:
        raise ValueError(f"Unsupported distance unit: {unit}")
    return names[unit]


def convertDistance(value, fromUnit=None, toUnit=None):
    """シーン設定を変更せず距離を変換する。

    Args:
        value (float): 変換する距離。
        fromUnit (str | None): 入力単位。Noneは現在のシーン単位。
        toUnit (str | None): 出力単位。Noneは現在のシーン単位。
            mm/cm/m/km/in/ft/yd/mi、またはMayaの長名を指定する。

    Returns:
        float: 出力単位での距離。

    Raises:
        TypeError: 単位の型が不正な場合。
        ValueError: 単位名が未対応の場合。
    """
    source = _distance_unit(fromUnit)
    target = _distance_unit(toUnit)
    return om2.MDistance(value, source).asUnits(target)


def distanceFromUi(value):
    """現在のUI距離単位の数値をcmへ変換する。

    Args:
        value (float): 現在のUI距離単位で表した値。

    Returns:
        float: cm単位の距離。
    """
    return om2.MDistance(value, om2.MDistance.uiUnit()).asCentimeters()


def _angle_constant(unit):
    """角度の単位名をMAngleの単位定数へ解決する。

    Args:
        unit (str): ``"deg"`` / ``"rad"`` と ``"degree"`` 等の別名。

    Returns:
        int: MAngleの単位定数。

    Raises:
        TypeError: unitが文字列・None以外の場合。
        ValueError: 未対応の単位名の場合。
    """
    return om2.MAngle.kDegrees if _angle_unit(unit) == "deg" else om2.MAngle.kRadians


def angleToUi(value, *, unit="deg"):
    """角度を現在のUI角度単位の数値へ変換する。

    Args:
        value (float): unitの単位の角度。
        unit (str): valueの単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
            (``"degree"`` / ``"radians"`` 等の別名も可)。

    Returns:
        float: 現在のUI角度単位で表した値。

    Raises:
        TypeError: unitが文字列・None以外の場合。
        ValueError: unitが未対応の単位名の場合。
    """
    return om2.MAngle(value, _angle_constant(unit)).asUnits(om2.MAngle.uiUnit())


def angleFromUi(value, *, unit="deg"):
    """現在のUI角度単位の数値を、指定単位の角度へ変換する。

    Args:
        value (float): 現在のUI角度単位で表した値。
        unit (str): 戻り値の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
            (``"degree"`` / ``"radians"`` 等の別名も可)。

    Returns:
        float: unitの単位の角度。

    Raises:
        TypeError: unitが文字列・None以外の場合。
        ValueError: unitが未対応の単位名の場合。
    """
    return om2.MAngle(value, om2.MAngle.uiUnit()).asUnits(_angle_constant(unit))


def convertAngle(value, fromUnit="deg", toUnit="rad"):
    """シーン設定を変更せず角度を変換する。

    Args:
        value (float): 変換する角度。
        fromUnit (str | None): 入力単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
            (``"degree"`` / ``"radians"`` 等の別名も可)。Noneは現在のUI角度単位。
        toUnit (str | None): 出力単位。既定 ``"rad"``。指定の仕方はfromUnitと同じ。

    Returns:
        float: 出力単位での角度。

    Raises:
        TypeError: 単位が文字列・None以外の場合。
        ValueError: 単位名が未対応の場合。
    """
    source = om2.MAngle.uiUnit() if fromUnit is None else _angle_constant(fromUnit)
    target = om2.MAngle.uiUnit() if toUnit is None else _angle_constant(toUnit)
    return om2.MAngle(value, source).asUnits(target)


def _time_constant(unit):
    """時間の単位名をMTimeの単位定数へ解決する。

    Args:
        unit (str | None): ``"frame"`` (現在のUI時間単位)・``"sec"`` とその別名、
            Mayaの ``currentUnit -time`` の名前(``"film"``・``"ntsc"``・``"24fps"``・``"29.97df"`` 等)。
            Noneは現在のUI時間単位。

    Returns:
        int: MTimeの単位定数。

    Raises:
        TypeError: 文字列またはNoneでない場合。
        ValueError: 未対応の単位名の場合。
    """
    if unit is None:
        return om2.MTime.uiUnit()
    if not isinstance(unit, str):
        raise TypeError("unit must be a string or None")
    names = {
        "hour": om2.MTime.kHours, "min": om2.MTime.kMinutes, "millisec": om2.MTime.kMilliseconds,
        "game": om2.MTime.kGames, "film": om2.MTime.kFilm, "pal": om2.MTime.kPALFrame,
        "ntsc": om2.MTime.kNTSCFrame, "show": om2.MTime.kShowScan, "palf": om2.MTime.kPALField,
        "ntscf": om2.MTime.kNTSCField,
    }
    if unit in names:
        return names[unit]
    match = re.match(r"^(\d+(?:\.\d+)?)(fps|df)$", unit)
    if match:
        constant = getattr(om2.MTime, "k{}{}".format(match.group(1).replace(".", "_"), match.group(2).upper()), None)
        if constant is not None:
            return constant
    try:
        normalized = _time_unit(unit)
    except ValueError:
        raise ValueError(f"Unsupported time unit: {unit}") from None
    return om2.MTime.uiUnit() if normalized == "frame" else om2.MTime.kSeconds


def convertTime(value, fromUnit=None, toUnit=None):
    """シーン設定を変更せず時間を変換する。

    Args:
        value (float): 変換する時間。
        fromUnit (str | None): 入力単位。Noneと ``"frame"`` は現在のUI時間単位のフレーム、``"sec"`` は秒
            (``"frames"`` / ``"seconds"`` 等の別名も可)。Mayaの時間単位の名前(``"film"``・``"ntsc"``・
            ``"pal"``・``"game"``・``"hour"``・``"min"``・``"millisec"``・``"24fps"``・``"29.97df"`` 等)も指定できる。
        toUnit (str | None): 出力単位。指定の仕方はfromUnitと同じ。

    Returns:
        float: 出力単位での時間。

    Raises:
        TypeError: 単位の型が不正な場合。
        ValueError: 単位名が未対応の場合。
    """
    source = _time_constant(fromUnit)
    target = _time_constant(toUnit)
    return om2.MTime(value, source).asUnits(target)


def secondsPerFrame():
    """現在の時間単位の1フレームの秒数を取得する。

    Returns:
        float: 1フレームの秒数。
    """
    return om2.MTime(1, om2.MTime.uiUnit()).asUnits(om2.MTime.kSeconds)


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ("angle_from_ui", "angle_to_ui", "convert_distance", "distance_from_ui", "distance_to_ui", "seconds_per_frame"):
    globals().pop(_obsolete_name, None)
