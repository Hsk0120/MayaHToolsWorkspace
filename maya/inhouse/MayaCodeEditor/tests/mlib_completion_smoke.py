"""実行前のmlibの戻り値補完と、Maya起動後の検索パス更新を専用GUIで検証する。"""
import json
import os
from pathlib import Path
import sys
import time
import traceback


def main(output_dir, finished):
    """ユーザー設定を変更せず、Qt入力・候補・画像連番を記録する。

    Args:
        output_dir (Path): 専用Mayaの証拠先。
        finished (callable): 結果をランナーへ返す通知。
    """
    from maya import cmds
    try:
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
        action_type = QtGui.QAction
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets, QtTest
        action_type = QtWidgets.QAction
    sys.path.insert(0, str(Path(__file__).parent))
    import gui_host

    output = Path(output_dir)
    root = Path(os.environ["MCE_PROJECT_ROOT"])
    (root / "pyrightconfig.json").write_text(json.dumps({"include": ["*.py"], "typeCheckingMode": "basic"}), encoding="utf-8")
    result = {"status": "error", "checks": [], "input_kind": "Qt QTest in dedicated Maya; no source execution"}
    original_paths = list(sys.path)
    frames = output / "recording"
    frames.mkdir(exist_ok=True)
    frame_number = [0]
    chapter = ["Waiting for type analysis"]
    recorder = None

    def wait(milliseconds):
        """Mayaのイベントを処理しながら待つ。"""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    def check(name, passed, detail=None):
        """合否と証拠を保存し、失敗時は処理を止める。"""
        result["checks"].append({"name": name, "passed": bool(passed), "detail": detail})
        (output / "progress.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if not passed:
            raise AssertionError(name + ": " + str(detail))

    try:
        # 起動後にライブラリを追加する環境を再現する。ユーザーのsys.pathには触れない。
        library = output / "late_library"
        library.mkdir(exist_ok=True)
        (library / "mce_late_module.py").write_text(
            'class Result:\n    def late_member(self): pass\ndef query() -> Result: ...\n'
            'raise RuntimeError("completion must not execute this file")\n', encoding="utf-8")
        cmds.loadPlugin("mayaCodeEditor", quiet=True)
        cmds.mayaCodeEditor(show=True)
        window = gui_host.editor()
        code = window.findChild(QtWidgets.QPlainTextEdit, "codeEditor")
        completer = code.findChild(QtWidgets.QCompleter)
        window.resize(1100, 760)
        window.findChild(QtWidgets.QSplitter, "editorSplitter").widget(0).hide()
        font = code.font()
        font.setPixelSize(18)
        code.setFont(font)
        wait(8000)
        window.window().raise_()
        window.window().activateWindow()
        QtWidgets.QApplication.setActiveWindow(window.window())
        code.setFocus()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if any(label.property("languageStatus") == "Type analysis ready" for label in window.findChildren(QtWidgets.QLabel)):
                break
            wait(100)
        check("type_analysis_ready", time.monotonic() < deadline)

        def capture():
            """エディターと所有ポップアップだけを撮影する。"""
            canvas = QtGui.QPixmap(1200, 900)
            canvas.fill(QtGui.QColor("#202020"))
            painter = QtGui.QPainter(canvas)
            painter.drawPixmap(0, 30, window.grab())
            origin = window.mapToGlobal(QtCore.QPoint(0, 0))
            for widget in [completer.popup()] + window.findChildren(QtWidgets.QFrame, "completionDetail"):
                if widget.isVisible():
                    point = widget.mapToGlobal(QtCore.QPoint(0, 0)) - origin
                    painter.drawPixmap(point.x(), point.y() + 30, widget.grab())
            painter.setPen(QtGui.QColor("white"))
            painter.drawText(12, 22, "Maya " + cmds.about(version=True) + " / Qt GUI test / " + chapter[0])
            painter.end()
            canvas.save(str(frames / ("%05d.png" % frame_number[0])))
            frame_number[0] += 1

        recorder = QtCore.QTimer(window)
        recorder.timeout.connect(capture)
        recorder.start(200)

        def candidates():
            """表示モデルの候補を読む。"""
            model = completer.popup().model()
            return [model.index(index, 0).data() for index in range(model.rowCount())]

        def suggest(source, expected=None):
            """末尾のドットを入力し、自動補完を待つ。"""
            completer.popup().hide()
            code.setPlainText(source[:-1])
            code.moveCursor(QtGui.QTextCursor.End)
            window.window().activateWindow()
            QtWidgets.QApplication.setActiveWindow(window.window())
            code.setFocus()
            wait(100)
            QtTest.QTest.keyClicks(code, ".")
            check("input_received", code.toPlainText() == source and code.hasFocus(),
                  {"text": code.toPlainText(), "focus": code.hasFocus()})
            deadline = time.monotonic() + (45 if expected else 3)
            while time.monotonic() < deadline:
                wait(100)
                if expected and completer.popup().isVisible() and expected in candidates():
                    break
            wait(500)
            return candidates() if completer.popup().isVisible() else []

        source = 'import mlib\n\njoint = mlib.ls(sl=True, type="joint")\njoint.'
        chapter[0] = "Library added after editor startup"
        late_source = 'import mce_late_module\nvalue = mce_late_module.query()\nvalue.'
        initial = suggest(late_source)
        check("initial_library_missing", "late_member" not in initial, initial)
        sys.path.insert(0, str(library))
        refresh = next(action for action in window.findChildren(action_type)
                       if action.text().replace("&", "").lower() == "refresh completion")
        refresh.trigger()
        wait(1500)
        names = suggest(late_source, "late_member")
        check("library_after_path_refresh", "late_member" in names, names)
        check("late_library_not_executed", "mce_late_module" not in sys.modules)
        chapter[0] = "Refresh completion: ls(type=joint) without executing"
        names = suggest(source, "getSkinClusters")
        check("mlib_ls_after_path_refresh", "getSkinClusters" in names and "setRadius" in names, names)
        check("source_not_imported", "mlib" not in sys.modules)
        wait(2000)
        row = names.index("getSkinClusters")
        completer.popup().setCurrentIndex(completer.popup().model().index(row, 0))
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
        check("enter_accepts_without_newline", code.toPlainText() == source + "getSkinClusters", code.toPlainText())

        cases = [
            ("import_alias", 'import mlib as ml\nvalue = ml.ls(sl=True, type="joint")\nvalue.', "getSkinClusters"),
            # 現行mlibスタブはtypeだけをLiteralで絞る。typでは汎用候補の維持を確認する。
            ("short_flag_generic_fallback", 'import mlib\nvalue = mlib.ls(sl=True, typ="joint")\nvalue.', "copy"),
            ("from_import", 'from mlib import ls\nvalue = ls(type="joint")\nvalue.', "setRadius"),
            ("loop_element", 'import mlib\nfor value in mlib.ls(type="joint"):\n    value.', "getJointOrient"),
            ("indexed_element", 'import mlib\nvalue = mlib.ls(type="joint")[0]\nvalue.', "getJointOrient"),
            ("skin_cluster_type", 'import mlib\nvalue = mlib.ls(type="skinCluster")[0]\nvalue.', "getWeights"),
        ]
        for name, text, expected in cases:
            chapter[0] = name
            names = suggest(text, expected)
            check(name, expected in names, names)
            if name == "skin_cluster_type":
                check("no_joint_members_on_skin_clusters", "setRadius" not in names)
            wait(800)
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Escape)
        wait(200)
        check("escape_closes", not completer.popup().isVisible())
        result["status"] = "passed"
    except BaseException:
        result["error"] = traceback.format_exc()
    finally:
        sys.path[:] = original_paths
        if recorder is not None:
            recorder.stop()
        result["frames"] = frame_number[0]
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        finished(result)
