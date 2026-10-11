"""専用フォルダーと専用Maya GUIで主要操作を検証する。"""
import json
import os
import sys
import time
import traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtGui, QtWidgets, QtTest


def pause(milliseconds):
    """Qt5/Qt6共通のイベント待機。

    Args:
        milliseconds (int): 待機時間。
    """
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(milliseconds, loop.quit)
    loop.exec_()


def waitFor(predicate):
    """非同期モデルとプレビューの完了を待つ。

    Args:
        predicate (callable): 完了条件。
    """
    limit = time.monotonic() + 15
    while not predicate():
        if time.monotonic() > limit:
            raise AssertionError('Timed out waiting for UI')
        pause(30)


def selectFile(widget, path):
    """非同期モデル上のファイルを選択する。

    Args:
        widget (Explorer): 対象画面。
        path (Path): ファイル。
    """
    waitFor(lambda: widget.fileProxy.mapFromSource(widget.fileModel.index(str(path))).isValid())
    index = widget.fileProxy.mapFromSource(widget.fileModel.index(str(path)))
    widget.files.setCurrentIndex(index)
    assert Path(widget.selectedPath()) == path


def clickFolder(widget, path):
    """実クリックでフォルダーを選択し子カラムの内容を確認する。

    Args:
        widget (Explorer): 対象画面。
        path (Path): 選択先。
    """
    index = widget.folderModel.index(str(path))
    views = [v for v in widget.columns.findChildren(QtWidgets.QListView)
             if v.isVisible() and v.rootIndex() == index.parent()]
    assert views, str(path)
    view = views[-1]
    view.scrollTo(index)
    QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton,
                           QtCore.Qt.NoModifier, view.visualRect(index).center())
    waitFor(lambda: Path(widget.currentDirectory) == path)
    def childReady():
        """選択先をルートにする子カラムに実際の項目があるか。"""
        return any(v.isVisible() and v.rootIndex() == index and v.model().rowCount(index) > 0
                   and widget.columns.viewport().rect().intersects(QtCore.QRect(
                       v.mapTo(widget.columns.viewport(), QtCore.QPoint()), v.size()))
                   for v in widget.columns.findChildren(QtWidgets.QListView))
    waitFor(childReady)


