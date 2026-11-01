"""専用一覧で選択・検索・ペイン・スクロールの応答時間と内容を検証する。"""
import json
import cProfile
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtWidgets
from qpe_ui_maya import pause, waitFor


def main(output_dir, finished=None):
    """操作ハンドラーと描画イベント処理までを別々に記録する。"""
    from quickPathExplorer import Explorer
    out = Path(output_dir).resolve()
    if ROOT / '.maya-output' not in out.parents:
        raise ValueError('Output must be inside .maya-output')
    out.mkdir(parents=True, exist_ok=True)
    fixture = out / 'files'
    fixture.mkdir(exist_ok=True)
    for number in range(2000):
        (fixture / ('item_%05d.txt' % number)).write_bytes(b'fixture\n')
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    e = Explorer(maya=bool(finished))
    e.resize(1280, 900)
    e.show()
    e.setBrowseRoot(str(out))
    e.navigate(str(fixture))
    waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 2000)
    pause(500)
    cases = []

    def measure(name, action, verify):
        """操作結果を照合し、同期処理とイベント処理時間を分ける。"""
        pause(100)
        profiler = cProfile.Profile() if os.environ.get('QPE_PROFILE_ACTIONS') else None
        if profiler is not None:
            profiler.enable()
        begin = time.perf_counter()
        action()
        returned = time.perf_counter()
        QtWidgets.QApplication.processEvents()
        end = time.perf_counter()
        if profiler is not None:
            profiler.disable()
            profiler.dump_stats(str(out / (name + '.prof')))
        verify()
        cases.append(dict(name=name, handler_ms=(returned - begin) * 1000,
                          painted_ms=(end - begin) * 1000))

    def selected(count):
        """選択件数と表示を照合する。"""
        assert len(e.selectedPaths()) == count
        if count:
            assert '%d selected' % count in e.footer.text()

    for repeat in range(3):
        measure('select_all_%d' % repeat, e.files.selectAll, lambda: selected(2000))
        measure('clear_selection_%d' % repeat, e.files.clearSelection, lambda: selected(0))
        index = e.fileProxy.index(repeat, 0, e.files.rootIndex())
        measure('select_one_%d' % repeat, lambda: e.files.setCurrentIndex(index), lambda: selected(1))
        measure('sidebar_show_%d' % repeat, lambda: e.sidebarButton.setChecked(True),
                lambda: None)
        measure('sidebar_hide_%d' % repeat, lambda: e.sidebarButton.setChecked(False), lambda: None)
        measure('inspector_show_%d' % repeat, lambda: e.inspectorButton.setChecked(True), lambda: None)
        measure('inspector_hide_%d' % repeat, lambda: e.inspectorButton.setChecked(False), lambda: None)
        measure('search_%d' % repeat, lambda: e.search.setText('item_001'), lambda: None)
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 100)
        measure('clear_search_%d' % repeat, e.search.clear, lambda: None)
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 2000)
        bar = e.files.verticalScrollBar()
        measure('scroll_bottom_%d' % repeat, lambda: bar.setValue(bar.maximum()), lambda: None)
        measure('scroll_top_%d' % repeat, lambda: bar.setValue(0), lambda: None)
    checks = []
    e.files.selectAll()
    with patch.object(QtCore, 'QFileInfo', side_effect=AssertionError('Selection must not stat files')):
        e._updateFooter()
    assert QtCore.QLocale.system().formattedDataSize(16000) in e.footer.text()
    checks.append('selection size uses enumerated metadata without filesystem queries')
    (fixture / 'item_00000.txt').write_bytes(b'fixture\n' * 20)
    e.fileModel.request(str(fixture))
    waitFor(lambda: QtCore.QLocale.system().formattedDataSize(16152) in e.footer.text())
    checks.append('refreshed file metadata updates the selected total')
    e.files.clearSelection()
    e.files.sortByColumn(0, QtCore.Qt.DescendingOrder)
    first = e.fileProxy.index(0, 0, e.files.rootIndex())
    last = e.fileProxy.index(1999, 0, e.files.rootIndex())
    selection = e.files.selectionModel()
    selection.select(first, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
    selection.select(last, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
    assert [Path(p).name for p in e.selectedPaths()] == ['item_01999.txt', 'item_00000.txt']
    checks.append('disjoint selection keeps descending display order and exact targets')
    selection.clear()
    selection.select(first.sibling(first.row(), 1), QtCore.QItemSelectionModel.Select)
    assert e.selectedPaths() == [] and e.selectedPath() == ''
    selection.clear()
    checks.append('partial cell selection retains Qt selectedRows semantics')
    e.files.sortByColumn(0, QtCore.Qt.AscendingOrder)
    import quickPathExplorer as implementation
    with patch.object(implementation, 'PreviewJob', wraps=implementation.PreviewJob) as jobs:
        for number in range(20):
            e.files.setCurrentIndex(e.fileProxy.index(number, 0, e.files.rootIndex()))
        assert jobs.call_count == 0
        e.inspectorButton.setChecked(True)
        assert jobs.call_count == 0
        e.detailsHeading.setChecked(True)
        waitFor(lambda: e.previewText.toPlainText() == 'fixture\n')
        assert jobs.call_count == 1
        e.detailsHeading.setChecked(False)
        e.files.setCurrentIndex(e.fileProxy.index(30, 0, e.files.rootIndex()))
        assert jobs.call_count == 1
        e.detailsHeading.setChecked(True)
        waitFor(lambda: e.previewText.toPlainText() == 'fixture\n')
        assert jobs.call_count == 2 and e._previewPath.endswith('item_00030.txt')
    checks.append('hidden preview does no work; expanding loads only the latest selection')
    icons = getattr(e.files, '_visibleIcons', None)
    if icons is not None:
        waitFor(lambda: not icons.timer.isActive())
        with patch.object(icons, 'key', wraps=icons.key) as keys:
            pause(350)
            assert keys.call_count == 0, keys.call_count
        bar.setValue(bar.maximum())
        assert icons.timer.isActive()
        waitFor(lambda: not icons.timer.isActive())
        target = e.fileProxy.index(1999, 0, e.files.rootIndex())
        assert icons.applied.get(QtCore.QPersistentModelIndex(target)) == icons.key(target)
        checks.append('idle icons stop polling and scroll resumes current visible requests')
    else:
        native = e.files._nativeIcons
        # 未訪問の中段に移り、C++側でも休止後に新しい可視行を取得する。
        before = native.property('requested') or 0
        bar.setValue(bar.maximum() // 2)
        waitFor(lambda: (native.property('requested') or 0) > before)
        checks.append('native icons resume visible requests after a new scroll position')
    result = dict(status='passed', cases=cases, checks=checks, qt=QtCore.qVersion(), maya=bool(finished),
                  evidence='Qt programmatic operations; not OS input')
    e.grab().save(str(out / 'overview.png'))
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    e.close()
    e.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    main(sys.argv[1])
    QtCore.QThreadPool.globalInstance().waitForDone(10000)
