"""破棄済みQtラッパーを保持したままQPEを繰り返し再生成する回帰検証。"""
import json
import os
from pathlib import Path
import sys
import traceback


def main(output_dir, finished):
    """実workspaceControlを20回破棄し、他の入力欄と通常終了を検証する。"""
    # 専用Maya GUIからのみ読み込み、通常Pythonの検査を妨げない。
    from maya import cmds
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'tools'))
    sys.path.insert(0, str(root / 'maya/inhouse/QuickPathExplorer/python'))
    from qpeQt import QtCore, QtWidgets, shiboken
    from qpe_ui_maya import pause
    import qpeHost
    import qpeDock

    out = Path(output_dir)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    result = {'status': 'running', 'cycles': [], 'input_kind': 'Qt programmatic GUI'}
    retained = []
    errors = []
    original_hook = sys.excepthook

    def capture(*args):
        """遅延コールバックのPython例外も合否へ反映する。"""
        errors.append(''.join(traceback.format_exception(*args)))

    sys.excepthook = capture
    peer = QtWidgets.QLineEdit('Independent unsaved text')
    peer.show()
    try:
        for cycle in range(20):
            (out / 'stage.txt').write_text('cycle %d: creating' % cycle, encoding='utf-8')
            widget = qpeHost.show(str(out))
            widget.folderTabs.add()
            widget.setInspectorVisible(True)
            widget.setInspectorVisible(False)
            pause(180)
            owned = [widget, widget._dockViewport, qpeDock._watcher]
            owned.extend(widget.findChildren(QtCore.QObject))
            # 他スクリプトが削除済みUIのPython参照を保持する条件を再現する。
            retained.extend(owned)
            cmds.deleteUI(qpeHost.CONTROL)
            pause(180)
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            owned[2].stop()  # 削除済み監視を保持する利用側からの二重停止も安全。
            alive = [{'class': type(obj).__name__, 'name': obj.objectName()}
                     for obj in retained if shiboken.isValid(obj)]
            row = {'cycle': cycle, 'captured': len(owned), 'survivors': alive,
                   'active_threads': QtCore.QThreadPool.globalInstance().activeThreadCount()}
            result['cycles'].append(row)
            (out / 'inventory.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            assert not alive, row
            assert not errors, errors
            assert shiboken.isValid(peer) and peer.text() == 'Independent unsaved text'
        current = qpeHost.show(str(out))
        pause(500)
        current.grab().save(str(out / 'final-restored.png'))
        result['status'] = 'passed'
    except Exception:
        result['status'] = 'error'
        result['error'] = traceback.format_exc()
    finally:
        result['python_errors'] = errors
        sys.excepthook = original_hook
        peer.close()
        peer.deleteLater()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    finished(result)
