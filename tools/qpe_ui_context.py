"""専用GUIで右クリック操作と表示倍率を実操作・実ファイルで検証する。"""
import json
import os
import sys
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_maya import pause, waitFor, selectFile
from qpeQt import QtCore, QtGui, QtWidgets, QtTest
from qpeSettings import readSettings
from qpeFileOperations import createEntry, renameEntry, validateName


def triggerMenu(menu, title):
    """生成したメニューから指定操作を実行する。

    Args:
        menu (QMenu): メニュー。
        title (str): 操作名。
    """
    action = next(a for a in menu.actions() if a.text() == title)
    assert action.isEnabled(), title
    action.trigger()
    if title == 'Rename…':
        pause(160)
    menu.deleteLater()


def answerInput(text=None):
    """次に開く入力ダイアログを、キー入力で確定またはキャンセルする。

    Args:
        text (str | None): 入力値。Noneはキャンセル。
    """
    def respond():
        """モーダル入力が開いた時点で入力を送る。"""
        dialog = QtWidgets.QApplication.activeModalWidget()
        if not isinstance(dialog, QtWidgets.QInputDialog):
            editor = QtWidgets.QApplication.focusWidget()
            assert editor is not None and editor.objectName() == 'inlineRename', type(editor)
            if text is not None:
                editor.setText(text)
            QtTest.QTest.keyClick(editor, QtCore.Qt.Key_Return if text is not None else QtCore.Qt.Key_Escape)
            return
        if text is None:
            QtTest.QTest.keyClick(dialog, QtCore.Qt.Key_Escape)
        else:
            dialog.setTextValue(text)
            QtTest.QTest.keyClick(dialog, QtCore.Qt.Key_Return)
    QtCore.QTimer.singleShot(80, respond)


