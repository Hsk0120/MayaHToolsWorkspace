"""一覧再構築後のアクセシビリティ参照と遅延レイアウトを検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtGui, QtWidgets
from qpe_ui_maya import waitFor, pause


def main(output_dir, finished=None):
    """専用120項目を再構築し、外部から見えるセル参照の生存を確認する。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    folder = out / 'Files'
    folder.mkdir(exist_ok=True)
    for number in range(120):
        (folder / ('item_%03d.txt' % number)).write_text('test', encoding='utf-8')
    from quickPathExplorer import Explorer
    e = Explorer(maya=bool(finished))
    e.resize(1100, 850)
    e.show()
    checks = []
    try:
        e.navigate(str(folder))
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 120)
        workspace = e.organizer.workspace
        for repeat in range(8):
            workspace.mode.setCurrentIndex(2 if repeat % 2 else 1)
            workspace.refresh()
            waitFor(lambda: not workspace.timer.isActive() and not workspace.restoring
                    and workspace.grid.count() == 120)
            view = workspace.stack.currentWidget()
            accessible = QtGui.QAccessible.queryAccessibleInterface(view)
            if accessible is None:
                raise AssertionError('Missing accessible view')
            count = accessible.childCount()
            visited = 0
            for number in range(min(count, 140)):
                child = accessible.child(number)
                if child is not None and child.isValid():
                    child.state()
                    if not QtGui.QAccessible.uniqueId(child):
                        raise AssertionError('Cell lost its accessible id after state query')
                    visited += 1
            if visited < 120:
                raise AssertionError(('Missing accessible cells', count, visited))
            checks.append(dict(repeat=repeat, mode=workspace.mode.currentIndex(), cells=visited))
            e.search.setText('item_00')
            waitFor(lambda: not workspace.timer.isActive() and not workspace.restoring
                    and workspace.grid.count() == 10)
            e.search.clear()
            waitFor(lambda: not workspace.timer.isActive() and not workspace.restoring
                    and workspace.grid.count() == 120)
        result = dict(status='passed', checks=checks, input='Qt accessibility API; not screen-reader OS input')
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    finally:
        e.close()
        e.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(e, QtCore.QEvent.DeferredDelete)
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if finished:
        finished(result)
    return result
