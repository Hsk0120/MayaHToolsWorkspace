"""Maya 2022のplaybackOptionsをUndo履歴に載せる専用コマンド。"""
from pathlib import Path
import maya.cmds as cmds
import maya.api.OpenMaya as om2


def maya_useNewAPI():
    """MayaにAPI 2.0プラグインであることを通知する。"""


class _PlaybackRangeCommand(om2.MPxCommand):
    """範囲変更をcmdsで実行し、変更前の四つの境界を保持する。"""

    def doIt(self, args):
        """対象フラグと開始・終了値を受け取り、変更する。"""
        self.flags = {args.asString(0): args.asDouble(2), args.asString(1): args.asDouble(3)}
        self.previous = {flag: cmds.playbackOptions(query=True, **{flag: True})
                         for flag in ("animationStartTime", "animationEndTime", "minTime", "maxTime")}
        self.redoIt()

    def redoIt(self):
        """指定範囲を再適用する。"""
        cmds.playbackOptions(**self.flags)

    def undoIt(self):
        """副作用を含め、変更前のアニメーション・再生範囲へ戻す。"""
        cmds.playbackOptions(animationStartTime=self.previous["animationStartTime"],
                             animationEndTime=self.previous["animationEndTime"])
        cmds.playbackOptions(minTime=self.previous["minTime"], maxTime=self.previous["maxTime"])

    def isUndoable(self):
        """bool: Undo/Redo可能なコマンドとして登録する。"""
        return True


def _syntax():
    """MSyntax: 二つのフラグ名と二つの時刻を受け取る。"""
    syntax = om2.MSyntax()
    for kind in (om2.MSyntax.kString, om2.MSyntax.kString, om2.MSyntax.kDouble, om2.MSyntax.kDouble):
        syntax.addArg(kind)
    return syntax


def initializePlugin(obj):
    """Mayaのコマンドを登録する。"""
    om2.MFnPlugin(obj, "hlib", "1.0").registerCommand("hlibSetPlaybackRange", _PlaybackRangeCommand, _syntax)


def uninitializePlugin(obj):
    """Mayaのコマンド登録を解除する。"""
    om2.MFnPlugin(obj).deregisterCommand("hlibSetPlaybackRange")


def set_range(start_flag, end_flag, start, end):
    """必要時にプラグインをロードし、Undo対応の範囲変更を実行する。"""
    path = str(Path(__file__).resolve())
    if not cmds.pluginInfo(path, query=True, loaded=True):
        cmds.loadPlugin(path, quiet=True)
    cmds.hlibSetPlaybackRange(start_flag, end_flag, start, end)