def main(output_dir, finished=None):
    """ファイル操作・DPI・設定保存を隔離フォルダーで検証する。

    Args:
        output_dir (Path): 証跡保存先。
        finished (callable | None): Mayaの完了通知。

    Returns:
        dict: 判定と証跡。
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(output_dir / 'settings.json')
    checks = []
    stage = 'setup'
    widget = None
    try:
        root = output_dir / 'Project'
        (root / 'Parent/Child').mkdir(parents=True)
        (root / 'other').mkdir()
        (root / 'original.txt').write_text('preserve original', encoding='utf-8')
        (root / 'occupied.txt').write_text('preserve occupied', encoding='utf-8')
        if finished:
            import qpeHost
            from maya import cmds, OpenMayaUI
            widget = qpeHost.show(str(root))
            assert widget.appearance.dpiScale == float(OpenMayaUI.MQtUtil.dpiScale(1.0))
        else:
            from quickPathExplorer import Explorer
            widget = Explorer()
            widget.show()
            widget.navigate(str(root))
        pause(250)
        stage = 'new file and folder from menus'
        answerInput('日本語 新規.txt')
        triggerMenu(widget.createFileMenu(), 'New Text File…')
        created = root / '日本語 新規.txt'
        assert created.read_bytes() == b''
        waitFor(lambda: Path(widget.selectedPath()) == created)
        answerInput('新規フォルダー')
        triggerMenu(widget.createFolderMenu(str(root)), 'New Folder…')
        assert (root / '新規フォルダー').is_dir()
        checks.append(stage)

        stage = 'rename F2 and preserve contents'
        selectFile(widget, root / 'original.txt')
        widget.window().activateWindow()
        widget.window().raise_()
        widget.files.setFocus()
        pause(100)
        answerInput('renamed.txt')
        QtTest.QTest.keyClick(widget.files, QtCore.Qt.Key_F2)
        waitFor(lambda: (root / 'renamed.txt').exists())
        assert (root / 'renamed.txt').read_text(encoding='utf-8') == 'preserve original'
        waitFor(lambda: Path(widget.selectedPath()) == root / 'renamed.txt')
        checks.append(stage)

        stage = 'collision and cancel leave originals intact'
        answerInput('occupied.txt')
        triggerMenu(widget.createFileMenu(), 'Rename…')
        assert (root / 'renamed.txt').exists()
        assert (root / 'occupied.txt').read_text(encoding='utf-8') == 'preserve occupied'
        answerInput(None)
        triggerMenu(widget.createFileMenu(), 'Rename…')
        answerInput('occupied.txt')
        triggerMenu(widget.createFileMenu(), 'New Text File…')
        assert (root / 'occupied.txt').read_text(encoding='utf-8') == 'preserve occupied'
        for name in ('../escape', 'a/b', 'NUL.txt', 'COM1', 'bad?', 'bad.', 'bad ', ''):
            try:
                validateName(name)
            except ValueError:
                continue
            raise AssertionError('accepted invalid name: ' + name)
        checks.append(stage)

        stage = 'right click and background preserve selection with independent targets'
        selectFile(widget, root / 'occupied.txt')
        index = widget.fileProxy.mapFromSource(widget.fileModel.index(str(root / 'renamed.txt')))
        widget.files.scrollTo(index)
        pause(60)
        observations = []
        def inspectPopup():
            """開いたメニューの選択対象を読み取って閉じる。"""
            popup = QtWidgets.QApplication.activePopupWidget()
            assert isinstance(popup, QtWidgets.QMenu)
            next(a for a in popup.actions() if a.text() == 'Copy Path').trigger()
            observations.append((widget.selectedPath(), QtWidgets.QApplication.clipboard().text()))
            popup.close()
        QtCore.QTimer.singleShot(80, inspectPopup)
        point = widget.files.visualRect(index).center()
        QtWidgets.QApplication.sendEvent(widget.files.viewport(), QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse, point, widget.files.viewport().mapToGlobal(point)))
        assert Path(observations[-1][0]) == root / 'occupied.txt'
        assert Path(observations[-1][1]) == root / 'renamed.txt'
        QtCore.QTimer.singleShot(80, inspectPopup)
        widget._fileMenu(QtCore.QPoint(10, widget.files.viewport().height() - 5))
        assert Path(observations[-1][0]) == root / 'occupied.txt'
        assert Path(observations[-1][1]) == root
        checks.append(stage)

        stage = 'folder context event targets clicked item rather than current directory'
        widget.navigate(str(root / 'Parent/Child'))
        pause(100)
        parent_index = widget.folderModel.index(str(root / 'Parent'))
        view = next(v for v in widget.columns.findChildren(QtWidgets.QListView)
                    if v.isVisible() and v.rootIndex() == parent_index.parent())
        view.scrollTo(parent_index)
        def copyFolder():
            """実際に開いたフォルダーメニューのパスコピーをクリックする。"""
            menu = QtWidgets.QApplication.activePopupWidget()
            assert isinstance(menu, QtWidgets.QMenu)
            action = next(a for a in menu.actions() if a.text() == 'Copy Path')
            QtTest.QTest.mouseClick(menu, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, menu.actionGeometry(action).center())
        QtCore.QTimer.singleShot(100, copyFolder)
        point = view.visualRect(parent_index).center()
        QtWidgets.QApplication.sendEvent(view.viewport(), QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse, point, view.viewport().mapToGlobal(point)))
        assert Path(QtWidgets.QApplication.clipboard().text()) == root / 'Parent'
        assert Path(widget.currentDirectory) == root / 'Parent/Child'
        checks.append(stage)

        stage = 'rename active ancestor remaps history and favorites'
        widget.navigate(str(root / 'Parent/Child'))
        widget.addFavorite()
        answerInput('RenamedParent')
        triggerMenu(widget.createFolderMenu(str(root / 'Parent')), 'Rename…')
        assert Path(widget.currentDirectory) == root / 'RenamedParent/Child'
        assert (root / 'RenamedParent/Child').is_dir()
        assert any(Path(p) == root / 'RenamedParent/Child' for p in readSettings()['favorites'])
        widget.navigate(str(root / 'other'))
        widget.backButton.click()
        assert Path(widget.currentDirectory) == root / 'RenamedParent/Child'
        watched_index = widget.folderModel.index(str(root / 'RenamedParent/Child'))
        waitFor(lambda: widget.folderModel.rowCount(watched_index) == 0)
        new_child = root / 'RenamedParent/Child/AfterRename'
        new_child.mkdir()
        waitFor(lambda: widget.folderModel.rowCount(watched_index) == 1)
        assert widget.folderModel.index(0, 0, watched_index).data() == 'AfterRename'
        checks.append(stage)

        stage = 'display settings live change persistence and no accumulated scaling'
        widget.navigate(str(root))
        widget.displayButton.click()
        appearance = widget.appearance
        appearance.fontSpin.setValue(16)
        appearance.scaleSpin.setValue(150)
        pause(120)
        assert widget.font().pixelSize() == round(16 * 1.5 * appearance.dpiScale)
        first = widget.actionButtons['open'].font().pixelSize()
        appearance.scaleSpin.setValue(100)
        appearance.scaleSpin.setValue(150)
        assert widget.actionButtons['open'].font().pixelSize() == first
        assert readSettings()[appearance.key] == {'fontSize': 16, 'uiPercent': 150}
        widget.grab().save(str(output_dir / 'display-large.png'))
        appearance._reset()
        assert widget.font().pixelSize() == round(12 * appearance.dpiScale)
        appearance.dialog.hide()
        checks.append(stage)

        stage = 'simulated 200 percent host DPI scales columns icons and text'
        from quickPathExplorer import Explorer
        scaled = Explorer(dpi_scale=2.0)
        scaled.resize(2400, 1400)
        scaled.show()
        scaled.navigate(str(root))
        pause(150)
        assert scaled.font().pixelSize() == 24
        assert scaled.sidebarButton.iconSize().width() == 40
        assert scaled.places.minimumWidth() == 2 * widget.places.minimumWidth()
        assert min(width for width in scaled.columns.columnWidths() if width) >= 160
        assert scaled.columns.columnWidths()[-1] == scaled.columns.contentWidth(scaled.columns.currentIndex())
        scaled.grab().save(str(output_dir / 'dpi200.png'))
        scaled.close()
        scaled.deleteLater()
        checks.append(stage)

        if finished:
            stage = 'Maya import and reference from file context menu'
            cmds.file(new=True, force=True)
            cmds.polyCube(name='qpeContextCube')
            scene = root / 'source.ma'
            cmds.file(rename=str(scene))
            cmds.file(save=True, type='mayaAscii')
            cmds.file(new=True, force=True)
            widget.navigate(str(root))
            selectFile(widget, scene)
            triggerMenu(widget.createFileMenu(), 'Import')
            assert cmds.objExists('source:qpeContextCube')
            cmds.file(new=True, force=True)
            selectFile(widget, scene)
            triggerMenu(widget.createFileMenu(), 'Reference')
            assert cmds.file(query=True, reference=True)
            checks.append(stage)
        widget.navigate(str(root))
        pause(200)
        widget.grab().save(str(output_dir / 'context.png'))
        result = {'status': 'passed', 'checks': checks, 'hostDpi': widget.appearance.dpiScale,
                  'limits': '200 percent host DPI simulated; physical 4K display not verified'}
    except Exception:
        result = {'status': 'error', 'stage': stage, 'checks': checks, 'error': traceback.format_exc()}
        if widget:
            widget.grab().save(str(output_dir / 'failure.png'))
    (output_dir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(Path(sys.argv[1]))
    sys.exit(0 if result['status'] == 'passed' else 1)
