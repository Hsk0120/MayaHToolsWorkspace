"""シーンの距離・角度・時間の UI 単位を扱う。"""

from .decorators.undo import undo_chunk

from contextlib import contextmanager

import maya.api.OpenMaya as om2
import maya.cmds as cmds


class Units:
    """Maya の現在の UI 単位(距離・角度・時間)を参照・変更する。

    取得・設定とも ``cmds.currentUnit`` の文字列表現(例: ``"cm"``、``"deg"``、
    ``"film"``)を使う。距離・角度は ``om2.MDistance``/``om2.MAngle`` の
    ``uiUnit()`` でも取得できるが、設定側は Undo 対応のため cmds を使う必要が
    あり、読み書きの表現を統一するため取得側も cmds に揃えている。
    """

    @staticmethod
    def linear():
        """現在の距離 UI 単位を取得する。

        Returns:
            str: 距離単位名(例: ``"cm"``、``"m"``)。
        """
        return cmds.currentUnit(query=True, linear=True)

    @staticmethod
    @undo_chunk("hlib.units.set_linear")
    def set_linear(unit):
        """距離 UI 単位を変更する。

        Args:
            unit (str): ``cmds.currentUnit`` が受け付ける距離単位名
                (例: ``"mm"``、``"cm"``、``"m"``、``"in"``、``"ft"``)。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: Maya が未対応の単位名を拒否した場合。
        """
        cmds.currentUnit(linear=unit)

    @staticmethod
    def angle():
        """現在の角度 UI 単位を取得する。

        Returns:
            str: ``"deg"`` または ``"rad"``。
        """
        return cmds.currentUnit(query=True, angle=True)

    @staticmethod
    @undo_chunk("hlib.units.set_angle")
    def set_angle(unit):
        """角度 UI 単位を変更する。

        Args:
            unit (str): ``"deg"`` または ``"rad"``。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: Maya が未対応の単位名を拒否した場合。
        """
        cmds.currentUnit(angle=unit)

    @staticmethod
    def time():
        """現在の時間 UI 単位を取得する。

        Returns:
            str: 時間単位名(例: ``"film"``、``"ntsc"``、``"pal"``、``"game"``)。
        """
        return cmds.currentUnit(query=True, time=True)

    @staticmethod
    @undo_chunk("hlib.units.set_time")
    def set_time(unit):
        """時間 UI 単位を変更する。

        Args:
            unit (str): ``cmds.currentUnit`` が受け付ける時間単位名
                (例: ``"film"``、``"ntsc"``、``"24fps"``)。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: Maya が未対応の単位名を拒否した場合。
        """
        cmds.currentUnit(time=unit)


@contextmanager
def native_units():
    """ブロック内だけ内部単位(距離=cm、角度=radian)を強制する。

    行列やベクトルの演算など、シーンの表示単位に依存しない計算をしたい場合に
    使う。ブロックを抜ける際(例外時を含む)に開始時点の UI 単位へ復元する。
    ``om2.MDistance``/``om2.MAngle`` の ``setUIUnit`` を直接呼ぶため MEL の
    往復が無く、時間単位には影響しない。表示単位の変更はシーンデータ自体を
    変更しないため、この切り替え自体は Maya の Undo キューに乗らない
    （計算中の単位変換用の一時状態であり、操作そのもののロールバックは行わない）。

    Yields:
        None: ブロック内では距離=センチメートル、角度=ラジアンとして扱ってよい。
    """
    previous_linear = om2.MDistance.uiUnit()
    previous_angle = om2.MAngle.uiUnit()
    try:
        om2.MDistance.setUIUnit(om2.MDistance.kCentimeters)
        om2.MAngle.setUIUnit(om2.MAngle.kRadians)
        yield
    finally:
        om2.MDistance.setUIUnit(previous_linear)
        om2.MAngle.setUIUnit(previous_angle)
