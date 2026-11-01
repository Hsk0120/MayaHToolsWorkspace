"""単一配布・C++部品・ソート検索・破棄再ロードを専用Mayaで確認する。"""
import json
import os
from pathlib import Path
import sys
import time


def main(output_dir, finished=None):
    """専用の異種ファイルと外部Qt部品を使って所有権と結果を検査する。"""
    from maya import cmds
    from qpeQt import QtCore, QtGui, QtWidgets
    from qpeDirectoryModel import SORT_VALUE
    import qpeNative
    import qpeHost
    out = Path(output_dir)
    fixture = out / 'fixture'
    fixture.mkdir()
    for name, size in [('a.txt', 900), ('b.py', 12), ('c.ma', 2000), ('日本語.txt', 123)]:
        (fixture / name).write_bytes(b'x' * size)
    (fixture / 'child').mkdir()
    checks = []

    def wait(predicate):
        """イベント処理を続けつつ、観測可能な完了だけを待つ。"""
        deadline = time.monotonic() + 30
        while not predicate():
            if time.monotonic() > deadline:
                raise AssertionError('Timed out')
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(20, loop.quit)
            (loop.exec if hasattr(loop, 'exec') else loop.exec_)()

    assert qpeNative.available()
    e = qpeHost.show(str(fixture))
    wait(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 4)
    assert e.files.uniformRowHeights()
    assert e.files.itemDelegate().property('qpeNativeDelegate')
    assert not e.windowIcon().isNull() and not e.sidebarButton.icon().isNull()
    assert QtCore.QFile.exists(':/qpe/icons/chevron-dark.svg')
    assert all(getattr(module.__loader__, 'qpe_embedded', False) for name, module in list(sys.modules.items())
               if name.startswith('qpe') and name not in ('qpe_native_smoke',))
    checks.append('embedded imports and icons; native proxy/delegate; four file rows')
    e.files.sortByColumn(1, QtCore.Qt.AscendingOrder)
    root = e.files.rootIndex()
    assert [e.fileProxy.index(i, 1, root).data(SORT_VALUE) for i in range(4)] == [12, 123, 900, 2000]
    assert e.fileProxy.index(0, 1, root).data() == QtCore.QLocale.system().formattedDataSize(12)
    e.search.setText('日本語')
    wait(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1)
    assert e.fileProxy.index(0, 0, e.files.rootIndex()).data() == '日本語.txt'
    e.search.clear()
    wait(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 4)
    # 非同期取得の成功はプレースホルダーとの差分で確認する。
    index = e.fileProxy.index(0, 0, e.files.rootIndex())
    placeholder = e.fileModel._placeholderIcon.cacheKey()
    wait(lambda: index.data(QtCore.Qt.DecorationRole).cacheKey() != placeholder)
    checks.append('numeric size sort, units, Unicode search, asynchronous file icon')
    e.grab().save(str(out / 'native.png'))
    other = QtWidgets.QLineEdit('external Qt input')
    other.show()
    plugin = cmds.pluginInfo('quickPathExplorer', query=True, path=True)
    cmds.unloadPlugin('quickPathExplorer')
    assert other.text() == 'external Qt input'
    assert not cmds.workspaceControl(qpeHost.CONTROL, exists=True)
    cmds.loadPlugin(plugin)
    import qpeHost as reloaded
    second = reloaded.show(str(fixture))
    wait(lambda: second.fileProxy.rowCount(second.files.rootIndex()) == 4)
    cmds.unloadPlugin('quickPathExplorer')
    other.close()
    other.deleteLater()
    checks.append('unload with shown dock, unrelated Qt intact, reload and unload')
    result = dict(status='passed', checks=checks, input='Qt programmatic', maya=cmds.about(version=True))
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if finished:
        finished(result)
    return result
