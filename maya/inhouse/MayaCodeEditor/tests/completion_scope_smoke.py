"""専用Maya GUIでローカル名の補完と、確定Enterによる改行混入を検証する。"""
import json
from pathlib import Path
import sys
import time
import traceback


def main(output_dir, finished):
    """実C++画面をQtから操作し、候補・本文・フォーカスを照合する。

    Args:
        output_dir (Path): 専用ランナーの証拠保存先。
        finished (callable): 専用Mayaの終了通知先。
    """
    # Maya GUI内でだけホストとQtを読み込む。
    from maya import cmds
    try:
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets, QtTest
    sys.path.insert(0, str(Path(__file__).parent))
    import gui_host

    out = Path(output_dir)
    result = {"status": "error", "checks": [], "input_kind": "Qt QTest in dedicated Maya GUI"}

    def wait(milliseconds):
        """Qtの描画・補完タイマーを処理する。"""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    try:
        cmds.loadPlugin("mayaCodeEditor", quiet=True)
        cmds.mayaCodeEditor(show=True)
        window = gui_host.editor()
        code = window.findChild(QtWidgets.QPlainTextEdit, "codeEditor")
        completer = code.findChild(QtWidgets.QCompleter)
        window.findChild(QtWidgets.QPlainTextEdit, "output").clear()
        # 操作記録ではコード欄を広く使う。起動時の出力はランナーのログに残る。
        window.findChild(QtWidgets.QSplitter, "editorSplitter").widget(0).hide()
        window.resize(1100, 750)
        font = code.font()
        font.setPixelSize(18)
        code.setFont(font)
        frames = out / "frames"
        frames.mkdir()
        frame_number = [0]
        # 古いホストの遅延起動UIが落ち着いてから、Qt入力の検証を開始する。
        wait(5000)

        def capture(label):
            """実画面と補完ポップアップを同じ画像へ記録する。"""
            canvas = QtGui.QPixmap(1280, 900)
            canvas.fill(QtGui.QColor("#202124"))
            painter = QtGui.QPainter(canvas)
            painter.setPen(QtGui.QColor("white"))
            font = painter.font()
            font.setPixelSize(24)
            painter.setFont(font)
            painter.drawText(16, 34, "Maya %s | %s" % (cmds.about(version=True), label))
            painter.drawPixmap(16, 60, window.grab().scaled(1248, 810, QtCore.Qt.KeepAspectRatio))
            if completer.popup().isVisible():
                painter.drawPixmap(700, 130, completer.popup().grab().scaled(550, 650, QtCore.Qt.KeepAspectRatio))
            painter.end()
            canvas.save(str(frames / ("%03d.png" % frame_number[0])))
            frame_number[0] += 1

        def popup(source, expected, position=None):
            """本文を設定し、候補一覧の表示と選択を実際の補完処理で待つ。"""
            completer.popup().hide()
            code.setPlainText(source)
            code.moveCursor(QtGui.QTextCursor.End)
            if position is not None:
                cursor = code.textCursor()
                cursor.setPosition(position)
                code.setTextCursor(cursor)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                window.activateWindow()
                code.setFocus()
                wait(100)
                QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
                wait(120)
                model = completer.completionModel()
                names = [model.index(row, 0).data() for row in range(model.rowCount())]
                if completer.popup().isVisible() and expected in names:
                    completer.popup().setCurrentIndex(model.index(names.index(expected), 0))
                    return
            raise AssertionError("Missing visible completion: %s, candidates=%r" % (expected, names))

        # Ctrl+Spaceだけでなく、通常入力での自動候補も確認する。
        code.setPlainText('def build():\n    scene_name = "test"\n    ')
        code.moveCursor(QtGui.QTextCursor.End)
        window.activateWindow()
        code.setFocus()
        # 起動時のホストUI構築が終わってから入力する。入力失敗を補完失敗と混同しない。
        wait(1200)
        QtWidgets.QApplication.setActiveWindow(window.window())
        code.setFocus()
        assert code.hasFocus(), "Code editor did not receive startup focus"
        QtTest.QTest.keyClicks(code, "sce", QtCore.Qt.NoModifier, 60)
        assert code.toPlainText().endswith("    sce"), code.toPlainText()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            wait(100)
            model = completer.completionModel()
            names = [model.index(row, 0).data() for row in range(model.rowCount())]
            if completer.popup().isVisible() and "scene_name" in names:
                break
        model = completer.completionModel()
        names = [model.index(row, 0).data() for row in range(model.rowCount())]
        assert completer.popup().isVisible() and "scene_name" in names, {
            "names": names, "focus": code.hasFocus(), "discard": code.property("languageDiscard"),
            "received": code.property("languageCompletionCount"), "text": code.toPlainText(),
            "active_window": QtWidgets.QApplication.activeWindow().objectName() if QtWidgets.QApplication.activeWindow() else None,
            "focus_widget": QtWidgets.QApplication.focusWidget().objectName() if QtWidgets.QApplication.focusWidget() else None,
        }
        capture("automatic local candidate while typing")
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Escape)
        result["checks"].append("ordinary typing automatically offers function local")

        # 未import・別名の元名・新しい宣言名では、手動要求でも無関係な候補を出さない。
        for label, source in (
            ("no import: no module members", "json."),
            ("alias hides original module name", "import json as j\njson."),
            ("new function name: no suggestions", "scene_name = 1\ndef sce"),
            ("new import alias: no suggestions", "import json as sce"),
        ):
            completer.popup().hide()
            code.setPlainText(source)
            code.moveCursor(QtGui.QTextCursor.End)
            window.activateWindow()
            code.setFocus()
            wait(100)
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
            wait(500)
            assert not completer.popup().isVisible(), label
            assert code.toPlainText() == source
            capture(label)
            result["checks"].append(label)

        for label, source in (
            ("imported module members", "import json\njson.du"),
            ("imported alias members", "import json as j\nj.du"),
            ("explicitly imported function", "from json import dumps\ndu"),
        ):
            popup(source, "dumps")
            capture(label)
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
            wait(100)
            assert code.toPlainText() == source[:-2] + "dumps"
            assert code.hasFocus()
            result["checks"].append(label)

        for label, source, expected in (
            ("function local", 'def build():\n    scene_name = "test"\n    sce', "scene_name"),
            ("function argument", 'def build(scene_argument):\n    sce', "scene_argument"),
            ("loop binding", 'for scene_item in objects:\n    sce', "scene_item"),
            ("module binding", 'scene_name = "test"\nsce', "scene_name"),
        ):
            popup(source, expected)
            capture(label + " candidate")
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
            wait(150)
            assert code.toPlainText() == source[:-3] + expected, code.toPlainText()
            assert code.hasFocus()
            assert not completer.popup().isVisible()
            capture(label + " accepted without newline")
            result["checks"].append(label + ": candidate + Enter preserves line count and focus")

        # 完全一致・似た候補が同時にある場合も、確定と改行を別々の操作として扱う。
        for target in ("editor", "popup"):
            for delay in (0, 150):
                source = 'scene_name = "a"\nscene_name_other = "b"\nscene_name'
                popup(source, "scene_name")
                wait(delay)
                capture("exact match before Enter: " + target)
                QtTest.QTest.keyClick(code if target == "editor" else completer.popup(), QtCore.Qt.Key_Return)
                wait(150)
                assert code.toPlainText() == source, code.toPlainText()
                assert not completer.popup().isVisible()
                assert code.hasFocus()
                QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
                wait(100)
                assert code.toPlainText() == source + "\n", code.toPlainText()
                capture("second Enter creates one newline")
                result["checks"].append("exact match %s delay=%d: first Enter accepts, second adds one newline" % (target, delay))

        popup('scene_name = 1\nsce', "scene_name")
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Tab)
        wait(100)
        assert code.toPlainText() == 'scene_name = 1\nscene_name'
        result["checks"].append("Tab accepts without newline")
        popup('scene_name = 1\nsce', "scene_name")
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Escape)
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
        wait(100)
        assert code.toPlainText() == 'scene_name = 1\nsce\n'
        result["checks"].append("Escape cancels; normal Enter adds newline")
        # 呼出し引数候補は確定時に「=」まで入力し、改行や重複した「=」を入れない。
        signature_source = 'def build(path, /, name="demo", count=2, *, enabled=True):\n    pass\n'
        for key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Tab):
            popup(signature_source + 'build(co', 'count=')
            capture("keyword argument candidate count=")
            QtTest.QTest.keyClick(code, key)
            wait(150)
            assert code.toPlainText() == signature_source + 'build(count=', code.toPlainText()
            result["checks"].append("keyword argument accepted without newline: %s" % key)
        existing_equals = signature_source + 'build(co=2)'
        popup(existing_equals, 'count=', existing_equals.rfind('co=') + 2)
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
        wait(150)
        assert code.toPlainText() == signature_source + 'build(count=2)', code.toPlainText()
        result["checks"].append("keyword completion reuses existing equals")
        popup('scene_name = "test"; sce', 'scene_name')
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
        assert code.toPlainText() == 'scene_name = "test"; scene_name', code.toPlainText()
        capture("same-line local accepted")
        result["checks"].append("same-line variable accepted")

        # 解決応答を待たずに確定し、直後の入力を失わないことを確認する。
        for key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Tab):
            popup('scene_name = "test"\nsce', 'scene_name')
            QtTest.QTest.keyClick(code, key)
            assert code.toPlainText().endswith('\nscene_name'), code.toPlainText()
            QtTest.QTest.keyClicks(code, '+1')
            wait(300)
            assert code.toPlainText() == 'scene_name = "test"\nscene_name+1', code.toPlainText()
            result["checks"].append("completion commits before immediate following input: %s" % key)

        # f文字列では補間式だけ通常のコードと同じ入力支援を行う。
        for quote in ('"', "'"):
            completer.popup().hide()
            source = 'scene_name = "test"\nresult = f' + quote + '{}' + quote
            code.setPlainText(source)
            cursor = code.textCursor()
            cursor.setPosition(len(source) - 2)
            code.setTextCursor(cursor)
            window.activateWindow()
            code.setFocus()
            QtTest.QTest.keyClicks(code, 'sce', QtCore.Qt.NoModifier, 60)
            wait(500)
            model = completer.completionModel()
            names = [model.index(row, 0).data() for row in range(model.rowCount())]
            assert completer.popup().isVisible() and 'scene_name' in names, names
            completer.popup().setCurrentIndex(model.index(names.index('scene_name'), 0))
            capture("automatic f-string variable completion: " + quote)
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
            wait(150)
            assert code.toPlainText() == source[:-2] + 'scene_name' + source[-2:], code.toPlainText()
            result["checks"].append("automatic f-string suggestion and Enter: " + quote)

        for prefix, typed, expected in (
            ('f', '"{(\'\'', 'f"{(\'\')}"'),
            ('f', "'{(\"\"", "f'{(\"\")}'"),
            ('f"{{literal', '(', 'f"{{literal()'),
            ('f"{value:>10', '(', 'f"{value:>10()'),
            ('f"{value:{', '(', 'f"{value:{()'),
        ):
            completer.popup().hide()
            code.setPlainText(prefix)
            code.moveCursor(QtGui.QTextCursor.End)
            code.setFocus()
            QtTest.QTest.keyClicks(code, typed, QtCore.Qt.NoModifier, 80)
            wait(150)
            assert code.toPlainText() == expected, (prefix, typed, code.toPlainText(), expected)
            capture("f-string quotes and brackets")
            result["checks"].append("f-string pairs: %r + %r" % (prefix, typed))

        # 同じf文字列の中で本文と変数に別の色が付き、編集後の再描画も追従する。
        completer.popup().hide()
        code.setPlainText('scene_name = "test"\nresult = f"label {scene_name}"')
        wait(300)
        block = code.document().lastBlock()
        ranges = block.layout().formats()
        def color_at(column):
            """描画用レイアウトの文字色を取得する。"""
            return next((item.format.foreground().color().name() for item in ranges
                         if item.start <= column < item.start + item.length), None)
        literal_color = color_at(block.text().index('label'))
        variable_color = color_at(block.text().index('scene_name'))
        assert literal_color and variable_color and literal_color != variable_color, (literal_color, variable_color)
        capture("f-string literal and expression have distinct colors")
        result["checks"].append("f-string expression highlighted separately from literal")

        code.setPlainText(signature_source + 'result = f"{build(1, count=)}"')
        cursor = code.textCursor()
        cursor.setPosition(code.toPlainText().rfind('count=') + len('count='))
        code.setTextCursor(cursor)
        code.setFocus()
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier)
        wait(300)
        help_widget = code.findChild(QtWidgets.QWidget, 'signatureHelp')
        assert help_widget and help_widget.isVisible(), 'signature help missing in f-string'
        capture("signature help inside f-string call")
        result["checks"].append("signature help visible inside f-string expression")
        # 表示する引数ヒントも候補と同じ束縛規則を使う。
        binding_source = ("class Builder:\n    def make(self, count=2): pass\n"
                          "    @staticmethod\n    def static(self=1): pass\n"
                          "    @classmethod\n    def create(cls, size=2): pass\nb = Builder()\n")
        for call, included, excluded in (
            ("b.make(", "count", "self"),
            ("Builder.make(", "self", None),
            ("b.static(", "self", None),
            ("Builder.create(", "size", "cls"),
        ):
            code.setPlainText(binding_source + call)
            code.moveCursor(QtGui.QTextCursor.End)
            code.setFocus()
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier)
            wait(300)
            help_widget = code.findChild(QtWidgets.QWidget, "signatureHelp")
            assert help_widget and help_widget.isVisible(), call
            html = " ".join(view.toPlainText() for view in help_widget.findChildren(QtWidgets.QTextBrowser))
            assert included in html and (excluded is None or excluded not in html), (call, html)
            capture("signature binding: " + call)
            result["checks"].append("signature binding: " + call)
        result["status"] = "passed"
    except Exception:
        result["error"] = traceback.format_exc()
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    finished(result)
