"""隔離QPEの実ウィジェットとワーカーで削除・復元を検証、録画する。"""
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtGui, QtWidgets
from qpe_ui_maya import pause, waitFor


def main(output_dir, finished=None):
    """確認ダイアログを含むQtプログラム操作を実OS入力とは区別して記録する。"""
    out = Path(output_dir).resolve()
    if ROOT / '.maya-output' not in out.parents:
        raise ValueError('Test output must be inside .maya-output')
    out.mkdir(parents=True, exist_ok=True)
    frames = out / 'frames'
    frames.mkdir(exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    from quickPathExplorer import Explorer
    import qpeRecycle
    folder = out / 'TestAssets'
    asset = folder / 'LargeFolder'
    asset.mkdir(parents=True, exist_ok=True)
    content = asset / 'test-data.bin'
    with content.open('wb') as stream:
        block = b'x' * 1024 * 1024
        for _ in range(64):
            stream.write(block)
    (asset / 'EmptyFolder').mkdir(exist_ok=True)
    e = Explorer(maya=bool(finished))
    e.resize(1080, 760)
    e.show()
    e.setBrowseRoot(str(folder))
    e.navigate(str(asset))
    caption = QtWidgets.QLabel(e)
    caption.setStyleSheet('background:#24414b;color:white;padding:10px;font-size:17px;')
    e.layout().insertWidget(0, caption)
    samples = []

    def capture():
        """このテスト画面と所有するダイアログだけを録画する。"""
        pix = e.grab()
        painter = QtGui.QPainter(pix)
        for window in QtWidgets.QApplication.topLevelWidgets():
            owner = window.parentWidget()
            while owner is not None and owner is not e:
                owner = owner.parentWidget()
            if window is not e and window.isVisible() and owner is e:
                painter.drawPixmap(e.mapFromGlobal(window.mapToGlobal(QtCore.QPoint())), window.grab())
        painter.end()
        pix.save(str(frames / ('%05d.png' % len(samples))))
        samples.append(time.monotonic())

    def step(text):
        """操作と期待結果を、テスト用字幕として画面に示す。"""
        caption.setText(text)
        pause(900)

    def delete(answer):
        """実際のフォルダーメニューと確認ダイアログを経由する。"""
        menu = e.createFolderMenu(str(asset))
        action = next(a for a in menu.actions() if a.text() == 'Delete')

        def respond():
            """この試験が開いた削除確認だけへQtプログラム操作で回答する。"""
            dialog = QtWidgets.QApplication.activeModalWidget()
            if not isinstance(dialog, QtWidgets.QMessageBox) or dialog.windowTitle() != 'Delete':
                raise AssertionError('Expected dedicated Delete confirmation')
            dialog.button(answer).click()

        QtCore.QTimer.singleShot(1200, respond)
        action.trigger()
        menu.deleteLater()

    timer = QtCore.QTimer(e)
    timer.setInterval(125)
    timer.timeout.connect(capture)
    checks = []
    try:
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1)
        e.folderTabs.add()
        e.folderTabs.bar.setCurrentIndex(0)
        pause(100)
        timer.start()
        step('Qt GUI test | Dedicated 64 MiB folder | No user files')
        pause(800)
        step('1. Cancel Delete confirmation -> original remains')
        delete(QtWidgets.QMessageBox.Cancel)
        assert content.exists() and not e.organizer.task
        checks.append('cancel confirmation preserves source')
        step('2. Delete -> direct Windows Recycle Bin; no backup copy')
        delete(QtWidgets.QMessageBox.Yes)
        waitFor(lambda: e.organizer.task is None)
        result = e.organizer.activeRecord['result']
        assert result and not result['errors'] and len(result['completed']) == 1, result
        assert not asset.exists()
        waitFor(lambda: str(asset).replace('\\', '/') not in e.folderModel._items)
        assert Path(e.currentDirectory) == folder
        assert not any(v.isVisible() and e.folderModel.filePath(v.rootIndex()).startswith(asset.as_posix())
                       for v in e.columns.findChildren(QtWidgets.QListView)), 'deleted child column remains'
        receipt = e.organizer.engine.history[-1]['entries'][0]['recycle']
        assert Path(receipt['physicalPath']).exists()
        checks.append('folder menu deletes through real worker and Shell')
        checks.append('deleted folder row and descendant columns disappear without Refresh')
        step('3. Switch other tab -> existing parent; no deleted rows or columns')
        e.folderTabs.bar.setCurrentIndex(1)
        waitFor(lambda: Path(e.currentDirectory) == folder)
        waitFor(lambda: str(asset).replace('\\', '/') not in e.folderModel._items)
        assert e.folderTabs.bar.tabText(1) == folder.name
        assert e.address.text() == folder.as_posix()
        assert not e.address.styleSheet(), 'stale missing-folder error'
        checks.append('other tab in deleted location returns to existing parent')
        step('4. File Undo -> original folder, file and empty folder restored')
        e.organizer.undo()
        waitFor(lambda: e.organizer.task is None)
        assert content.stat().st_size == 64 * 1024 * 1024
        assert (asset / 'EmptyFolder').is_dir()
        assert not Path(receipt['physicalPath']).exists()
        waitFor(lambda: asset.as_posix() in e.folderModel._items)
        e.navigate(str(asset))
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1)
        checks.append('File Undo restores original directory and contents')
        step('5. Redo Delete -> File Undo again')
        e.organizer.run('Redo file operation', lambda c, p: e.organizer.engine.redo())
        waitFor(lambda: e.organizer.task is None)
        assert not asset.exists(), e.organizer.activeRecord
        e.organizer.undo()
        waitFor(lambda: e.organizer.task is None)
        assert content.exists(), e.organizer.activeRecord
        checks.append('worker Redo and second Undo restore original')
        e.navigate(str(asset))
        step('PASS | Delete / Cancel / File Undo / Redo | Originals restored')
        pause(1400)
        e.grab().save(str(out / 'passed.png'))
        result = dict(status='passed', checks=checks, module=qpeRecycle.__file__,
                      evidence='Qt widget actions and real Shell I/O; not physical OS input')
    except Exception:
        result = dict(status='failed', checks=checks, error=traceback.format_exc())
    finally:
        timer.stop()
        (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
        (out / 'frames.json').write_text(json.dumps(samples), encoding='utf8')
        e.close()
        e.deleteLater()
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(sys.argv[1])
    QtCore.QThreadPool.globalInstance().waitForDone(10000)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result['status'] == 'passed' else 1)
