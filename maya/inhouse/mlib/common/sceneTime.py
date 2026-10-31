"""シーンの現在時刻と、再生範囲・アニメーション範囲を扱う。"""

import contextlib
import math

import maya.cmds as cmds

from ..core.attributeType import _from_seconds, _to_seconds
from ..util import _time_unit


class Time:
    """現在時刻と時間範囲の照会・変更をまとめた静的メソッドの集まり。インスタンスは作らない。

    時間の数値は既定で現在のUI時間単位のフレーム(``timeUnit="sec"`` で秒)。
    変更は Maya の ``currentTime``・``playbackOptions`` と同じ扱い(Undo も同じ)。fast引数は持たない。

    .. code-block:: python

        from mlib.common import Time

        start, end = Time.getPlaybackRange()
        with Time.preserved():
            for frame in range(int(start), int(end) + 1):
                Time.setCurrent(frame)
                ...  # 各フレームの値を読む
    """

    def __new__(cls, *args, **kwargs):
        """インスタンスを作らせない。

        Raises:
            TypeError: 常に送出する。
        """
        raise TypeError("Time only provides static methods; call Time.getCurrent() etc. directly")

    @staticmethod
    def getCurrent(*, timeUnit="frame"):
        """現在時刻を取得する。

        Args:
            timeUnit (str): 戻り値の単位。``"frame"`` (現在のUI時間単位)または ``"sec"``。

        Returns:
            float: 現在時刻。
        """
        return _from_ui(cmds.currentTime(query=True), _time_unit(timeUnit))

    @staticmethod
    def setCurrent(value, *, timeUnit="frame", update=True):
        """現在時刻を変える(``cmds.currentTime(value, update=update)`` 相当)。

        Args:
            value (float): 新しい時刻。
            timeUnit (str): valueの単位。``"frame"`` または ``"sec"``。
            update (bool): Trueは変えた時刻でシーンを評価し直す(既定。直後に値を読める)。

        Returns:
            float: 設定した時刻(timeUnitの単位)。

        Raises:
            TypeError: valueが数値でない、またはupdateがbool以外の場合。
            ValueError: valueが有限でない、またはtimeUnitが未対応の単位名の場合。
        """
        unit = _time_unit(timeUnit)
        if not isinstance(update, bool):
            raise TypeError("update must be a bool")
        cmds.currentTime(_to_ui(_finite_time(value, "value"), unit), update=update)
        return Time.getCurrent(timeUnit=unit)

    @staticmethod
    def getPlaybackRange(*, timeUnit="frame"):
        """再生範囲(タイムスライダーの開始・終了)を取得する。

        Args:
            timeUnit (str): 戻り値の単位。``"frame"`` または ``"sec"``。

        Returns:
            tuple[float, float]: (開始, 終了)。
        """
        return _get_range("minTime", "maxTime", _time_unit(timeUnit))

    @staticmethod
    def setPlaybackRange(start, end, *, timeUnit="frame"):
        """再生範囲(タイムスライダーの開始・終了)を変える。

        Args:
            start (float): 開始。
            end (float): 終了。start以上。
            timeUnit (str): start・endの単位。``"frame"`` または ``"sec"``。

        Returns:
            tuple[float, float]: 設定した (開始, 終了)。

        Raises:
            TypeError: start・endが数値でない場合。
            ValueError: 有限でない、startがendより大きい、またはtimeUnitが未対応の単位名の場合。
        """
        return _set_range("minTime", "maxTime", start, end, _time_unit(timeUnit))

    @staticmethod
    def getAnimationRange(*, timeUnit="frame"):
        """アニメーション範囲(レンジスライダーの両端)を取得する。

        Args:
            timeUnit (str): 戻り値の単位。``"frame"`` または ``"sec"``。

        Returns:
            tuple[float, float]: (開始, 終了)。
        """
        return _get_range("animationStartTime", "animationEndTime", _time_unit(timeUnit))

    @staticmethod
    def setAnimationRange(start, end, *, timeUnit="frame"):
        """アニメーション範囲(レンジスライダーの両端)を変える。

        Args:
            start (float): 開始。
            end (float): 終了。start以上。
            timeUnit (str): start・endの単位。``"frame"`` または ``"sec"``。

        Returns:
            tuple[float, float]: 設定した (開始, 終了)。

        Raises:
            TypeError: start・endが数値でない場合。
            ValueError: 有限でない、startがendより大きい、またはtimeUnitが未対応の単位名の場合。
        """
        return _set_range("animationStartTime", "animationEndTime", start, end, _time_unit(timeUnit))

    @staticmethod
    @contextlib.contextmanager
    def preserved():
        """``with`` の間は時刻を変えてよく、抜けると(例外でも)元の時刻へ戻すコンテキスト。

        Yields:
            float: 入る前の時刻(現在のUI時間単位のフレーム)。
        """
        original = cmds.currentTime(query=True)
        try:
            yield original
        finally:
            cmds.currentTime(original, update=True)


def _finite_time(value, name):
    """時刻の数値を検証する。

    Args:
        value (float): 時刻。boolは受け付けない。
        name (str): 例外メッセージに使う引数名。

    Returns:
        float: 検証した値。

    Raises:
        TypeError: 数値でない場合。
        ValueError: 有限でない場合。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _to_ui(value, unit):
    """指定単位の時刻をUI時間単位のフレームへ変換する。

    Args:
        value (float): 時刻。
        unit (str): valueの単位(``"frame"`` / ``"sec"``)。

    Returns:
        float: UI時間単位のフレーム。
    """
    return value if unit == "frame" else _from_seconds(value, "frame")


def _from_ui(value, unit):
    """UI時間単位のフレームを指定単位へ変換する。

    Args:
        value (float): UI時間単位のフレーム。
        unit (str): 戻り値の単位(``"frame"`` / ``"sec"``)。

    Returns:
        float: 指定単位の時刻。
    """
    return float(value) if unit == "frame" else _to_seconds(value, "frame")


def _get_range(start_flag, end_flag, unit):
    """playbackOptions の範囲を取得する。

    Args:
        start_flag (str): 開始のフラグ名。
        end_flag (str): 終了のフラグ名。
        unit (str): 戻り値の単位。

    Returns:
        tuple[float, float]: (開始, 終了)。
    """
    return (_from_ui(cmds.playbackOptions(query=True, **{start_flag: True}), unit),
            _from_ui(cmds.playbackOptions(query=True, **{end_flag: True}), unit))


def _set_range(start_flag, end_flag, start, end, unit):
    """playbackOptions の範囲を設定する。

    Args:
        start_flag (str): 開始のフラグ名。
        end_flag (str): 終了のフラグ名。
        start (float): 開始。
        end (float): 終了。
        unit (str): start・endの単位。

    Returns:
        tuple[float, float]: 設定後の (開始, 終了)。

    Raises:
        TypeError: start・endが数値でない場合。
        ValueError: 有限でない、またはstartがendより大きい場合。
    """
    start, end = _finite_time(start, "start"), _finite_time(end, "end")
    if start > end:
        raise ValueError(f"start must not be greater than end: {start} > {end}")
    cmds.playbackOptions(**{start_flag: _to_ui(start, unit), end_flag: _to_ui(end, unit)})
    return _get_range(start_flag, end_flag, unit)
