"""画像ワーカーとGUI QObject破棄の同時実行を専用プロセスで検証する。"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
import traceback


def main(output_dir, finished=None):
    """GIL/Qtロックの逆転、画像寸法、縮小結果、読込失敗を検査する。"""
    from qpeQt import QtCore, QtGui, QtWidgets
    from qpeNative import prepareImageReader, readImage
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / '日本語 image.png'
    source = QtGui.QImage(240, 120, QtGui.QImage.Format_RGB32)
    source.fill(QtGui.QColor('#227788'))
    assert source.save(str(path))
    prepareImageReader()
    checks = []
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(readImage, str(path), index % 2 == 0) for index in range(300)]
            deadline = time.monotonic() + 30
            cycles = 0
            while not all(item.done() for item in futures):
                if time.monotonic() > deadline:
                    raise TimeoutError('Image workers did not finish during QObject destruction')
                for unused in range(20):
                    owner = QtCore.QObject()
                    child = QtCore.QObject(owner)
                    child.setObjectName('qpeImageWorkerProbe')
                    owner.deleteLater()
                    QtCore.QCoreApplication.sendPostedEvents(owner, QtCore.QEvent.DeferredDelete)
                cycles += 1
                QtWidgets.QApplication.processEvents()
            for index, future in enumerate(futures):
                image, size, error = future.result()
                assert not error and size == QtCore.QSize(240, 120), (size, error)
                assert image.isNull() == bool(index % 2)
        checks.append(dict(operation='300 worker reads with GUI QObject destruction', gui_cycles=cycles))
        image, size, error = readImage(str(out / 'missing.png'))
        assert image.isNull() and not size.isValid() and error
        checks.append('missing image returns an error without an exception or crash')
        result = dict(status='passed', checks=checks, input='Qt API / worker threads')
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if finished:
        finished(result)
    return result
