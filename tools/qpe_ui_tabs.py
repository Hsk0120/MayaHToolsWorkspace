"""タブ間の履歴・選択・非同期更新とWindows表示を検証する。"""
import json
import os
import sys
import traceback
from pathlib import Path
from qpe_ui_maya import pause, waitFor, selectFile
from qpeQt import QtCore, QtWidgets, QtTest


def main(output_dir, finished=None):
    """専用データを使いホストから独立して検証する。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    checks = []
    try:
        from quickPathExplorer import Explorer
        folders = [out / 'Assets', out / 'Shots']
        for folder in folders:
            folder.mkdir(exist_ok=True)
            (folder / 'notes.txt').write_text(folder.name, encoding='utf8')
            (folder / 'scene.ma').write_text('//Maya ASCII 2022 scene', encoding='utf8')
        e = Explorer(maya=bool(finished))
        e.resize(1240, 820)
        e.show()
        e.navigate(str(folders[0]))
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 2)
        selectFile(e, folders[0] / 'notes.txt')
        waitFor(lambda: e.previewText.toPlainText() == 'Assets')
        history = list(e._history)
        e.folderTabs.add()
        e.navigate(str(folders[1]))
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 2)
        e.search.setText('scene')
        e.folderTabs.bar.setCurrentIndex(0)
        waitFor(lambda: Path(e.selectedPath()) == folders[0] / 'notes.txt')
        assert e._history == history and not e.search.text()
        waitFor(lambda: e.previewText.toPlainText() == 'Assets')
        checks.append('tab restores independent history, filter, selection and preview')
        for index in (1, 0, 1, 0):
            e.folderTabs.bar.setCurrentIndex(index)
        waitFor(lambda: Path(e.selectedPath()) == folders[0] / 'notes.txt')
        pause(200)
        assert Path(e.currentDirectory) == folders[0] and e.previewText.toPlainText() == 'Assets'
        checks.append('rapid A-B-A tab changes reject stale restoration and preview')
        assert '2 items' in e.footer.text() and '1 selected' in e.footer.text()
        e.files.clearSelection()
        assert 'selected' not in e.footer.text()
        checks.append('footer follows selection and clearing')
        e.folderTabs.bar.setCurrentIndex(1)
        assert e.search.text() == 'scene'
        e.folderTabs.close(0)
        assert e.folderTabs.active == 0 and Path(e.currentDirectory) == folders[1]
        e.folderTabs.close(0)
        assert e.folderTabs.bar.count() == 1
        e.folderTabs.add()
        e.folderTabs.close(1)
        assert e.folderTabs.bar.count() == 1
        checks.append('close active/inactive tabs and retain final tab')
        e.search.clear()
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 2)
        selectFile(e, folders[1] / 'scene.ma')
        e.setInspectorVisible(True)
        pause(200)
        from qpeFileIcons import fileType, windowsIcon
        sample = str(folders[1] / 'scene.ma')
        assert not e._placeIcons.icon(sample).isNull()
        if os.name == 'nt':
            assert not windowsIcon(sample.replace('\\', '/')).isNull()
            assert fileType(sample.replace('\\', '/')) == fileType(os.path.normpath(sample))
        assert all(label in e.metadata.text() for label in ('Type', 'Size', 'Location', 'Modified'))
        assert e.details.geometry().top() < e.operationTabs.geometry().top() < e.metadata.geometry().top()
        checks.append('native icon and preview-actions-details layout')
        bar = e.folderTabs.bar
        strip = e.folderTabs.strip
        assert bar.tabRect(0).width() == 240
        for count in range(2, 15):
            e.folderTabs.add()
            pause(40)
            widths = [bar.tabRect(i).width() for i in range(count)]
            assert max(widths) - min(widths) <= 1, widths
            assert 100 <= min(widths) <= 240, widths
            assert e.folderTabs.addButton.geometry().right() < strip.width()
            if count in (3, 6, 14):
                e.grab().save(str(out / ('tabs-%02d.png' % count)))
        assert bar.tabRect(0).width() == 100
        assert any(b.isVisible() for b in bar.findChildren(QtWidgets.QToolButton))
        checks.append('equal 240-to-100 tab widths, adjacent plus and overflow controls')
        for count in range(14, 3, -1):
            e.folderTabs.close(count - 1)
        pause(80)
        assert bar.tabRect(0).width() == 240
        e.resize(800, 820)
        pause(80)
        e.appearance.apply(12, 200, save=False)
        pause(80)
        scaled_width = bar.tabRect(0).width()
        assert 200 <= scaled_width < 480
        e.resize(1800, 1000)
        pause(80)
        assert bar.tabRect(0).width() > scaled_width
        e.appearance.apply(12, 100, save=False)
        e.resize(1240, 820)
        pause(80)
        assert bar.tabRect(0).width() == 240
        checks.append('closing, resizing and UI scaling redistribute tab widths')
        from qpeTabs import TabGlyphButton
        assert all(not bar.tabIcon(i).isNull() for i in range(bar.count()))
        close_button = bar.tabButton(1, QtWidgets.QTabBar.RightSide)
        assert isinstance(close_button, TabGlyphButton)
        assert close_button.width() >= 24
        QtTest.QTest.mouseMove(close_button, close_button.rect().center())
        pause(80)
        e.grab().save(str(out / 'close-hover.png'))
        QtTest.QTest.mouseClick(close_button, QtCore.Qt.LeftButton)
        pause(80)
        assert bar.count() == 2
        assert e.folderTabs.active == bar.currentIndex()
        QtTest.QTest.mouseClick(e.folderTabs.addButton, QtCore.Qt.LeftButton)
        pause(80)
        assert bar.count() == 3 and bar.currentIndex() == 2
        assert isinstance(bar.tabButton(2, QtWidgets.QTabBar.RightSide), TabGlyphButton)
        checks.append('native folder tab icons, close hit area, hover and actual close/add clicks')
        for mode in ('light', 'dark'):
            e.appearance.theme.setMode(mode)
            pause(50)
            e.grab().save(str(out / (mode + '.png')))
        result = dict(status='passed', checks=checks)
        e.close()
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(sys.argv[1])
    sys.exit(0 if result['status'] == 'passed' else 1)
