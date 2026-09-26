"""実際の.modを使い、専用Maya GUIでPoseDriverConnect拡張を検証する。"""
import argparse
import datetime
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]


def main(output_dir=None, finished=None):
    """専用GUI内の検証。外部APIのパスをsys.pathへ手動追加しない。"""
    from maya import cmds
    from maya import OpenMayaUI
    try:
        from PySide6 import QtCore, QtWidgets
        from shiboken6 import wrapInstance
    except ImportError:
        from PySide2 import QtCore, QtWidgets
        from shiboken2 import wrapInstance
    output = Path(output_dir)
    result = {"status": "running", "checks": [], "skipped": [], "screenshots": []}
    created = []
    window = None

    def check(value, description):
        if not value:
            raise AssertionError(description)
        result["checks"].append(description)

    def finish():
        try:
            pointer = OpenMayaUI.MQtUtil.mainWindow()
            widget = wrapInstance(int(pointer), QtWidgets.QWidget)
            image = output / "extension_gui.png"
            if not widget.grab().save(str(image)):
                raise RuntimeError("Failed to save GUI screenshot")
            result["screenshots"].append(str(image))
            if window:
                panel = wrapInstance(int(OpenMayaUI.MQtUtil.findWindow(window)), QtWidgets.QWidget)
                panel.grab().save(str(output / "extension_report.png"))
        except Exception:
            result.update(status="error", screenshot_error=traceback.format_exc())
        finally:
            try:
                if window and cmds.window(window, exists=True):
                    cmds.deleteUI(window)
                for node in created:
                    if cmds.objExists(node):
                        cmds.delete(node)
                result["cleanup"] = "passed"
            except Exception:
                result.update(status="error", cleanup_error=traceback.format_exc())
            (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            finished(result)

    try:
        version = str(cmds.about(version=True)).split('.')[0]
        check(not cmds.about(batch=True), "Running in Maya GUI")
        modules = cmds.moduleInfo(listModules=True) or []
        result["modules"] = modules
        check('hlib_posedriverconnect' in modules, "Actual hlib_posedriverconnect.mod detected")
        module_path = cmds.moduleInfo(moduleName='hlib_posedriverconnect', path=True)
        result["extension_module_path"] = module_path
        check(Path(module_path).resolve() == (ROOT / 'maya/inhouse/hlib_posedriverconnect').resolve(),
              "Extension module resolves to workspace package")
        before = set(cmds.pluginInfo(query=True, listPlugins=True) or [])
        import hlib
        state = hlib.extensions.status().get('hlib_posedriverconnect')
        result["extension_state"] = state
        check(state is not None, "Extension found without explicit extension import")
        check(before == set(cmds.pluginInfo(query=True, listPlugins=True) or []),
              "Import does not load Maya plugins")
        native_binary = ROOT / 'maya/external/PoseDriverConnect/plug-ins/windows' / version / 'MayaUERBFPlugin.mll'
        if native_binary.exists():
            check(state['state'] == 'loaded', 'PoseDriverConnect Python API registered')
            check('PoseDriverConnect' in modules, 'Actual pose_driver_connect.mod detected')
            # MetaHumanにも同名バイナリがあるため、.modのルートから対象を明示する。
            plugin_root = Path(cmds.moduleInfo(moduleName='PoseDriverConnect', path=True))
            native_binary = plugin_root / 'plug-ins/windows' / version / 'MayaUERBFPlugin.mll'
            cmds.loadPlugin(str(native_binary), quiet=True)
            loaded_path = cmds.pluginInfo('MayaUERBFPlugin', query=True, path=True)
            check(Path(loaded_path).resolve() == native_binary.resolve(), 'Expected PoseDriverConnect binary loaded')
            solver = hlib.createNode('UERBFSolverNode', name='hlibExtensionGuiSolver')
            created.append(solver.full_name())
            blender = hlib.createNode('UEPoseBlenderNode', name='hlibExtensionGuiBlender')
            created.append(blender.full_name())
            check(type(solver).__module__.startswith('hlib_posedriverconnect.'), 'Solver uses extension wrapper')
            check(type(blender).__module__.startswith('hlib_posedriverconnect.'), 'Blender uses extension wrapper')
            cmds.select(solver.full_name())
            check(type(hlib.ls(selection=True)[0]) is type(solver), 'hlib.ls(selection=True) dispatches extension')
            before_radius = solver.radius()
            solver.set_radius(before_radius + 10)
            check(abs(solver.radius() - before_radius - 10) < 1e-6, 'Radius edit applied')
            cmds.undo()
            check(abs(solver.radius() - before_radius) < 1e-6, 'Undo restores radius')
            cmds.redo()
            check(abs(solver.radius() - before_radius - 10) < 1e-6, 'Redo restores edit')
            result['radius'] = {'before': before_radius, 'after_redo': solver.radius()}
            name = solver.full_name()
            hlib.reload()
            solver = hlib.node(name)
            check(isinstance(solver, hlib.nodes.Node) and hasattr(solver, 'radius'), 'Reload restores extension registration')
            result['plugin'] = cmds.pluginInfo('MayaUERBFPlugin', query=True, path=True)
        else:
            result['skipped'].append('Matching external plugin binary is not installed; node tests skipped')
            node = hlib.createNode('transform', name='hlibExtensionFallback')
            created.append(node.full_name())
            check(node.is_valid(), 'Core hlib remains usable')
        result['status'] = 'passed'
    except Exception:
        result.update(status='failed', error=traceback.format_exc())
    lines = ['Maya ' + str(cmds.about(version=True)), 'Extension GUI/.mod test: ' + result['status'].upper()]
    lines += ['PASS: ' + text for text in result['checks']]
    lines += ['SKIP: ' + text for text in result['skipped']]
    lines += [json.dumps(result.get('extension_state')), result.get('error', '')]
    window = cmds.window(title='hlib PoseDriverConnect verification', widthHeight=(750, 470))
    cmds.columnLayout(adjustableColumn=True)
    cmds.scrollField(editable=False, wordWrap=True, text='\n'.join(lines), height=440)
    cmds.showWindow(window)
    QtCore.QTimer.singleShot(1500, finish)


def launch():
    from run_hlib_gui_versions import run_version
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--versions', nargs='+', default=['2022', '2024', '2025', '2026', '2027'])
    parser.add_argument('--timeout', type=int, default=150)
    args = parser.parse_args()
    output = ROOT / '.maya-output/extension-gui' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    output.mkdir(parents=True)
    print('Results: ' + str(output), flush=True)
    results = []
    for version in args.versions:
        print('Maya ' + version + ': starting', flush=True)
        result = run_version(version, output / version, Path(os.environ['ProgramFiles']) / 'Autodesk',
                             args.timeout, suite_path=Path(__file__).resolve(),
                             environment={'MAYA_MODULE_PATH': str(ROOT / 'maya/modules')})
        results.append(result)
        (output / 'summary.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print('Maya ' + version + ': ' + result['status'], flush=True)
    return int(any(result['status'] != 'passed' for result in results))


if __name__ == '__main__':
    sys.exit(launch())
