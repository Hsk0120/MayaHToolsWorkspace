"""再訪・フォルダー除外・数値ソート・遅いアイコンの入力阻害を検証する。"""
import json
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtGui, QtWidgets
from qpe_ui_maya import pause, waitFor
from quickPathExplorer import Explorer
import qpeFileIcons


def main(output_dir, finished=None):
    """専用データだけを作り、通常QtとMaya内の同じ表示結果を検証する。"""
    out = Path(output_dir).resolve()
    if ROOT / '.maya-output' not in out.parents:
        raise ValueError('Dedicated output required')
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    root = out / 'fixtures'
    child = root / 'child'
    child.mkdir(parents=True, exist_ok=True)
    (root / 'small.txt').write_text('x' * 9, encoding='utf-8')
    (root / 'large.txt').write_text('x' * 1024, encoding='utf-8')
    (child / 'other.txt').write_text('other', encoding='utf-8')
    checks = []
    e = Explorer(maya=bool(finished))
    e.resize(1000, 750)
    e.show()

    def go(path):
        """結果の採用と描画を待つ。"""
        e.navigate(str(path))
        waitFor(lambda: e.fileModel.states.get(str(path).replace('\\', '/'), ('',))[0] == 'ready')
        pause(80)

    def names():
        """現在のファイルビューから表示行名を取得する。"""
        return [e.fileProxy.index(i, 0, e.files.rootIndex()).data()
                for i in range(e.fileProxy.rowCount(e.files.rootIndex()))]

    try:
        e.setBrowseRoot(str(root))
        go(child)
        go(root)
        assert sorted(names()) == ['large.txt', 'small.txt'], names()
        go(child)
        assert names() == ['other.txt'], names()
        go(root)
        assert sorted(names()) == ['large.txt', 'small.txt'], names()
        checks.append('parent/child/revisit: visited folder never appears in file rows')
        e.files.sortByColumn(1, QtCore.Qt.AscendingOrder)
        assert names() == ['small.txt', 'large.txt'], names()
        e.files.sortByColumn(1, QtCore.Qt.DescendingOrder)
        assert names() == ['large.txt', 'small.txt'], names()
        checks.append('size sort uses 9 < 1024, independent of display units')
        e.search.setText('small')
        assert names() == ['small.txt'], names()
        e.search.clear()
        assert len(names()) == 2
        checks.append('search invalidation still works with retained proxy mappings')
        (root / 'added.txt').write_text('new', encoding='utf-8')
        e.fileModel.request(str(root))
        waitFor(lambda: 'added.txt' in names())
        checks.append('external changes refresh retained folder contents')
        e._selectWhenReady(str(root / 'small.txt'))
        assert Path(e.selectedPath()) == root / 'small.txt'
        late = root / 'late.txt'
        e._selectWhenReady(str(late))
        e.files.setCurrentIndex(e.fileProxy.mapFromSource(e.fileModel.pathIndex(str(root / 'large.txt'))))
        late.write_text('late', encoding='utf-8')
        e.fileModel.request(str(root))
        waitFor(lambda: 'late.txt' in names())
        pause(150)
        assert Path(e.selectedPath()) == root / 'large.txt'
        checks.append('ready selection is immediate; delayed selection cannot steal newer user selection')
        if hasattr(e.files, '_visibleIcons'):
            gate = threading.Event()
            entered = threading.Event()
            callers = []
            original = qpeFileIcons._shellImages

            def slow(path, directory=False):
                """Shellの遅延を再現し、GUIが待たずに別フォルダーへ移れるか確かめる。"""
                callers.append(threading.get_ident())
                entered.set()
                gate.wait(5)
                return original(path, directory)

            pending_root = root / 'slow'
            pending_root.mkdir(exist_ok=True)
            for i in range(80):
                (pending_root / ('entry_%03d.txt' % i)).write_text('x', encoding='utf-8')
            with patch.object(qpeFileIcons, '_shellImages', slow):
                try:
                    go(pending_root)
                    waitFor(entered.is_set)
                    assert len(names()) == 80
                    assert threading.get_ident() not in callers
                    before = time.monotonic()
                    go(child)
                    assert time.monotonic() - before < 2
                    assert names() == ['other.txt']
                    checks.append('blocked Shell worker does not block listing or next navigation')
                finally:
                    gate.set()
                waitFor(lambda: all(job.ready for _, _, job in e.files._visibleIcons.pending))
                pause(100)
                assert names() == ['other.txt']
                checks.append('late icon completion does not replace current folder rows')
        e.grab().save(str(out / 'navigation.png'))
        result = dict(status='passed', checks=checks, qt=QtCore.qVersion())
    finally:
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
