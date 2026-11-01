"""専用Mayaの1セッションでネイティブQPEの既存機能を回帰する。"""
import json
import os
from pathlib import Path
import runpy
import sys
import time
import traceback


def main(output_dir, finished):
    """利用者のMayaでは実行せず、runnerの専用prefsでのみ使用する。"""
    from maya import cmds
    from qpeQt import QtCore, QtWidgets, shiboken
    import qpeNative
    if not qpeNative.available():
        raise RuntimeError('This suite requires the embedded plugin')
    out = Path(output_dir).resolve()
    root = Path(__file__).resolve().parents[1]
    if not (root / '.maya-output') in out.parents:
        raise ValueError('Host regression output must be in .maya-output')
    sys.path.insert(0, str(root / 'tools'))
    results = {}
    suites = ['qpe_ui_image_workers', 'qpe_ui_advanced', 'qpe_ui_shortcuts', 'qpe_ui_accessibility',
              'qpe_ui_scene', 'qpe_read_options_test', 'qpe_fbx_test',
              'qpe_ui_dock_lifetime', 'qpe_native_benchmark']
    for name in suites:
        folder = out / name
        folder.mkdir(exist_ok=True)
        os.environ['QPE_SETTINGS_FILE'] = str(folder / 'settings.json')
        cmds.file(new=True, force=True)
        completed = []
        try:
            returned = runpy.run_path(str(root / 'tools' / (name + '.py')))['main'](folder, completed.append)
            deadline = time.monotonic() + 120
            while not completed:
                if time.monotonic() > deadline:
                    raise TimeoutError(name + ' callback timed out')
                loop = QtCore.QEventLoop()
                QtCore.QTimer.singleShot(25, loop.quit)
                (loop.exec if hasattr(loop, 'exec') else loop.exec_)()
            results[name] = completed[-1]
        except Exception:
            results[name] = dict(status='error', error=traceback.format_exc())
        finally:
            for widget in QtWidgets.QApplication.allWidgets():
                if shiboken.isValid(widget) and widget.objectName() == 'qpeExplorer':
                    widget.close()
                    widget.deleteLater()
                    QtCore.QCoreApplication.sendPostedEvents(widget, QtCore.QEvent.DeferredDelete)
        (out / 'progress.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        # 各スイートは専用シーン/設定とUI破棄で分離する。失敗を保持して残りも検査する。
    result = dict(status='passed' if len(results) == len(suites) and all(r.get('status') == 'passed' for r in results.values()) else 'error',
                  suites=results, maya=cmds.about(version=True), input='Qt programmatic / actual Maya scene operations')
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    finished(result)
    return result