def main(output_dir, finished=None):
    """本番画面とMaya操作を隔離環境で検証する。

    Args:
        output_dir (Path): 証跡保存先。
        finished (callable | None): Mayaランナーの終了通知。
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(output_dir / 'settings.json')
    import faulthandler
    crash_log = (output_dir / 'python-crash.log').open('w')
    faulthandler.enable(file=crash_log)
    checks = []
    try:
        from quickPathExplorer import Explorer
        folder = output_dir / 'project/assets/characters/hero/textures'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'notes.txt').write_text('QuickPathExplorer preview', encoding='utf8')
        (folder / 'empty.mb').write_bytes(b'preview only')
        image = QtGui.QImage(640, 400, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor('#42bdc7'))
        image.save(str(folder / 'hero_color.png'))
        if finished:
            from maya import cmds
            import qpeHost
            import runpy
            runpy.run_path(str(ROOT / 'maya/inhouse/QuickPathExplorer/scripts/userSetup.py'))
            pause(100)
            qpeHost.installMenu()
            assert cmds.menuItem(qpeHost.MENU, exists=True)
            assert cmds.menuItem(qpeHost.MENU, query=True, image=True).endswith('quickPathExplorer.png')
            callback = cmds.menuItem(qpeHost.MENU, query=True, command=True)
            if callable(callback):
                callback()
            else:
                exec(callback, {})
            pause(200)
            widget = qpeHost.show(str(folder))
            assert qpeHost.show() is widget
            checks.append('Window menu registration and single-instance dock')
        else:
            widget = Explorer()
            widget.show()
            widget.navigate(str(folder))
        assert widget.places.isHidden()
        assert not widget.sidebarButton.icon().isNull()
        widget.sidebarButton.click()
        assert not widget.places.isHidden()
        widget.sidebarButton.click()
        assert widget.places.isHidden()
        assert widget.lower.count() == 2
        checks.append('sidebar hidden by default, icon toggles both ways, combined action/details pane')
        pause(1000)
        waitFor(lambda: widget.fileProxy.rowCount(widget.files.rootIndex()) == 3)
        checks.append('folder-only columns / file-only list')
        widget.search.setText('hero')
        waitFor(lambda: widget.fileProxy.rowCount(widget.files.rootIndex()) == 1)
        widget.search.clear()
        waitFor(lambda: widget.fileProxy.rowCount(widget.files.rootIndex()) == 3)
        widget.fileFilter.setCurrentIndex(2)
        waitFor(lambda: widget.fileProxy.rowCount(widget.files.rootIndex()) == 1)
        widget.fileFilter.setCurrentIndex(0)
        waitFor(lambda: widget.fileProxy.rowCount(widget.files.rootIndex()) == 3)
        checks.append('filename search and extension filter')
        widget.addFavorite()
        widget.addFavorite()
        from qpeSettings import readSettings
        assert len(readSettings()['favorites']) == 1
        widget.navigate(str(folder.parent))
        widget._back()
        assert Path(widget.currentDirectory) == folder
        widget._forward()
        assert Path(widget.currentDirectory) == folder.parent
        widget.navigate(str(folder))
        selectFile(widget, folder / 'notes.txt')
        waitFor(lambda: widget.previewText.toPlainText() == 'QuickPathExplorer preview')
        selectFile(widget, folder / 'hero_color.png')
        waitFor(lambda: not widget._image.isNull())
        checks.append('favorites deduplication, history, text/image preview')
        assert not widget.columns.resizeGripsVisible()
        widget.columns.horizontalScrollBar().setValue(0)
        saved_widths = widget.columns.columnWidths()
        widget.navigate(str(folder.parent))
        widget.backButton.click()
        pause(350)
        assert Path(widget.address.text()) == folder
        assert widget.columns.horizontalScrollBar().value() == 0, (widget.columns.horizontalScrollBar().value(), widget.currentDirectory, widget._columnStates.get(os.path.normcase(widget.currentDirectory)))
        assert widget.columns.columnWidths() == saved_widths
        widget.forwardButton.click()
        assert Path(widget.currentDirectory) == folder.parent
        widget.address.setText(str(folder))
        widget.address.returnPressed.emit()
        pause(350)
        assert widget.columns.horizontalScrollBar().value() == 0, (widget.columns.horizontalScrollBar().value(), widget.currentDirectory, widget._columnStates.get(os.path.normcase(widget.currentDirectory)))
        widget.columns.setCurrentIndex(widget.folderModel.index(str(folder.parent)))
        assert Path(widget.currentDirectory) == folder.parent
        widget.navigate(str(folder))
        pause(350)
        assert widget.columns.horizontalScrollBar().value() == 0, (widget.columns.horizontalScrollBar().value(), widget.currentDirectory, widget._columnStates.get(os.path.normcase(widget.currentDirectory)))
        checks.append('path input, back/forward icons, hidden grips, revisit restores column position/widths')
        branches = output_dir / 'column-clicks'
        for name in ('branchA', 'branchB'):
            (branches / name / ('child_' + name) / 'leaf').mkdir(parents=True, exist_ok=True)
        widget.navigate(str(branches))
        pause(500)
        for name in ('branchA', 'branchB', 'branchA'):
            clickFolder(widget, branches / name)
            pause(100)
        deep = branches / 'branchA/child_branchA'
        (deep / '/'.join('level' + str(i) for i in range(9))).mkdir(parents=True, exist_ok=True)
        clickFolder(widget, deep)
        for number in range(8):
            deep = deep / ('level' + str(number))
            clickFolder(widget, deep)
            pause(100)
        widget.columns.horizontalScrollBar().setValue(0)
        widget.navigate(str(branches))
        widget.navigate(str(deep.parent))
        pause(100)
        clickFolder(widget, deep)
        pause(350)
        child_index = widget.folderModel.index(str(deep))
        assert any(v.isVisible() and v.rootIndex() == child_index
                   and widget.columns.viewport().rect().intersects(QtCore.QRect(
                       v.mapTo(widget.columns.viewport(), QtCore.QPoint()), v.size()))
                   for v in widget.columns.findChildren(QtWidgets.QListView))
        checks.append('actual mouse clicks update sibling and deeper child columns')
        widget.navigate(str(folder))

        selectFile(widget, folder / 'hero_color.png')
        waitFor(lambda: not widget._image.isNull())

        widget.copyPath()
        assert Path(QtWidgets.QApplication.clipboard().text()) == folder / 'hero_color.png'
        widget.grab().save(str(output_dir / 'browser.png'))
        if finished:
            cmds.file(new=True, force=True)
            cube = cmds.polyCube(name='qpeTestCube')[0]
            widget.fileName.setText('saved_scene')
            qpeHost.perform(widget, 'saveAs')
            scene = folder / 'saved_scene.ma'
            assert scene.is_file()
            cmds.setAttr(cube + '.translateX', 2)
            qpeHost.perform(widget, 'save')
            assert not cmds.file(query=True, modified=True)
            cmds.select(cube)
            widget.fileName.setText('exported')
            qpeHost.perform(widget, 'export')
            assert (folder / 'exported.ma').is_file()
            assert Path(cmds.file(query=True, sceneName=True)) == scene
            checks.append('Save As, Save and Export Selection actual Maya files')
            selectFile(widget, scene)
            cmds.setAttr(cube + '.translateX', 3)
            original = QtWidgets.QMessageBox.question
            QtWidgets.QMessageBox.question = lambda *args: QtWidgets.QMessageBox.Cancel
            try:
                qpeHost.perform(widget, 'open')
                assert cmds.getAttr(cube + '.translateX') == 3
                before = scene.read_bytes()
                qpeHost.perform(widget, 'saveAs')
                assert scene.read_bytes() == before
            finally:
                QtWidgets.QMessageBox.question = original
            checks.append('unsaved Open cancel and overwrite cancel preserve scene/file')
            cmds.file(modified=False)
            qpeHost.perform(widget, 'open')
            assert cmds.getAttr(cube + '.translateX') == 2
            selectFile(widget, folder / 'exported.ma')
            qpeHost.perform(widget, 'import')
            assert len(cmds.ls(type='mesh')) >= 2
            selectFile(widget, folder / 'exported.ma')
            qpeHost.perform(widget, 'reference')
            assert cmds.file(query=True, reference=True)
            checks.append('Open, Import and Reference')
            selectFile(widget, folder / 'hero_color.png')
            waitFor(lambda: not widget._image.isNull())
            widget.grab().save(str(output_dir / 'browser.png'))
        widget.saveLayout()
        assert readSettings()[widget._settingsKey]['lower']
        QtCore.QThreadPool.globalInstance().waitForDone(10000)
        result = {'status': 'passed', 'checks': checks}
    except Exception:
        result = {'status': 'error', 'checks': checks, 'error': traceback.format_exc()}
    (output_dir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    faulthandler.disable()
    crash_log.close()
    print(json.dumps(result, ensure_ascii=True))
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(Path(sys.argv[1]))
    sys.exit(0 if result['status'] == 'passed' else 1)
