"""ダブルクリックと全高サイドバーを専用データで検証する。"""
import json
import os
import sys
import traceback
from pathlib import Path
from qpe_ui_maya import pause, waitFor
from qpeQt import QtCore, QtWidgets, QtTest


def main(output_dir, finished=None):
    """独立GUIまたは専用Mayaで操作対象と一覧の表示を検証する。

    Args:
        output_dir (Path): 証跡保存先。
        finished (callable | None): 専用Mayaの終了通知。
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(output_dir / 'settings.json')
    from quickPathExplorer import Explorer
    checks = []
    widget = None
    try:
        folder = output_dir / 'Assets'
        folder.mkdir(exist_ok=True)
        for name in ('Characters', 'Environments', 'Props', 'Textures'):
            (folder / name).mkdir(exist_ok=True)
        paths = [folder / name for name in ('Hero_animation_v001.ma', 'Hero_animation_v002.ma', 'notes.txt')]
        for path in paths:
            path.write_text('//Maya ASCII 2022 scene\n' if path.suffix == '.ma' else 'Review notes', encoding='utf-8')
        widget = Explorer(maya=bool(finished))
        widget.resize(1240, 790)
        widget.show()
        widget.navigate(str(folder))
        waitFor(lambda: widget.fileProxy.rowCount(widget.files.rootIndex()) == 3)
        pause(350)
        assert not widget.actionsPanel.isVisible()
        closed_width = widget.files.width()
        checks.append('details hidden by default')
        events = []
        widget.actionRequested.connect(lambda action: events.append((action, widget.operationPaths())))
        indices = [widget.fileProxy.mapFromSource(widget.fileModel.index(str(p))) for p in paths]
        for previous in ('none', 'other', 'multiple'):
            widget.files.clearSelection()
            if previous != 'none':
                widget.files.setCurrentIndex(indices[1])
            if previous == 'multiple':
                widget.files.selectionModel().select(indices[2], QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
            events[:] = []
            QtTest.QTest.mouseDClick(widget.files.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                                    widget.files.visualRect(indices[0]).center())
            pause(80)
            assert len(events) == 1 and events[0][0] == 'open' and [Path(p) for p in events[0][1]] == [paths[0]], events
            checks.append('double click from ' + previous)
        events[:] = []
        QtTest.QTest.mouseDClick(widget.files.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                                QtCore.QPoint(20, widget.files.viewport().height() - 10))
        assert not events
        checks.append('blank double click does not open')
        selected = widget.selectedPaths()
        widget.grab().save(str(output_dir / 'sidebar-closed.png'))
        QtTest.QTest.mouseClick(widget.inspectorButton, QtCore.Qt.LeftButton)
        pause(250)
        assert widget.actionsPanel.isVisible() and widget.actionsPanel.parentWidget() is widget.outer
        assert widget.actionsPanel.height() == widget.vertical.height()
        assert widget.files.width() < closed_width and widget.selectedPaths() == selected
        assert widget.files.columnWidth(0) > 235
        checks.append('full height sidebar and flexible filename width')
        widget.grab().save(str(output_dir / 'sidebar-open.png'))
        QtTest.QTest.mouseClick(widget.inspectorButton, QtCore.Qt.LeftButton)
        pause(150)
        assert widget.files.width() == closed_width and widget.selectedPaths() == selected
        checks.append('close restores file width and selection')
        views = [v for v in widget.columns.findChildren(QtWidgets.QListView) if v.isVisible()]
        assert views and all(v.alternatingRowColors() for v in views) and widget.files.alternatingRowColors()
        checks.append('alternating folder and file rows')
        widget.files.setCurrentIndex(indices[2])
        waitFor(lambda: widget.previewText.toPlainText() == 'Review notes')
        from unittest.mock import patch
        with patch.object(widget, 'requestFiles') as request:
            widget.openSelectedFile()
            assert request.call_count == 1
            assert request.call_args[0][0] == 'open'
            assert [Path(v) for v in request.call_args[0][1]] == [paths[2]]
        checks.append('Open dispatch works while sidebar is hidden')
        widget.addFavoritePath(str(paths[2]))
        favorite = widget.places.topLevelItem(0).child(0)
        assert not favorite.icon(0).isNull()
        widget._placeClicked(favorite, 0)
        waitFor(lambda: Path(widget.selectedPath()) == paths[2])
        groups = [widget.places.topLevelItem(i) for i in range(widget.places.topLevelItemCount())]
        assert [g.text(0) for g in groups] == ['Favorites', 'Recent items']
        recent_paths = [Path(groups[1].child(i).data(0, QtCore.Qt.UserRole)) for i in range(groups[1].childCount())]
        assert folder in recent_paths and paths[0] not in recent_paths
        # このテストはOpen要求だけを捕捉しており、ホストでの読込成功前にRecentへ加えてはいけない。
        assert all(not groups[1].child(i).icon(0).isNull() for i in range(groups[1].childCount()))
        checks.append('Favorites/Recent only, folder/file icons and file favorite selection')
        if finished:
            import maya.cmds as cmds
            import qpeHost
            widget.actionRequested.connect(lambda action: qpeHost.perform(widget, action))
            cmds.file(new=True, force=True)
            widget.files.setCurrentIndex(indices[1])
            QtTest.QTest.mouseDClick(widget.files.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                                    widget.files.visualRect(indices[0]).center())
            pause(100)
            assert Path(cmds.file(query=True, sceneName=True)) == paths[0]
            checks.append('Maya opens clicked scene from different selection')
            widget.prepareSave(str(folder))
            assert widget.actionsPanel.isVisible() and widget.inspectorButton.isChecked()
            assert widget.details.isHidden() and widget.fileName.width() > 200
            checks.append('save here reveals sidebar')
        result = dict(status='passed', checks=checks)
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    (output_dir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)
    if widget is not None:
        # このテストのExplorerはqpeHost.showの管理対象ではない。
        # MayaのPython終了まで残さず、所有している検証画面をQtが生存中に破棄する。
        widget.close()
        widget.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(widget, QtCore.QEvent.DeferredDelete)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(sys.argv[1])
    sys.exit(0 if result['status'] == 'passed' else 1)
