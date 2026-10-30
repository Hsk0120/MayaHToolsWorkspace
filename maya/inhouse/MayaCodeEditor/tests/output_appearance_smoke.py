"""専用Mayaで出力の行頭着色、通知種別の保持、独立ズームを検証する。"""
import json
from pathlib import Path
import sys
import traceback


def main(output_dir, finished):
    """専用GUIランナーから実行し、結果・実画面・録画フレームを保存する。

    Args:
        output_dir (str): 使い捨てGUIの結果フォルダー。
        finished (callable): 結果を渡して専用GUIを終了する関数。
    """
    from maya import cmds, OpenMaya
    try:
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets, QtTest
    sys.path.insert(0, str(Path(__file__).parent))
    import gui_host

    directory = Path(output_dir)
    result = {"status": "error", "checks": [], "input": "Qt/API; no native OS input"}
    recorder = None

    def wait(milliseconds=180):
        """遅延描画が進むよう、専用GUIのイベントループを有界で回す。"""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    try:
        cmds.loadPlugin("mayaCodeEditor", quiet=True)
        cmds.mayaCodeEditor(show=True, floating=True)
        window = gui_host.editor()
        output = window.findChild(QtWidgets.QPlainTextEdit, "output")
        code = window.findChild(QtWidgets.QPlainTextEdit, "codeEditor")
        action_type = getattr(QtWidgets, "QAction", None) or QtGui.QAction
        actions = {action.objectName(): action for action in window.findChildren(action_type)}
        clear = next(action for action in window.findChildren(action_type) if action.text() == "Clear output")
        modes = window.findChild(QtWidgets.QComboBox, "outputMode")
        prefs_path = Path(cmds.mayaCodeEditor(sessionPath=True)).with_name("preferences.json")
        QtWidgets.QApplication.setActiveWindow(window.window())
        cmds.workspaceControl(gui_host.CONTROL, edit=True, resizeWidth=1100, resizeHeight=760)
        wait(6000)
        clear.trigger()
        frames = directory / "frames"
        frames.mkdir(exist_ok=True)
        frame_count = [0]
        phase = ["Output appearance / real Maya widget / Qt test"]

        def capture():
            """検証中のエディターだけを撮影する。ユーザーの他の画面は含めない。"""
            canvas = QtGui.QPixmap(1200, 900)
            canvas.fill(QtGui.QColor("#333333"))
            painter = QtGui.QPainter(canvas)
            painter.setPen(QtGui.QColor("#eeeeee"))
            font = QtGui.QFont("Segoe UI")
            font.setPixelSize(18)
            painter.setFont(font)
            painter.drawText(16, 28, phase[0])
            painter.drawPixmap(16, 48, window.grab())
            painter.end()
            canvas.save(str(frames / ("%05d.png" % frame_count[0])))
            frame_count[0] += 1

        recorder = QtCore.QTimer()
        recorder.timeout.connect(capture)
        recorder.start(125)

        def check(name, condition):
            """不一致を名前付きで停止し、成功したケースを記録する。"""
            if not condition:
                raise AssertionError(name)
            result["checks"].append(name)

        def color(marker):
            """文書書式に重なるハイライトを含め、指定文字の表示色を読む。"""
            cursor = output.document().find(marker)
            if cursor.isNull():
                raise AssertionError("missing output: " + marker)
            position = cursor.selectionStart()
            block = output.document().findBlock(position)
            offset = position - block.position()
            actual = None
            for item in block.layout().formats():
                if item.start <= offset < item.start + item.length:
                    actual = item.format.foreground().color().name()
            return actual or cursor.charFormat().foreground().color().name()

        print("# Error: printed_error")
        print("// Error: mel_style_error")
        print("# Warning: printed_warning")
        print("// Warning: mel_style_warning")
        print("# Result: printed_result")
        print("// Result: mel_style_result")
        print("plain text with # Error: not_at_start")
        print(" # Error: indented_literal")
        OpenMaya.MGlobal.displayInfo("native_info")
        OpenMaya.MGlobal.displayWarning("native_warning\nwarning_continuation")
        OpenMaya.MGlobal.displayError("native_error\nerror_continuation")
        OpenMaya.MGlobal.executePythonCommand("print('history_marker')", True, False)
        wait(600)
        for marker, expected in (
            ("printed_error", "#f42828"), ("mel_style_error", "#f42828"),
            ("printed_warning", "#dfe527"), ("mel_style_warning", "#dfe527"),
            ("printed_result", "#2ab422"), ("mel_style_result", "#2ab422"),
            ("not_at_start", "#d4d4d4"), ("indented_literal", "#d4d4d4"),
            ("native_info", "#d4d4d4"), ("native_warning", "#dfe527"),
            ("warning_continuation", "#d4d4d4"), ("native_error", "#f42828"),
            ("error_continuation", "#d4d4d4"), ("print('history_marker')", "#d4d4d4"),
        ):
            check("color_" + marker, color(marker) == expected)
        print("# Err", end="")
        wait()
        print("or: fragmented_error")
        wait()
        check("split_print_prefix", color("fragmented_error") == "#f42828")
        print("normal_after_error")
        wait()
        check("no_color_leak", color("normal_after_error") == "#d4d4d4")
        check("frameless", output.frameWidth() == 0)
        check("margin_preserved", output.document().documentMargin() == 4)
        palette = output.palette()
        check("selection_background", palette.color(QtGui.QPalette.Highlight).name() == "#5285a6")
        check("selection_foreground", palette.color(QtGui.QPalette.HighlightedText).name() == "#ffffff")
        wait(700)
        window.grab().save(str(directory / "appearance.png"))

        phase[0] = "Filtering still uses real Maya message types"
        modes.setCurrentIndex(3)
        wait()
        text = output.toPlainText()
        check("filter_keeps_native_error_and_continuation", "native_error" in text and "error_continuation" in text)
        check("printed_prefix_not_reclassified", "printed_error" not in text and "fragmented_error" not in text)
        modes.setCurrentIndex(0)
        wait()
        check("prefix_survives_filter_rebuild", color("fragmented_error") == "#f42828")
        cursor = output.document().find("native_info")
        output.setTextCursor(cursor)
        output.verticalScrollBar().setValue(0)
        selection = output.textCursor().selectedText()
        text = output.toPlainText()
        phase[0] = "Optional info/history colors; text and selection preserved"
        actions["option_outputDetailColors"].setChecked(True)
        wait()
        check("optional_info_color", color("native_info") == "#9cdcfe")
        check("optional_history_color", color("print('history_marker')") == "#a0a0a0")
        check("recolor_preserves_selection_and_text", output.textCursor().selectedText() == selection and output.toPlainText() == text)
        actions["option_outputDetailColors"].setChecked(False)
        wait()
        check("colors_reset", color("native_info") == "#d4d4d4")

        phase[0] = "Output zoom is independent of the code editor"
        code_size = code.font().pixelSize()
        initial_output_size = output.font().pixelSize()
        actions["outputZoomIn"].trigger()
        wait()
        check("independent_output_zoom", output.font().pixelSize() > initial_output_size and code.font().pixelSize() == code_size)
        check("output_zoom_saved", json.loads(prefs_path.read_text(encoding="utf-8"))["outputFontPixels"] == 13)
        output.setFocus()
        wait()
        wheel = QtGui.QWheelEvent(QtCore.QPointF(10, 10), QtCore.QPointF(10, 10), QtCore.QPoint(), QtCore.QPoint(0, 120), QtCore.Qt.NoButton, QtCore.Qt.ControlModifier, QtCore.Qt.NoScrollPhase, False)
        QtWidgets.QApplication.sendEvent(output.viewport(), wheel)
        wait()
        check("ctrl_wheel_output_zoom", json.loads(prefs_path.read_text(encoding="utf-8"))["outputFontPixels"] == 14 and code.font().pixelSize() == code_size)
        actions["zoomReset"].trigger()
        wait()
        check("focused_reset_output_only", output.font().pixelSize() == initial_output_size and code.font().pixelSize() == code_size)
        code.setFocus()
        wait()
        actions["zoomIn"].trigger()
        wait()
        check("code_zoom_does_not_change_output", code.font().pixelSize() > code_size and output.font().pixelSize() == initial_output_size)
        actions["zoomReset"].trigger()
        actions["outputZoomIn"].trigger()
        saved = json.loads(prefs_path.read_text(encoding="utf-8"))
        check("both_sizes_saved_separately", saved["fontPixels"] == 14 and saved["outputFontPixels"] == 13)
        actions["outputZoomReset"].trigger()
        wait()
        check("explicit_output_reset", output.font().pixelSize() == initial_output_size)
        phase[0] = "Updated Output / default colors and 12px font"
        modes.setCurrentIndex(0)
        output.verticalScrollBar().setValue(0)
        wait(900)
        window.grab().save(str(directory / "final.png"))
        result["status"] = "passed"
        result["frame_count"] = frame_count[0]
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        if recorder is not None:
            recorder.stop()
    (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    finished(result)
