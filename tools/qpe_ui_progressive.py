"""大量一覧の段階表示・取消・世代逆転・選択保持を専用Qtモデルで検証する。"""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtWidgets, QtTest
from qpeDirectoryModel import DirectoryModel, ScanSignals, SORT_VALUE
from qpe_ui_maya import pause, waitFor


class ManualJob(QtCore.QRunnable):
    """実I/Oと独立して完了順序だけを制御する。"""
    def __init__(self, path, generation):
        """要求対象と同じ識別子を保持する。"""
        super().__init__()
        self.path, self.generation = path, generation
        self.signals = ScanSignals()

    def run(self):
        """GUI側から明示的に完了を注入するため、ワーカーは何もしない。"""


def main(output_dir, finished=None):
    """実ウィジェットを使い、未完了一覧を完了扱いしないことも確認する。"""
    out = Path(output_dir).resolve()
    if ROOT / '.maya-output' not in out.parents:
        raise ValueError('Dedicated output required')
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    paths = [out / name for name in ('A', 'B')]
    for path in paths:
        path.mkdir(exist_ok=True)
    a, b = (str(p).replace('\\', '/') for p in paths)
    view = QtWidgets.QTreeView()
    model = DirectoryModel(view)
    model.jobFactory = ManualJob
    model.setFilter(QtCore.QDir.Files)
    view.setModel(model)
    view.setUniformRowHeights(True)
    view.resize(900, 600)
    view.show()
    loaded, checks = [], []
    model.directoryLoaded.connect(lambda path: loaded.append(path))
    entries = [('item_%05d.%s' % (i, 'txt' if i % 2 else 'ma'), False, i, 1000.) for i in range(3000)]
    entries[-1] = (entries[-1][0], False, 2 ** 40 + 1025, 1000.)

    def begin(path, data):
        """要求し、描画前に最初の一片だけを適用する。"""
        model.activate([path])
        view.setRootIndex(model.pathIndex(path))
        generation = model._generations[path]
        model.receive(path, generation, data, '')
        model._mergeTimer.stop()
        model._drainMerge()
        model._mergeTimer.stop()
        return generation

    def finish(path):
        """Qtイベントで残りを反映する。"""
        model._mergeTimer.start(0)
        waitFor(lambda: model.states.get(path, ('',))[0] == 'ready')
        pause(30)

    try:
        import qpeSettings
        assert qpeSettings.writeSettings({'streamTest': 1})
        with patch.object(qpeSettings.QtCore, 'QSaveFile', wraps=QtCore.QSaveFile) as writes:
            assert qpeSettings.writeSettings({'streamTest': 1}) and writes.call_count == 0
            assert qpeSettings.writeSettings({'streamTest': 2}) and writes.call_count == 1
        assert qpeSettings.readSettings()['streamTest'] == 2
        checks.append('identical settings skip commit; changed settings persist atomically')
        generation = begin(a, entries)
        index = model.pathIndex(a)
        count = model.rowCount(index)
        assert 0 < count < 3000, count
        assert model.states[a][0] == 'loading' and a not in loaded
        target = QtCore.QPersistentModelIndex(model.index(0, 0, index))
        view.setCurrentIndex(QtCore.QModelIndex(target))
        view.verticalScrollBar().setValue(0)
        finish(a)
        assert model.rowCount(index) == 3000 and loaded.count(a) == 1
        assert view.currentIndex() == target and view.verticalScrollBar().value() == 0
        assert [model.index(i, 0, index).data() for i in range(3000)] == sorted(e[0] for e in entries)
        checks.append('partial rows usable while loading; final count/order/current/scroll retained')

        newer = entries + [('z_new.txt', False, 9, 1000.)]
        old = begin(a, newer)
        frozen = model.rowCount(index)
        model.activate([b])
        model.receive(b, model._generations[b], [('only.txt', False, 1, 1000.)], '')
        pause(80)
        assert model.rowCount(index) == frozen and not model._pendingMerges
        model.activate([a])
        current = model._generations[a]
        model.receive(a, old, [], 'old error')
        assert model.states[a][0] == 'loading'
        model.receive(a, current, entries, '')
        finish(a)
        assert model.rowCount(index) == 3000 and not model.pathIndex(a + '/z_new.txt').isValid()
        checks.append('A-B-A cancels pending chunks and rejects stale success/error')

        begin(a, newer)
        model.setNameFilters(['*.txt'])
        pause(60)
        assert model.states[a][0] == 'ready'
        assert model.rowCount(index) == 1501
        assert all(model.index(i, 0, index).data().endswith('.txt') for i in range(1501))
        model.setNameFilters([])
        assert model.rowCount(index) == 3001
        checks.append('filter changes during merge do not resume obsolete row additions')

        begin(a, entries)
        model.request(a)
        model.receive(a, model._generations[a], [], 'test failure')
        pause(50)
        assert model.states[a] == ('error', 'test failure') and model.rowCount(index) == 0
        checks.append('latest failed refresh removes stale partial rows and stays error')

        begin(a, entries)
        frozen = model.rowCount(index)
        model.suspend()
        pause(80)
        assert model.rowCount(index) == frozen and not model._pendingMerges
        begin(a, entries)
        view.close()
        model.suspend()
        view.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        pause(30)
        checks.append('suspend/close discard queued GUI work without later mutations')
        from quickPathExplorer import Explorer
        explorer = Explorer(maya=bool(finished))
        try:
            explorer.resize(1100, 800)
            explorer.show()
            explorer.fileModel.jobFactory = ManualJob
            explorer.setBrowseRoot(str(out))
            explorer.folderTabs.openPath(a)
            # 読込待ちのタブに保存済みの選択がある条件を再現する。
            explorer.folderTabs.states[explorer.folderTabs.active]['selected'] = [a + '/item_00001.txt']
            files = explorer.fileModel
            files.receive(a, files._generations[a], entries, '')
            files._mergeTimer.stop()
            files._drainMerge()
            files._mergeTimer.stop()
            pause(30)
            item = explorer.fileProxy.index(0, 0, explorer.files.rootIndex())
            expected = files.filePath(explorer.fileProxy.mapToSource(item))
            QtTest.QTest.mouseClick(explorer.files.viewport(), QtCore.Qt.LeftButton,
                                   QtCore.Qt.NoModifier, explorer.files.visualRect(item).center())
            files._mergeTimer.start(0)
            waitFor(lambda: files.states[a][0] == 'ready')
            pause(100)
            assert explorer.selectedPaths() == [expected], explorer.selectedPaths()
            checks.append('selection made during streamed tab loading overrides saved tab selection')

            # キャッシュ済みタブは次のディスク列挙を止めても選択をすぐ復元する。
            explorer.folderTabs.openPath(b)
            files.receive(b, files._generations[b], [('only.txt', False, 1, 1000.)], '')
            pause(60)
            explorer.folderTabs.bar.setCurrentIndex(1)
            pause(80)
            assert files.states[a][0] == 'loading'
            assert explorer.folderTabs.pendingSerial is None
            assert explorer.selectedPaths() == [expected]
            # 最新結果で削除された保存選択は消え、別行へ移らない。
            files.receive(a, files._generations[a], entries[1:], '')
            waitFor(lambda: files.states[a][0] == 'ready')
            assert explorer.selectedPaths() == []
            checks.append('cached tab restores before refresh; removed selection is not redirected')
            explorer.files.sortByColumn(1, QtCore.Qt.DescendingOrder)
            largest = explorer.fileProxy.index(0, 1, explorer.files.rootIndex())
            assert largest.data(SORT_VALUE) == 2 ** 40 + 1025
            assert largest.data() == QtCore.QLocale.system().formattedDataSize(2 ** 40 + 1025)
            checks.append('terabyte sizes retain exact numeric sorting and formatted display')
        finally:
            explorer.close()
            explorer.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        result = dict(status='passed', checks=checks, qt=QtCore.qVersion(), evidence='Qt programmatic, not OS input')
    finally:
        # close済みの場合はPySideの無効ラッパーへ触れない。
        from qpeQt import shiboken
        if shiboken.isValid(view):
            model.suspend()
            view.close()
            view.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    print(json.dumps(main(sys.argv[1])))
    QtCore.QThreadPool.globalInstance().waitForDone(10000)
