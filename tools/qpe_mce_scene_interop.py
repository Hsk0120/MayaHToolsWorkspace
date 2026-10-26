"""隔離Mayaでシーン入出力と未保存エディター本文の相互干渉を確認する。"""
import json
import os
from pathlib import Path
import sys
import time
import traceback


def main(output_dir, finished):
    """両ツールと独立Qt画面を保持して実ファイル操作を検証・録画する。"""
    # 専用Maya GUI内からのみ呼び、通常PythonでMayaを初期化しない。
    from maya import cmds, mel

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    sys.path.insert(0, str(root / "maya/inhouse/QuickPathExplorer/python"))
    sys.path.insert(0, str(root / "maya/inhouse/MayaCodeEditor/tests"))
    from qpeQt import QtCore, QtGui, QtWidgets, QtTest, shiboken
    from qpe_ui_maya import pause, waitFor
    from recovery_gui import heads
    import gui_host
    import qpeHost

    out = Path(output_dir).resolve()
    os.environ["QPE_SETTINGS_FILE"] = str(out / "qpe-settings.json")
    frames = out / "frames"
    frames.mkdir(exist_ok=True)
    folder = out / "Scenes 日本語"
    folder.mkdir(exist_ok=True)
    result = {"status": "error", "input_kind": "Qt QTest / Maya commands; not OS input", "checks": []}
    samples = []
    stage = ["01 Both tools and independent editor"]
    recorder = None
    peer = None
    errors = []
    old_hook = sys.excepthook

    def record_error(*info):
        """Qtスロットの例外も終了結果へ残す。"""
        errors.append("".join(traceback.format_exception(*info)))

    sys.excepthook = record_error
    try:
        cmds.loadPlugin("mayaCodeEditor", quiet=True)
        session = Path(cmds.mayaCodeEditor(sessionPath=True)).resolve()
        if out not in session.parents:
            raise ValueError("Scene test requires disposable editor recovery data")
        cmds.mayaCodeEditor(show=True, floating=True)
        editor = gui_host.editor()
        editor.resize(760, 650)
        tabs = editor.findChild(QtWidgets.QTabWidget)
        code = tabs.currentWidget()
        marker = "# 未保存・シーン操作の保護確認\nscene_interop = 42\n"
        code.setPlainText(marker)
        peer = QtWidgets.QPlainTextEdit()
        peer.setPlainText("Independent tool text")
        peer.setWindowTitle("Independent Qt scene test")
        peer.show()
        qpe = qpeHost.show(str(folder))
        cmds.workspaceControl(qpeHost.CONTROL, edit=True, floating=True, resizeWidth=1250, resizeHeight=820)
        pause(1000)

        def capture():
            """実ウィジェットの画面を並べる。デスクトップ録画とは区別する。"""
            pix = QtGui.QPixmap(1920, 1100)
            pix.fill(QtGui.QColor("#202226"))
            painter = QtGui.QPainter(pix)
            painter.setPen(QtCore.Qt.white)
            painter.setFont(QtGui.QFont("Segoe UI", 18))
            painter.drawText(20, 35, "Qt automated GUI / real widget captures / " + stage[0])
            painter.drawPixmap(15, 65, qpe.grab().scaled(1200, 960, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
            painter.drawPixmap(1230, 65, editor.grab().scaled(675, 760, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
            modal = QtWidgets.QApplication.activeModalWidget()
            if modal is not None:
                painter.drawPixmap(450, 450, modal.grab())
            painter.end()
            path = frames / ("%05d.png" % len(samples))
            pix.save(str(path))
            samples.append({"path": path.as_posix(), "seconds": time.monotonic(), "stage": stage[0]})

        recorder = QtCore.QTimer(qpe)
        recorder.timeout.connect(capture)
        recorder.start(250)

        def answer_dialog(title, answer):
            """予期した実ダイアログだけを期限付きで操作する。"""
            timer = QtCore.QTimer(qpe)
            attempts = [0]
            answered = []

            def respond():
                """表示後の標準ボタンを押して結果を記録する。"""
                attempts[0] += 1
                modal = QtWidgets.QApplication.activeModalWidget()
                if isinstance(modal, QtWidgets.QMessageBox) and modal.windowTitle() == title:
                    capture()
                    button = modal.button(answer)
                    if button is not None:
                        answered.append(modal.text())
                        timer.stop()
                        button.click()
                elif attempts[0] > 50:
                    timer.stop()
                    if modal is not None:
                        modal.reject()

            timer.timeout.connect(respond)
            timer.start(200)
            return timer, answered

        def check(label):
            """本文と確定済み復元データ、別Qt画面を操作ごとに確認する。"""
            pause(300)
            assert code.toPlainText() == marker, label
            assert marker in heads(session), label + ": recovery head missing"
            assert shiboken.isValid(peer) and peer.toPlainText() == "Independent tool text"
            assert not errors, errors
            result["checks"].append(label)
            stage[0] = "%02d %s" % (len(result["checks"]) + 1, label)
            capture()
            pause(1100)

        cmds.file(new=True, force=True)
        node = cmds.createNode("transform", name="sceneInteropMarker")
        qpe.window().raise_()
        qpe.window().activateWindow()
        pause(300)
        QtTest.QTest.mouseClick(qpe.saveAsButton, QtCore.Qt.LeftButton)
        pause(350)
        assert qpe.operationTabs.currentWidget() is qpe.savePanel
        qpe.fileName.setText("source")
        pause(350)
        capture()
        QtTest.QTest.mouseClick(qpe.actionButtons["saveAs"], QtCore.Qt.LeftButton)
        source = folder / "source.mb"
        assert source.is_file() and cmds.file(query=True, type=True) == ["mayaBinary"], {
            "directory": qpe.currentDirectory, "target": qpe.targetPath(),
            "status": qpe.status.text(), "scene": cmds.file(query=True, sceneName=True),
            "buttonVisible": qpe.actionButtons["saveAs"].isVisible()}
        check("Save As Binary preserves both editors")

        cmds.setAttr(node + ".tx", 9)
        qpeHost.perform(qpe, "save")
        qpeHost.perform(qpe, "new")
        assert not cmds.objExists(node)
        qpe.requestFiles("open", [str(source)])
        assert cmds.getAttr(node + ".tx") == 9
        waitFor(lambda: Path(qpe.currentDirectory) == folder)
        check("Save / New / Open restores scene and follows folder")

        controls = qpe.readOptions.controls["reference"]
        controls["mode"].setCurrentIndex(1)
        controls["name"].setText("invalidSelf:asset")
        timer, answered = answer_dialog("QuickPathExplorer", QtWidgets.QMessageBox.Ok)
        qpe.requestFiles("reference", [str(source)])
        timer.stop()
        assert answered and "Cannot reference the current scene" in answered[0]
        assert not cmds.namespace(exists="invalidSelf")
        assert not cmds.file(query=True, reference=True)
        assert not qpe.status.text().startswith("Completed")
        check("Self-reference rejected before namespace mutation")

        # 現在シーン自身の参照は禁止されるため、作業シーンを別名保存して素材を読む。
        qpe.fileName.setText("working")
        qpeHost.perform(qpe, "saveAs")
        assert Path(cmds.file(query=True, sceneName=True)) == folder / "working.mb"
        for action, namespace in (("import", "shot:imported"), ("reference", "shot:referenced")):
            controls = qpe.readOptions.controls[action]
            controls["mode"].setCurrentIndex(1)
            controls["name"].setText(namespace)
            qpe.requestFiles(action, [str(source)])
            target = namespace + ":" + node
            assert cmds.objExists(target), {
                "expected": target, "status": qpe.status.text(),
                "options": qpe.readOptions.fileArguments(action, str(source)),
                "nodes": cmds.ls(type="transform"), "references": cmds.file(query=True, reference=True)}
            assert cmds.referenceQuery(target, isNodeReferenced=True) == (action == "reference")
            assert cmds.namespaceInfo(currentNamespace=True) == ":"
            check(action.title() + " uses nested namespace and preserves editor recovery")

        cmds.select(node, replace=True)
        cmds.setAttr(node + ".tx", 12)
        cmds.undo()
        assert cmds.getAttr(node + ".tx") == 9
        cmds.redo()
        assert cmds.getAttr(node + ".tx") == 12
        cmds.currentTime(24)
        assert cmds.currentTime(query=True) == 24
        check("Selection / Undo / Redo / timeline remain functional")

        timer, answered = answer_dialog("Unsaved scene", QtWidgets.QMessageBox.Cancel)
        qpe.requestFiles("open", [str(source)])
        timer.stop()
        assert answered and cmds.getAttr(node + ".tx") == 12
        assert cmds.objExists("shot:referenced:" + node)
        check("Actual Cancel dialog preserves modified scene and editors")

        cmds.file(modified=False)
        qpeHost.perform(qpe, "new")
        # Maya標準の外部OpenもQPEへ通知され、MCEの本文を変更しない。
        cmds.file(str(source), open=True, force=True)
        waitFor(lambda: Path(qpe.currentDirectory) == folder)
        mel.eval("OutlinerWindow;")
        mel.eval("ScriptEditor;")
        check("Standard scene Open / Outliner / Script Editor preserve MCE")
        editor.window().raise_()
        editor.window().activateWindow()
        code.setFocus()
        pause(200)
        qpe.navigate(str(out))
        pause(700)
        assert QtWidgets.QApplication.focusWidget() is code
        check("Directory completion does not steal editor focus")
        result["status"] = "passed"
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        if recorder is not None:
            recorder.stop()
        if peer is not None:
            peer.close()
            peer.deleteLater()
        sys.excepthook = old_hook
    manifest = []
    for index, sample in enumerate(samples):
        duration = samples[index + 1]["seconds"] - sample["seconds"] if index + 1 < len(samples) else 1.0
        manifest.extend(["file '%s'" % sample["path"], "duration %.6f" % duration])
    if samples:
        manifest.append("file '%s'" % samples[-1]["path"])
    (out / "frames.txt").write_text("\n".join(manifest), encoding="utf-8")
    (out / "timeline.json").write_text(json.dumps(samples, indent=2), encoding="utf-8")
    result["slot_errors"] = errors
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    finished(result)
