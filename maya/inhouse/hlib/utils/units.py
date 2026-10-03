"""シーン設定を書き換えずに距離・角度・時間を変換する。"""
import maya.api.OpenMaya as om2


def distanceToUi(centimeters):
    """内部距離を現在の表示単位へ変換する。

    Args:
        centimeters (float): cm単位の値。

    Returns:
        float: 現在の距離単位。
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
        raise ValueError("Unsupported distance unit: " + unit)
    return names[unit]


def convertDistance(value, from_unit=None, to_unit=None):
    """シーン設定を変更せず距離を変換する。

    Args:
        value (float): 変換する距離。
        from_unit (str | None): 入力単位。Noneは現在のシーン単位。
        to_unit (str | None): 出力単位。Noneは現在のシーン単位。
            mm/cm/m/km/in/ft/yd/mi、またはMayaの長名を指定する。
    Returns:
        float: 出力単位での距離。
    Raises:
        TypeError: 単位の型が不正な場合。
        ValueError: 単位名が未対応の場合。
    """
    source = _distance_unit(from_unit)
    target = _distance_unit(to_unit)
    return om2.MDistance(value, source).asUnits(target)


def distanceFromUi(value):
    """現在の表示距離を内部単位へ変換する。

    Args:
        value (float): 現在の距離単位。

    Returns:
        float: cm単位の値。
    """
    return om2.MDistance(value, om2.MDistance.uiUnit()).asCentimeters()


def angleToUi(radians):
    """内部角度を現在の表示単位へ変換する。

    Args:
        radians (float): rad単位の値。

    Returns:
        float: 現在の角度単位。
    """
    return om2.MAngle(radians).asUnits(om2.MAngle.uiUnit())


def angleFromUi(value):
    """現在の表示角度を内部単位へ変換する。

    Args:
        value (float): 現在の角度単位。

    Returns:
        float: rad単位の値。
    """
    return om2.MAngle(value, om2.MAngle.uiUnit()).asRadians()


def secondsPerFrame():
    """現在の時間単位の1フレームの秒数を取得する。

    Returns:
        float: 1フレームの秒数。
    """
    return om2.MTime(1, om2.MTime.uiUnit()).asUnits(om2.MTime.kSeconds)


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ('angle_from_ui', 'angle_to_ui', 'convert_distance', 'distance_from_ui', 'distance_to_ui', 'seconds_per_frame'):
    globals().pop(_obsolete_name, None)
