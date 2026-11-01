"""フォルダー移動・戻る・タブ切替の待ち時間と再列挙を計測する。"""
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtWidgets
from quickPathExplorer import Explorer
import qpeFileIcons


def main(output_dir, finished=None):
    """現行UIのデータ内容・復元完了を待ち、パスと件数も確認する。"""
    out = Path(output_dir).resolve()
    if not (ROOT / ".maya-output") in out.parents:
        raise ValueError("Benchmark output must be inside .maya-output")
    out.mkdir(parents=True, exist_ok=True)
    base = out / 'fixtures'
    for name, count in [('empty', 0), ('files_1000', 1000), ('files_5000', 5000)]:
        folder = base / name
        folder.mkdir(parents=True, exist_ok=True)
        for number in range(count):
            (folder / ('item_%05d.txt' % number)).write_text('QPE benchmark fixture\n', encoding='utf-8')
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    e = Explorer(maya=bool(finished))
    e.resize(1280, 900)
    e.show()
    e.setBrowseRoot(str(base))
    def pump(ms=5):
        """GUIイベントを処理し、指定時間だけ待つ。"""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()
    def settled():
        """モデル要求とタブ復元が完了するまで待つ。"""
        deadline = time.perf_counter() + 90
        while (any(m.states.get(p, ('',))[0] != 'ready' for m in (e.folderModel,e.fileModel) for p in m._active)
               or e.folderTabs.pendingSerial is not None):
            if time.perf_counter() > deadline:
                raise TimeoutError('navigation did not settle')
            pump()
        QtWidgets.QApplication.processEvents()
    e.navigate(str(base / 'empty'))
    settled()
    traces, rows, gaps = [], [], []
    e.folderModel.traceSink = traces.append
    e.fileModel.traceSink = traces.append
    previous = [time.perf_counter()]
    def tick():
        """GUIイベント配送間隔を記録する。"""
        now = time.perf_counter()
        gaps.append((now - previous[0]) * 1000)
        previous[0] = now
    timer = QtCore.QTimer(e)
    timer.setInterval(10)
    timer.timeout.connect(tick)
    timer.start()
    def measure(name, action, count):
        """操作を一度実行し、件数を照合して待ち時間を記録する。"""
        pump(100)
        traces.clear()
        gaps.clear()
        with patch.object(qpeFileIcons, 'windowsIcon', wraps=qpeFileIcons.windowsIcon) as native:
            begin = previous[0] = time.perf_counter()
            action()
            returned = time.perf_counter()
            settled()
            end = time.perf_counter()
            pump(30)
            actual = e.fileProxy.rowCount(e.files.rootIndex())
            assert actual == count, (name, actual)
            rows.append(dict(name=name, handler_ms=(returned-begin)*1000, ready_ms=(end-begin)*1000,
                             max_event_gap_ms=max(gaps or [0]), rows=actual,
                             enumerations=sum(t['operation']=='directory-start' for t in traces),
                             shell_icons=native.call_count, retained_file_items=len(e.fileModel._items),
                             file_snapshots=len(e.fileModel._snapshots)))
        (out / 'result.json').write_text(json.dumps(dict(cases=rows), indent=2), encoding='utf-8')
    measure('first_A_1000', lambda:e.navigate(str(base/'files_1000')), 1000)
    measure('first_B_5000', lambda:e.navigate(str(base/'files_5000')), 5000)
    for repeat in range(3):
        measure('back_A_%d'%repeat, e._back, 1000)
        measure('forward_B_%d'%repeat, e._forward, 5000)
    measure('new_tab_A', lambda:e.folderTabs.openPath(str(base/'files_1000')), 1000)
    for repeat in range(3):
        measure('tab_B_%d'%repeat, lambda:e.folderTabs.bar.setCurrentIndex(0), 5000)
        measure('tab_A_%d'%repeat, lambda:e.folderTabs.bar.setCurrentIndex(1), 1000)
    measure('empty_after_browsing', lambda:e.navigate(str(base/'empty')), 0)
    result = dict(status='passed', cases=rows, qt=QtCore.qVersion(), maya=bool(finished))
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
