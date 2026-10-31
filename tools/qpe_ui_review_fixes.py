"""操作調査で見つかった検索・フォーカス・狭幅・再表示の回帰検証。"""
import json
import os
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_maya import ROOT, pause, waitFor, selectFile
from qpeQt import QtCore, QtWidgets, QtTest


def main(output_dir, finished=None):
    """専用設定と実ファイルでQt操作を検証し、OS実入力とは区別して保存する。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    root = out / 'Project'
    leaf = root / 'Assets/Characters/LongCharacterName/Rig/Work'
    (leaf / 'Child').mkdir(parents=True, exist_ok=True)
    (root / 'Library/Asset').mkdir(parents=True, exist_ok=True)
    file = leaf / 'long_file_name_for_layout_verification_01234567890123456789.txt'
    file.write_text('fixture', encoding='utf8')
    if finished:
        import qpeHost
        e = qpeHost.show(str(leaf))
    else:
        from quickPathExplorer import Explorer
        e = Explorer(maya=True)
        e.show()
        e.navigate(str(leaf))
    checks = []
    try:
        e.window().resize(1180, 820)
        e.setBrowseRoot(str(root))
        e.navigate(str(leaf))
        e.window().activateWindow()
        QtWidgets.QApplication.setActiveWindow(e.window())
        pause(450)
        selectFile(e, file)
        dialog = e.organizer.search()
        pause(100)
        assert QtWidgets.QApplication.focusWidget() is dialog.query
        assert not dialog.advancedToggle.isChecked()
        dialog.query.setText('long_file_name')
        QtTest.QTest.keyClick(dialog.query, QtCore.Qt.Key_Return)
        waitFor(lambda: dialog.results.topLevelItemCount() == 1 and dialog.task is None)
        assert dialog.results.height() >= 160
        assert dialog.results.topLevelItem(0).text(1) == '.'
        dialog.close()
        checks.append('UX01/02: query focus, Enter search, collapsed conditions, relative locations')
        e.address.setText(str(out / 'missing'))
        e.address.setFocus()
        QtTest.QTest.keyClick(e.address, QtCore.Qt.Key_Return)
        assert e.address.styleSheet()
        QtTest.QTest.keyClick(e.address, QtCore.Qt.Key_Escape)
        assert Path(e.address.text()) == leaf and not e.address.styleSheet()
        checks.append('UX03: invalid address Escape restores current location')
        e.window().activateWindow()
        QtWidgets.QApplication.setActiveWindow(e.window())
        e.columns.setFocus()
        pause(100)
        with patch.object(e, 'newFolder') as create:
            QtTest.QTest.keyClick(QtWidgets.QApplication.focusWidget(), QtCore.Qt.Key_N, QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier)
            assert create.call_count == 1, (create.call_count, QtWidgets.QApplication.focusWidget())
        checks.append('UX04: CtrlShiftN is handled once within columns')
        e.folderTabs.add()
        pause(200)
        from qpe_ui_maya import clickFolder
        clickFolder(e, root / 'Library')
        pause(120)
        for unused in range(4):
            before = e.folderTabs.active
            focus = QtWidgets.QApplication.focusWidget()
            QtTest.QTest.keyClick(focus, QtCore.Qt.Key_Tab, QtCore.Qt.ControlModifier)
            pause(120)
            assert e.folderTabs.active != before, (before, QtWidgets.QApplication.focusWidget())
        checks.append('BUG02: four consecutive tab switches retain browser keyboard ownership')
        e.retainBrowserFocus()
        e.address.setFocus()
        pause(120)
        assert QtWidgets.QApplication.focusWidget() is e.address
        outside = QtWidgets.QLineEdit()
        outside.show()
        outside.activateWindow()
        QtWidgets.QApplication.setActiveWindow(outside)
        outside.setFocus()
        e.retainBrowserFocus()
        pause(120)
        assert QtWidgets.QApplication.focusWidget() is outside
        outside.close()
        outside.deleteLater()
        e.window().activateWindow()
        QtWidgets.QApplication.setActiveWindow(e.window())
        checks.append('Focus boundary: pending restoration preserves address and external editor input')
        QtTest.QTest.mouseClick(e.folderTabs.bar, QtCore.Qt.MiddleButton, QtCore.Qt.NoModifier, e.folderTabs.bar.tabRect(1).center())
        assert e.folderTabs.bar.count() == 1
        e.navigate(str(leaf))
        checks.append('UX05: middle click closes target tab')
        e.fileName.setText('scene.ma')
        e._syncSaveExtension()
        assert e.fileName.text() == 'scene.mb'
        e.saveType.setCurrentIndex(e.saveType.findData('mayaAscii'))
        assert e.fileName.text() == 'scene.ma'
        checks.append('UX09: scene name extension follows selected format')
        e.sidebarButton.setChecked(True)
        e.inspectorButton.setChecked(True)
        e.window().resize(800, 820)
        pause(300)
        assert e.files.isColumnHidden(3)
        assert e.files.columnWidth(0) >= 150, e.files.columnWidth(0)
        selectFile(e, file)
        assert e.readTarget.toolTip() and 'SummaryLabel' in type(e.readTarget).__name__
        checks.append('UX06/07: name priority, middle elision and full target tooltip')
        e.window().resize(600, 820)
        pause(350)
        assert e.modern.inspectorPage and e.vertical.isHidden() and not e.actionsPanel.isHidden()
        horizontal = e.modern.pageHorizontal
        e.inspectorButton.setChecked(False)
        pause(200)
        assert not e.vertical.isHidden()
        waitFor(lambda: e._resumeHorizontal is None and abs(e.columns.horizontalScrollBar().value() - min(horizontal, e.columns.horizontalScrollBar().maximum())) <= 2)
        assert abs(e.columns.horizontalScrollBar().value() - min(horizontal, e.columns.horizontalScrollBar().maximum())) <= 2, (horizontal, e.columns.horizontalScrollBar().value(), e.columns.horizontalScrollBar().maximum(), e._resumeHorizontal)
        assert abs(e.places.width() - e._sidebarWidth) <= 2
        checks.append('UX08: narrow details page toggles back to browser')
        e.window().resize(850, 820)
        pause(250)
        bar = e.columns.horizontalScrollBar()
        bar.setValue(bar.maximum())
        before = bar.value()
        assert before > 0
        if finished:
            from maya import cmds
            cmds.workspaceControl(qpeHost.CONTROL, edit=True, visible=False)
            pause(100)
            qpeHost.show()
        else:
            e.hide()
            pause(100)
            e.show()
        pause(650)
        assert abs(bar.value() - before) <= 2, (before, bar.value())
        checks.append('UX13: hide/reopen preserves horizontal column position')
        if finished:
            from maya import cmds
            cmds.file(new=True, force=True)
            cmds.polyCube(name='QPE_ReviewCube')
            scene = leaf / 'review.ma'
            cmds.file(rename=str(scene))
            cmds.file(save=True, type='mayaAscii')
            cmds.file(new=True, force=True)
            e._resetFileModels()
            pause(250)
            e.requestFiles('open', [str(scene)])
            waitFor(lambda: e.selectedPath() and Path(e.selectedPath()) == scene)
            assert Path(cmds.file(query=True, sceneName=True)) == scene
            checks.append('UX11: Maya Open keeps opened file selected')
            e.requestFiles('import', [str(scene)])
            assert e.status.isVisible() and 'namespace:' in e.status.text(), e.status.text()
            cmds.file(new=True, force=True)
            e.requestFiles('reference', [str(scene)])
            assert e.status.isVisible() and 'Reference' in e.status.text(), e.status.text()
            checks.append('UX10: Import/Reference success and namespace are visible in QPE')
            import qpeDock
            qpeDock.saveState()
            saved = qpeDock.savedState()['geometry'][2:]
            cmds.workspaceControl(qpeHost.CONTROL, edit=True, dockToControl=('MainPane', 'right'))
            pause(650)
            cmds.workspaceControl(qpeHost.CONTROL, edit=True, floating=True)
            pause(750)
            frame = e.window().geometry()
            from qpeQt import shiboken
            diagnostics = dict(watcher=bool(qpeDock._watcher), saved=qpeDock.savedState(),
                               frame=[frame.x(), frame.y(), frame.width(), frame.height()],
                               screen_valid=shiboken.isValid(e.window().screen()),
                               refs=len(qpeDock._screenReferences))
            (out / 'dock-diagnostic.json').write_text(json.dumps(diagnostics), encoding='utf8')
            screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
            assert screen.contains(frame), (screen, frame)
            assert frame.width() <= saved[0] + 20 and frame.height() <= saved[1] + 20, (saved, frame)
            checks.append('UX12: isolated Maya dock/float restores bounded floating size')
        result = dict(status='passed', checks=checks)
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    e.grab().save(str(out / 'final.png'))
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    if finished:
        finished(result)
    else:
        e.close()
        e.deleteLater()
        pause(200)
    return result
