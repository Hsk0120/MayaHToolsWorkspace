"""現在時刻・再生範囲・タイムスライダー選択を扱う。"""

from contextlib import contextmanager
import math

import maya.cmds as cmds
import maya.mel as mel

from ..decorators.undo import undo_chunk

class TimeSlider:
    """現在のタイムラインを参照する。時刻の単位はMayaの現在の時間単位。

    時刻と再生範囲はバッチでも使用可能。選択範囲の取得にはGUIが必要。
    """

    def __init__(self, control=None):
        """UI名を保持する。省略時はUI操作の都度メインスライダーを取得する。

        Args:
            control (str | None): timeControl名。生成だけではUIを作成/変更しない。
        """
        self._control = control

    def name(self):
        """str: 実在するtimeControl名。GUIがなければ RuntimeError。"""
        if cmds.about(batch=True):
            raise RuntimeError("Time slider selection requires Maya GUI")
        control = self._control or mel.eval(
            'global string $gPlayBackSlider; $hlibSlider = $gPlayBackSlider;')
        if not control or not cmds.timeControl(control, exists=True):
            raise RuntimeError(f"Time control is unavailable: {control}")
        return control

    @staticmethod
    def _time(value):
        """有限の数値時刻へ変換する。不正値は ValueError/TypeError。"""
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Time must be finite")
        return value

    def current_time(self):
        """float: 現在の時刻を返す。"""
        return float(cmds.currentTime(query=True))

    def set_current_time(self, value, update=True):
        """現在時刻を変更する。

        Args:
            value (float): Mayaの現在の時間単位での時刻。
            update (bool): 時刻変更に伴いシーンを更新するか。

        Returns:
            None: 値を返さない。
        """
        cmds.currentTime(self._time(value), edit=True, update=update)

    def playback_range(self):
        """tuple[float, float]: 再生の開始・終了時刻。両端を含む。"""
        return (float(cmds.playbackOptions(query=True, minTime=True)),
                float(cmds.playbackOptions(query=True, maxTime=True)))

    def animation_range(self):
        """tuple[float, float]: アニメーション全体の開始・終了時刻。両端を含む。"""
        return (float(cmds.playbackOptions(query=True, animationStartTime=True)),
                float(cmds.playbackOptions(query=True, animationEndTime=True)))

    def _set_range(self, start, end, start_flag, end_flag):
        """有限値かつ開始<=終了を検証して範囲を設定する。

        Maya 2022 の ``playbackOptions`` はUndo履歴を作らないため、その
        バージョンではこのメソッド(および ``set_playback_range``/
        ``set_animation_range``)による変更はUndo/Redoできない
        (Mayaネイティブの既知の制限で、hlibは独自プラグインでは補わない方針)。
        """
        start, end = self._time(start), self._time(end)
        if start > end:
            raise ValueError("Range start must not exceed end")
        if start_flag == "minTime":
            # 自動拡張されたanimation範囲は標準Undoで戻らないため明示的に記録する。
            animation_start, animation_end = self.animation_range()
            expanded = (min(animation_start, start), max(animation_end, end))
            if expanded != (animation_start, animation_end):
                cmds.playbackOptions(animationStartTime=expanded[0], animationEndTime=expanded[1])
        cmds.playbackOptions(**{start_flag: start, end_flag: end})

    @undo_chunk("hlibTimeSliderPlaybackRange")
    def set_playback_range(self, start, end):
        """再生範囲を設定する。

        Maya 2022 では ``playbackOptions`` 自体がUndo履歴を作らないため、
        このバージョンでの変更はUndo/Redoできない(Mayaネイティブの制限)。

        Args:
            start (float): 開始時刻（含む）。
            end (float): 終了時刻（含む）。開始より前なら ValueError。

        Returns:
            None: 値を返さない。
        """
        self._set_range(start, end, "minTime", "maxTime")

    @undo_chunk("hlibTimeSliderAnimationRange")
    def set_animation_range(self, start, end):
        """アニメーション全体の範囲を設定する。

        Maya 2022 では ``playbackOptions`` 自体がUndo履歴を作らないため、
        このバージョンでの変更はUndo/Redoできない(Mayaネイティブの制限)。

        Args:
            start (float): 開始時刻（含む）。
            end (float): 終了時刻（含む）。開始より前なら ValueError。

        Returns:
            None: 値を返さない。
        """
        self._set_range(start, end, "animationStartTime", "animationEndTime")

    def selected_range(self):
        """タイムスライダー上の選択範囲を取得する。

        Returns:
            tuple[float, float] | None: MayaのrangeArrayをそのまま返す。
            終端を含まない範囲（例: 1〜10フレームの選択は (1, 11)）。
            ハイライトがない場合は None。再生範囲とは終端の意味が異なる。
        """
        control = self.name()
        if not cmds.timeControl(control, query=True, rangeVisible=True):
            return None
        return tuple(float(x) for x in cmds.timeControl(control, query=True, rangeArray=True))

    def is_playing(self):
        """bool: 再生中か返す。"""
        return bool(cmds.play(query=True, state=True))

    def play(self, forward=True):
        """再生を開始する。

        Args:
            forward (bool): Trueで順再生、Falseで逆再生。

        Returns:
            None: 値を返さない。
        """
        cmds.play(forward=bool(forward))

    def stop(self):
        """再生を停止する。戻り値はない。"""
        cmds.play(state=False)

    @contextmanager
    def preserve_time(self):
        """例外時も開始時の時刻へ戻す。再生状態や範囲は復元しない。

        Yields:
            TimeSlider: このインスタンス。
        """
        previous = self.current_time()
        try:
            yield self
        finally:
            self.set_current_time(previous)
