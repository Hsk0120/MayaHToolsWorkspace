"""1000画像の列挙・サムネイル切替時のイベント応答を実測する。"""
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtGui, QtWidgets
from qpe_ui_maya import waitFor, pause


def main(output):
    """専用の小画像だけで測定し、重い実素材の性能保証と区別する。"""
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    folder = root / 'images'
    folder.mkdir(exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(root / 'settings.json')
    image = QtGui.QImage(32, 32, QtGui.QImage.Format_RGB32)
    image.fill(QtGui.QColor('#4488aa'))
    for number in range(1000):
        image.save(str(folder / ('image_%04d.png' % number)))
    from quickPathExplorer import Explorer
    e = Explorer()
    e.resize(1280, 900)
    e.show()
    intervals = []
    previous = [time.monotonic()]
    timer = QtCore.QTimer()
    timer.setInterval(20)
    def tick():
        """メインスレッドに届いた実時刻の間隔を測る。"""
        now = time.monotonic()
        intervals.append(now - previous[0])
        previous[0] = now
    timer.timeout.connect(tick)
    timer.start()
    start = time.monotonic()
    e.navigate(str(folder))
    waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1000)
    listing = time.monotonic() - start
    listing_max = max(intervals or [0])
    intervals.clear()
    previous[0] = time.monotonic()
    start = time.monotonic()
    w = e.organizer.workspace
    w.mode.setCurrentIndex(1)
    waitFor(lambda: w.grid.count() == 1000 and not w.restoring)
    elapsed = time.monotonic() - start
    pause(500)
    result = dict(status='passed', count=1000, listingSeconds=listing, listingMaxEventGap=listing_max,
                  thumbnailsSeconds=elapsed, thumbnailsMaxEventGap=max(intervals or [0]), eventTicks=len(intervals),
                  cacheCount=len(w.cache), activeImageWorkers=len(w.previewJobs), fixture='32x32 PNG, local disk')
    assert len(intervals) > 1 and len(w.cache) <= 256 and len(w.previewJobs) <= 2
    e.grab().save(str(root / '1000-images.png'))
    timer.stop()
    e.close()
    (root / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    main(sys.argv[1])
    QtCore.QThreadPool.globalInstance().waitForDone(10000)
