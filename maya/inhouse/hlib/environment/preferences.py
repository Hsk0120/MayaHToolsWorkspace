"""Mayaの作業単位とユーザー設定を操作する。"""

import math
from pathlib import Path

import maya.cmds as cmds
import maya.mel as mel

from ..decorators.undo import undoChunk


class Preferences:
    """現在のMaya設定を操作する。設定値のコピーは保持しない。

    getメソッドは毎回Mayaを照会し、setメソッドは実行中の設定を変更する。
    単位はシーン保存の対象、それ以外はユーザー設定として扱われる。
    単位以外のsetterのsave=Trueまたはsave()で一般ユーザー設定全体を保存する。
    単位のsetterはsave引数を持たず、Scene.save()でシーンに保存する。
    各項目の保存区分は設定保存ガイドを参照する。"""

    @staticmethod
    def getLinearUnit():
        """現在の距離 UI 単位を取得する。

        Returns:
            str: 距離単位名(例: ``"cm"``、``"m"``)。

        Note:
            現在のシーンに作用し、シーン保存時に保持される。新規シーンの既定値とは別。
        """
        return cmds.currentUnit(query=True, linear=True)

    @staticmethod
    @undoChunk("hlib.environment.Preferences.setLinearUnit")
    def setLinearUnit(unit):
        """距離 UI 単位を変更する。

        Args:
            unit (str): ``cmds.currentUnit`` が受け付ける距離単位名
                (例: ``"mm"``、``"cm"``、``"m"``、``"in"``、``"ft"``)。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: Maya が未対応の単位名を拒否した場合。

        Note:
            現在のシーンに作用し、シーン保存時に保持される。新規シーンの既定値とは別。 Scene.save()でシーンを保存する。
        """
        cmds.currentUnit(linear=unit)

    @staticmethod
    def getAngleUnit():
        """現在の角度 UI 単位を取得する。

        Returns:
            str: ``"deg"`` または ``"rad"``。

        Note:
            現在のシーンに作用し、シーン保存時に保持される。新規シーンの既定値とは別。
        """
        return cmds.currentUnit(query=True, angle=True)

    @staticmethod
    @undoChunk("hlib.environment.Preferences.setAngleUnit")
    def setAngleUnit(unit):
        """角度 UI 単位を変更する。

        Args:
            unit (str): ``"deg"`` または ``"rad"``。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: Maya が未対応の単位名を拒否した場合。

        Note:
            現在のシーンに作用し、シーン保存時に保持される。新規シーンの既定値とは別。 Scene.save()でシーンを保存する。
        """
        cmds.currentUnit(angle=unit)

    @staticmethod
    def getTimeUnit():
        """現在の時間 UI 単位を取得する。

        Returns:
            str: 時間単位名(例: ``"film"``、``"ntsc"``、``"pal"``、``"game"``)。

        Note:
            現在のシーンに作用し、シーン保存時に保持される。新規シーンの既定値とは別。
        """
        return cmds.currentUnit(query=True, time=True)

    @staticmethod
    @undoChunk("hlib.environment.Preferences.setTimeUnit")
    def setTimeUnit(unit):
        """時間 UI 単位を変更する。

        Args:
            unit (str): ``cmds.currentUnit`` が受け付ける時間単位名
                (例: ``"film"``、``"ntsc"``、``"24fps"``)。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: Maya が未対応の単位名を拒否した場合。

        Note:
            現在のシーンに作用し、シーン保存時に保持される。新規シーンの既定値とは別。 Scene.save()でシーンを保存する。
        """
        cmds.currentUnit(time=unit)

    @staticmethod
    def getUpAxis():
        """現在の上方向を取得する。

        Returns:
            str: y/z。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。
        """
        return cmds.upAxis(query=True, axis=True)

    @staticmethod
    @undoChunk("hlibPreferences")
    def setUpAxis(axis, rotate_view=False, *, save=False):
        """上方向を変更する。既定ではカメラを回転しない。

        Args:
            save (bool): Trueで一般ユーザー設定全体を保存する。既定はFalse。シーン保存は行わない。
            axis (str): y/z。
            rotate_view (bool): 表示カメラも回転させるか。
        Returns:
            None: 値を返さない。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。 save=Trueの場合のみユーザー設定を保存する。シーンは保存しない。
        """
        Preferences._validate_save(save)
        if axis not in ("y", "z"):
            raise ValueError("axis must be y or z")
        cmds.upAxis(axis=axis, rotateView=Preferences._boolean(rotate_view))
        if save:
            Preferences.save()

    @staticmethod
    def getUndoEnabled():
        """現在の設定を取得する。

        Returns:
            bool: 有効ならTrue。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。
        """
        return bool(cmds.undoInfo(query=True, state=True))

    @staticmethod
    def setUndoEnabled(enabled, flush=True, *, save=False):
        """Undoの記録を切り替える。Undoチャンクには含めない。

        Args:
            save (bool): Trueで一般ユーザー設定全体を保存する。既定はFalse。シーン保存は行わない。
            enabled (bool): 記録するか。
            flush (bool): TrueはMaya標準のstateで切り替え、履歴を消去する。
                Falseは履歴を保持する。無効中に破壊的操作を行った場合、以前の履歴は安全に戻せない。
        Returns:
            None: 値を返さない。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。 save=Trueの場合のみユーザー設定を保存する。シーンは保存しない。
        """
        Preferences._validate_save(save)
        enabled = Preferences._boolean(enabled)
        flush = Preferences._boolean(flush)
        cmds.undoInfo(**{"state" if flush else "stateWithoutFlush": enabled})
        if save:
            Preferences.save()

    @staticmethod
    def getUndoInfinite():
        """現在の設定を取得する。

        Returns:
            bool: 有効ならTrue。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。
        """
        return bool(cmds.undoInfo(query=True, infinity=True))

    @staticmethod
    def setUndoInfinite(enabled, *, save=False):
        """設定を変更する。Undo履歴の上限設定で、無限を無効にすると既存の上限が適用される。

        Args:
            save (bool): Trueで一般ユーザー設定全体を保存する。既定はFalse。シーン保存は行わない。
            enabled (bool): 有効にするか。
        Returns:
            None: 値を返さない。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。 save=Trueの場合のみユーザー設定を保存する。シーンは保存しない。
        """
        Preferences._validate_save(save)
        cmds.undoInfo(infinity=Preferences._boolean(enabled))
        if save:
            Preferences.save()

    @staticmethod
    def getAutosaveEnabled():
        """現在の設定を取得する。

        Returns:
            bool: 有効ならTrue。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。
        """
        return bool(cmds.autoSave(query=True, enable=True))

    @staticmethod
    @undoChunk("hlibPreferences")
    def setAutosaveEnabled(enabled, *, save=False):
        """設定を変更する。

        Args:
            save (bool): Trueで一般ユーザー設定全体を保存する。既定はFalse。シーン保存は行わない。
            enabled (bool): 有効にするか。
        Returns:
            None: 値を返さない。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。 save=Trueの場合のみユーザー設定を保存する。シーンは保存しない。
        """
        Preferences._validate_save(save)
        cmds.autoSave(enable=Preferences._boolean(enabled))
        if save:
            Preferences.save()

    @staticmethod
    def getTrackSelectionOrder():
        """現在の設定を取得する。

        Returns:
            bool: 有効ならTrue。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。
        """
        return bool(cmds.selectPref(query=True, trackSelectionOrder=True))

    @staticmethod
    @undoChunk("hlibPreferences")
    def setTrackSelectionOrder(enabled, *, save=False):
        """設定を変更する。

        Args:
            save (bool): Trueで一般ユーザー設定全体を保存する。既定はFalse。シーン保存は行わない。
            enabled (bool): 有効にするか。
        Returns:
            None: 値を返さない。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。 save=Trueの場合のみユーザー設定を保存する。シーンは保存しない。
        """
        Preferences._validate_save(save)
        cmds.selectPref(trackSelectionOrder=Preferences._boolean(enabled))
        if save:
            Preferences.save()

    @staticmethod
    def getUndoLimit():
        """設定されているUndo履歴の上限を取得する。

        Returns:
            int: 上限。無限が有効な間は適用されない。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。
        """
        return cmds.undoInfo(query=True, length=True)

    @staticmethod
    def setUndoLimit(count, *, save=False):
        """履歴上限を設定し、無限を無効にする。古い履歴が削除され得る。

        Args:
            save (bool): Trueで一般ユーザー設定全体を保存する。既定はFalse。シーン保存は行わない。
            count (int): 正の整数。
        Returns:
            None: 値を返さない。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。 save=Trueの場合のみユーザー設定を保存する。シーンは保存しない。
        """
        Preferences._validate_save(save)
        if type(count) is not int or not 1 <= count <= 4294967295:
            raise ValueError("count must be a positive uint")
        cmds.undoInfo(infinity=False, length=count)
        if save:
            Preferences.save()

    @staticmethod
    def getAutosaveInterval():
        """自動保存の間隔を取得する。

        Returns:
            float: 秒。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。
        """
        return cmds.autoSave(query=True, interval=True)

    @staticmethod
    @undoChunk("hlibPreferences")
    def setAutosaveInterval(seconds, *, save=False):
        """自動保存間隔を変更する。保存は実行しない。

        Args:
            save (bool): Trueで一般ユーザー設定全体を保存する。既定はFalse。シーン保存は行わない。
            seconds (float): 正の有限な秒数。
        Returns:
            None: 値を返さない。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。 save=Trueの場合のみユーザー設定を保存する。シーンは保存しない。
        """
        Preferences._validate_save(save)
        seconds = float(seconds)
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("seconds must be positive and finite")
        cmds.autoSave(interval=seconds)
        if save:
            Preferences.save()

    @staticmethod
    def getAutosaveDirectory():
        """現在の保存方式を反映した実際の自動保存先を取得する。

        Returns:
            Path: Mayaが解決した絶対パス。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。
        """
        return Path(cmds.autoSave(query=True, destinationFolder=True))

    @staticmethod
    @undoChunk("hlibPreferences")
    def setAutosaveDirectory(path, *, save=False):
        """自動保存先を指定フォルダー方式へ変更する。作成・保存は行わない。

        Args:
            save (bool): Trueで一般ユーザー設定全体を保存する。既定はFalse。シーン保存は行わない。
            path (str | Path): 保存先。ユーザーホームを展開し絶対化する。
        Returns:
            None: 値を返さない。

        Note:
            Maya全体の実行中設定を扱う。永続化はMayaのユーザー設定保存・同期処理に従う。 save=Trueの場合のみユーザー設定を保存する。シーンは保存しない。
        """
        Preferences._validate_save(save)
        if not isinstance(path, (str, Path)) or not str(path).strip():
            raise ValueError("path must be a non-empty string or Path")
        folder = Path(path).expanduser().resolve()
        cmds.autoSave(folder=str(folder), destination=1)
        if save:
            Preferences.save()

    @staticmethod
    def save():
        """Maya GUIで対応するユーザー設定を同期し、一般プリファレンスを保存する。

        単位はシーンの設定として保持し、新規シーンの既定単位には転記しない。
        上方向・Undo・選択順・自動保存をMaya標準の保存用optionVarへ転記する。
        savePrefsは一般optionVar全体を保存するため、他の一般設定も書き出される。
        シーン・シェルフ・UI配置は保存しない。ディスク保存はUndoで戻らない。
        保存失敗時の例外は呼び出し元へ伝わり、現在値の変更は巻き戻さない。

        Returns:
            None: 値を返さない。
        """
        if cmds.about(batch=True):
            raise RuntimeError("Preferences.save requires Maya GUI (savePrefs)")
        integer_values = {
            "undoIsEnabled": Preferences.getUndoEnabled(),
            "undoIsInfinite": Preferences.getUndoInfinite(),
            "undoLength": Preferences.getUndoLimit(),
            "TrackSelectionOrder": Preferences.getTrackSelectionOrder(),
            "autoSaveEnable": Preferences.getAutosaveEnabled(),
            "autoSaveDestination": cmds.autoSave(query=True, destination=True),
        }
        for name, value in integer_values.items():
            cmds.optionVar(intValue=(name, int(value)))
        cmds.optionVar(stringValue=("upAxisDirection", Preferences.getUpAxis()))
        cmds.optionVar(stringValue=("autoSaveFolder", cmds.autoSave(query=True, folder=True)))
        # 起動時のMayaは分単位の保存値を60倍して秒に戻す。
        cmds.optionVar(floatValue=("autoSaveInterval", Preferences.getAutosaveInterval() / 60.0))
        mel.eval("savePrefs -general;")

    @staticmethod
    def _boolean(value):
        """boolのみ受け付ける。

        Args:
            value (bool): 検証する値。
        Returns:
            bool: 検証済み。型が異なる場合はTypeError。
        """
        if type(value) is not bool:
            raise TypeError("Expected bool")
        return value

    @staticmethod
    def _validate_save(save):
        """保存要求を変更前に検証する。batchでの部分更新を防ぐ。

        Args:
            save: 設定をディスクへ保存するか。
        """
        Preferences._boolean(save)
        if save and cmds.about(batch=True):
            raise RuntimeError("Preferences.save requires Maya GUI (savePrefs)")
