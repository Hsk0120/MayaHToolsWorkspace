# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""シーン設定を書き換えずに距離・角度・時間を変換する。"""

import maya.api.OpenMaya as om2
from ..util import _angle_unit


def distanceToUi(centimeters: float) -> float:
    """cm距離を現在のUI距離単位の数値へ変換する。

    Args:
        centimeters (float): cm単位の距離。

    Returns:
        float: 現在のUI距離単位で表した値。
    """
    ...

def _distance_unit(unit: str | None) -> int:
    """距離単位名をOpenMayaの単位へ解決する。

    Args:
        unit (str | None): Mayaの長名・短名。Noneは現在のUI単位。

    Returns:
        int: MDistanceの単位定数。

    Raises:
        TypeError: 文字列またはNoneでない場合。
        ValueError: 未対応の単位名の場合。
    """
    ...

def convertDistance(value: float, fromUnit: str | None = ..., toUnit: str | None = ...) -> float:
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
    ...

def distanceFromUi(value: float) -> float:
    """現在のUI距離単位の数値をcmへ変換する。

    Args:
        value (float): 現在のUI距離単位で表した値。

    Returns:
        float: cm単位の距離。
    """
    ...

def _angle_constant(unit: str) -> int:
    """角度の単位名をMAngleの単位定数へ解決する。

    Args:
        unit (str): ``"deg"`` / ``"rad"`` と ``"degree"`` 等の別名。

    Returns:
        int: MAngleの単位定数。

    Raises:
        TypeError: unitが文字列以外の場合。
        ValueError: 未対応の単位名の場合。
    """
    ...

def angleToUi(value: float, *, unit: str = ...) -> float:
    """角度を現在のUI角度単位の数値へ変換する。

    Args:
        value (float): unitの単位の角度。
        unit (str): valueの単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
            (``"degree"`` / ``"radians"`` 等の別名も可)。

    Returns:
        float: 現在のUI角度単位で表した値。

    Raises:
        TypeError: unitが文字列以外の場合。
        ValueError: unitが未対応の単位名の場合。
    """
    ...

def angleFromUi(value: float, *, unit: str = ...) -> float:
    """現在のUI角度単位の数値を、指定単位の角度へ変換する。

    Args:
        value (float): 現在のUI角度単位で表した値。
        unit (str): 戻り値の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
            (``"degree"`` / ``"radians"`` 等の別名も可)。

    Returns:
        float: unitの単位の角度。

    Raises:
        TypeError: unitが文字列以外の場合。
        ValueError: unitが未対応の単位名の場合。
    """
    ...

def secondsPerFrame() -> float:
    """現在の時間単位の1フレームの秒数を取得する。

    Returns:
        float: 1フレームの秒数。
    """
    ...
