"""整理機能のUI、要求世代、タブ永続化を専用データで検証する。"""
import json
import os
import sys
import threading
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtGui, QtWidgets, QtTest
from qpe_ui_maya import pause, waitFor, selectFile


def main(output_dir, finished=None):
    """スタンドアロンと隔離Mayaの両方で同じ操作を検証する。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    checks = []
    e = None
    try:
        from quickPathExplorer import Explorer
        from qpeSettings import readSettings, writeSettings
        import qpeTools
        folder = out / 'Assets'
        target = out / 'Destination'
        folder.mkdir(exist_ok=True)
        target.mkdir(exist_ok=True)
        (folder / 'notes.txt').write_text('notes', encoding='utf8')
        (folder / '.hidden.txt').write_text('hidden', encoding='utf8')
        (folder / 'sub').mkdir(exist_ok=True)
        (folder / 'sub' / 'nested.ma').write_text('//Maya ASCII 2027 scene', encoding='utf8')
        e = Explorer(maya=bool(finished))
        e.show()
        e.navigate(str(folder))
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1)
        e.organizer.setHidden(True)
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 2)
        e.organizer.setHidden(False)
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1)
        checks.append('hidden toggle refreshes generation-managed model')
        e.organizer.populateTools()
        menu = e.createFileMenu([str(folder / 'notes.txt')])
        assert any(a.text() == 'Copy' for a in menu.actions())
        selectFile(e, folder / 'notes.txt')
        e.window().raise_()
        e.window().activateWindow()
        QtWidgets.QApplication.setActiveWindow(e.window())
        pause(150)
        e.files.setFocus()
        waitFor(lambda: QtWidgets.QApplication.focusWidget() is e.files)
        QtTest.QTest.keyClick(e.files, QtCore.Qt.Key_C, QtCore.Qt.ControlModifier)
        urls = QtWidgets.QApplication.clipboard().mimeData().urls()
        assert [Path(url.toLocalFile()) for url in urls] == [folder / 'notes.txt'], {
            'urls': [url.toString() for url in urls],
            'status': e.status.text(), 'selected': e.selectedPaths(),
            'focus': repr(QtWidgets.QApplication.focusWidget()),
            'active': e.isActiveWindow(),
            'clipboard': QtWidgets.QApplication.clipboard().text()}
        e.navigate(str(target))
        e.organizer.paste(str(target))
        waitFor(lambda: e.organizer.task is None)
        assert (target / 'notes.txt').read_text() == 'notes'
        e.organizer.undo()
        waitFor(lambda: e.organizer.task is None)
        assert not (target / 'notes.txt').exists()
        checks.append('actual Ctrl+C, paste worker, filesystem result and Undo')
        e.search.setText('abc')
        e.search.setFocus()
        QtTest.QTest.keyClick(e.search, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        QtTest.QTest.keyClick(e.search, QtCore.Qt.Key_X, QtCore.Qt.ControlModifier)
        assert not e.search.text() and QtWidgets.QApplication.clipboard().text() == 'abc'
        checks.append('text editing shortcuts remain native')
        e.navigate(str(folder))
        dialog = e.organizer.search()
        dialog.query.setText('nested')
        dialog.types.setText('*.ma')
        dialog.search()
        waitFor(lambda: dialog.task is None)
        assert dialog.results.topLevelItemCount() == 1
        dialog.locate(dialog.results.topLevelItem(0))
        waitFor(lambda: Path(e.selectedPath()) == folder / 'sub' / 'nested.ma')
        checks.append('recursive search result locates its actual directory')
        import qpeAdvancedIO
        original = qpeAdvancedIO.searchAdvanced
        gate = threading.Event()

        def delayed(**kwargs):
            """旧要求の完了を意図的に新要求の後へ回す。"""
            if kwargs['query'] == 'old':
                gate.wait(3)
                return dict(paths=[str(folder / 'notes.txt')], errors=[])
            return dict(paths=[str(folder / 'sub' / 'nested.ma')], errors=[])
        qpeAdvancedIO.searchAdvanced = delayed
        try:
            dialog.query.setText('old')
            dialog.search()
            pause(60)
            dialog.query.setText('new')
            dialog.search()
            waitFor(lambda: dialog.task is None)
            gate.set()
            pause(150)
            assert dialog.results.topLevelItem(0).text(0) == 'nested.ma'
            checks.append('out-of-order search result rejected')
        finally:
            gate.set()
            qpeAdvancedIO.searchAdvanced = original
        dialog.close()
        e.navigate(str(folder))
        e.folderTabs.add()
        e.navigate(str(target))
        pause(150)
        e.folderTabs.saveSession()
        session = readSettings()[e._settingsKey + 'Tabs']
        e.folderTabs.close(1)
        e.folderTabs.reopen()
        assert Path(e.currentDirectory) == target
        assert e.folderTabs.restoreSession(session)
        assert e.folderTabs.bar.count() == 2 and Path(e.currentDirectory) == target
        checks.append('serialized tab session, closed tab restore and saved selection')
        writeSettings({'savedSearches': {'Scenes': dict(root=str(folder), query='', extensions='*.ma', days=0)}})
        e._placeRefreshTimer.stop()
        e._loadPlaces()
        favorites = e.places.topLevelItem(0)
        assert any(favorites.child(i).text(0) == 'Search: Scenes' for i in range(favorites.childCount()))
        checks.append('saved searches appear within Favorites')
        e.organizer.toggleSecond()
        e.organizer.second.navigate(str(folder))
        assert Path(e.organizer.second.address.text()) == folder and Path(e.currentDirectory) == target
        checks.append('second pane navigates independently')
        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl.fromLocalFile(str(folder / 'notes.txt'))])
        viewport = e.files.viewport()
        enter = QtGui.QDragEnterEvent(QtCore.QPoint(20, 20), QtCore.Qt.CopyAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(viewport, enter)
        drop = QtGui.QDropEvent(QtCore.QPointF(20, 20), QtCore.Qt.CopyAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(viewport, drop)
        waitFor(lambda: e.organizer.task is None)
        assert (target / 'notes.txt').exists()
        e.organizer.undo()
        waitFor(lambda: e.organizer.task is None)
        checks.append('actual URL drop event shares copy and Undo backend')
        e.navigate(str(folder))
        e.organizer.batchRename([str(folder / 'notes.txt')])
        rename = e.organizer.dialogs[-1]
        fields = rename.findChildren(QtWidgets.QLineEdit)
        fields[2].setText('review_')
        button = next(b for b in rename.findChildren(QtWidgets.QPushButton) if b.text() == 'Apply rename')
        assert button.isEnabled()
        button.click()
        waitFor(lambda: e.organizer.task is None)
        assert (folder / 'review_notes.txt').exists()
        e.organizer.undo()
        waitFor(lambda: e.organizer.task is None)
        assert (folder / 'notes.txt').exists()
        checks.append('batch rename preview, apply and Undo through UI')
        if finished:
            e.readOptions.controls['import']['mode'].setCurrentIndex(1)
            e.readOptions.controls['import']['name'].setText('shot:asset')
            state = e.readOptions.snapshot()
            e.readOptions.controls['import']['name'].setText('other')
            e.readOptions.restore(state)
            assert e.readOptions.fileArguments('import', str(folder / 'scene.ma'))['namespace'] == ':shot:asset'
            checks.append('Maya namespace preset roundtrip')
            from maya import cmds
            from qpeSceneMetadata import saveCurrent
            cmds.file(new=True, force=True)
            cmds.polyCube(name='qpeSidecarProbe')
            scene = (folder / 'sidecar_scene.ma').as_posix()
            cmds.file(rename=scene)
            cmds.file(save=True, type='mayaAscii', force=True)
            saveCurrent(e)
            assert Path(scene + '.qpe.json').exists()
            assert Path(scene + '.qpe.png').exists()
            metadata = json.loads(Path(scene + '.qpe.json').read_text(encoding='utf8'))
            assert metadata['maya'] and metadata['scene'] == scene
            from qpeHost import perform
            before = readSettings().get('recents', [])
            e._actionPaths = [str(folder / 'missing.ma')]
            from unittest.mock import patch
            with patch.object(QtWidgets.QMessageBox, 'warning'):
                perform(e, 'open')
            assert readSettings().get('recents', []) == before
            e._actionPaths = [scene]
            perform(e, 'open')
            e._actionPaths = None
            assert scene in readSettings()['recents']
            checks.append('real Maya scene sidecar thumbnail and success-only Recent')
        from qpeMedia import relatedFrames
        for number in (1001, 1002, 1003):
            image = QtGui.QImage(120, 80, QtGui.QImage.Format_RGB32)
            image.fill(QtGui.QColor('#227788'))
            image.save(str(folder / ('tile.%s.png' % number)))
        assert len(relatedFrames(str(folder / 'tile.1001.png'))) == 3
        checks.append('sequence / UDIM related frame discovery; no internal playback window')
        e.organizer.toggleSecond()
        e.setInspectorVisible(True)
        pause(200)
        e.grab().save(str(out / 'organizer.png'))
        result = dict(status='passed', checks=checks)
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    finally:
        if e:
            for dialog in e.organizer.dialogs:
                dialog.close()
            e.close()
        pause(250)
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(sys.argv[1])
    QtCore.QThreadPool.globalInstance().waitForDone(5000)
    sys.exit(0 if result['status'] == 'passed' else 1)
