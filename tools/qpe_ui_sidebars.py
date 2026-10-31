"""左右サイドバーの繰り返し開閉と末端カラムの可視範囲を検証する。"""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_maya import pause, waitFor
from qpeQt import QtCore, QtWidgets


class PaintPositions(QtCore.QObject):
    """実際の描画時に見える列位置を記録する。"""

    def __init__(self, columns):
        """対象カラムを保持する。"""
        super().__init__(columns)
        self.columns = columns
        self.positions = []

    def eventFilter(self, watched, event):
        """入力を妨げず、カラムの描画直前の位置だけを採取する。"""
        if event.type() == QtCore.QEvent.Paint and isinstance(watched, QtWidgets.QWidget) and self.columns.isAncestorOf(watched):
            views = [v for v in self.columns.findChildren(QtWidgets.QListView) if v.isVisible()]
            self.positions.append(tuple(sorted((v.mapTo(self.columns.viewport(), QtCore.QPoint()).x(), v.width()) for v in views)))
        return False


def main(output_dir, finished=None):
    """専用フォルダーを使いQt単体またはMayaホストで検証する。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(output_dir / 'settings.json')
    root = output_dir / 'Project'
    child = root.joinpath(*('Folder_long_name_%d' % i for i in range(7)))
    (child / 'Leaf').mkdir(parents=True, exist_ok=True)
    if finished:
        import qpeHost
        widget = qpeHost.show(str(child))
    else:
        from quickPathExplorer import Explorer
        widget = Explorer()
    widget.window().resize(1280, 820)
    widget.show()
    widget.setBrowseRoot(str(root))
    widget.navigate(str(child))
    waitFor(lambda: widget.folderModel.rowCount(widget.columns.currentIndex()) == 1)
    pause(400)
    widget.sidebarButton.setChecked(True)
    widget.inspectorButton.setChecked(True)
    pause(200)
    widget.outer.setSizes([180, widget.outer.width() - 180 - 310 - 2 * widget.outer.handleWidth(), 310])
    pause(150)
    baseline = widget.outer.sizes()
    for _ in range(20):
        widget.inspectorButton.setChecked(False)
        pause(30)
        assert abs(widget.outer.sizes()[0] - baseline[0]) <= 1, (baseline, widget.outer.sizes())
        widget.inspectorButton.setChecked(True)
        pause(30)
        assert all(abs(a - b) <= 1 for a, b in zip(widget.outer.sizes(), baseline)), (baseline, widget.outer.sizes())
        widget.sidebarButton.setChecked(False)
        pause(30)
        assert abs(widget.outer.sizes()[2] - baseline[2]) <= 1
        widget.sidebarButton.setChecked(True)
        pause(30)
        assert all(abs(a - b) <= 1 for a, b in zip(widget.outer.sizes(), baseline)), (baseline, widget.outer.sizes())
    checks = ['20 repeated left/right toggles preserve manual widths']
    widget.inspectorButton.setChecked(False)
    widget.columns.horizontalScrollBar().setValue(0)
    widget.inspectorButton.setChecked(True)
    pause(500)
    views = [view for view in widget.columns.findChildren(QtWidgets.QListView)
             if view.isVisible() and view.rootIndex() == widget.columns.currentIndex()]
    assert views
    view = views[-1]
    x = view.mapTo(widget.columns.viewport(), QtCore.QPoint()).x()
    assert x >= 0 and x + view.width() <= widget.columns.viewport().width(), (x, view.width(), widget.columns.viewport().width())
    checks.append('opening inspector reveals deepest child column')
    for inspector in (False, True):
        widget.inspectorButton.setChecked(inspector)
        widget.sidebarButton.setChecked(False)
        pause(100)
        widget.columns.horizontalScrollBar().setValue(0)
        observer = PaintPositions(widget.columns)
        QtWidgets.QApplication.instance().installEventFilter(observer)
        widget.sidebarButton.setChecked(True)
        pause(250)
        QtWidgets.QApplication.instance().removeEventFilter(observer)
        assert observer.positions and len(set(observer.positions)) == 1, observer.positions
        views = [v for v in widget.columns.findChildren(QtWidgets.QListView)
                 if v.isVisible() and v.rootIndex() == widget.columns.currentIndex()]
        assert views
        view = views[-1]
        x = view.mapTo(widget.columns.viewport(), QtCore.QPoint()).x()
        assert x >= 0 and x + view.width() <= widget.columns.viewport().width()
    checks.append('opening left sidebar reveals child with inspector hidden or shown')
    checks.append('painted column positions do not jump during left sidebar opening')
    bar = widget.columns.horizontalScrollBar()
    bar.setValue(0)
    pause(500)
    assert bar.value() == 0
    checks.append('later repaint preserves manually scrolled ancestor position')
    widget.grab().save(str(output_dir / 'sidebars.png'))
    result = {'status': 'passed', 'checks': checks, 'widths': baseline}
    (output_dir / 'result.json').write_text(json.dumps(result), encoding='utf-8')
    print(result, flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    main(Path(sys.argv[1]))
