"""全操作レビューで見つけた状態復元とメニューの回帰を検証する。"""
import copy
import json
import os
from pathlib import Path
import sys
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_maya import pause, waitFor
from qpe_ui_navigation import inspectFolder
from qpeQt import QtWidgets


def main(output_dir, finished=None):
    """短時間の階層往復と欠損タブ復元を専用データで確認する。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out/'settings.json')
    from quickPathExplorer import Explorer
    root = out/'Fixture'
    for name in ('A/childA', 'B/childB', 'C'):
        (root/name).mkdir(parents=True, exist_ok=True)
    e = Explorer(maya=bool(finished))
    e.show()
    e.setBrowseRoot(str(root))
    checks = []
    try:
        for number in range(40):
            for name in ('A', 'B', ''):
                e.navigate(str(root/name))
                pause(number % 4 * 10)
            inspectFolder(e, root)
        checks.append('40 rapid A/B/root cycles preserve populated root column')
        tabs = e.folderTabs
        e.navigate(str(root/'A'))
        tabs.add()
        e.navigate(str(root/'B'))
        tabs.add()
        e.navigate(str(root/'C'))
        tabs.bar.setCurrentIndex(1)
        waitFor(lambda: tabs.pendingSerial is None)
        state = copy.deepcopy(tabs.session())
        state['states'][0]['path'] = str(root/'missing')
        assert tabs.restoreSession(state)
        assert Path(e.currentDirectory) == root/'B'
        checks.append('missing earlier saved tab does not change the active location')
        e.organizer.populateTools()
        actions = e.organizer.toolsMenu.actions()
        assert len(actions) <= 9
        titles = []
        def collect(menu):
            """再分類後も全アクションが残ることを確認する。"""
            for action in menu.actions():
                if action.menu():
                    collect(action.menu())
                else:
                    titles.append(action.text())
        collect(e.organizer.toolsMenu)
        for title, callback in e.organizer.workspace.commands().values():
            assert title in titles, title
        assert len(titles) == len(set(titles))
        preview_action = next(action for group in actions if group.menu() for action in group.menu().actions()
                              if action.text() == 'Open selected file')
        assert not preview_action.isEnabled()
        checks.append('compact Tools menu preserves every searchable command once')
        from qpePreferences import PreferencesDialog, importPreferences
        from unittest.mock import patch
        settings = out/'import.json'
        key = e.appearance.key
        settings.write_text(json.dumps(dict(format='qpe.preferences', version=1,
                                            settings={key: dict(fontSize=14, uiPercent=125)})), encoding='utf8')
        dialog = PreferencesDialog(e.organizer.workspace)
        with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=(str(settings), '')), \
                patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Yes):
            dialog.load()
        assert e.appearance.fontSize == 14 and e.appearance.uiPercent == 125
        (root/'B'/'layout.txt').write_text('Layout regression fixture')
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1 and e.files.isVisible())
        pause(200)
        assert sum(e.files.columnWidth(i) for i in range(4)) >= e.files.viewport().width() - 5
        e.fileFilter.setCurrentIndex(1)
        pause(150)
        e.fileFilter.setCurrentIndex(0)
        e.search.setText('no_matching_file')
        pause(100)
        e.search.clear()
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1)
        e.files.sortByColumn(1, e.files.header().sortIndicatorOrder())
        pause(150)
        assert sum(e.files.columnWidth(i) for i in range(4)) >= e.files.viewport().width() - 5
        assert e.files.header().sectionResizeMode(0) == QtWidgets.QHeaderView.Stretch
        checks.append('empty extension/name filters and sorting preserve the flexible filename column')
        settings.write_text(json.dumps(dict(format='qpe.preferences', version=1,
                                            settings={'commandKeys': {'jobs': 'Ctrl+C'}})), encoding='utf8')
        try:
            importPreferences(settings)
            raise AssertionError('Imported reserved shortcut was accepted')
        except ValueError:
            pass
        from qpeSettings import readSettings
        before = readSettings()
        settings.write_text(json.dumps(dict(format='qpe.preferences', version=1,
                                            settings={'favorites': [123]})), encoding='utf8')
        try:
            importPreferences(settings)
            raise AssertionError('Invalid favorite was accepted')
        except ValueError:
            pass
        assert readSettings() == before
        checks.append('imported appearance is applied immediately and reserved shortcuts are rejected')
        result = dict(status='passed', checks=checks)
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    e.grab().save(str(out/'overview.png'))
    e.close()
    pause(200)
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(sys.argv[1])
    sys.exit(0 if result['status'] == 'passed' else 1)
