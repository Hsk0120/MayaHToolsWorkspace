"""隔離Maya GUIで型解析の補完・確定・診断・全文共有を確認する。"""
import json
import os
import faulthandler
from pathlib import Path
import sys
import time
import traceback


def main(output_dir, finished):
    """実GUIをQt入力で操作し、結果と画像を記録する。

    Args:
        output_dir (Path): 証拠先。
        finished (callable): 終了通知。
    """
    from maya import cmds
    try:
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
        QAction = QtGui.QAction
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets, QtTest
        QAction = QtWidgets.QAction
    sys.path.insert(0, str(Path(__file__).parent))
    import gui_host

    output = Path(output_dir)
    fault_stream = (output / "python-fault.log").open("w", encoding="utf-8")
    faulthandler.enable(file=fault_stream, all_threads=True)
    frames = output / "frames"
    frames.mkdir(exist_ok=True)
    result = {"status": "error", "checks": [], "input_kind": "Qt QTest; dedicated Maya GUI"}
    (output / "pyrightconfig.json").write_text(json.dumps({"include": ["."], "exclude": ["maya_app", "temp", "frames"], "typeCheckingMode": "standard"}), encoding="utf-8")
    (output / "auto_helper.py").write_text("class LocalWidget: pass\n", encoding="utf-8")
    (output / "source_a.py").write_text("def source_value(count: int):\n    return count * 2\n", encoding="utf-8")
    (output / "source_b.py").write_text("from source_a import source_value\nvalue = source_value(2)\n", encoding="utf-8")

    def wait(milliseconds):
        """イベントループを回す。"""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    def check(name, condition, detail=None):
        """失敗を含めて記録する。"""
        result["checks"].append({"name": name, "passed": bool(condition), "detail": detail})
        (output / "progress.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if not condition:
            raise AssertionError(name + ": " + str(detail))

    try:
        cmds.loadPlugin("mayaCodeEditor", quiet=True)
        cmds.mayaCodeEditor(show=True)
        window = gui_host.editor()
        code = window.findChild(QtWidgets.QPlainTextEdit, "codeEditor")
        tabs = window.findChild(QtWidgets.QTabWidget)
        completer = code.findChild(QtWidgets.QCompleter)
        window.resize(1100, 760)
        window.activateWindow()
        code.setFocus()
        wait(8000)  # Mayaの起動時プラグイン/遅延UIが落ち着いてから入力する。
        window.window().raise_()
        window.window().activateWindow()
        QtWidgets.QApplication.setActiveWindow(window.window())
        code.setFocus()
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if any(item.property("languageStatus") == "Type analysis ready" for item in window.findChildren(QtWidgets.QLabel)):
                break
            wait(100)
        check("server_ready", time.monotonic() < deadline,
              [item.text() for item in window.findChildren(QtWidgets.QLabel)])
        window.findChild(QtWidgets.QPlainTextEdit, "output").clear()
        output_pane = window.findChild(QtWidgets.QSplitter, "editorSplitter").widget(0)
        output_pane.hide()
        font = code.font()
        font.setPixelSize(18)
        code.setFont(font)
        recording = output / "recording"
        recording.mkdir()
        frame = [0]

        def capture():
            """実ウィジェットの描画とポップアップを固定サイズへ記録する。"""
            canvas = QtGui.QPixmap(1200, 900)
            canvas.fill(QtGui.QColor("#202020"))
            painter = QtGui.QPainter(canvas)
            painter.drawPixmap(0, 28, window.grab())
            origin = window.mapToGlobal(QtCore.QPoint(0, 0))
            # Maya全体の一時ウィジェットを列挙しない。録画対象の所有物だけを参照する。
            widgets = [completer.popup(), QtWidgets.QApplication.activeModalWidget()]
            widgets.extend(window.findChildren(QtWidgets.QFrame, "signatureHelp"))
            widgets.extend(window.findChildren(QtWidgets.QFrame, "completionDetail"))
            for widget in widgets:
                if widget is not None and widget.isVisible():
                    point = widget.mapToGlobal(QtCore.QPoint(0, 0)) - origin
                    painter.drawPixmap(point.x(), point.y() + 28, widget.grab())
            painter.setPen(QtGui.QColor("white"))
            painter.drawText(12, 20, "MCE / Maya " + cmds.about(version=True) + " / Qt GUI test capture")
            painter.end()
            canvas.save(str(recording / ("%05d.png" % frame[0])))
            frame[0] += 1

        recorder = QtCore.QTimer(window)
        recorder.timeout.connect(capture)
        recorder.start(200)
        wait(500)
        trace = output / "language.jsonl"
        watch_count = trace.read_text(encoding="utf-8").count('"method":"workspace/didChangeWatchedFiles"')
        (output / "unrelated.log").write_text("unrelated output", encoding="utf-8")
        wait(600)
        check("unrelated_file_does_not_reload_analysis", trace.read_text(encoding="utf-8").count('"method":"workspace/didChangeWatchedFiles"') == watch_count)

        def action(name):
            """表示名または安定IDでメニューを選ぶ。"""
            return next(item for item in window.findChildren(QAction) if item.text() == name or item.objectName() == name)

        def dialogs(trigger, replies):
            """テスト専用入力と下見のApply/CancelをQt操作する。"""
            queue = list(replies)
            seen = []
            deadline = time.monotonic() + 25

            def respond():
                """予期したダイアログだけへ応答する。"""
                dialog = QtWidgets.QApplication.activeModalWidget()
                if time.monotonic() > deadline and dialog is not None:
                    dialog.reject()
                    return
                if not queue or dialog is None or queue[0][0] not in dialog.windowTitle():
                    return
                title, value = queue.pop(0)
                seen.append(dialog.windowTitle())
                capture()
                wait(500)  # 動画で変更内容を読める時間を確保する。
                if isinstance(dialog, QtWidgets.QInputDialog):
                    combo = dialog.findChild(QtWidgets.QComboBox)
                    if combo is not None:
                        choices = [combo.itemText(index) for index in range(combo.count())]
                        match = next((index for index, choice in enumerate(choices) if choice.replace("\\", "/").endswith(value.replace("\\", "/"))), -1)
                        if match < 0:
                            result["dialog_choices"] = choices
                            dialog.reject()
                            return
                        combo.setCurrentIndex(match)
                    else:
                        dialog.setTextValue(value)
                    dialog.accept()
                elif dialog.findChild(QtWidgets.QLineEdit, "fileNameEdit") is not None:
                    # 静的QFileDialogはPySideでは基底QDialogとして返る場合がある。
                    field = dialog.findChild(QtWidgets.QLineEdit, "fileNameEdit")
                    field.setText(value)
                    field.setFocus()
                    QtTest.QTest.keyClick(field, QtCore.Qt.Key_Return)
                elif value:
                    dialog.accept()
                else:
                    dialog.reject()

            timer = QtCore.QTimer(window)
            timer.timeout.connect(respond)
            timer.start(200)
            trigger()
            deadline = time.monotonic() + 15
            while queue and time.monotonic() < deadline:
                wait(100)
            timer.stop()
            timer.deleteLater()
            check("dialogs_" + replies[0][0], not queue, {"seen": seen, "pending": queue})
            wait(250)

        def popup(source, target, position=None):
            """補完を待ち、対象候補を選ぶ。"""
            completer.popup().hide()
            code.setPlainText(source)
            cursor = code.textCursor()
            cursor.setPosition(len(source) if position is None else position)
            code.setTextCursor(cursor)
            QtWidgets.QApplication.setActiveWindow(window.window())
            code.setFocus()
            wait(450)
            names = []
            deadline = time.monotonic() + 60
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
            while time.monotonic() < deadline:
                wait(350)
                if not code.hasFocus() and QtWidgets.QApplication.activeModalWidget() is None:
                    QtWidgets.QApplication.setActiveWindow(window.window())
                    code.setFocus()
                    QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
                model = completer.completionModel()
                names = [model.index(row, 0).data() for row in range(model.rowCount())]
                if target in names and completer.popup().isVisible():
                    completer.popup().setCurrentIndex(model.index(names.index(target), 0))
                    wait(450)
                    capture()
                    return names
            return names

        base = "class Widget:\n    def run(self, count=1): pass\n"
        cases = [
            ("string", "name = 'demo'\nname.upp", "upper"),
            ("annotation", "name: str = 'demo'\nname.upp", "upper"),
            ("dictionary", "values = {'name': 1}\nvalues.it", "items"),
            ("typevar", "from typing import TypeVar\nT = TypeVar('T')\ndef identity(value: T) -> T:\n    return value\nname = identity('demo')\nname.upp", "upper"),
            ("protocol", "from typing_extensions import Protocol\nclass Runner(Protocol):\n    def run(self) -> int: ...\ndef work(value: Runner):\n    value.ru", "run"),
            ("return", base + "def make() -> Widget:\n    return Widget()\nw = make()\nw.ru", "run"),
            ("alias", base + "w = Widget()\nalias = w\nalias.ru", "run"),
            ("element", base + "items: list[Widget] = []\nitems[0].ru", "run"),
            ("for", base + "items: list[Widget] = []\nfor w in items:\n    w.ru", "run"),
            ("self", "class Widget:\n    def __init__(self):\n        self.count = 1\n    def run(self):\n        self.co", "count"),
            ("narrow", base + "def work(w: object):\n    if isinstance(w, Widget):\n        w.ru", "run"),
        ]
        for name, source, target in cases:
            names = popup(source, target)
            check(name, target in names, {"names": names[:30], "discard": code.property("languageDiscard"), "focus": code.hasFocus()})
            window.grab().save(str(frames / (name + ".png")))
            before = code.toPlainText()
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
            wait(600)
            check(name + "_accept_no_newline", code.toPlainText().count("\n") == before.count("\n") and code.toPlainText().endswith(target), code.toPlainText())
        literal = 'from typing_extensions import Literal\ndef create(kind: Literal["joint", "transform"]): pass\ncreate("jo")'
        names = popup(literal, '"joint"', literal.rindex('jo') + 2)
        check("literal_candidate", '"joint"' in names, names)
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
        wait(300)
        check("literal_accept_quotes", code.toPlainText().endswith('create("joint")'), code.toPlainText())
        code.undo()
        check("literal_undo", code.toPlainText() == literal)
        dictionary = 'from typing_extensions import TypedDict\nclass Settings(TypedDict):\n    namespace: str\nsettings: Settings = {"namespace": "rig"}\nsettings["na"]'
        names = popup(dictionary, '"namespace"', dictionary.rindex('na') + 2)
        check("typed_dict_candidate", '"namespace"' in names, names)
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
        wait(300)
        check("typed_dict_accept", code.toPlainText().endswith('settings["namespace"]'), code.toPlainText())
        names = popup("class Joint:\n    def getJointOrient(self): pass\n    def getChildJointNames(self): pass\njoint = Joint()\njoint.gJO", "getJointOrient")
        check("fuzzy_best_match", names[0] == "getJointOrient", names)
        names = popup("class Joint:\n    def getJointOrient(self): pass\njoint = Joint()\njoint.", "getJointOrient")
        check("public_before_dunder", names.index("getJointOrient") < names.index("__class__"), names)
        (output / "sample.pyi").write_text(base, encoding="utf-8")
        names = popup("import sample\nw = sample.Widget()\nw.ru", "run")
        check("stub", "run" in names, names)
        source = "def first():\n    lat\n\ndef later(): pass\n"
        names = popup(source, "later", source.index("lat") + 3)
        check("full_document", "later" in names, names)
        completer.popup().hide()
        signature_source = "from typing import overload\n@overload\ndef parse(value: int, base: int) -> int: ...\n@overload\ndef parse(value: str, base: int) -> str: ...\ndef parse(value, base): return value\nparse('text', "
        code.setPlainText(signature_source)
        code.moveCursor(QtGui.QTextCursor.End)
        code.setFocus()
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier)
        wait(1100)
        signature = code.findChild(QtWidgets.QFrame, "signatureHelp")
        signature_text = " ".join(item.toPlainText() for item in signature.findChildren(QtWidgets.QTextBrowser)) if signature else ""
        check("overload_signature", signature is not None and signature.isVisible() and "base" in signature_text and "Overload" in signature_text, signature_text)
        static_action = next(action for action in window.findChildren(QAction) if action.text().startswith("Static analysis"))
        if not static_action.isChecked():
            static_action.trigger()
        code.setPlainText("count: int = 'wrong'\ndef build(size: int): pass\nbuild()\nimport nonexistent_qpe_mce_package\n")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and (code.property("languageDiagnosticCount") or 0) < 3:
            wait(100)
        count = code.property("languageDiagnosticCount") or 0
        check("type_call_import_diagnostics", count >= 3, count)
        window.grab().save(str(frames / "diagnostics.png"))
        check("semantic_colors", bool(code.property("languageTokens")))
        action("Type and argument hints").trigger()
        source = "def scale(amount: int):\n    return amount * 2\nvalue = scale(2)\n"
        code.setPlainText(source)
        wait(1200)
        check("inlay_hints", bool(code.property("languageHints")))
        check("hints_do_not_change_text", code.toPlainText() == source)
        problems = window.findChild(QtWidgets.QListWidget, "analysisProblems")
        check("type_analysis_status", problems.count() == 1 and problems.item(0).text() == "No problems found by type analysis",
              [problems.item(index).text() for index in range(problems.count())])
        action("Suggest auto imports").trigger()
        names = popup("LocalWidg", "LocalWidget")
        check("auto_import_candidate", "LocalWidget" in names, names)
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
        wait(800)
        check("auto_import_edit", "from auto_helper import LocalWidget" in code.toPlainText(), code.toPlainText())
        code.undo()
        check("auto_import_single_undo", code.toPlainText() == "LocalWidg", code.toPlainText())
        completer.popup().hide()
        code.setPlainText("item = LocalWidget()\n")
        cursor = code.textCursor()
        cursor.setPosition(12)
        code.setTextCursor(cursor)
        code.setFocus()
        wait(1400)
        dialogs(lambda: QtTest.QTest.keyClick(code, QtCore.Qt.Key_Period, QtCore.Qt.ControlModifier), [("Code actions", "from auto_helper import LocalWidget"), ("Review changes", True)])
        check("code_action_import", "from auto_helper import LocalWidget" in code.toPlainText(), code.toPlainText())
        code.undo()
        check("code_action_undo", code.toPlainText() == "item = LocalWidget()\n")
        # 保存済みファイルの代わりに、2つの未保存タブの本文を共有する。
        code.setProperty("path", str(output / "source_a.py"))
        code.setPlainText((output / "source_a.py").read_text(encoding="utf-8"))
        action("New Python tab").trigger()
        other = tabs.currentWidget()
        other.setProperty("path", str(output / "source_b.py"))
        other.setPlainText("from source_a import source_value\nunsaved = source_value(3)\n")
        tabs.setCurrentWidget(code)
        code.setFocus()
        cursor = code.textCursor()
        cursor.setPosition(8)
        code.setTextCursor(cursor)
        wait(700)
        dialogs(lambda: QtTest.QTest.keyClick(code, QtCore.Qt.Key_F2), [("Rename symbol", "renamed_value"), ("Review changes", False)])
        check("rename_cancel", "source_value" in code.toPlainText() and "source_value(3)" in other.toPlainText())
        dialogs(lambda: QtTest.QTest.keyClick(code, QtCore.Qt.Key_F2), [("Rename symbol", "renamed_value"), ("Review changes", True)])
        check("rename_unsaved_tabs", "renamed_value" in code.toPlainText() and "renamed_value(3)" in other.toPlainText())
        check("rename_preserves_disk", "source_value" in (output / "source_a.py").read_text(encoding="utf-8"))
        code.undo()
        other.undo()
        check("rename_undo", "source_value" in code.toPlainText() and "source_value(3)" in other.toPlainText())
        tabs.setCurrentWidget(other)
        other.setFocus()
        cursor = other.textCursor()
        cursor.setPosition(other.toPlainText().rindex("source_value") + 3)
        other.setTextCursor(cursor)
        wait(500)
        QtTest.QTest.keyClick(other, QtCore.Qt.Key_F12)
        wait(900)
        check("definition_activates_existing_tab", tabs.currentWidget() == code and code.textCursor().blockNumber() == 0)
        dialogs(lambda: QtTest.QTest.keyClick(code, QtCore.Qt.Key_F12, QtCore.Qt.ShiftModifier), [("Locations", "source_b.py:2")])
        check("references_found", tabs.currentWidget() == other and other.textCursor().blockNumber() == 1)
        tabs.setCurrentWidget(code)
        code.setFocus()
        text = "def calculate(x, y):\n    return x + y\n"
        code.setPlainText(text)
        cursor = code.textCursor()
        cursor.setPosition(text.index("x + y"))
        cursor.setPosition(text.index("x + y") + 5, QtGui.QTextCursor.KeepAnchor)
        code.setTextCursor(cursor)
        wait(400)
        dialogs(lambda: action("refactor_variable").trigger(), [("Extract variable", "sum_value"), ("Review changes", True)])
        check("extract_variable_gui", "sum_value = x + y" in code.toPlainText(), code.toPlainText())
        code.undo()
        check("extract_undo", code.toPlainText() == text)
        cursor = code.textCursor()
        cursor.setPosition(text.index("    return"))
        cursor.setPosition(len(text), QtGui.QTextCursor.KeepAnchor)
        code.setTextCursor(cursor)
        code.setFocus()
        dialogs(lambda: action("refactor_function").trigger(), [("Extract function", "add_values"), ("Review changes", True)])
        check("extract_function_gui", "def add_values" in code.toPlainText() and "add_values(x, y)" in code.toPlainText(), code.toPlainText())
        code.undo()
        code.setPlainText("import os\nimport sys\nprint(sys.version)\n")
        wait(400)
        dialogs(lambda: action("refactor_imports").trigger(), [("Review changes", True)])
        check("organize_imports_gui", "import os" not in code.toPlainText() and "import sys" in code.toPlainText())
        # 新規ファイル操作はテスト用ルートだけ。下見の取消、改名、変更セット復元を確認する。
        original = (output / "source_a.py").read_text(encoding="utf-8")
        consumer = (output / "source_b.py").read_text(encoding="utf-8")
        code.setPlainText(original)
        other.setPlainText(consumer)
        tabs.setCurrentWidget(code)
        code.setFocus()
        wait(600)
        dialogs(lambda: action("refactor_rename_module").trigger(), [("Rename module", "renamed_module"), ("Review changes", False)])
        check("module_rename_cancel", (output / "source_a.py").exists() and not (output / "renamed_module.py").exists())
        dialogs(lambda: action("refactor_rename_module").trigger(), [("Rename module", "renamed_module"), ("Review changes", True)])
        check("module_rename_apply", not (output / "source_a.py").exists() and (output / "renamed_module.py").exists()
              and "from renamed_module" in other.toPlainText(), {"path": code.property("path"), "text": other.toPlainText()})
        check("module_rename_tab_title", tabs.tabText(tabs.indexOf(code)).startswith("renamed_module.py"), tabs.tabText(tabs.indexOf(code)))
        action("Undo last refactoring").trigger()
        check("module_group_undo", (output / "source_a.py").exists() and not (output / "renamed_module.py").exists()
              and code.toPlainText() == original and other.toPlainText() == consumer,
              {"path": code.property("path"), "text": code.toPlainText(), "consumer": other.toPlainText(),
               "status": [label.text() for label in window.findChildren(QtWidgets.QLabel)]})
        action("Redo last refactoring").trigger()
        check("module_group_redo", (output / "renamed_module.py").exists() and "from renamed_module" in other.toPlainText())
        other.moveCursor(QtGui.QTextCursor.End)
        other.insertPlainText("# later user edit\n")
        action("Undo last refactoring").trigger()
        check("group_undo_conflict_preserved", (output / "renamed_module.py").exists() and "later user edit" in other.toPlainText())
        other.undo()
        action("Undo last refactoring").trigger()
        check("group_undo_after_conflict_removed", (output / "source_a.py").exists() and other.toPlainText() == consumer)
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_DontUseNativeDialogs, True)
        tabs.setCurrentWidget(code)
        code.setFocus()
        cursor = code.textCursor(); cursor.setPosition(original.index("source_value") + 3); code.setTextCursor(cursor)
        destination = output / "new_module.py"
        dialogs(lambda: action("refactor_move_new").trigger(), [("Move global symbol", str(destination)), ("Review changes", True)])
        new_code = next(item for item in window.findChildren(QtWidgets.QPlainTextEdit, "codeEditor")
                        if str(item.property("path") or "").replace("\\", "/") == destination.as_posix())
        check("move_new_module", "def source_value" in new_code.toPlainText() and "import new_module" in other.toPlainText()
              and "new_module.source_value(2)" in other.toPlainText() and not destination.exists(),
              {"new": new_code.toPlainText(), "consumer": other.toPlainText()})
        action("Undo last refactoring").trigger()
        check("move_new_group_undo", code.toPlainText() == original and other.toPlainText() == consumer and new_code.toPlainText() == "")
        action("Redo last refactoring").trigger()
        check("move_new_group_redo", "def source_value" in new_code.toPlainText() and "new_module.source_value(2)" in other.toPlainText())
        action("Undo last refactoring").trigger()
        tabs.setCurrentWidget(code)
        # 解析完了が別ウィジェットのフォーカスを奪わないことを確認。
        code.setPlainText("text = 'a'\ntext.upp")
        cursor = code.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        code.setTextCursor(cursor)
        code.setFocus()
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
        output_widget = window.findChild(QtWidgets.QPlainTextEdit, "output")
        output_pane.show()
        output_widget.setFocus()
        wait(1000)
        check("async_does_not_steal_focus", output_widget.hasFocus() and not completer.popup().isVisible())
        # 要求中に別タブへ移って本文を変更する。古い補完が新本文へ挿入されない。
        code.setFocus()
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
        tabs.setCurrentWidget(other)
        code.setPlainText("replacement = 42\n")
        wait(800)
        check("stale_completion_discarded", code.toPlainText() == "replacement = 42\n" and not completer.popup().isVisible() and tabs.currentWidget() == other)
        # 応答待ちのタブを破棄しても、他タブとMayaを維持する。
        tabs.setCurrentWidget(code)
        code.setPlainText("word = 'test'\nword.upp")
        code.moveCursor(QtGui.QTextCursor.End)
        code.setFocus()
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
        tabs.removeTab(tabs.indexOf(code))
        recorder.stop()  # 以降は破棄対象のcompleterへ撮影コールバックからアクセスしない。
        code.deleteLater()
        wait(700)
        check("close_pending_tab", tabs.indexOf(other) >= 0 and cmds.about(batch=True) is False)
        result["status"] = "passed"
    except BaseException:
        result["error"] = traceback.format_exc()
        try:
            window.grab().save(str(output / "failure.png"))
        except BaseException:
            pass
    if "recorder" in locals():
        recorder.stop()
        result["recorded_frames"] = frame[0]
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    faulthandler.disable()
    fault_stream.close()
    finished(result)
