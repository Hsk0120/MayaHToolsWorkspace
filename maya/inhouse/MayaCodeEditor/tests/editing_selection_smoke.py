"""専用Maya GUIで改行・字下げ・選択保持を検査し実際の描画を記録する。"""
import json
from pathlib import Path
import sys
import traceback


def main(output_dir, finished):
    """Qtキー入力による本文・選択端点・Undo/Redoの検証を実行する。

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
    result = {"status": "error", "maya": cmds.about(version=True), "input": "Qt QTest; not OS input", "checks": []}
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
        wait(1200)  # 起動時のレイアウト・設定反映が終わってから撮影用の表示を整える。
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
        cases = []
        for source in ("# keep this comment:", '"keep this text"', "    # keep", 'f"{value}"'):
            expected = source + "\n" + ("    " if source.startswith("    ") else "")
            cases.append(("Enter preserves text", source, len(source), len(source), QtCore.Qt.Key_Return, no, expected, len(expected), len(expected)))
        cases += [
            ("Split without duplicate indentation", "def example():\n    one    two", 22, 22, QtCore.Qt.Key_Return, no, "def example():\n    one\n    two", 27, 27),
            ("Complete triple double quotes", '""', 2, 2, '"', no, '""""""', 3, 3),
            ("Complete triple single quotes", "''", 2, 2, "'", no, "''''''", 3, 3),
            ("Complete raw triple quotes", 'r""', 3, 3, '"', no, 'r""""""', 4, 4),
            ("Complete formatted triple quotes", 'f""', 3, 3, '"', no, 'f""""""', 4, 4),
            ("Pair inside a comment", "# note ", 7, 7, "(", no, "# note ()", 8, 8),
            ("Pair inside a string", '"hello "', 7, 7, "(", no, '"hello ()"', 8, 8),
            ("Tab to column 4", "  value", 2, 2, QtCore.Qt.Key_Tab, no, "    value", 4, 4),
            ("Tab after a word", "abc", 3, 3, QtCore.Qt.Key_Tab, no, "abc ", 4, 4),
            ("Indent to next stop", "     one", 0, 8, QtCore.Qt.Key_Tab, no, "        one", 0, 11),
            ("Outdent to previous stop", "     one", 5, 5, QtCore.Qt.Key_Backtab, shift, "    one", 4, 4),
            ("Normalize tab indentation", "\tone\n\t\ttwo", 1, 9, QtCore.Qt.Key_Tab, no, "        one\n            two", 1, 26),
            ("Replace partial selection with Tab", "one two", 1, 5, QtCore.Qt.Key_Tab, no, "o   wo", 4, 4),
            ("Indent partial selection", "one\n    two\nthree", 1, 11, QtCore.Qt.Key_Tab, no, "    one\n        two\nthree", 5, 19),
            ("Outdent partial selection", "    one\n        two\nthree", 6, 16, QtCore.Qt.Key_Backtab, shift, "one\n    two\nthree", 2, 8),
            ("Move partial selection", "one\ntwo\nthree", 1, 6, QtCore.Qt.Key_Down, alt, "three\none\ntwo", 7, 12),
            ("Move reverse selection", "one\ntwo\nthree", 6, 1, QtCore.Qt.Key_Down, alt, "three\none\ntwo", 12, 7),
            ("Duplicate partial selection", "one\ntwo\nthree", 1, 6, QtCore.Qt.Key_Down, alt | shift, "one\ntwo\none\ntwo\nthree", 9, 14),
            ("Align block comments", "    one\n        two\n", 0, 19, QtCore.Qt.Key_Slash, ctrl, "    # one\n    #     two\n", 0, 23),
            ("Comment reverse selection", "one\ntwo\nthree", 7, 0, QtCore.Qt.Key_Slash, ctrl, "# one\n# two\nthree", 11, 2),
            ("Keep next-line boundary", "one\ntwo\nthree", 0, 4, QtCore.Qt.Key_Tab, no, "    one\ntwo\nthree", 0, 8),
            ("Select touched lines first", "one\ntwo\nthree", 1, 6, QtCore.Qt.Key_L, ctrl, "one\ntwo\nthree", 0, 8),
            ("Extend a complete line selection", "one\ntwo\nthree", 0, 4, QtCore.Qt.Key_L, ctrl, "one\ntwo\nthree", 0, 8),
            ("Word left crosses one dot", "one.two", 4, 4, QtCore.Qt.Key_Left, ctrl, "one.two", 0, 0),
            ("Word right reaches word end", "one.two", 3, 3, QtCore.Qt.Key_Right, ctrl, "one.two", 7, 7),
            ("Select through a word", "one.two", 3, 3, QtCore.Qt.Key_Right, ctrl | shift, "one.two", 3, 7),
            ("Delete whitespace before word", "one two", 3, 3, QtCore.Qt.Key_Delete, ctrl, "onetwo", 3, 3),
            ("Delete consecutive whitespace", "one  two", 5, 5, QtCore.Qt.Key_Backspace, ctrl, "onetwo", 3, 3),
        ]
        for name, source, anchor, position, key, modifiers, expected, expected_anchor, expected_position in cases:
            code.setPlainText(source)
            cursor = code.textCursor()
            cursor.setPosition(anchor)
            cursor.setPosition(position, QtGui.QTextCursor.KeepAnchor)
            code.setTextCursor(cursor)
            window.activateWindow()
            code.setFocus()
            label[0] = name + " | before"
            wait(500)
            if isinstance(key, str):
                QtTest.QTest.keyClicks(code, key, modifiers)
            else:
                QtTest.QTest.keyClick(code, key, modifiers)
            wait(250)
            actual = (code.toPlainText(), code.textCursor().anchor(), code.textCursor().position())
            assert actual == (expected, expected_anchor, expected_position), (name, actual)
            label[0] = name + " | verified"
            wait(700)
            label[0] = name + " | Undo / Redo"
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Z, ctrl)
            wait(150)
            assert code.toPlainText() == source, (name, "Undo", code.toPlainText())
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Z, ctrl | shift)
            wait(150)
            assert code.toPlainText() == expected, (name, "Redo", code.toPlainText())
            result["checks"].append(name)
        result["status"] = "passed"
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        if recording is not None:
            recording.stop()
        result["frames"] = frame_number[0]
        (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        finished(result)
