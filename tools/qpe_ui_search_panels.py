"""検索解除と補助列の寸法更新を、専用データと実Qtモデルで検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtWidgets
from qpeDirectoryModel import SORT_VALUE
from qpe_ui_maya import pause, waitFor


def main(output_dir, finished=None):
    """表示単位・数値ソート・文字サイズ・スクロール後の列幅を照合する。"""
    from quickPathExplorer import Explorer
    out = Path(output_dir).resolve()
    if ROOT / '.maya-output' not in out.parents:
        raise ValueError('Output must be inside .maya-output')
    out.mkdir(parents=True, exist_ok=True)
    fixture = out / 'files'
    fixture.mkdir(exist_ok=True)
    for i in range(180):
        (fixture / ('item_%03d.txt' % i)).write_bytes(b'x' * i)
    special = fixture / 'zz_NEEDLE[1].very_long_extension_for_width'
    special.write_bytes(b'x' * 4096)
    (fixture / 'subfolder').mkdir(exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    e = Explorer(maya=bool(finished))
    checks = []
    try:
        e.resize(1700, 900)
        e.show()
        e.setBrowseRoot(str(out))
        e.navigate(str(fixture))
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 181)
        e.search.setText('needle[1]')
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1)
        assert e.fileProxy.index(0, 0, e.files.rootIndex()).data() == special.name
        e.search.clear()
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 181)
        assert not any(e.fileModel.isDir(e.fileProxy.mapToSource(e.fileProxy.index(i, 0, e.files.rootIndex())))
                       for i in range(181))
        checks.append('literal/case-insensitive search and clear retain files-only root')

        for order in (QtCore.Qt.AscendingOrder, QtCore.Qt.DescendingOrder):
            e.files.sortByColumn(1, order)
            values = [e.fileProxy.index(i, 1, e.files.rootIndex()).data(SORT_VALUE) for i in range(181)]
            assert values == sorted(values, reverse=order == QtCore.Qt.DescendingOrder)
            for row in (0, 180):
                index = e.fileProxy.index(row, 1, e.files.rootIndex())
                assert index.data() == QtCore.QLocale.system().formattedDataSize(index.data(SORT_VALUE))
        checks.append('zero/byte/KiB values keep numeric sort and formatted display in both directions')
        for column in (0, 2, 3):
            for order in (QtCore.Qt.AscendingOrder, QtCore.Qt.DescendingOrder):
                e.files.sortByColumn(column, order)
                values = [e.fileProxy.index(i, column, e.files.rootIndex()).data(SORT_VALUE) for i in range(181)]
                if column == 3:
                    values = [value.toMSecsSinceEpoch() for value in values]
                assert values == sorted(values, reverse=order == QtCore.Qt.DescendingOrder)
        checks.append('name/extension/date keep their typed sorting keys in both directions')
        e.files.sortByColumn(0, QtCore.Qt.AscendingOrder)
        last = e.fileProxy.mapFromSource(e.fileModel.pathIndex(str(special)))
        e.files.setCurrentIndex(last)
        e.files.scrollTo(last)
        pause(200)

        def widths_fit():
            """表示された各補助列が可視内容の必要幅を持つ。"""
            for column in (1, 2, 3):
                if not e.files.isColumnHidden(column):
                    assert e.files.columnWidth(column) >= e.files.sizeHintForColumn(column), column

        widths_fit()
        checks.append('scrolling to a long extension recomputes visible column widths')
        for width in (850, 550, 1700):
            e.resize(width, 900)
            for state in (True, False):
                e.inspectorButton.setChecked(state)
                e.sidebarButton.setChecked(state)
                pause(150)
                widths_fit()
                assert e.selectedPath() == str(special).replace('\\', '/')
        checks.append('narrow/full-width pane transitions retain selection and usable column sizes')
        e.resize(2000, 1000)
        for size in (18, 10, 12):
            e.appearance.apply(size, 100, save=False)
            pause(150)
            widths_fit()
        checks.append('font size changes recompute widths without clipping metadata')

        special.write_bytes(b'x' * 123456)
        e.fileModel.request(str(fixture))
        waitFor(lambda: e.fileProxy.mapFromSource(e.fileModel.pathIndex(str(special))).sibling(last.row(), 1)
                .data(SORT_VALUE) == 123456)
        pause(100)
        widths_fit()
        assert '1 selected' in e.footer.text()
        checks.append('metadata refresh updates formatted size, widths and selection')
        e.grab().save(str(out / 'overview.png'))
        result = dict(status='passed', checks=checks, qt=QtCore.qVersion())
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    finally:
        e.close()
        e.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(sys.argv[1])
    QtCore.QThreadPool.globalInstance().waitForDone(10000)
    sys.exit(0 if result['status'] == 'passed' else 1)
