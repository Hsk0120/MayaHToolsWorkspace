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
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "SimplePhysics" / "scripts"))
    from simpleCloth import api, ui

    cmds.file(new=True, force=True)
    cmds.currentUnit(time="film")
    cmds.currentTime(1)
    mesh = cmds.polyPlane(subdivisionsX=2, subdivisionsY=2)[0]
    node = api.create(mesh)
    api.setVertexWeights(node, [0, 1, 2], 0)
    cmds.setAttr(node + ".solverRate", 24)
    window = ui.show()
    for frame in cmds.lsUI(type="frameLayout", long=True) or []:
        if frame.startswith(window + "|"):
            cmds.frameLayout(frame, edit=True, collapse=False)
    cmds.currentTime(6.25)
    cmds.refresh()
    QtWidgets.QApplication.processEvents()
    widget = wrapInstance(int(omui.MQtUtil.findWindow(window)), QtWidgets.QWidget)
    visible = [label.text() for label in widget.findChildren(QtWidgets.QLabel) if label.isVisible()]
    labels = ('Peak Particle Speed (cm/s)', 'Pinned Vertices', 'Contact Particles')
    checks = {label: label in visible for label in labels}
    checks["positive_speed"] = cmds.getAttr(node + ".peakParticleSpeed") > 0
    checks["fixed_count"] = cmds.getAttr(node + ".pinnedVertexCount") == 3
    def click(label):
        # Setups and Undo may rebuild the panel. Resolve the current control at click time.
        control_name = next(item for item in cmds.lsUI(type="button", long=True) or []
                            if item.startswith(window + "|") and cmds.button(item, query=True, label=True) == label)
        control = wrapInstance(int(omui.MQtUtil.findControl(control_name)), QtWidgets.QPushButton)
        control.click()

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
    result = {"status": "passed" if all(checks.values()) else "failed", "checks": checks}
    (Path(output_dir) / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    finished(result)
