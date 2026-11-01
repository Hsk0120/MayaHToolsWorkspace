"""起動後最初の日本語フォルダーで、構築・先頭描画・全件完了を分けて測る。"""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtWidgets


def main(output_dir, finished=None):
    """専用設定/データだけで起動し、描画中の件数と日本語表示も記録する。"""
    from quickPathExplorer import Explorer
    out = Path(output_dir).resolve()
    if ROOT / '.maya-output' not in out.parents:
        raise ValueError('Dedicated output required')
    out.mkdir(parents=True, exist_ok=True)
    fixture = out / '初回フォルダー'
    fixture.mkdir(exist_ok=True)
    count = int(os.environ.get('QPE_FIRST_COUNT', '1000'))
    for number in range(count):
        (fixture / ('日本語_%05d.txt' % number)).write_bytes(b'fixture')
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    started = time.perf_counter()
    e = Explorer(maya=bool(finished))
    result = dict(construct_ms=(time.perf_counter() - started) * 1000, qt=QtCore.qVersion(),
                  maya=bool(finished), font=e.font().family(), rows=count)

    class PaintProbe(QtCore.QObject):
        """実描画の配送を観測し、UI処理へ介入しない。"""
        def eventFilter(self, watched, event):
            """先頭内容があるPaintイベントを時刻として使う。"""
            if event.type() == QtCore.QEvent.Paint and 'first_content_ms' not in result:
                rows = e.fileProxy.rowCount(e.files.rootIndex())
                if rows:
                    result['first_content_ms'] = (time.perf_counter() - started) * 1000
                    result['first_content_rows'] = rows
            return False

    probe = PaintProbe(e)
    e.files.viewport().installEventFilter(probe)
    e.resize(1280, 800)
    e.browseRoot = str(out).replace('\\', '/')
    e.show()
    e.navigate(str(fixture))
    result['show_navigate_ms'] = (time.perf_counter() - started) * 1000
    deadline = time.perf_counter() + 60
    while (e.fileModel.states.get(e.currentDirectory, ('',))[0] != 'ready'
           or 'first_content_ms' not in result):
        if time.perf_counter() > deadline:
            raise TimeoutError('First display did not finish')
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(5, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()
    result['ready_ms'] = (time.perf_counter() - started) * 1000
    assert e.fileProxy.rowCount(e.files.rootIndex()) == count
    assert e.fileProxy.index(0, 0, e.files.rootIndex()).data() == '日本語_00000.txt'
    e.grab().save(str(out / 'first-display.png'))
    result.update(status='passed', evidence='Qt programmatic; constructor through Paint/ready; excludes Python import')
    e.close()
    e.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    print(json.dumps(main(sys.argv[1])))
    QtCore.QThreadPool.globalInstance().waitForDone(10000)
