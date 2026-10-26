"""実ドック内の改名終了後に、次のキー入力が正しい対象へ届くか検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback


def main(output_dir, finished):
    """改名確定・取消・別欄への移動を隔離Mayaで操作する。"""
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    sys.path.insert(0, str(root / "maya/inhouse/QuickPathExplorer/python"))
    from qpeQt import QtCore, QtWidgets, QtTest
    from qpe_ui_maya import pause, selectFile, waitFor
    import qpeHost

    out = Path(output_dir)
    os.environ["QPE_SETTINGS_FILE"] = str(out / "settings.json")
    folder = out / "Files"
    folder.mkdir()
    source = folder / "sample.txt"
    target = folder / "renamed.txt"
    source.write_text("protected file contents", encoding="utf-8")
    checks = []
    try:
        e = qpeHost.show(str(folder))
        e.window().activateWindow()
        QtWidgets.QApplication.setActiveWindow(e.window())
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1)
        selectFile(e, source)
        e.files.setFocus()
        waitFor(lambda: QtWidgets.QApplication.focusWidget() is e.files)
        QtTest.QTest.keyClick(e.files, QtCore.Qt.Key_F2)
        editor = e._inlineRename
        waitFor(lambda: QtWidgets.QApplication.focusWidget() is editor)
        editor.setText(target.name)
        QtTest.QTest.keyClick(editor, QtCore.Qt.Key_Return)
        waitFor(lambda: target.exists() and Path(e.selectedPath()) == target)
        pause(200)
        assert QtWidgets.QApplication.focusWidget() is e.files, repr(QtWidgets.QApplication.focusWidget())
        assert target.read_text(encoding="utf-8") == "protected file contents"
        checks.append("Enter commits rename and retains list focus")
        # 実際の現在入力先へ送る。明示setFocusによる不具合の隠蔽をしない。
        QtTest.QTest.keyClick(QtWidgets.QApplication.focusWidget(), QtCore.Qt.Key_F2)
        second = e._inlineRename
        waitFor(lambda: QtWidgets.QApplication.focusWidget() is second)
        second.setText("cancelled.txt")
        QtTest.QTest.keyClick(second, QtCore.Qt.Key_Escape)
        pause(200)
        assert QtWidgets.QApplication.focusWidget() is e.files
        assert target.exists() and not (folder / "cancelled.txt").exists()
        checks.append("F2 works immediately after rename; Escape retains file and list focus")
        QtTest.QTest.keyClick(e.files, QtCore.Qt.Key_F2)
        third = e._inlineRename
        waitFor(lambda: QtWidgets.QApplication.focusWidget() is third)
        third.setText("clicked.txt")
        QtTest.QTest.mouseClick(e.search, QtCore.Qt.LeftButton)
        waitFor(lambda: (folder / "clicked.txt").exists())
        pause(200)
        assert QtWidgets.QApplication.focusWidget() is e.search
        QtTest.QTest.keyClicks(e.search, "clicked")
        assert e.search.text() == "clicked"
        checks.append("Clicking search commits rename without stealing search focus")
        result = {"status": "passed", "checks": checks}
    except Exception:
        result = {"status": "error", "checks": checks, "error": traceback.format_exc()}
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    finished(result)
