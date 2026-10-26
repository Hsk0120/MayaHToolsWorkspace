"""隔離MayaでQPE・Code Editor・標準操作・別Qt画面の相互干渉を検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback


def main(output_dir, finished):
    """専用GUIで画面の寿命を交互に変え、本文と外側の操作を確認する。

    Args:
        output_dir (Path): ランナー所有の設定と証拠の保存先。
        finished (callable): 専用Mayaの終了を通知する関数。
    """
    # この入口はMaya GUI内だけで呼ぶ。
    from maya import cmds, mel, OpenMayaUI

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    sys.path.insert(0, str(root / "maya/inhouse/QuickPathExplorer/python"))
    sys.path.insert(0, str(root / "maya/inhouse/MayaCodeEditor/tests"))
    from qpeQt import QtCore, QtWidgets, QtTest, shiboken
    from qpe_ui_maya import pause
    import gui_host
    import qpeHost
    import qpeDock

    out = Path(output_dir).resolve()
    os.environ["QPE_SETTINGS_FILE"] = str(out / "qpe-settings.json")
    result = {"status": "error", "input_kind": "Qt QTest and Maya commands", "checks": [], "errors": []}
    previous_hook = sys.excepthook
    live_widgets = {}

    def record_error(*info):
        """QtがPythonの呼出元へ返さない例外も検証失敗として記録する。"""
        result["errors"].append("".join(traceback.format_exception(*info)))

    def tabs():
        """再ドックで古くなったQt5ラッパーを使わず現在のタブを取得する。"""
        window = gui_host.editor()
        # C++製画面の親ラッパーを一時変数だけにすると、子のPython参照も無効化され得る。
        live_widgets["window"] = window
        live_widgets["all"] = QtWidgets.QApplication.allWidgets()
        return next(w for w in live_widgets["all"]
                    if isinstance(w, QtWidgets.QTabWidget) and window.isAncestorOf(w))

    def check_text():
        """未保存の本文が一つだけ存在し、別画面が実体を破棄していないか確認する。"""
        current = tabs()
        texts = [current.widget(i).toPlainText() for i in range(current.count())]
        assert texts.count(marker) == 1, texts
        assert shiboken.isValid(peer) and peer.toPlainText() == "independent peer"

    def standard_operations(label):
        """Mayaの選択・アトリビュート・Undo/Redo・時間変更を値で検証する。"""
        cmds.select(node, replace=True)
        cmds.setAttr(node + ".tx", 3.5)
        cmds.undo()
        assert cmds.getAttr(node + ".tx") == 0.0
        cmds.redo()
        assert cmds.getAttr(node + ".tx") == 3.5
        cmds.setAttr(node + ".tx", 0.0)
        cmds.currentTime(12)
        assert cmds.currentTime(query=True) == 12
        assert cmds.ls(selection=True) == [node]
        result["checks"].append(label + ": Maya selection/Undo/Redo/time intact")

    sys.excepthook = record_error
    peer = None
    try:
        cmds.loadPlugin("mayaCodeEditor", quiet=True)
        recovery = Path(cmds.mayaCodeEditor(sessionPath=True)).resolve()
        if out not in recovery.parents:
            raise ValueError("Interop test requires a disposable Maya profile")
        app = QtWidgets.QApplication.instance()
        style = int(shiboken.getCppPointer(app.style())[0])
        font = app.font().toString()
        palette = app.palette().cacheKey()
        sheet = app.styleSheet()
        main_window = shiboken.wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()), QtWidgets.QWidget)
        peer = QtWidgets.QPlainTextEdit(main_window)
        peer.setWindowFlags(QtCore.Qt.Window)
        peer.setObjectName("qpeMceIndependentPeer")
        peer.setWindowTitle("Independent Qt editor — interference test")
        peer.resize(420, 220)
        peer.setPlainText("independent peer")
        peer.show()
        node = cmds.createNode("transform", name="qpeMceInteropMarker")
        marker = "# 未保存の相互干渉テスト\ninterop_preserved = 42\n"
        cmds.mayaCodeEditor(show=True, floating=True)
        tabs().currentWidget().setPlainText(marker)
        qpe = qpeHost.show(str(out))
        pause(800)
        standard_operations("both floating")

        for cycle, side in enumerate(("right", "bottom", "left", "right")):
            cmds.workspaceControl(gui_host.CONTROL, edit=True, dockToMainWindow=(side, False))
            cmds.workspaceControl(qpeHost.CONTROL, edit=True, tabToControl=(gui_host.CONTROL, -1))
            pause(500)
            qpeHost.show()
            cmds.mayaCodeEditor(show=True)
            pause(700)
            check_text()
            # QPE破棄前後で別ツールとMaya標準操作を比較する。
            old_qpe = qpeHost._window
            cmds.deleteUI(qpeHost.CONTROL)
            qpe = qpeHost.show(str(out))
            pause(800)
            assert qpe is not old_qpe
            assert qpeDock._watcher.isCurrent()
            check_text()
            standard_operations("cycle %d QPE regenerated" % cycle)
            # Code Editorの画面を破棄してもQPEの現在内容と監視は維持される。
            before = qpe.currentDirectory
            cmds.deleteUI(gui_host.CONTROL)
            pause(250)
            cmds.mayaCodeEditor(show=True, floating=True)
            pause(650)
            check_text()
            assert qpe.currentDirectory == before and qpeDock._watcher.isCurrent()
            result["checks"].append("cycle %d: both deletion orders preserve peer and text" % cycle)
            main_window.grab().save(str(out / ("interop-%02d.png" % cycle)))

        # 別Qtツール内のUndo/Redo/全選択がQPEやMCEに流れないことを確かめる。
        peer.show()
        peer.raise_()
        peer.activateWindow()
        peer.setFocus()
        pause(300)
        QtTest.QTest.keyClick(peer, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        QtTest.QTest.keyClicks(peer, "new independent text")
        assert peer.toPlainText() == "new independent text"
        QtTest.QTest.keyClick(peer, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
        # QPlainTextEditの入力は一つのUndoブロックへまとまる。
        assert peer.toPlainText() == "independent peer", peer.toPlainText()
        check_text()
        result["checks"].append("independent Qt editor selection/type/Undo does not affect MCE")
        mel.eval("OutlinerWindow;")
        mel.eval("ScriptEditor;")
        pause(500)
        standard_operations("standard panels opened")
        assert app.styleSheet() == sheet and app.font().toString() == font
        assert app.palette().cacheKey() == palette
        assert int(shiboken.getCppPointer(app.style())[0]) == style
        assert not result["errors"], result["errors"]
        result["checks"].append("global Qt style/font/palette unchanged")
        result["status"] = "passed"
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        sys.excepthook = previous_hook
        if peer is not None and shiboken.isValid(peer):
            peer.close()
            peer.deleteLater()
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    finished(result)
