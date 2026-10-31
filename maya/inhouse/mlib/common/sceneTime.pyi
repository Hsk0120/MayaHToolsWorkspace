# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""シーンの現在時刻と、再生範囲・アニメーション範囲を扱う。"""

import contextlib
import math
import maya.cmds as cmds
from ..core.attributeType import _from_seconds, _to_seconds
from ..util import _time_unit
from typing import Any, Iterator
from mlib._stubtypes import GeneratorContextManager
from typing_extensions import Self



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
    def __new__(cls, *args, **kwargs) -> Self:
        """インスタンスを作らせない。

        Raises:
            TypeError: 常に送出する。
        """
        ...
    @staticmethod
    def getCurrent(*, timeUnit: str = ...) -> float:
        """現在時刻を取得する。

        Args:
            timeUnit (str): 戻り値の単位。``"frame"`` (現在のUI時間単位)または ``"sec"``。

        Returns:
            float: 現在時刻。
        """
        ...
    @staticmethod
    def setCurrent(value: float, *, timeUnit: str = ..., update: bool = ...) -> float:
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
        ...
    @staticmethod
    def getPlaybackRange(*, timeUnit: str = ...) -> tuple[float, float]:
        """再生範囲(タイムスライダーの開始・終了)を取得する。

        Args:
            timeUnit (str): 戻り値の単位。``"frame"`` または ``"sec"``。

        Returns:
            tuple[float, float]: (開始, 終了)。
        """
        ...
    @staticmethod
    def setPlaybackRange(start: float, end: float, *, timeUnit: str = ...) -> tuple[float, float]:
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
        ...
    @staticmethod
    def getAnimationRange(*, timeUnit: str = ...) -> tuple[float, float]:
        """アニメーション範囲(レンジスライダーの両端)を取得する。

        Args:
            timeUnit (str): 戻り値の単位。``"frame"`` または ``"sec"``。

        Returns:
            tuple[float, float]: (開始, 終了)。
        """
        ...
    @staticmethod
    def setAnimationRange(start: float, end: float, *, timeUnit: str = ...) -> tuple[float, float]:
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
        ...
    @staticmethod
    def preserved() -> GeneratorContextManager[float]:
        """``with`` の間は時刻を変えてよく、抜けると(例外でも)元の時刻へ戻すコンテキスト。

        Yields:
            float: 入る前の時刻(現在のUI時間単位のフレーム)。
        """
        ...

def _finite_time(value: float, name: str) -> float:
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
    ...

def _to_ui(value: float, unit: str) -> float:
    """指定単位の時刻をUI時間単位のフレームへ変換する。

    Args:
        value (float): 時刻。
        unit (str): valueの単位(``"frame"`` / ``"sec"``)。

    Returns:
        float: UI時間単位のフレーム。
    """
    ...

def _from_ui(value: float, unit: str) -> float:
    """UI時間単位のフレームを指定単位へ変換する。

    Args:
        value (float): UI時間単位のフレーム。
        unit (str): 戻り値の単位(``"frame"`` / ``"sec"``)。

    Returns:
        float: 指定単位の時刻。
    """
    ...

def _get_range(start_flag: str, end_flag: str, unit: str) -> tuple[float, float]:
    """playbackOptions の範囲を取得する。

    Args:
        start_flag (str): 開始のフラグ名。
        end_flag (str): 終了のフラグ名。
        unit (str): 戻り値の単位。

    Returns:
        tuple[float, float]: (開始, 終了)。
    """
    ...

def _set_range(start_flag: str, end_flag: str, start: float, end: float, unit: str) -> tuple[float, float]:
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
    ...
