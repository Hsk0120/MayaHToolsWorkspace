"""ホストのショートカットとQPEの一覧操作が競合する条件を検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "maya/inhouse/QuickPathExplorer/python"))
from qpeQt import QAction, QtCore, QtGui, QtWidgets, QtTest
from qpe_ui_maya import pause, selectFile, waitFor


def main(output_dir, finished=None):
    """ホスト相当の競合Actionを置き、一覧と編集欄の入力境界を確認する。"""
    out = Path(output_dir).resolve()
    os.environ["QPE_SETTINGS_FILE"] = str(out / "settings.json")
    folder = out / "Files"
    folder.mkdir(parents=True)
    path = folder / "notes.txt"
    path.write_text("test", encoding="utf-8")
    from quickPathExplorer import Explorer
    e = Explorer(maya=bool(finished))
    checks = []
    calls = []
    events = []

    class InputTrace(QtCore.QObject):
        """検証時だけキー配送とフォーカスを記録し、処理は変更しない。"""

        def eventFilter(self, watched, event):
            """ホストと一覧のどちらに届いたかを記録する。"""
            if event.type() in (QtCore.QEvent.KeyPress, QtCore.QEvent.ShortcutOverride):
                focus = QtWidgets.QApplication.focusWidget()
                events.append({"target": watched.objectName(), "class": type(watched).__name__,
                               "kind": str(event.type()), "key": event.key(),
                               "focus": focus.objectName() if focus else None})
            return False

    trace = InputTrace(e)
    QtWidgets.QApplication.instance().installEventFilter(trace)
    try:
        e.show()
        e.navigate(str(folder))
        selectFile(e, path)
        e.raise_()
        e.activateWindow()
        QtWidgets.QApplication.setActiveWindow(e)
        pause(200)
        # Mayaや別の埋込みホストが同じWindowShortcutを持つ状況を再現する。
        for sequence in ("Ctrl+C", "Ctrl+Z", "Space", "Return"):
            action = QAction(e)
            action.setShortcut(QtGui.QKeySequence(sequence))
            action.setShortcutContext(QtCore.Qt.WindowShortcut)
            action.triggered.connect(lambda checked=False, key=sequence: calls.append(key))
            e.addAction(action)
        for mode in (0, 1, 2):
            workspace = e.organizer.workspace
            workspace.mode.setCurrentIndex(mode)
            view = (e.files, workspace.grid, workspace.tree)[mode]
            if mode:
                waitFor(lambda: not workspace.timer.isActive() and not workspace.restoring)
                waitFor(lambda: bool(workspace.items))
                if mode == 1:
                    waitFor(lambda: view.count() == 1)
                    view.setCurrentRow(0)
                else:
                    waitFor(lambda: view.topLevelItemCount() == 1)
                    view.setCurrentItem(view.topLevelItem(0))
                    view.topLevelItem(0).setSelected(True)
                assert [Path(value) for value in workspace.selected()] == [path]
            view.setFocus()
            waitFor(lambda: QtWidgets.QApplication.focusWidget() is view)
            QtWidgets.QApplication.clipboard().clear()
            with patch.object(e.organizer, "clipboard", wraps=e.organizer.clipboard) as copied:
                QtTest.QTest.keyClick(view, QtCore.Qt.Key_C, QtCore.Qt.ControlModifier)
                assert copied.call_count == 1, (mode, copied.call_count)
            urls = QtWidgets.QApplication.clipboard().mimeData().urls()
            assert [Path(url.toLocalFile()) for url in urls] == [path], (mode, calls)
            assert not calls, calls
            checks.append(f"mode {mode}: Copy reaches QPE exactly once, host action remains idle")
            with patch.object(e.organizer, "undo") as undo:
                QtTest.QTest.keyClick(view, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
                assert undo.call_count == 1
            with patch.object(e, "openSelectedFile") as opened:
                QtTest.QTest.keyClick(view, QtCore.Qt.Key_Space)
                assert opened.call_count == 1
            with patch.object(e, "renamePath") as renamed:
                QtTest.QTest.keyClick(view, QtCore.Qt.Key_Return)
                assert renamed.call_count == 1
            assert QtWidgets.QApplication.focusWidget() is view
            assert not calls, calls
            checks.append(f"mode {mode}: Undo / Open / Rename stay inside the focused list")
        e.search.setText("text edit")
        e.search.setFocus()
        e.search.selectAll()
        QtTest.QTest.keyClick(e.search, QtCore.Qt.Key_C, QtCore.Qt.ControlModifier)
        assert QtWidgets.QApplication.clipboard().text() == "text edit"
        assert not calls, calls
        checks.append("search field retains native text Copy")
        # QPEの子でも一覧外ではホスト側の操作を奪わない。
        outside = QtWidgets.QWidget(e)
        outside.setFocusPolicy(QtCore.Qt.StrongFocus)
        outside.show()
        outside.setFocus()
        waitFor(lambda: QtWidgets.QApplication.focusWidget() is outside)
        QtTest.QTest.keyClick(outside, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
        assert calls == ["Ctrl+Z"], calls
        checks.append("outside lists, host Undo shortcut remains available")
        result = {"status": "passed", "checks": checks}
    except Exception:
        result = {"status": "error", "checks": checks, "error": traceback.format_exc()}
    finally:
        QtWidgets.QApplication.instance().removeEventFilter(trace)
        result["input_events"] = events
        e.close()
        e.deleteLater()
        pause(150)
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if finished:
        finished(result)
    return result
