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
    # 製品と同じロックを取り、他の専用Mayaの整理途中を観測しない。
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore
    lock = QtCore.QLockFile(str(root / "store.lock"))
    lock.setStaleLockTime(0)
    assert lock.tryLock(1000), "Recovery inspection lock timeout"
    try:
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
    finally:
        lock.unlock()



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
            qpe = None
            if os.environ.get("MCE_RECOVERY_WITH_QPE") == "1":
                # 併用試験も各GUI専用の設定へ隔離し、共有するのはMCEの復元データだけ。
                root = Path(__file__).resolve().parents[4]
                sys.path.insert(0, str(root / "maya/inhouse/QuickPathExplorer/python"))
                os.environ["QPE_SETTINGS_FILE"] = str(output / "qpe-settings.json")
                import qpeHost
                qpe = qpeHost.show(str(output))
                wait(400)
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
                if qpe is not None and step in (3, 7, 11):
                    before = code.toPlainText()
                    cmds.deleteUI(qpeHost.CONTROL)
                    qpe = qpeHost.show(str(output))
                    wait(100)
                    assert code.toPlainText() == before, "QPE recreation changed the editor"
                    assert before in heads(path), "QPE recreation lost saved recovery text"
                wait(100)
            # 待機もQt終了通知も挟まず、最後の入力直後にプロセスを終了する。
            code.insertPlainText("last_edit_" + stage + " = 'survives crash'\n")
            assert code.toPlainText() in heads(path)
            capture()
            result["checks"].append("every_edit_committed_without_idle")
            external_termination = os.environ.get("MCE_RECOVERY_EXTERNAL_TERMINATE") == "1"
            result["checks"].append("external_termination_ready" if external_termination
                                    else "os_exit_without_Qt_aboutToQuit")
            if qpe is not None:
                result["checks"].append("qpe_recreated_three_times_during_concurrent_editing")
            result["status"] = "passed"
            (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            if external_termination:
                # 所有PIDを確認した親ランナーがTerminateProcessするまでGUIを生かす。
                # Windowsのos._exitはDLL終了処理を通るため、別の障害条件として扱う。
                wait(30000)
                raise RuntimeError("External termination did not arrive within 30 seconds")
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
                # 履歴復元メニューは廃止。専用の新規タブを作って破棄後の整理を確認する。
                action_class = QtGui.QAction if hasattr(QtGui, "QAction") else QtWidgets.QAction
                assert window.findChild(action_class, "recoverSnapshot") is None
                action = next(a for a in window.findChildren(action_class) if a.text() == "New Python tab")
                action.trigger()
                tabs.currentWidget().setPlainText("discarded synthetic body")
                assert tabs.count() == 3
                wait(1800)
                discard_attempts = [0]
                discard_widgets = []
                def discard():
                    """専用モーダルが表示されるまで待ち、選んだボタンも証跡に残す。"""
                    discard_attempts[0] += 1
                    widget = QtWidgets.QApplication.activeModalWidget()
                    if widget is not None:
                        discard_widgets.append(widget)
                    buttons = widget.findChildren(QtWidgets.QAbstractButton) if widget is not None else []
                    (output / "discard-poll.json").write_text(json.dumps({
                        "attempt": discard_attempts[0],
                        "title": widget.windowTitle() if widget is not None else None,
                        "type": type(widget).__name__,
                        "buttons": [button.text() for button in buttons],
                    }), encoding="utf-8")
                    if widget is not None and widget.windowTitle() == "Unsaved script":
                        button = next((button for button in buttons
                                       if button.text().replace("&", "") == "Discard"), None)
                        if button is not None:
                            button.click()
                            return
                    if discard_attempts[0] < 50:
                        QtCore.QTimer.singleShot(100, discard)
                    elif widget is not None:
                        # 失敗時はテストを返してタブ数のassertで失敗させる。
                        widget.close()
                QtCore.QTimer.singleShot(200, discard)
                tabs.tabCloseRequested.emit(2)
                wait(1800)
                assert tabs.count() == 2
                assert values == all_texts()
                assert len(list(Path(str(path) + ".recovery/snapshots").glob("*.json"))) == 1
                for body in Path(str(path) + ".recovery/bodies").glob("*.qz"):
                    assert b"discarded synthetic body" not in zlib.decompress(body.read_bytes()[4:])
                result["checks"].append("discard_removes_body_preserves_other_tabs")
        result["status"] = "passed"
    except Exception:
        result["error"] = traceback.format_exc()
    finish()
