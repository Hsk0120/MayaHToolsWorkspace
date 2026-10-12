"""アイコンのLRUと大量行通知の集約を実際のQtビューで検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback
from unittest.mock import patch
from qpe_ui_maya import pause, waitFor
from qpeQt import QtCore, QtGui, QtWidgets


def main(output_dir, finished=None):
    """専用データでキャッシュ失効・共有・表示内容を検証する。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    import qpeFileIcons
    from quickPathExplorer import Explorer, FolderColumns
    checks, counts = [], dict(summary=0, hints=0)
    e = None
    try:
        fixture = out / 'files'
        fixture.mkdir(exist_ok=True)
        folders = out / 'folders'
        for number in range(200):
            (folders / ('folder_%03d' % number)).mkdir(parents=True, exist_ok=True)
        image = QtGui.QImage(32, 32, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor('#4488aa'))
        paths = [fixture / ('image_%04d.png' % i) for i in range(1000)]
        for path in paths:
            image.save(str(path))
        icon = QtGui.QIcon(QtGui.QPixmap.fromImage(image))
        with patch.object(qpeFileIcons, 'windowsIcon', return_value=icon) as native:
            cache = qpeFileIcons.FileIcons()
            cache.capacity = 3
            for path in paths[:3]:
                cache.icon(str(path))
            cache.icon(str(paths[0]))
            cache.icon(str(paths[3]))
            cache.icon(str(paths[0]))
            assert native.call_count == 4
            cache.icon(str(paths[1]))
            assert native.call_count == 5 and len(cache._cache) == 3
            with paths[1].open('ab') as stream:
                stream.write(b'changed')
            cache.icon(str(paths[1]))
            assert native.call_count == 6
            checks.append('per-file keys, least recently used eviction, size-change invalidation')
        image.save(str(paths[1]))
        summary, hints = Explorer._updateFileSummary, FolderColumns.refreshHints

        def update_summary(widget, *args):
            """大量通知による件数再計算を数える。"""
            counts['summary'] += 1
            return summary(widget, *args)

        def update_hints(widget, *args):
            """カラム表示の全走査を数える。"""
            counts['hints'] += 1
            return hints(widget, *args)

        with patch.object(Explorer, '_updateFileSummary', update_summary), patch.object(FolderColumns, 'refreshHints', update_hints):
            e = Explorer(maya=bool(finished))
            e.resize(1280, 900)
            e.show()
            e.setBrowseRoot(str(out))
            pause(300)
            counts.update(summary=0, hints=0)
            e.navigate(str(folders))
            waitFor(lambda: e.folderModel.rowCount(e.folderModel.index(str(folders))) == 200)
            pause(100)
            assert counts['hints'] < 100, counts
            checks.append('200 folder insertions coalesce column decoration without hiding children')
            e.navigate(str(fixture))
            waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1000)
            pause(300)
            assert counts['summary'] < 100 and counts['hints'] < 100, counts
            assert '1000' in e.folderLabel.text().replace(',', '')
            assert e.fileModel._icons is e._placeIcons
            checks.append('1000 rows preserve final count with fewer than 100 summary/hint updates')
            workspace = e.organizer.workspace
            with patch.object(qpeFileIcons, 'windowsIcon', wraps=qpeFileIcons.windowsIcon) as native:
                workspace.mode.setCurrentIndex(1)
                waitFor(lambda: workspace.grid.count() == 1000 and not workspace.restoring)
                assert native.call_count == 0, native.call_count
            checks.append('thumbnail mode reuses all 1000 native file icons without new Shell queries')
            e.grab().save(str(out / 'overview.png'))
        result = dict(status='passed', checks=checks, updates=counts)
    except Exception:
        result = dict(status='error', checks=checks, updates=counts, error=traceback.format_exc())
    finally:
        if e is not None:
            e.close()
            e.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(e, QtCore.QEvent.DeferredDelete)
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(sys.argv[1])
    QtCore.QThreadPool.globalInstance().waitForDone(10000)
    sys.exit(0 if result['status'] == 'passed' else 1)
