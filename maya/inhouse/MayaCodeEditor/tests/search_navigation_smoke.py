"""専用Maya GUIで検索・置換・フォーカス復帰を検査し描画を記録する。

Qtの入力合成とWindowsの実入力は区別する。ホストが別の部品へフォーカスを
移した場合も失敗として残し、実入力で同じ現象が起きるとは断定しない。
"""
import json
import os
from pathlib import Path
import sys
import traceback


def main(output_dir, finished):
    """Qtキー入力とボタン操作による検索・置換・Undoを検証する。

    Args:
        output_dir (str): 専用GUIランナーの証拠フォルダー。
        finished (callable): 検査結果を受け取る完了通知。
    """
    from maya import cmds
    try:
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets, QtTest
    sys.path.insert(0, str(Path(__file__).parent))
    import gui_host

    directory = Path(output_dir)
    frames = directory / "recording"
    frames.mkdir(exist_ok=True)
    result = {"status": "error", "maya": cmds.about(version=True), "input": "Qt key events and QTest mouse clicks; not OS input", "checks": []}
    recording = None
    label = ["Preparing"]
    frame_number = [0]

    def wait(milliseconds):
        """Qtイベントを動かしながら表示を待つ。"""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    try:
        cmds.loadPlugin("mayaCodeEditor", quiet=True)
        cmds.mayaCodeEditor(show=True)
        window = gui_host.editor()
        window.resize(1180, 780)
        code = window.findChild(QtWidgets.QTabWidget).currentWidget()
        wait(5000)  # 起動時のレイアウト・設定反映が終わってから撮影用の表示を整える。
        window.findChild(QtWidgets.QPlainTextEdit, "output").clear()
        window.findChild(QtWidgets.QSplitter, "editorSplitter").widget(0).hide()
        font = code.font()
        font.setPixelSize(19)
        code.setFont(font)
        actions = window.findChildren(getattr(QtWidgets, "QAction", None) or QtGui.QAction)
        for name in ("option_completeLetters", "option_completeDot"):
            action = next(a for a in actions if a.objectName() == name)
            if action.isChecked():
                action.trigger()

        def capture():
            """所有する編集画面だけを描画し、試験名と入力種別を添える。"""
            canvas = QtGui.QPixmap(1200, 850)
            canvas.fill(QtGui.QColor("#202124"))
            painter = QtGui.QPainter(canvas)
            painter.setPen(QtGui.QColor("#eeeeee"))
            heading = painter.font()
            heading.setPixelSize(21)
            painter.setFont(heading)
            painter.drawText(16, 30, "Maya " + result["maya"] + " | Qt keyboard verification")
            painter.drawText(16, 58, label[0])
            painter.drawPixmap(10, 70, window.grab().scaled(1180, 770, QtCore.Qt.KeepAspectRatio))
            painter.end()
            canvas.save(str(frames / ("%05d.png" % frame_number[0])))
            frame_number[0] += 1

        recording = QtCore.QTimer(window)
        recording.timeout.connect(capture)
        recording.start(200)
        no = QtCore.Qt.NoModifier
        ctrl = QtCore.Qt.ControlModifier
        shift = QtCore.Qt.ShiftModifier
        alt = QtCore.Qt.AltModifier
        # ドックの子QMainWindowではなく、実際のトップレベルを有効化する。
        host_window = window.window()
        host_window.activateWindow()
        QtWidgets.QApplication.setActiveWindow(host_window)
        wait(1200)  # ホストの非同期アクティブ化を、検索欄への移動より先に完了させる。
        if os.environ.get("MCE_TEST_MANUAL_FOCUS") == "1":
            # QtのactivateWindowだけではWindowsの前面ウィンドウが変わらない場合がある。
            # 実クリックを開始条件にし、以後の合成入力とは別の手順として記録する。
            started = [False]
            start_button = QtWidgets.QPushButton("Start search verification", window)
            start_button.setObjectName("startSearchVerification")
            start_button.setGeometry(20, 80, 380, 44)

            def start_verification():
                """開始ボタンのクリックを受け取り、待機を終える。"""
                started[0] = True

            start_button.clicked.connect(start_verification)
            start_button.show()
            start_button.raise_()
            label[0] = "Click Start search verification to activate this window"
            for attempt in range(900):
                if started[0]:
                    break
                wait(100)
            start_button.hide()
            start_button.deleteLater()
            assert started[0], "Manual foreground activation timed out"
            result["input"] = "Foreground start-button click, then Qt key events and QTest mouse clicks"
        code.setFocus()
        wait(200)
        assert code.hasFocus(), "Dedicated editor did not obtain focus"
        source = "alpha beta alpha\nALPHA alphabet\nalpha"
        code.setPlainText(source)
        cursor = code.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(5, QtGui.QTextCursor.KeepAnchor)
        code.setTextCursor(cursor)
        def press(widget, key, modifiers=no):
            """Qtイベントを届ける。QTestの独立した修飾キー合成はMayaのフォーカスを変えるため使わない。"""
            QtWidgets.QApplication.sendEvent(widget, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, modifiers))
            target = QtWidgets.QApplication.focusWidget() or widget
            QtWidgets.QApplication.sendEvent(target, QtGui.QKeyEvent(QtCore.QEvent.KeyRelease, key, modifiers))

        press(code, QtCore.Qt.Key_F, ctrl)
        wait(300)
        bar = window.findChild(QtWidgets.QWidget, "findBar")
        query = window.findChild(QtWidgets.QLineEdit, "findText")
        replacement = window.findChild(QtWidgets.QLineEdit, "replaceText")
        count = window.findChild(QtWidgets.QLabel, "searchCount")

        def verified(name):
            """状態が確定した画面を記録し、検査項目を残す。"""
            label[0] = name + " | checking focus"
            wait(600)
            focus = QtWidgets.QApplication.focusWidget()
            result.setdefault("focus_trace", []).append({"step": name, "focus": repr(focus)})
            if name not in ("Escape closes search and returns editor focus", "Replace All is one Undo step", "Redo restores all replacements"):
                assert focus in (query, replacement), (name, "Focus left search", repr(focus))
            result["checks"].append(name)
            label[0] = name + " | verified"

        def click(name):
            """対象ウィンドウ内で名前が確認できたボタンをQtで押す。"""
            button = window.findChild(QtWidgets.QToolButton, name)
            assert button is not None and button.isVisible(), name
            QtTest.QTest.mouseClick(button, QtCore.Qt.LeftButton)
            wait(250)

        def enter_query(text):
            """検索欄へ実際のQtキー入力で文字列を入れる。"""
            query.setFocus()
            query.selectAll()
            QtTest.QTest.keyClicks(query, text)
            wait(300)

        assert bar.isVisible() and query.hasFocus() and query.text() == "alpha", {
            "visible": bar.isVisible(), "query_focus": query.hasFocus(), "query": query.text(),
            "focus": repr(QtWidgets.QApplication.focusWidget()),
            "active": repr(QtWidgets.QApplication.activeWindow()),
        }
        assert count.text().endswith("of 5"), count.text()
        verified("Find seeds selected text and focuses field")
        press(query, QtCore.Qt.Key_Return)
        wait(150)
        assert code.textCursor().selectionStart() == 11
        verified("Enter finds next occurrence")
        press(query, QtCore.Qt.Key_Return, shift)
        wait(150)
        assert code.textCursor().selectionStart() == 0
        verified("Shift Enter finds previous occurrence")
        click("searchCase")
        assert count.text().endswith("of 4"), count.text()
        click("searchWord")
        assert count.text().endswith("of 3"), count.text()
        verified("Match Case and Whole Word narrow matches")
        enter_query("missing")
        assert "No results" in count.text(), count.text()
        assert code.toPlainText() == source
        verified("Missing query keeps text unchanged")
        click("searchRegex")
        enter_query("[")
        error = window.findChild(QtWidgets.QLabel, "findError")
        assert error.isVisible() and error.text()
        assert code.toPlainText() == source
        verified("Invalid regular expression is non-destructive")
        enter_query("alpha")
        click("searchRegex")
        click("toggleReplace")
        assert replacement.isVisible()
        replacement.setFocus()
        QtTest.QTest.keyClicks(replacement, "item")
        click("replaceAll")
        assert code.toPlainText() == "item beta item\nALPHA alphabet\nitem", code.toPlainText()
        verified("Replace All obeys case and word options")
        query.setFocus()
        press(query, QtCore.Qt.Key_Escape)
        wait(200)
        assert not bar.isVisible() and code.hasFocus(), {"visible": bar.isVisible(), "code_focus": code.hasFocus(), "focus": repr(QtWidgets.QApplication.focusWidget())}
        verified("Escape closes search and returns editor focus")
        press(code, QtCore.Qt.Key_Z, ctrl)
        assert code.toPlainText() == source
        verified("Replace All is one Undo step")
        press(code, QtCore.Qt.Key_Z, ctrl | shift)
        assert code.toPlainText() == "item beta item\nALPHA alphabet\nitem"
        verified("Redo restores all replacements")
        result["status"] = "passed"
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        if recording is not None:
            recording.stop()
        result["frames"] = frame_number[0]
        (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        finished(result)
