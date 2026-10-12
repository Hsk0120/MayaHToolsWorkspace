"""専用Mayaを複数回起動してQPEの配置と開閉状態を検証する。"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maya/inhouse/QuickPathExplorer/python'))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main(output_dir, finished):
    """隔離された設定を共有する4回のGUI起動で順に検証する。"""
    from maya import cmds
    import qpeHost
    import qpeDock
    from qpe_ui_maya import pause
    phase = int(os.environ['QPE_DOCK_PHASE'])
    checks = []
    if phase == 1:
        widget = qpeHost.show()
        pause(400)
        widget.window().setGeometry(210, 160, 1050, 720)
        pause(600)
        qpeDock.saveState()
        checks.append('floating geometry saved')
    elif phase == 2:
        expected = qpeDock.savedState()['geometry']
        qpeDock.startup()
        pause(1200)
        widget = qpeHost._window
        assert widget is not None
        actual = widget.window().geometry()
        assert all(abs(a - b) < 8 for a, b in zip(actual.getRect(), expected)), (expected, actual.getRect())
        checks.append('floating position and size restored after process restart')
        cmds.workspaceControl(qpeHost.CONTROL, edit=True, close=True)
        pause(400)
        assert not qpeDock.savedState()['open']
        assert qpeHost.show() is widget
        pause(300)
        checks.append('close and reopen retain the same control')
        cmds.workspaceControl(qpeHost.CONTROL, edit=True, dockToMainWindow=('right', False))
        pause(500)
        assert not cmds.workspaceControl(qpeHost.CONTROL, query=True, floating=True)
        qpeDock.saveState()
        checks.append('right dock saved')
    elif phase == 3:
        qpeDock.startup()
        pause(1200)
        widget = qpeHost._window
        assert widget is not None
        assert not cmds.workspaceControl(qpeHost.CONTROL, query=True, floating=True), qpeDock.savedState()
        checks.append('docked state restored after process restart')
        cmds.workspaceControl(qpeHost.CONTROL, edit=True, close=True)
        pause(400)
        assert not qpeDock.savedState()['open']
        checks.append('explicit close saved')
    else:
        qpeDock.startup()
        pause(1000)
        assert not qpeDock.savedState()['open']
        if cmds.workspaceControl(qpeHost.CONTROL, exists=True):
            assert not cmds.workspaceControl(qpeHost.CONTROL, query=True, visible=True)
        checks.append('closed QPE does not auto-open after restart')
        widget = qpeHost.show()
        pause(500)
        assert not cmds.workspaceControl(qpeHost.CONTROL, query=True, floating=True)
        checks.append('manual reopen restores docking after restart')
    widget.grab().save(str(Path(output_dir) / 'qpe.png'))
    result = {'status': 'passed', 'phase': phase, 'checks': checks, 'state': qpeDock.savedState()}
    (Path(output_dir) / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    finished(result)


if __name__ == '__main__':
    import argparse
    import datetime
    from run_mlib_gui_versions import run_version
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='2027', choices=['2022', '2023', '2024', '2025', '2026', '2027'])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    base = root / '.maya-output/verification' / ('qpe-dock-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    for phase in range(1, 5):
        environment = {
            'PYTHONPATH': str(root / 'maya/inhouse/QuickPathExplorer/python') + os.pathsep + str(root / 'maya/inhouse'),
            'QPE_SETTINGS_FILE': str(base / 'settings.json'), 'QPE_DOCK_PHASE': str(phase)}
        if phase > 1:
            environment['MAYA_APP_DIR'] = str(base / 'phase1/maya_app')
        result = run_version(args.version, base / ('phase' + str(phase)), Path('C:/Program Files/Autodesk'),
                             120, 30, suite_path=Path(__file__).resolve(), environment=environment)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result['status'] != 'passed':
            sys.exit(1)
