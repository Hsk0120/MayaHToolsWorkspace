"""エディター設定の明示的なUndo/Redoコマンド。自動ロード設定は変更しない。"""
import json
from pathlib import Path
from maya import cmds
from maya.api import OpenMaya as om


def maya_useNewAPI():
    """API 2.0を使用する。"""


def _set(record):
    """固定のエディター種類だけを実行する。"""
    kind, name, values = record["editor"], record["target"], record["values"]
    if kind == "timeline":
        cmds.playbackOptions(animationStartTime=values["animationStartTime"], animationEndTime=values["animationEndTime"])
        cmds.playbackOptions(minTime=values["minTime"], maxTime=values["maxTime"])
        cmds.currentTime(values["currentTime"])
        return
    from hlib.editors.viewport import Viewport
    from hlib.editors.outliner import Outliner
    classes = {"viewport": Viewport, "outliner": Outliner}
    cls = classes[kind]
    if set(values) - set(cls._flags):
        raise ValueError("Unsupported editor flags")
    command = cmds.modelEditor if kind == "viewport" else cmds.outlinerEditor
    if not command(name, exists=True):
        raise RuntimeError("Editor no longer exists: " + name)
    command(name, edit=True, **values)


class _EditorCommand(om.MPxCommand):
    """設定変更前後を保存する。Undo時に消えたUIは再作成しない。"""
    def doIt(self, args):
        self.states = json.loads(args.asString(0))
        self.redoIt()

    def _run(self, key):
        # ネイティブコマンドがUndo対応のバージョンでも二重登録しない。
        enabled = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(stateWithoutFlush=False)
        try:
            for state in self.states:
                _set(state[key])
        except BaseException:
            # 適用失敗時は専用コマンドがUndo履歴へ入らないため、元状態へ戻す。
            if key == "after":
                for state in reversed(self.states):
                    _set(state["before"])
            raise
        finally:
            cmds.undoInfo(stateWithoutFlush=enabled)

    def redoIt(self):
        self._run("after")

    def undoIt(self):
        self._run("before")

    def isUndoable(self):
        return True


def _syntax():
    syntax = om.MSyntax()
    syntax.addArg(om.MSyntax.kString)
    return syntax


def initializePlugin(obj):
    om.MFnPlugin(obj, "hlib", "1.0").registerCommand("hlibJsonEditorState", _EditorCommand, _syntax)


def uninitializePlugin(obj):
    om.MFnPlugin(obj).deregisterCommand("hlibJsonEditorState")


def apply(states):
    """必要時に専用プラグインをロードして変更を一操作にまとめる。"""
    path = str(Path(__file__).resolve())
    if not cmds.pluginInfo(path, query=True, loaded=True):
        cmds.loadPlugin(path, quiet=True)
    cmds.hlibJsonEditorState(json.dumps(states, allow_nan=False))
