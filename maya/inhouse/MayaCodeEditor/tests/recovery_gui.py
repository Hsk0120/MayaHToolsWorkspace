"""専用Mayaの多重起動と即時終了で、未保存本文を実画面から検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback
import zlib


def heads(path):
    """保存先の確定先端と、その検証用本文を返す。"""
    root = Path(str(path) + ".recovery")
    records = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (root / "snapshots").glob("*.json")}
    parents = {parent for record in records.values() for parent in record["parents"]}
    result = []
    for key, record in records.items():
        if key in parents:
            continue
        for tab in record["tabs"]:
            blob = root / "bodies" / (record["bodies"][tab["id"]] + ".qz")
            result.append(zlib.decompress(blob.read_bytes()[4:]).decode("utf-8"))
    return result


def main(output_dir, finished):
    """専用GUI内で、指定された保存・強制終了・復元段階を実行する。"""
    # GUIランナーが起動したMayaだけでQtとコマンドを読み込む。
    from maya import cmds
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gui_host

    output = Path(output_dir)
    stage = os.environ["MCE_RECOVERY_STAGE"]
    path = Path(os.environ["MCE_SESSION_FILE"])
    result = {"status": "error", "stage": stage, "checks": []}
    frames = output / "frames"
    frames.mkdir(exist_ok=True)
    cmds.loadPlugin("mayaCodeEditor", quiet=True)
    cmds.mayaCodeEditor(show=True, floating=True)
    window = gui_host.editor()
    window.resize(1120, 760)
    tabs = window.findChild(QtWidgets.QTabWidget)
    frame = [0]

    def capture():
        target = QtWidgets.QApplication.activeModalWidget() or window.window()
        target.grab().save(str(frames / ("{:05d}.png".format(frame[0]))))
        frame[0] += 1

    recorder = QtCore.QTimer(window)
    recorder.timeout.connect(capture)
    recorder.start(200)

    def wait(ms):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    def all_texts():
        values = []
        for index in range(tabs.count()):
            tabs.setCurrentIndex(index)
            values.append(tabs.currentWidget().toPlainText())
        return values

    def finish():
        recorder.stop()
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        finished(result)

    try:
        window.statusBar().showMessage("Recovery test: " + stage)
        wait(1200)
        actions = window.findChildren(QtGui.QAction if hasattr(QtGui, "QAction") else QtWidgets.QAction)
        next(action for action in actions if action.text() == "Show input only").trigger()
        if stage == "seed":
            tabs.currentWidget().setPlainText("# Recovery test\nbase = 1\n")
            assert "# Recovery test\nbase = 1\n" in heads(path)
            result["checks"].append("seed_saved_before_return")
            wait(1500)
        elif stage in ("A", "B"):
            # 両方が同じ状態を復元してから編集を開始する。
            signal = path.with_name(stage + ".ready")
            signal.write_text(str(os.getpid()), encoding="utf-8")
            for _ in range(240):
                if path.with_name("go").exists():
                    break
                wait(200)
            else:
                raise RuntimeError("Concurrent GUI barrier timed out")
            code = tabs.currentWidget()
            code.setPlainText("# Maya " + stage + " — 未保存の編集\n")
            for step in range(12):
                code.moveCursor(QtGui.QTextCursor.End)
                code.insertPlainText("value_{} = {}\n".format(step, step))
                assert code.toPlainText() in heads(path), "Edit was not committed synchronously"
                wait(100)
            # 待機もQt終了通知も挟まず、最後の入力直後にプロセスを終了する。
            code.insertPlainText("last_edit_" + stage + " = 'survives crash'\n")
            assert code.toPlainText() in heads(path)
            capture()
            result["checks"].append("every_edit_committed_without_idle")
            result["checks"].append("exit_without_destructor_or_aboutToQuit")
            result["status"] = "passed"
            (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            os._exit(23)
        else:
            values = all_texts()
            assert sum("last_edit_A" in value for value in values) == 1, values
            assert sum("last_edit_B" in value for value in values) == 1, values
            assert len(values) == 2, "Repeated recovery must not add duplicate tabs"
            result["checks"].append("both_concurrent_edits_restored_once")
            for index in range(tabs.count()):
                tabs.setCurrentIndex(index)
                assert tabs.currentWidget().document().isModified()
                wait(1800)
            if stage == "verify":
                # 明示的な履歴復元も現在のタブを消さずに追加する。OSダイアログではなくQt版で検証する。
                QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_DontUseNativeDialogs, True)
                snapshots = sorted(Path(str(path) + ".recovery/snapshots").glob("*.json"))

                def choose_snapshot():
                    # Mayaはダイアログをドックの外側へ付け替える。MainWindowの子とは限らない。
                    dialog = next((w for w in QtWidgets.QApplication.allWidgets()
                                   if w.objectName() == "recoverySnapshotDialog"), None)
                    if dialog is None:
                        (output / "dialog-poll.json").write_text(json.dumps({"found": False}), encoding="utf-8")
                        QtCore.QTimer.singleShot(100, choose_snapshot)
                        return
                    # selectFileは表示済みのダイアログで入力欄を変更しないQt版がある。
                    edit = dialog.findChild(QtWidgets.QLineEdit, "fileNameEdit")
                    edit.setText(snapshots[0].as_posix())
                    (output / "dialog-poll.json").write_text(json.dumps({"found": True, "file": edit.text()}), encoding="utf-8")
                    QtCore.QTimer.singleShot(800, lambda: dialog.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Open).click())

                QtCore.QTimer.singleShot(300, choose_snapshot)
                window.findChild(QtGui.QAction if hasattr(QtGui, "QAction") else QtWidgets.QAction, "recoverSnapshot").trigger()
                assert tabs.count() == 3
                assert values == all_texts()[:2]
                result["checks"].append("history_recovery_adds_tab_without_replacing_current")
                wait(1800)
                # 追加した履歴タブだけ閉じる。確認ダイアログでDiscardを選ぶ。
                def discard():
                    for widget in QtWidgets.QApplication.topLevelWidgets():
                        if isinstance(widget, QtWidgets.QMessageBox):
                            widget.button(QtWidgets.QMessageBox.Discard).click()
                            return
                QtCore.QTimer.singleShot(200, discard)
                tabs.tabCloseRequested.emit(2)
                wait(1800)
                assert tabs.count() == 2
                result["checks"].append("closing_recovered_copy_preserves_original_tabs")
        result["status"] = "passed"
    except Exception:
        result["error"] = traceback.format_exc()
    finish()
