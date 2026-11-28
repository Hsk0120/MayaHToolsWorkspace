"""隔離したMaya GUIで案件比較・部品編集・サーフェス再分割の各入口を検査する。"""

import json
import sys
from pathlib import Path


def main(output_dir, finished):
    """7個のメニューを開き、適用・読戻し・Undo・比較結果を確かめる。"""
    import maya.cmds as cmds
    import maya.OpenMayaUI as omui
    from PySide6 import QtWidgets
    from shiboken6 import wrapInstance

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from HTools import userSetup
    from HTools.system import rigPackageInspection

    top = QtWidgets.QMenu()
    userSetup._inhouse_add_htools_menu_items(top)

    def launch(category, tool, window):
        menu, = [item.menu() for item in top.actions() if item.text() == category]
        action, = [item for item in menu.actions() if item.text().split("\t", 1)[0] == tool]
        action.trigger()
        assert cmds.window(window, query=True, visible=True)
        return window

    def click(window, label):
        widget = wrapInstance(int(omui.MQtUtil.findWindow(window)), QtWidgets.QWidget)
        button, = [item for item in widget.findChildren(QtWidgets.QPushButton) if item.text() == label]
        button.click()

    def controls(window, kind):
        return [item for item in cmds.lsUI(long=True, type=kind) if item.startswith(window + "|")]

    def set_field(window, label, value, kind="textFieldGrp"):
        control_fn = getattr(cmds, kind)
        ctl, = [c for c in controls(window, kind) if control_fn(c, query=True, label=True) == label]
        control_fn(ctl, edit=True, text=str(value))

    def report(window):
        ctl, = controls(window, "scrollField")
        return cmds.scrollField(ctl, query=True, text=True)

    owner = cmds.createNode("transform", name="localRig")
    cmds.addAttr(owner, longName="mlrigDefinition", dataType="string")
    cmds.setAttr(owner + ".mlrigDefinition", "original", type="string")
    cmds.select(owner)
    window = launch("system", "rigPackageInspection", "HToolsRigPackageInspection")
    set_field(window, "Display label", "Hero")
    set_field(window, "Display version", "v2")
    click(window, "Update selected rig display information")
    assert "Display label: Hero" in report(window)
    scene = output_dir / "asset.ma"
    cmds.file(rename=str(scene))
    cmds.file(save=True, type="mayaAscii")
    cmds.file(str(scene), open=True, force=True)
    assert rigPackageInspection.displayInfo(owner) == ("Hero", "v2")
    assert cmds.getAttr(owner + ".mlrigDefinition") == "original"

    source = cmds.polyCube(name="prop", constructionHistory=False)[0]
    visible = cmds.rename(cmds.listRelatives(source, shapes=True)[0], "wrongName")
    intermediate = cmds.createNode("mesh", parent=source, name="intermediate")
    cmds.setAttr(intermediate + ".intermediateObject", True)
    cmds.select(source)
    window = launch("rigging", "renamePreview", "HToolsRenamePreview")
    click(window, "Preview selected shapes by purpose")
    listing, = controls(window, "textScrollList")
    items = cmds.textScrollList(listing, query=True, allItems=True)
    row, = [r for r in items if "wrongName -> propShape " in r]
    cmds.textScrollList(listing, edit=True, selectItem=row)
    click(window, "Rename selected preview rows")
    assert cmds.objExists("propShape") and cmds.objExists(intermediate)
    cmds.undo()
    assert cmds.objExists(visible)

    cmds.select(source)
    window = launch("rigging", "rigFinish", "HToolsRigFinish")
    click(window, "Preview export duplicate cleanup")
    assert "Unused intermediate" in report(window) and "initialShadingGroup" in report(window)
    click(window, "Create cleaned export duplicate")
    assert cmds.getAttr("prop.visibility") and not cmds.getAttr("prop_export.visibility")
    assert cmds.objExists("|prop|intermediate") and not cmds.objExists("|prop_export|intermediate")
    assert cmds.listConnections("|prop_export|wrongName", type="shadingEngine") == cmds.listConnections("|prop|wrongName", type="shadingEngine")
    cmds.undo()
    assert not cmds.objExists("prop_export")

    for key, value in (("A", 2026), ("B", 2027)):
        (output_dir / (key + ".json")).write_text(json.dumps(dict(maya=value)), encoding="utf-8")
    window = launch("system", "compareProjectSettings", "HToolsCompareProjectSettings")
    for key in ("A", "B"):
        set_field(window, "Project " + key, output_dir / (key + ".json"), "textFieldButtonGrp")
    click(window, "Compare settings")
    assert "/maya   A: 2026   B: 2027" in report(window)

    window = launch("system", "diagnosticLaunchPreview", "HToolsDiagnosticLaunchPreview")
    set_field(window, "Diagnostic Python file", Path(__file__).resolve())
    for label in ("A", "B"):
        (output_dir / label).mkdir()
        set_field(window, "Project", output_dir / label)
        set_field(window, "History label", label)
        click(window, "Save current preview to history")
    listing, = controls(window, "textScrollList")
    assert cmds.textScrollList(listing, query=True, numberOfItems=True) == 2
    cmds.textScrollList(listing, edit=True, selectIndexedItem=[1, 2])
    click(window, "Compare two saved records")
    assert "A -> B" in report(window) and "project" in report(window)
    cmds.textScrollList(listing, edit=True, deselectAll=True)
    cmds.textScrollList(listing, edit=True, selectIndexedItem=1)
    click(window, "Restore selected history to preview")
    assert str(output_dir / "A") in report(window)

    surf = cmds.nurbsPlane(patchesU=2, patchesV=3)[0]
    cmds.select(surf)
    window = launch("rigging", "knotRangePreview", "HToolsKnotRangePreview")
    nodes = set(cmds.ls())
    click(window, "Compare uniform surface subdivision")
    summary = report(window)
    assert "spans: (4, 4)" in summary and "guideCm" in summary and set(cmds.ls()) == nodes
    from HTools.animation.footContact import inspectContact

    floor = cmds.polyPlane(width=12, height=12, axis=(0, 1, 0))[0]
    shape = cmds.listRelatives(floor, shapes=True, fullPath=True)[0]
    foot = cmds.createNode("transform", parent=floor, name="contactProbe")
    for frame, x, angle in ((1, 0, 0), (3, 5, 35)):
        cmds.setKeyframe(floor, attribute="translateX", time=frame, value=x)
        cmds.setKeyframe(floor, attribute="rotateZ", time=frame, value=angle)
    original_time = cmds.currentTime(query=True)
    rigid = inspectContact(foot, 1, 3, 1, 3, floorMesh=shape, rigidFloor=True)
    assert max(rigid[key] for key in ("slide", "clearance", "penetration")) < 1e-6
    for frame, x, y in ((1, 0, 0), (2, 1, -0.25), (3, 2, 0.5)):
        cmds.setKeyframe(foot, attribute="translateX", time=frame, value=x)
        cmds.setKeyframe(foot, attribute="translateY", time=frame, value=y)
    cmds.select(foot)
    window = launch("animation", "footContact", "HToolsFootContact")
    for control in controls(window, "floatFieldGrp"):
        if cmds.floatFieldGrp(control, query=True, label=True) in ("Contact frames", "Loop frames"):
            cmds.floatFieldGrp(control, edit=True, value1=1, value2=3)
    set_field(window, "Floor mesh shape (optional DAG path)", shape)
    moving, = controls(window, "checkBox")
    cmds.checkBox(moving, edit=True, value=True)
    click(window, "Inspect selected feet")
    measured = report(window)
    assert all(text in measured for text in ("slide=2.0000", "clearance=0.5000", "penetration=0.2500"))
    static = cmds.polyPlane(width=30, height=30)[0]
    static_shape = cmds.listRelatives(static, shapes=True, fullPath=True)[0]
    local_foot = cmds.createNode("transform")
    for frame, x, y in ((1, 0, 0), (2, 1, -0.25), (3, 2, 0.5)):
        cmds.setKeyframe(local_foot, attribute="translateX", time=frame, value=x)
        cmds.setKeyframe(local_foot, attribute="translateY", time=frame, value=y)
    static_result = inspectContact(local_foot, 1, 3, 1, 3, floorMesh=static_shape)
    assert all(abs(static_result[key] - value) < 1e-6 for key, value in
               (("slide", 2), ("clearance", 0.5), ("penetration", 0.25)))
    assert cmds.currentTime(query=True) == original_time
    result = dict(status="passed", tools=7, subdivision=summary, stationaryFoot=rigid, movingFoot=measured, staticFloor=static_result)
    (output_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    finished(result)
