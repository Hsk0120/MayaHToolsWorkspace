"""使い捨てのMaya GUIで診断欄を展開し、値とラベルを確認する。"""

import json
from pathlib import Path
import sys
from unittest.mock import patch


def main(output_dir, finished):
    """検証シーンにソルバーを作り、診断欄の表示結果を保存する。"""
    import maya.cmds as cmds
    import maya.OpenMayaUI as omui
    from PySide6 import QtWidgets
    from shiboken6 import wrapInstance

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from simplePhysics import api, ui

    cmds.file(new=True, force=True)
    cmds.currentUnit(time="film")
    cmds.currentTime(1)
    root = cmds.joint(position=(0, 10, 0))
    cmds.joint(position=(5, 10, 0))
    node = api.create([root])
    cmds.setAttr(node + ".warmupSteps", 0)
    cmds.setAttr(node + ".targetFramerate", 24)
    window = ui.show().window
    for frame in cmds.lsUI(type="frameLayout", long=True) or []:
        if frame.startswith(window + "|"):
            cmds.frameLayout(frame, edit=True, collapse=False)
    cmds.currentTime(6.25)
    cmds.refresh()
    QtWidgets.QApplication.processEvents()
    widget = wrapInstance(int(omui.MQtUtil.findWindow(window)), QtWidgets.QWidget)
    visible = [label.text() for label in widget.findChildren(QtWidgets.QLabel) if label.isVisible()]
    labels = ('Maximum Particle Speed (cm/s)', 'Fixed Roots', 'Contact Particles')
    checks = {label: label in visible for label in labels}
    checks["positive_speed"] = cmds.getAttr(node + ".maxParticleSpeed") > 0
    checks["fixed_count"] = cmds.getAttr(node + ".fixedRootCount") == 1
    # コールバックをMayaの実ボタンから呼び、現在選択の根元が編集対象になることを確かめる。
    def click(label):
        # Setups and Undo may rebuild the panel. Resolve the current control at click time.
        control_name = next(item for item in cmds.lsUI(type="button", long=True) or []
                            if item.startswith(window + "|") and cmds.button(item, query=True, label=True) == label)
        control = wrapInstance(int(omui.MQtUtil.findControl(control_name)), QtWidgets.QPushButton)
        control.click()
    cmds.select(clear=True)
    other = cmds.joint(position=(0, 10, 2))
    cmds.joint(position=(5, 10, 2))
    cmds.select(other)
    click("Add Selected Roots")
    checks["added_root"] = cmds.getAttr(node + ".fixedRootCount") == 2
    cmds.select(other)
    click("Exclude Selected Roots")
    checks["excluded_root"] = cmds.getAttr(node + ".fixedRootCount") == 1
    click("Restore Selected Roots")
    checks["restored_root"] = cmds.getAttr(node + ".fixedRootCount") == 2
    with patch.object(cmds, "confirmDialog") as dialog:
        click("Compare Input Strands")
        checks["strand_report"] = "Minimum segment distance: 2 cm" in dialog.call_args.kwargs["message"]
    cmds.currentTime(12)
    path = Path(output_dir) / "simulation-state.json"
    with patch.object(cmds, "fileDialog2", return_value=[str(path)]), patch.object(cmds, "confirmDialog") as dialog:
        click("Save Simulation State")
        saved = json.loads(path.read_text(encoding="utf-8"))
        checks["saved_solver"] = saved["solver"] == cmds.ls(node, uuid=True)[0] and saved["frame"] == 12
        click("Compare Saved State")
        checks["comparison"] = (dialog.called and dialog.call_args.kwargs.get("message") ==
                                "Maximum position difference: 0 cm\nMaximum velocity difference: 0 cm/s")
        cmds.currentTime(1)
        click("Resume Simulation State")
        checks["resumed"] = json.loads(cmds.getAttr(node + ".resumeState") or "null") == saved
        cmds.undo()
        checks["resume_undo"] = not cmds.getAttr(node + ".resumeState")
    curve = cmds.curve(degree=1, point=[(0, 0, 0), (2, 0, 0), (2, 3, 0)])
    cmds.select(curve)
    click("Capsules from Polyline (1 cm)")
    guides = cmds.ls(selection=True, long=True)
    checks["curve_capsules_selected"] = len(guides) == 2
    cmds.undo()
    checks["curve_capsules_undo"] = cmds.ls(selection=True) == [curve] and not any(cmds.objExists(guide) for guide in guides)
    cmds.redo()
    checks["curve_capsules_redo"] = cmds.ls(selection=True, long=True) == guides
    cmds.select(clear=True)
    field = cmds.radial(position=(0, 4, 0), magnitude=10, attenuation=1)[0]
    cmds.select(field)
    click("Attach Selected Static Maya Field")
    checks["field_attached"] = bool(cmds.listConnections(node + ".fieldForces", source=True, destination=False))
    click("Detach Selected Maya Field")
    checks["field_detached"] = not cmds.listConnections(node + ".fieldForces", source=True, destination=False)
    cmds.select(api.connections(node, "outputBones")[1])
    click("選択出力にヒンジを設定")
    checks["hinge_attached"] = "1" in json.loads(cmds.getAttr(node + ".hingeLimits"))
    click("選択出力のヒンジを解除")
    checks["hinge_removed"] = not json.loads(cmds.getAttr(node + ".hingeLimits"))
    click("選択粒子の速度を線で表示 (cm/s)")
    checks["indicator"] = bool(cmds.listConnections(node + ".velocityEndpoint", source=False, destination=True))
    click("現在の姿勢を開始状態に設定（初速0）")
    checks["settled"] = bool(cmds.getAttr(node + ".settledOffsets"))
    click("元の開始姿勢に戻す")
    checks["reset_settled"] = not cmds.getAttr(node + ".settledOffsets")
    result = {"status": "passed" if all(checks.values()) else "failed", "checks": checks}
    (Path(output_dir) / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    finished(result)
