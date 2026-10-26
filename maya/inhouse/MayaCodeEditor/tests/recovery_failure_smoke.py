"""保存不能の警告・再試行・破棄と再生成を専用Mayaで確認する。"""
import json
from pathlib import Path
import sys
import traceback


def main(output_dir, finished):
    """専用GUIの復元先だけを一時的に書込不能にし、元に戻して再試行する。"""
    # Maya外のランナーからはQtを読み込まない。
    from maya import cmds
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gui_host
    from recovery_gui import heads

    output = Path(output_dir).resolve()
    result = {"status": "error", "checks": []}

    def wait(ms):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    try:
        cmds.loadPlugin("mayaCodeEditor", quiet=True)
        cmds.mayaCodeEditor(show=True, floating=True)
        path = Path(cmds.mayaCodeEditor(sessionPath=True)).resolve()
        # ユーザーの保存先で障害試験をしない。
        if output not in path.parents:
            raise ValueError("Recovery failure test requires a disposable profile inside output_dir")
        window = gui_host.editor()
        tabs = window.findChild(QtWidgets.QTabWidget)
        code = tabs.currentWidget()
        code.setPlainText("before_failure = True\n")
        before = window.property("sessionWrites")
        directory = Path(str(path) + ".recovery/snapshots")
        held = directory.with_name("snapshots-held")
        directory.rename(held)
        directory.write_text("block commit", encoding="utf-8")
        try:
            code.insertPlainText("during_failure = True\n")
            expected = code.toPlainText()
            warning = window.findChild(QtWidgets.QLabel, "recoveryStatus")
            assert warning.isVisible()
            assert window.property("sessionWrites") == before
            code.setTextCursor(code.textCursor())
            wait(200)
            assert warning.isVisible()
            window.grab().save(str(output / "save-failed.png"))
            result["checks"].append("failed_commit_not_marked_saved_and_warning_persists")
        finally:
            directory.unlink()
            held.rename(directory)
        for _ in range(50):
            if not warning.isVisible():
                break
            wait(200)
        assert not warning.isVisible()
        assert expected in heads(path)
        result["checks"].append("retry_saved_current_text_and_cleared_warning")
        # 元のUIを破棄して作り直しても、同じ確定本文を読む。
        cmds.unloadPlugin("mayaCodeEditor")
        cmds.loadPlugin("mayaCodeEditor", quiet=True)
        cmds.mayaCodeEditor(show=True, floating=False)
        wait(600)
        # 破棄直後のアドレスが再利用される場合、findChildのキャッシュに古いラッパーが残る。
        live = gui_host.editor()
        rebuilt = next(widget for widget in QtWidgets.QApplication.allWidgets()
                       if isinstance(widget, QtWidgets.QTabWidget) and live.isAncestorOf(widget))
        assert rebuilt.currentWidget().toPlainText() == expected
        result["checks"].append("unload_recreate_docked_preserved_text")
        result["status"] = "passed"
    except Exception:
        result["error"] = traceback.format_exc()
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    finished(result)
