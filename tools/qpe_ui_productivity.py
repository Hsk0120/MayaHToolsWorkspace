"""追加8項目の接続と回帰を隔離GUIで検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_advanced import QtCore, QtGui, QtWidgets, QtTest
from qpe_ui_maya import pause, waitFor, selectFile


def main(output_dir, finished=None):
    """Maya/独立Qtに同じ操作を適用し、証跡を保存する。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out/'settings.json')
    checks = []
    e = None
    try:
        from quickPathExplorer import Explorer
        from qpeSettings import readSettings
        from qpeProductivity import ArchiveDialog
        root = out/'ReviewProject'
        root.mkdir(exist_ok=True)
        a, b = root/'Alpha', root/'Beta'
        a.mkdir(exist_ok=True)
        b.mkdir(exist_ok=True)
        note = a/'note.txt'
        note.write_text('first\nHero texture guide\nlast', encoding='utf8')
        image = QtGui.QImage(320, 200, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor('#569baa'))
        image.save(str(a/'image.png'))
        with zipfile.ZipFile(a/'bundle.zip', 'w') as archive:
            archive.writestr('materials/readme.txt', 'selected content')
            archive.writestr('other.txt', 'other')
        e = Explorer(maya=bool(finished))
        e.resize(1360, 900)
        e.show()
        e.activateWindow()
        e.setBrowseRoot(str(root))
        e.navigate(str(a))
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 3)
        w = e.organizer.workspace
        p = w.productivity
        selectFile(e, note)
        from unittest.mock import patch
        with patch.object(e, 'requestFiles') as request:
            e.openSelectedFile()
            assert request.call_count == 1
            assert request.call_args[0][0] == 'open'
            assert [Path(v) for v in request.call_args[0][1]] == [note]
        checks.append('Open selected file dispatches the selected path without an internal viewer')
        renamed = []
        original = e.renamePath
        e.renamePath = lambda path: renamed.append(path)
        for mode in (0, 1, 2):
            w.mode.setCurrentIndex(mode)
            if mode == 0:
                selectFile(e, note)
                view = e.files
            else:
                waitFor(lambda: len(w.items) == 3)
                view = w.grid if mode == 1 else w.tree
                view.clearSelection()
                for i in range(view.count() if mode == 1 else view.topLevelItemCount()):
                    item = view.item(i) if mode == 1 else view.topLevelItem(i)
                    path = item.data(QtCore.Qt.UserRole) if mode == 1 else item.data(0, QtCore.Qt.UserRole)
                    if Path(path) == note:
                        item.setSelected(True)
                        view.setCurrentItem(item)
                        break
            e.activateWindow()
            e.raise_()
            view.setFocus()
            pause(250)
            print("KEY_MODE", mode, "focus", QtWidgets.QApplication.focusWidget(), "selected", e.selectedPaths(), "current", e.selectedPath(), flush=True)
            QtTest.QTest.keyClick(view, QtCore.Qt.Key_Return)
            print("KEY_COUNT", mode, len(renamed), flush=True)
        e.renamePath = original
        assert len(renamed) == 3 and all(Path(v) == note for v in renamed), renamed
        checks.append('Enter consistently renames in Details/Thumbnails/Metadata')
        e.address.setFocus()
        e.address.setText(str(root).replace('\\', '/') + '/Al')
        p.edited(e.address.text())
        waitFor(lambda: any(value.endswith('/Alpha') for value in p.model.stringList()))
        p.completer.popup().hide()
        e.address.setText(str(a))
        checks.append('asynchronous path completion without directory navigation')
        tabs = e.folderTabs
        tabs.add()
        p.setTabFlag(tabs.active, 'pinned', True)
        assert not tabs.bar.tabButton(tabs.active, QtWidgets.QTabBar.RightSide).isEnabled()
        tabs.updateTitle()
        assert 'Pinned' in tabs.bar.tabToolTip(tabs.active)
        count = tabs.bar.count()
        tabs.close(tabs.active)
        assert tabs.bar.count() == count
        p.setTabFlag(tabs.active, 'locked', True)
        e.navigate(str(b))
        assert tabs.bar.count() == count + 1
        assert Path(tabs.states[1]['path']) == a
        p.saveSet('Review')
        e.navigate(str(a))
        p.loadSet('Review')
        waitFor(lambda: Path(e.currentDirectory) == b)
        assert readSettings()['previousWorkspace']
        assert readSettings()['tabSets']['Review']['states'][1]['pinned']
        from unittest.mock import patch
        saved = readSettings()['tabSets']['Review']
        with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Cancel) as question:
            p.saveSet(' Review ')
            assert question.call_count == 1
        assert readSettings()['tabSets']['Review'] == saved
        checks.append('pinned tab, location lock, named workspace and previous workspace backup')
        e.navigate(str(a))
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 3)
        dialog = e.organizer.search()
        dialog.content.setText('hero')
        dialog.search()
        waitFor(lambda: dialog.task is None)
        assert dialog.results.topLevelItemCount() == 1
        assert dialog.results.topLevelItem(0).text(2).startswith('2:')
        dialog.grab().save(str(out/'content-search.png'))
        dialog.close()
        checks.append('content search lists matching line and snippet')
        archive = ArchiveDialog(str(a/'bundle.zip'), e.organizer)
        archive.show()
        waitFor(lambda: archive.extract.isEnabled())
        assert archive.table.topLevelItemCount() == 2
        archive.grab().save(str(out/'zip-browser.png'))
        archive.close()
        checks.append('ZIP read-only browse without extracting')
        e.organizer.queuePaused = True
        e.organizer.transfer('copy', [str(note)], str(b), 'rename')
        e.organizer.transfer('copy', [str(a/'image.png')], str(b), 'rename')
        assert len(e.organizer.queue) == 2
        second = e.organizer.queue[1][-1]
        w.jobs()
        jobs = e.organizer.dialogs[-1]
        table = jobs.findChild(QtWidgets.QTreeWidget)
        table.setCurrentItem(table.topLevelItem(len(e.organizer.jobRecords)-1))
        next(button for button in jobs.findChildren(QtWidgets.QPushButton) if button.text() == 'Move up').click()
        assert e.organizer.queue[0][-1] is second
        assert table.currentItem().data(0, QtCore.Qt.UserRole) == id(second)
        assert any(button.text() == 'Resume queue' for button in jobs.findChildren(QtWidgets.QPushButton))
        second['paused'].set()
        e.organizer.queuePaused = False
        e.organizer.nextJob()
        pause(300)
        assert e.organizer.task is not None and not (b/'image.png').exists()
        next(button for button in jobs.findChildren(QtWidgets.QPushButton) if button.text() == 'Pause / resume active transfer').click()
        waitFor(lambda: not e.organizer.task and not e.organizer.queue)
        assert (b/'image.png').exists() and (b/'note.txt').exists()
        assert all(not r['result']['errors'] for r in e.organizer.jobRecords)
        jobs.grab().save(str(out/'jobs.png'))
        jobs.close()
        checks.append('queue reordering, active pause/resume, durable real file transfers')
        w.recoverTransfers()
        recovery = e.organizer.dialogs[-1]
        assert recovery.findChild(QtWidgets.QTreeWidget).topLevelItemCount() == 0
        recovery.close()
        checks.append('completed jobs excluded from recovery')
        w.mode.setCurrentIndex(2)
        waitFor(lambda: w.tree.topLevelItemCount() == 3)
        assert w.tree.headerItem().text(8) == 'Availability'
        assert all(w.tree.topLevelItem(i).text(8) for i in range(3))
        from qpePreferences import exportPreferences, importPreferences
        w.setColumn(8, False)
        exportPreferences(out/'preferences.json', includeLocal=True)
        importPreferences(out/'preferences.json')
        w.setColumn(8, True)
        checks.append('settings export/import includes the new availability column')
        p.diagnose([str(note)])
        waitFor(lambda: e.organizer.task is None)
        for dialog in e.organizer.dialogs:
            dialog.close()
        e.grab().save(str(out/'overview.png'))
        checks.append('availability column and read-only diagnosis')
        result = dict(status='passed', checks=checks, limitations=['Real OneDrive/provider sync state, network interruption, physical IME and mixed DPI not tested'])
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
        if e:
            e.grab().save(str(out/'failure.png'))
    finally:
        if e:
            for record in e.organizer.jobRecords:
                if record.get('paused'):
                    record['paused'].clear()
            if e.organizer.task:
                e.organizer.task.cancel.set()
                waitFor(lambda: e.organizer.task is None)
            for dialog in e.organizer.dialogs:
                dialog.close()
            e.close()
        pause(300)
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(sys.argv[1])
    QtCore.QThreadPool.globalInstance().waitForDone(10000)
    sys.exit(0 if result['status'] == 'passed' else 1)
