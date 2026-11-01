"""画像読込中のmll解除・再ロードを専用Mayaで検査する。"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import time


def main(output_dir, finished):
    """旧モジュールのワーカーが残る境界で、独立Qtと画像結果を検査する。"""
    from maya import cmds
    from qpeQt import QtCore, QtGui, QtWidgets
    import qpeHost
    import qpeNative
    out = Path(output_dir)
    source = QtGui.QImage(240, 120, QtGui.QImage.Format_RGB32)
    source.fill(QtGui.QColor('#227788'))
    path = out / 'worker-lifetime.png'
    assert source.save(str(path))
    qpeNative.prepareImageReader()
    reader = qpeNative.readImage
    plugin = cmds.pluginInfo('quickPathExplorer', query=True, path=True)
    qpeHost.show(str(out))
    other = QtWidgets.QLineEdit('independent Qt')
    other.show()
    started = threading.Event()

    def read_images():
        """Maya APIを呼ばず、解除前のモジュールへの参照を保持して読む。"""
        started.set()
        for unused in range(1000):
            image, size, error = reader(str(path))
            assert not error and not image.isNull() and size == QtCore.QSize(240, 120)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(read_images)
        assert started.wait(5)
        pending_at_unload = not future.done()
        assert pending_at_unload, 'Worker finished before the unload boundary'
        cmds.unloadPlugin('quickPathExplorer')
        assert other.text() == 'independent Qt'
        cmds.loadPlugin(plugin)
        import qpeNative as current_native
        import qpeHost as current_host
        assert current_native is not qpeNative
        current_native.prepareImageReader()
        current_host.show(str(out))
        deadline = time.monotonic() + 30
        while not future.done():
            if time.monotonic() > deadline:
                raise TimeoutError('Image worker did not finish across reload')
            QtWidgets.QApplication.processEvents()
        future.result()
        assert not current_native.readImage(str(path))[0].isNull()
    cmds.unloadPlugin('quickPathExplorer')
    other.close()
    other.deleteLater()
    result = dict(status='passed', maya=cmds.about(version=True), pending_at_unload=pending_at_unload,
                  reads=1000, input='Qt API / worker thread / Maya plugin commands',
                  checks=['old image worker survives unload/reload', 'new embedded module reads image',
                          'independent Qt input remains intact'])
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    finished(result)
    return result
