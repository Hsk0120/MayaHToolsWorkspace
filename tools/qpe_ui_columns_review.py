"""カラム主体表示とメニュー・狭幅の詳細表示を専用データで回帰検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback

from qpe_ui_maya import pause, waitFor, selectFile
from qpeQt import QtCore, QtWidgets, QtTest


def main(output_dir, finished=None):
    """Qtの入力と実レイアウトを検査する。OS入力とは別の証拠を保存する。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    from quickPathExplorer import Explorer
    from qpeSettings import readSettings
    root = out / 'Project'
    leaf = root / 'Characters/Hero/Rig/Work'
    leaf.mkdir(parents=True, exist_ok=True)
    (root / ('unselected_' + 'long_name_' * 8)).mkdir(exist_ok=True)
    note = leaf / 'note.txt'
    note.write_text('Dedicated UI regression data', encoding='utf-8')
    e = Explorer(maya=bool(finished))
    checks = []
    try:
        e.resize(1240, 820)
        e.show()
        e.setBrowseRoot(str(root))
        e.navigate(str(leaf))
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1)
        pause(250)
        e.setSidebarVisible(True)
        e.setInspectorVisible(True)
        selectFile(e, note)
        e.detailsHeading.setChecked(True)
        waitFor(lambda: e.previewText.isVisible())
        pause(250)

        for width, scale in ((1240, 100), (850, 100), (1240, 150), (1240, 200)):
            e.resize(width, 820)
            e.appearance.apply(12, scale, save=False)
            e.outer.setSizes([150, max(300, width - 410), 260])
            pause(300)
            required = e.metadata.heightForWidth(e.metadata.width())
            assert e.metadata.height() >= required, (width, scale, e.metadata.height(), required)
            assert e.previewText.y() >= e.metadata.geometry().bottom(), (width, scale)
            scroll = e.inspectorScroll
            scroll.ensureWidgetVisible(e.previewText)
            pause(50)
            assert scroll.widget().height() >= scroll.widget().minimumSizeHint().height()
            e.grab().save(str(out / ('details-%s-%s.png' % (width, scale))))
        checks.append('metadata fully allocated at narrow width and 100/150/200%; preview never overlaps')
        e.appearance.apply(12, 100, save=False)
        e.resize(1240, 820)
        e.setInspectorVisible(False)
        pause(200)

        e.modern.areaMode.setCurrentIndex(e.modern.areaMode.findData('columns'))
        pause(150)
        sizes = e.vertical.sizes()
        assert sizes[0] > sizes[1] * 2, sizes
        assert readSettings()[e._settingsKey]['browserMode'] == 'columns'
        e.navigate(str(root / 'Characters'))
        pause(250)
        assert abs(e.vertical.sizes()[0] - sizes[0]) <= 2
        checks.append('Columns first persists ratio; navigation does not resize panes')

        e.navigate(str(leaf))
        pause(250)
        columns = [v for v in e.columns.findChildren(QtWidgets.QListView) if v.isVisible()]
        root_view = next(v for v in columns if v.rootIndex() == e.folderModel.index(str(root)))
        assert 120 <= root_view.width() <= 221, root_view.width()
        current = e.columns.currentIndex()
        current_view = next(v for v in columns if v.rootIndex() == current.parent())
        e.files.setFocus()
        e.interaction.updateFocus()
        assert current_view.property('qpeSelectionColor') == e.appearance.theme.colors['accent']
        assert root_view.property('qpeSelectionColor') == e.appearance.theme.colors['inactive']
        checks.append('long unselected sibling does not dominate; current path stays accented from file list')

        before = current_view.property('qpeRowHeight')
        e.modern.rowSpacing.setCurrentIndex(1)
        pause(100)
        assert current_view.property('qpeRowHeight') > before
        e.modern.rowSpacing.setCurrentIndex(0)
        checks.append('density is accessible in View and applies to columns')

        menu = e.createFolderMenu(str(root / 'Characters'))
        selected = e.selectedPaths()
        directory = e.currentDirectory
        top = [a for a in menu.actions() if not a.isSeparator()]
        assert len(top) <= 16, [a.text() for a in top]
        assert {'New', 'Organize', 'Advanced', 'Navigation / view'} <= {a.text() for a in top}
        assert e.selectedPaths() == selected and e.currentDirectory == directory
        next(a for a in top if a.text() == 'Copy Path').trigger()
        assert QtWidgets.QApplication.clipboard().text() == str(root / 'Characters')
        next(a for a in top if a.text() == 'Open in new tab').trigger()
        pause(250)
        assert Path(e.currentDirectory) == root / 'Characters'
        assert e.folderTabs.bar.count() == 2
        menu.deleteLater()
        checks.append('grouped context menu keeps snapshot target; folder opens in independent tab')

        e.window().activateWindow()
        e.window().raise_()
        e.files.setFocus()
        waitFor(lambda: QtWidgets.QApplication.focusWidget() is e.files)
        QtTest.QTest.keyClick(e.files, QtCore.Qt.Key_Backtab, QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier)
        pause(250)
        assert e.folderTabs.active == 0 and Path(e.currentDirectory) == leaf
        e.files.setFocus()
        QtTest.QTest.keyClick(e.files, QtCore.Qt.Key_Tab, QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier)
        pause(250)
        assert e.folderTabs.active == 1
        e.files.setFocus()
        QtTest.QTest.keyClick(e.files, QtCore.Qt.Key_Tab, QtCore.Qt.ControlModifier)
        pause(250)
        assert e.folderTabs.active == 0
        e.address.setFocus()
        active = e.folderTabs.active
        QtTest.QTest.keyClick(e.address, QtCore.Qt.Key_Backtab, QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier)
        pause(100)
        assert e.folderTabs.active == active
        checks.append('reverse tab wraps with Tab/Backtab; forward works; editor focus is protected')
        e.grab().save(str(out / 'overview.png'))
        result = dict(status='passed', checks=checks, input_kind='Qt programmatic GUI')
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
        e.grab().save(str(out / 'failure.png'))
    e.close()
    e.deleteLater()
    pause(100)
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    sys.exit(0 if main(sys.argv[1])['status'] == 'passed' else 1)
