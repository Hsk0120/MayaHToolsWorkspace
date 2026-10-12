"""追加表示・検索・設定・キューを専用データで操作するGUI検証。"""
import json
import os
from pathlib import Path
import sys
import threading
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtGui, QtWidgets, QtTest
from qpe_ui_maya import waitFor, pause, selectFile


def main(output_dir, finished=None):
    """Maya隔離GUIまたは専用QApplicationで同じ操作を確認する。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    checks, limitations = [], []
    e = None
    gate = threading.Event()
    try:
        from quickPathExplorer import Explorer
        from qpeSettings import writeSettings, readSettings
        from qpePreferences import exportPreferences, importPreferences, PreferencesDialog
        folder = out / 'Assets'
        folder.mkdir(exist_ok=True)
        (folder / 'sub').mkdir(exist_ok=True)
        (folder / 'sub/nested.txt').write_text('nested')
        (folder / 'readme.md').write_text('# Test heading\n\n**Bold** text', encoding='utf8')
        images = []
        for number in range(15):
            path = folder / ('texture_%02d.png' % number)
            image = QtGui.QImage(240, 120, QtGui.QImage.Format_RGB32)
            image.fill(QtGui.QColor('#227788' if number % 2 else '#a97744'))
            image.save(str(path))
            images.append(path)
        e = Explorer(maya=bool(finished))
        e.resize(1300, 900)
        e.show()
        e.navigate(str(folder))
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 16)
        w = e.organizer.workspace
        selectFile(e, images[0])
        w.mode.setCurrentIndex(1)
        waitFor(lambda: w.grid.count() == 16 and bool(w.cache))
        assert Path(e.selectedPath()) == images[0]
        assert len(w.previewJobs) <= 2
        checks.append('thumbnail grid, bounded workers, preserved selection')
        w.mode.setCurrentIndex(0)
        assert Path(e.selectedPath()) == images[0]
        checks.append('return to details preserves selection')
        writeSettings({'fileLabels': {os.path.normcase(str(images[0])): dict(tags=['Hero'], rating=4, collection='Test')}})
        w.mode.setCurrentIndex(2)
        waitFor(lambda: w.tree.topLevelItemCount() == 16 and any(w.tree.topLevelItem(n).text(4) == 'Hero' for n in range(16)))
        rows = [w.tree.topLevelItem(n) for n in range(w.tree.topLevelItemCount())]
        hero = next(i for i in rows if i.text(0) == images[0].name)
        assert hero.text(4) == 'Hero' and hero.text(5) == '★★★★'
        waitFor(lambda: hero.text(7) == '240 × 120')
        w.labelFilter.setCurrentIndex(w.labelFilter.findData('Hero'))
        waitFor(lambda: w.tree.topLevelItemCount() == 1)
        w.labelFilter.setCurrentIndex(0)
        waitFor(lambda: w.tree.topLevelItemCount() == 16)
        checks.append('visible tags and ratings, clickable tag filtering')
        w.group.setCurrentText('Type')
        waitFor(lambda: w.tree.topLevelItemCount() == 2)
        assert not w.tree.topLevelItem(0).data(0, QtCore.Qt.UserRole)
        checks.append('group headers cannot become file operation targets')
        w.group.setCurrentIndex(0)
        w.setColumn(3, False)
        e.navigate(str(folder / 'sub'))
        assert w.mode.currentIndex() == 0
        e.navigate(str(folder))
        assert w.mode.currentIndex() == 2 and w.tree.isColumnHidden(3)
        checks.append('folder-specific mode and column visibility restored')
        w.flat.setChecked(True)
        waitFor(lambda: any(Path(p).name == 'nested.txt' for p in w.items))
        assert w.tree.topLevelItemCount() == 17
        checks.append('flat list includes descendant files with actual paths')
        dialog = e.organizer.search()
        dialog.root.setText(str(folder))
        dialog.kind.setCurrentText('Folders')
        dialog.search()
        waitFor(lambda: dialog.task is None)
        assert dialog.results.topLevelItemCount() == 1
        assert dialog.results.topLevelItem(0).text(0) == 'sub'
        conditions = dialog.conditions()
        dialog.restoreAdvanced(conditions)
        assert dialog.kind.currentText() == 'Folders'
        dialog.close()
        checks.append('folder search and advanced condition persistence')
        order = []
        def first(cancel, progress):
            """先頭を止め、後続の予約を確実に作る。"""
            gate.wait(5)
            order.append(1)
            return dict(completed=['first'], errors=[], skipped=[], cancelled=False)
        def second(cancel, progress):
            """先頭より前に走らないことを検証する。"""
            order.append(2)
            return dict(completed=[], errors=['expected failure'], skipped=[], cancelled=False, retry=['test'])
        e.organizer.run('First', first)
        e.organizer.run('Second', second)
        assert len(e.organizer.queue) == 1
        gate.set()
        waitFor(lambda: e.organizer.task is None and not e.organizer.queue)
        assert order == [1, 2]
        assert e.organizer.jobRecords[-1]['state'] == 'Partial / failed'
        checks.append('FIFO queued jobs and partial failure state')
        w.jobs()
        w.history()
        preferences = PreferencesDialog(w)
        preferences.show()
        preferences.days.setValue(14)
        assert preferences.apply()
        settings_file = out / 'export.json'
        exportPreferences(settings_file)
        exported = json.loads(settings_file.read_text(encoding='utf8'))
        assert 'favorites' not in exported['settings']
        writeSettings({'preferences': {'undoDays': 60, 'undoMiB': 1}})
        importPreferences(settings_file)
        assert readSettings()['preferences']['undoDays'] == 14
        exported['version'] = 999
        settings_file.write_text(json.dumps(exported), encoding='utf8')
        try:
            importPreferences(settings_file)
            raise AssertionError('unknown schema was accepted')
        except ValueError:
            pass
        checks.append('preferences apply, portable export, schema validation')
        preferences.close()
        for child in e.organizer.dialogs:
            child.close()
        e.activateWindow()
        e.raise_()
        pause(100)
        calls = []
        original = w.commands
        w.commands = lambda: {'palette': ('Test', lambda: calls.append(True))}
        e.search.setFocus()
        pause(50)
        w.shortcut('palette')
        assert not calls
        w.tree.setFocus()
        pause(50)
        w.shortcut('palette')
        assert calls
        w.commands = original
        checks.append('command shortcuts protect focused text editors')
        def choosePalette():
            """実際の検索欄からサムネイルコマンドを選ぶ。"""
            active = QtWidgets.QApplication.activeModalWidget()
            query = active.findChild(QtWidgets.QLineEdit)
            query.setText('View: thumbnails')
            QtTest.QTest.keyClick(query, QtCore.Qt.Key_Return)
        QtCore.QTimer.singleShot(100, choosePalette)
        w.palette()
        assert w.mode.currentIndex() == 1
        checks.append('command palette searches and executes actual action')
        for d in e.organizer.dialogs:
            d.close()
        w.flat.setChecked(False)
        w.mode.setCurrentIndex(1)
        waitFor(lambda: w.grid.count() == 16)
        e.organizer.report('Validation fixtures — thumbnail and metadata views')
        pause(200)
        e.grab().save(str(out / 'thumbnails.png'))
        w.mode.setCurrentIndex(2)
        pause(250)
        e.grab().save(str(out / 'metadata.png'))
        result = dict(status='passed', checks=checks, limitations=limitations)
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc(), limitations=limitations)
    finally:
        gate.set()
        if e:
            for dialog in e.organizer.dialogs:
                dialog.close()
            e.close()
        pause(500)
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    outcome = main(sys.argv[1])
    QtCore.QThreadPool.globalInstance().waitForDone(10000)
    sys.exit(0 if outcome['status'] == 'passed' else 1)
