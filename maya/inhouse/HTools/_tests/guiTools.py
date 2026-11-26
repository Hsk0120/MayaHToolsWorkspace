"""専用のMaya GUIでHToolsのメニュー入口と操作結果を照合する。"""

import json
import sys
from pathlib import Path

import maya.cmds as cmds
import maya.OpenMayaUI as omui
from PySide6 import QtWidgets
from shiboken6 import wrapInstance


def main(output_dir, finished):
    """実行専用の空シーンにメッシュを作り、各ボタンの結果を検査する。"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from HTools.material import shaderAssignments
    from HTools.rigging import deformerOrder

    from HTools import userSetup
    menu_root = QtWidgets.QMenu()
    userSetup._inhouse_add_htools_menu_items(menu_root)

    def launch(module, window):
        menu = menu_root
        parts = module.split(".")
        for section in parts[:-1]:
            action, = [item for item in menu.actions() if item.text()==section]
            menu = action.menu()
        action, = [item for item in menu.actions() if item.text().split("\t", 1)[0] == parts[-1]]
        action.trigger()
        assert cmds.window(window, query=True, visible=True)
        return wrapInstance(int(omui.MQtUtil.findWindow(window)), QtWidgets.QWidget)

    def click(window, label):
        button, = [b for b in window.findChildren(QtWidgets.QPushButton) if b.text() == label]
        assert button.isEnabled()
        button.click()

    transform, _ = cmds.polyCube()
    shape, = cmds.listRelatives(transform, shapes=True, fullPath=True)
    cmds.cluster(shape + ".vtx[0:3]")
    cmds.cluster(shape + ".vtx[3:7]")
    cmds.select(transform)
    window = launch("rigging.deformerOrder", "HToolsDeformerOrder")
    stack = deformerOrder.history(shape)
    listing, = [item for item in cmds.lsUI(type="textScrollList", long=True) if item.startswith("HToolsDeformerOrder|")]
    cmds.textScrollList(listing, edit=True, selectItem=stack)
    click(window, "Swap selected pair")
    assert deformerOrder.history(shape) == stack[::-1]
    cmds.undo()
    assert deformerOrder.history(shape) == stack

    extra = cmds.createNode("mesh", parent=transform, name="secondOrig")
    cmds.connectAttr(shape + ".outMesh", extra + ".inMesh")
    cmds.setAttr(extra + ".intermediateObject", True)
    cmds.select(transform)
    window = launch("rigging.copyOriginalMesh", "HToolsCopyOriginalMesh")
    listing, = [item for item in cmds.lsUI(type="textScrollList", long=True) if item.startswith("HToolsCopyOriginalMesh|")]
    candidates = cmds.textScrollList(listing, query=True, allItems=True)
    chosen, = [path for path in candidates if path.endswith("|secondOrig")]
    assert len(candidates) >= 2
    cmds.textScrollList(listing, edit=True, selectItem=chosen)
    click(window, "Copy selected shape")
    assert cmds.objExists("originalComparison1")
    cmds.undo()
    assert not cmds.objExists("originalComparison1")

    cmds.select(transform)
    window = launch("material.shaderAssignments", "HToolsShaderAssignments")
    saved = shaderAssignments.capture(shape)
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    cmds.sets(shape + ".f[2]", edit=True, forceElement=group)
    click(window, "Compare with captured assignments")
    report, = [item for item in cmds.lsUI(type="scrollField", long=True) if item.startswith("HToolsShaderAssignments|")]
    assert "f[2]" in cmds.scrollField(report, query=True, text=True)
    click(window, "Restore captured assignments")
    assert not shaderAssignments.differences(saved)

    cmds.select(transform)
    window = launch("animation.footContact", "HToolsFootContact")
    click(window, "Inspect selected feet")
    report, = [item for item in cmds.lsUI(type="scrollField", long=True) if item.startswith("HToolsFootContact|")]
    assert "slide=0.0000" in cmds.scrollField(report, query=True, text=True)
    window = launch("system.pluginDependencies", "HToolsPluginDependencies")
    click(window, "Refresh")
    from HTools.system import scriptNodeReloadAudit

    scene = str(output_dir / "audit.ma")
    cmds.file(rename=scene)
    user_script = cmds.scriptNode(name="artistSettings", scriptType=0)
    cmds.file(save=True, type="mayaAscii")
    cmds.file(scene, open=True, force=True, executeScriptNodes=False)
    config = {"uiConfigurationScriptNode", "sceneConfigurationScriptNode"}
    assert config <= set(scriptNodeReloadAudit.capture())
    cmds.delete(sorted(config))
    before = scriptNodeReloadAudit.capture()
    window = launch("system.scriptNodeReloadAudit", "HToolsScriptNodeAudit")
    cmds.file(save=True, type="mayaAscii")
    cmds.file(scene, open=True, force=True, executeScriptNodes=False)
    after = scriptNodeReloadAudit.capture()
    click(window, "Compare with captured state")
    rows = scriptNodeReloadAudit.compare(before, after)
    assert set(rows) == {(name, "Added", "Maya configuration name") for name in config}, rows
    assert before[user_script] == after[user_script]
    assert not cmds.file(query=True, modified=True)

    cmds.file(new=True, force=True)
    cmds.file(scene, reference=True, namespace="asset", executeScriptNodes=False)
    mesh, = cmds.ls("asset:pCubeShape1", long=True)
    cmds.select(mesh)
    window = launch("material.shaderAssignments", "HToolsShaderAssignments")
    saved = shaderAssignments.capture(mesh)
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    cmds.sets(mesh + ".f[1]", edit=True, forceElement=group)
    click(window, "Restore captured assignments")
    assert not shaderAssignments.differences(saved)
    cmds.undo()
    assert shaderAssignments.differences(saved) == [(1, saved["shaders"][1], group)]
    cmds.file(new=True, force=True)
    cube, _ = cmds.polyCube()
    shape, = cmds.listRelatives(cube, shapes=True, fullPath=True)
    cmds.sets(shape, edit=True, remove="initialShadingGroup")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    cmds.sets(shape + ".f[2]", edit=True, forceElement=group)
    saved = shaderAssignments.capture(shape)
    assert saved["shaders"].count(None) == 5
    cmds.sets(shape, edit=True, forceElement=group)
    assert shaderAssignments.restore(saved) == 5
    cmds.undo()
    assert shaderAssignments.capture(shape)["shaders"] == (group,) * 6
    cmds.redo()
    cmds.sets(shape + ".f[3]", edit=True, forceElement=group)
    assert shaderAssignments.restore(saved) == 1

    unknown_file = output_dir / "missingPlugin.ma"
    unknown_file.write_text(
        '//Maya ASCII 2027 scene\nrequires maya "2027";\n'
        'requires -nodeType "auditMissingType" "auditMissingPlugin" "1.0";\n'
        'createNode auditMissingType -n "artistNode";\n', encoding="ascii")
    cmds.file(new=True, force=True)
    cmds.file(str(unknown_file), reference=True, namespace="missing", executeScriptNodes=False)
    cmds.select("missing:artistNode", noExpand=True)
    cmds.file(rename=str(output_dir / "withReference.ma"))
    cmds.file(save=True, type="mayaAscii")
    window = launch("system.pluginDependencies", "HToolsPluginDependencies")
    click(window, "Refresh")
    report, = [item for item in cmds.lsUI(type="scrollField", long=True) if item.startswith("HToolsPluginDependencies|")]
    text = cmds.scrollField(report, query=True, text=True)
    assert all(word in text for word in ("auditMissingPlugin", "auditMissingType", "Reference:", "requires maya")), text
    assert not cmds.file(query=True, modified=True)
    cmds.file(new=True, force=True)
    joint = cmds.joint(name="testJoint")
    cmds.setAttr(joint + ".rotateOrder", 5)
    cmds.setAttr(joint + ".jointOrient", 10, 20, 30)
    cmds.setAttr(joint + ".rotateAxis", 3, 4, 5)
    driver = cmds.createNode("animCurveTA")
    cmds.connectAttr(driver + ".output", joint + ".rotateX")
    cmds.select(joint)
    matrix = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
    window = launch("rigging.inspectRotation", "HToolsRotationInspection")
    click(window, "Inspect selected transforms")
    report, = [item for item in cmds.lsUI(type="scrollField", long=True) if item.startswith("HToolsRotationInspection|")]
    text = cmds.scrollField(report, query=True, text=True)
    assert all(word in text for word in ("zyx", "jointOrient", "rotateAxis", driver + ".output")), text
    assert cmds.xform(joint, query=True, worldSpace=True, matrix=True) == matrix
    cmds.file(new=True, force=True)
    plane, _ = cmds.polyPlane(width=4, height=4, subdivisionsX=8, subdivisionsY=8)
    cluster, handle = cmds.cluster(plane + ".vtx[*]")
    cmds.setAttr(handle + ".ty", 1)
    before = cmds.xform(plane + ".vtx[*]", query=True, worldSpace=True, translation=True)
    cmds.select(cluster, noExpand=True)
    window = launch("rigging.clusterSphereMask", "HToolsClusterSphereMask")
    click(window, "Preview current weights")
    assert cmds.xform(plane + ".vtx[*]", query=True, worldSpace=True, translation=True) == before
    click(window, "Multiply current weights by mask")
    after = cmds.xform(plane + ".vtx[*]", query=True, worldSpace=True, translation=True)
    for x, y, z in zip(after[::3], after[1::3], after[2::3]):
        distance = (x*x + z*z)**0.5
        t = max(0, 1-distance)
        assert abs(y - t*t*(3-2*t)) < 1e-6, (x, y, z)
    cmds.undo()
    assert cmds.xform(plane + ".vtx[*]", query=True, worldSpace=True, translation=True) == before
    from HTools.rigging import knotRangePreview

    for transform in (cmds.curve(degree=2, point=[(0,0,0), (1,2,1), (2,1,0), (3,0,1)]),
                      cmds.nurbsPlane(patchesU=4, patchesV=1)[0]):
        shape, = cmds.listRelatives(transform, shapes=True, fullPath=True)
        is_curve = cmds.nodeType(shape) == "nurbsCurve"
        consumer = cmds.createNode("pointOnCurveInfo" if is_curve else "pointOnSurfaceInfo")
        target = consumer + (".inputCurve" if is_curve else ".inputSurface")
        cmds.connectAttr(shape + ".worldSpace[0]", target)
        attr = ".minMaxValue" if is_curve else ".minMaxRangeU"
        domain = cmds.getAttr(shape + attr)
        ranges, error, sinks = knotRangePreview.preview(shape, (0,12), (2,7))
        assert error < 1e-8 and target in sinks, (ranges, error, sinks)
        cmds.select(transform)
        window = launch("rigging.knotRangePreview", "HToolsKnotRangePreview")
        click(window, "Preview on geometry copy")
        assert cmds.getAttr(shape + attr) == domain
    guide = cmds.polyPlane(width=10, height=10)[0]
    plane = cmds.polyPlane(subdivisionsX=2, subdivisionsY=2)[0]
    cmds.move(0, 0.5, 0, plane + ".vtx[4]", relative=True)
    points = cmds.xform(plane + ".vtx[*]", query=True, worldSpace=True, translation=True)
    uv = cmds.polyEditUV(plane + ".map[*]", query=True)
    faces = cmds.polyEvaluate(plane, face=True)
    cmds.select(guide)
    window = launch("rigging.relaxOnGuide", "HToolsRelaxOnGuide")
    click(window, "Use selected guide mesh")
    cmds.select(plane + ".vtx[*]")
    click(window, "Relax selected vertices once")
    expected = points[:]
    expected[13] = 0
    assert cmds.xform(plane + ".vtx[*]", query=True, worldSpace=True, translation=True) == expected
    assert cmds.polyEditUV(plane + ".map[*]", query=True) == uv and cmds.polyEvaluate(plane, face=True) == faces
    cmds.undo()
    assert cmds.xform(plane + ".vtx[*]", query=True, worldSpace=True, translation=True) == points
    cmds.file(new=True, force=True)
    for side in (1, -1):
        cmds.select(clear=True)
        parent = cmds.joint(position=(0,0,0))
        child = cmds.joint(position=(side * 2,1,0))
        skin_geo = cmds.polyCube()[0]
        skin = cmds.skinCluster(parent, child, skin_geo)[0]
        matrix = cmds.xform(child, query=True, worldSpace=True, matrix=True)
        positions = cmds.xform(skin_geo + ".vtx[*]", query=True, worldSpace=True, translation=True)
        cmds.select(parent)
        window = launch("rigging.advancedOrientJointUI", "OrientJointLikeWin")
        click(window, "Preview orientations and affected joints")
        text = cmds.scrollField("oj_preview_report", query=True, text=True)
        assert child in text and skin in text and "Proposed jointOrient" in text, text
        assert cmds.xform(child, query=True, worldSpace=True, matrix=True) == matrix
        assert cmds.xform(skin_geo + ".vtx[*]", query=True, worldSpace=True, translation=True) == positions
        window = launch("byMlib.rigging.advancedOrientJointUI", "OrientJointLikeWin")
        click(window, "Preview orientations and affected joints")
        assert cmds.scrollField("oj_preview_report", query=True, text=True) == text
        click(window, "Apply")
        assert max(abs(a-b) for a,b in zip(matrix, cmds.xform(child, query=True, worldSpace=True, matrix=True))) < 1e-6
        assert max(abs(a-b) for a,b in zip(positions, cmds.xform(skin_geo + ".vtx[*]", query=True, worldSpace=True, translation=True))) < 1e-6
        assert abs(cmds.getAttr(parent + ".jointOrientZ") - (26.565051 if side == 1 else 153.434949)) < 1e-5
        (output_dir / f"orient-preview-{side}.txt").write_text(text, encoding="utf-8")
    from HTools.rigging import replaceDeformerInput
    cmds.file(new=True, force=True)
    cube = cmds.polyCube()[0]
    replacement = cmds.duplicate(cube)[0]
    replacement_shape, = cmds.listRelatives(replacement, shapes=True, fullPath=True)
    cluster, handle = cmds.cluster(cube + ".vtx[*]")
    cmds.setAttr(handle + ".ty", 2)
    cmds.move(1, 0, 0, replacement + ".vtx[0]", relative=True)
    before = cmds.pointPosition(cube + ".vtx[0]", world=True)
    old, new, target = replaceDeformerInput.inspect(replacement_shape, cluster)
    window = launch("rigging.replaceDeformerInput", "HToolsReplaceDeformerInput")
    fields = [item for item in cmds.lsUI(type="textFieldGrp", long=True) if item.startswith("HToolsReplaceDeformerInput|")]
    for field in fields:
        label = cmds.textFieldGrp(field, query=True, label=True)
        cmds.textFieldGrp(field, edit=True, text=cluster if label == "Deformer" else replacement_shape)
    click(window, "Preview input connection")
    assert cmds.connectionInfo(target, sourceFromDestination=True) == old
    click(window, "Replace input connection")
    after = cmds.pointPosition(cube + ".vtx[0]", world=True)
    assert abs(after[0]-before[0]-1) < 1e-6 and after[1:] == before[1:], (before, after, old, new, target, fields, cmds.connectionInfo(target, sourceFromDestination=True))
    cmds.undo()
    assert cmds.connectionInfo(target, sourceFromDestination=True) == old
    cmds.polyEditUV(replacement + ".map[0]", uValue=0.25)
    try:
        replaceDeformerInput.inspect(replacement_shape, cluster)
    except ValueError as error:
        assert "UV" in str(error)
    else:
        raise AssertionError("UV mismatch accepted")
    cmds.file(new=True, force=True)
    root = cmds.joint(position=(0,0,0))
    tip = cmds.joint(position=(2,0,0))
    base = cmds.polyCube()[0]
    source = cmds.duplicate(base)[0]
    source_shape, = cmds.listRelatives(source, shapes=True, fullPath=True)
    skin = cmds.skinCluster(root, tip, base)[0]
    cmds.skinPercent(skin, base + ".vtx[0]", transformValue=[(root, 0.25), (tip, 0.75)])
    weights = [cmds.skinPercent(skin, f"{base}.vtx[{i}]", query=True, value=True) for i in range(8)]
    cmds.setAttr(tip + ".ty", 2)
    before = cmds.pointPosition(base + ".vtx[0]", world=True)
    cmds.move(0, 0, 0.5, source + ".vtx[0]", relative=True)
    old, new, target = replaceDeformerInput.inspect(source_shape, skin)
    cmds.connectAttr(new, target, force=True)
    after = cmds.pointPosition(base + ".vtx[0]", world=True)
    assert after[:2] == before[:2] and abs(after[2]-before[2]-0.5) < 1e-6
    assert [cmds.skinPercent(skin, f"{base}.vtx[{i}]", query=True, value=True) for i in range(8)] == weights
    cmds.undo()
    assert cmds.connectionInfo(target, sourceFromDestination=True) == old
    from HTools.animation import footContact
    cmds.file(new=True, force=True)
    steps = [cmds.polyPlane(width=2, height=2)[0] for _ in range(2)]
    cmds.setAttr(steps[1] + ".translate", 2, 1, 0)
    ground = cmds.polyUnite(*steps, constructionHistory=False)[0]
    ground_shape, = cmds.listRelatives(ground, shapes=True, fullPath=True)
    foot = cmds.createNode("transform")
    for frame, x, y in ((1,0,0), (2,2,1), (3,2,1.25), (4,2,0.75)):
        cmds.setKeyframe(foot, attribute="tx", time=frame, value=x)
        cmds.setKeyframe(foot, attribute="ty", time=frame, value=y)
    time = cmds.currentTime(query=True)
    contact = footContact.inspectContact(foot, 1, 4, 1, 4, floorMesh=ground_shape)
    assert abs(contact["slide"]-2)<1e-5 and abs(contact["clearance"]-0.25)<1e-5 and abs(contact["penetration"]-0.25)<1e-5, contact
    assert cmds.currentTime(query=True) == time
    from HTools.rigging import renamePreview
    cmds.file(new=True, force=True)
    root = cmds.createNode("transform", name="rig")
    control = cmds.parent(cmds.polyCube(name="left_ctl")[0], root)[0]
    cmds.createNode("transform", name="right_ctl", parent=root)
    cmds.addAttr(root, longName="mlrigPublishedChannels", dataType="string")
    cmds.setAttr(root+".mlrigPublishedChannels", '{"ports":{"arm":{"path":"left_ctl"}}}', type="string")
    cmds.file(rename=str(output_dir / "rig.ma"))
    cmds.file(save=True, type="mayaAscii")
    cmds.file(new=True, force=True)
    cmds.file(str(output_dir / "rig.ma"), reference=True, namespace="actor")
    node, = cmds.ls("actor:left_ctl", long=True)
    rows = renamePreview.preview([node], "left", "right")
    assert len(rows) == 2 and all("Referenced" in row for row in rows)
    assert all(word in rows[0] for word in ("actor:right_ctl", "Name collision", "mlrigPublishedChannels")), rows
    assert cmds.objExists(node)
    cmds.select(node)
    window = launch("rigging.renamePreview", "HToolsRenamePreview")
    for item in cmds.lsUI(type="textFieldGrp", long=True):
        if item.startswith("HToolsRenamePreview|"):
            label = cmds.textFieldGrp(item, query=True, label=True)
            cmds.textFieldGrp(item, edit=True, text="left" if label.startswith("Find") else "right")
    click(window, "Preview names and dependencies")
    report, = [item for item in cmds.lsUI(type="scrollField", long=True) if item.startswith("HToolsRenamePreview|")]
    assert "Name collision" in cmds.scrollField(report, query=True, text=True)
    from HTools.system import diagnosticLaunchPreview
    import os
    probe = output_dir / "diagnostic probe.py"
    probe.write_text("raise AssertionError('The preview must not run the probe.')", encoding="utf-8")
    rows = diagnosticLaunchPreview.commands(Path(os.environ["MAYA_LOCATION"]).parent, probe, output_dir, output_dir)
    assert len(rows) >= 2 and len({argv[4] for _, argv in rows}) == len(rows)
    for version, argv in rows:
        assert Path(argv[0]).is_file() and argv[2] == str(output_dir) and version in argv[4]
        assert "diagnostic probe.py" in argv[-1]
    window = launch("system.diagnosticLaunchPreview", "HToolsDiagnosticLaunchPreview")
    field, = [item for item in cmds.lsUI(type="textFieldGrp", long=True)
              if item.startswith("HToolsDiagnosticLaunchPreview|") and cmds.textFieldGrp(item, query=True, label=True) == "Diagnostic Python file"]
    cmds.textFieldGrp(field, edit=True, text=str(probe))
    click(window, "Compare launch settings")
    report, = [item for item in cmds.lsUI(type="scrollField", long=True) if item.startswith("HToolsDiagnosticLaunchPreview|")]
    assert "Maya2027.log" in cmds.scrollField(report, query=True, text=True)
    from HTools.rigging import featureRemovalPreview, publishedChannelAudit
    from mlrig.publishedChannels import setPorts
    cmds.file(new=True, force=True)
    roots = [cmds.createNode("transform", name=name) for name in ("leftRig", "rightRig")]
    for node in roots:
        setPorts(node, {"turn": {"path":"", "attribute":"rx", "kind":"default"}})
    graph = cmds.createNode("unitConversion")
    cmds.addAttr(roots[0], longName="graph", attributeType="message", multi=True)
    cmds.connectAttr(graph+".message", roots[0]+".graph[0]")
    for node in roots:
        cmds.connectAttr(graph+".output", node+".rx")
    cmds.setAttr(roots[1]+".rx", lock=True)
    rows = featureRemovalPreview.inspect(roots[0])
    assert any(graph in row for row in rows) and any("External output" in row and roots[1] in row for row in rows), rows
    cmds.select(roots[0])
    window = launch("rigging.featureRemovalPreview", "HToolsFeatureRemovalPreview")
    click(window, "Inspect hierarchy and registered graph")
    rows = publishedChannelAudit.inspect(roots)
    assert len(rows)==2 and all("unitConversion" in row for row in rows) and "Locked" in rows[1]
    cmds.select(roots)
    window = launch("rigging.publishedChannelAudit", "HToolsPublishedChannelAudit")
    click(window, "Compare selected rigs")
    assert all(cmds.isConnected(graph+".output", node+".rx") for node in roots)
    from HTools.rigging import boneFacePreview
    cmds.select(roots[0])
    window = launch("rigging.featureRemovalPreview", "HToolsFeatureRemovalPreview")
    click(window, "Capture feature before removal")
    cmds.delete(roots[0])
    click(window, "Check surviving feature nodes")
    report, = [item for item in cmds.lsUI(type="scrollField", long=True) if item.startswith("HToolsFeatureRemovalPreview|")]
    text = cmds.scrollField(report, query=True, text=True)
    assert "Remaining: "+graph in text and "Removed: |"+roots[0] in text and cmds.objExists(roots[1]), text
    cmds.file(new=True, force=True)
    root = cmds.joint(position=(-3,0,0))
    mid = cmds.joint(position=(0,0,0))
    tip = cmds.joint(position=(3,0,0))
    mesh = cmds.polyPlane(width=6, height=2, subdivisionsX=3, subdivisionsY=2)[0]
    shape, = cmds.listRelatives(mesh, shapes=True, fullPath=True)
    skin = cmds.skinCluster(root,mid,tip,mesh)[0]
    weights = cmds.skinPercent(skin, mesh+".vtx[0]", query=True, value=True)
    rows = boneFacePreview.classify(shape, [mid,tip])
    assert sorted(len(faces) for faces in rows.values()) == [2,4]
    assert sorted(rows[mid]+rows[tip]) == list(range(6))
    cmds.select(mesh, mid, tip)
    window = launch("rigging.boneFacePreview", "HToolsBoneFacePreview")
    click(window, "Classify selected mesh and bones")
    listing, = [item for item in cmds.lsUI(type="textScrollList", long=True) if item.startswith("HToolsBoneFacePreview|")]
    cmds.textScrollList(listing, edit=True, selectIndexedItem=1)
    click(window, "Select faces in highlighted group")
    assert len(cmds.ls(selection=True, flatten=True)) == 4
    assert cmds.skinPercent(skin, mesh+".vtx[0]", query=True, value=True) == weights
    shader = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    cmds.sets(mesh+".f[0]", edit=True, forceElement=shader)
    uvs = cmds.polyEditUV(mesh+".map[*]", query=True)
    click(window, "Copy highlighted faces")
    copied, = cmds.ls("boneFaces*", transforms=True)
    copied_shape, = cmds.listRelatives(copied, shapes=True, fullPath=True)
    assert cmds.polyEvaluate(copied, face=True)==4 and cmds.polyEvaluate(mesh, face=True)==6
    assert shaderAssignments.capture(copied_shape)["shaders"].count(shader)==1
    assert cmds.polyEvaluate(copied, uvShell=True)==1
    assert cmds.polyEditUV(mesh+".map[*]", query=True)==uvs
    cmds.undo()
    assert not cmds.objExists(copied) and cmds.objExists(mesh)
    from HTools.animation import referenceRigLoad
    cmds.file(new=True, force=True)
    driver = cmds.createNode("transform", name="driver")
    follower = cmds.createNode("transform", name="follow")
    cmds.parentConstraint(driver, follower)
    for frame in (1, 7, 12):
        cmds.setKeyframe(driver, attribute="tx", time=frame, value=frame)
    asset = str(output_dir / "followRig.ma")
    cmds.file(rename=asset)
    cmds.file(save=True, type="mayaAscii")
    timings = []
    for count in (1,4,16):
        cmds.file(new=True, force=True)
        nodes = []
        for index in range(count):
            namespace = f"actor{index}"
            cmds.file(asset, reference=True, namespace=namespace, executeScriptNodes=False)
            nodes.append(namespace + ":follow")
        for mode in ("off", "parallel"):
            cmds.evaluationManager(mode=mode)
            previous = cmds.currentTime(query=True)
            result = referenceRigLoad.measure(nodes, range(1,13,2))
            assert result["references"] == count and result["maxMatrixDifference"] < 1e-8
            assert cmds.currentTime(query=True)==previous
            timings.append(result)
    (output_dir / "rig-load.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")
    cmds.select(nodes)
    window = launch("animation.referenceRigLoad", "HToolsReferenceRigLoad")
    click(window, "Measure selected transforms")
    cmds.file(new=True, force=True)
    root = cmds.createNode("transform", name="rig")
    ctrl = cmds.parent(cmds.polyCube(name="control")[0], root)[0]
    cmds.instance(ctrl, name="sharedControl")
    cmds.sets(ctrl, name="controls")
    asset = str(output_dir / "roles.ma")
    cmds.file(rename=asset)
    cmds.file(save=True, type="mayaAscii")
    cmds.file(new=True, force=True)
    for namespace in ("one","two"):
        cmds.file(asset, reference=True, namespace=namespace, executeScriptNodes=False)
    cmds.select("one:rig")
    window = launch("rigging.roleGroup", "HToolsRoleGroup")
    click(window, "Use selected rig root")
    field, = [item for item in cmds.lsUI(type="textFieldGrp", long=True)
              if item.startswith("HToolsRoleGroup|") and cmds.textFieldGrp(item, query=True, label=True) == "Role object set"]
    cmds.textFieldGrp(field, edit=True, text="controls")
    click(window, "Select group")
    assert cmds.ls(selection=True)==["one:control"]
    click(window, "Hide group")
    assert not cmds.getAttr("one:control.visibility") and cmds.getAttr("two:control.visibility")
    assert cmds.getAttr("one:sharedControl.visibility") and cmds.getAttr("one:controlShape.visibility")
    cmds.undo()
    assert cmds.getAttr("one:control.visibility")
    cmds.file(new=True, force=True)
    root = cmds.createNode("transform", name="ports")
    setPorts(root, {"turn":{"path":"","attribute":"rotateX","kind":"default"}})
    asset = str(output_dir / "ports.ma")
    cmds.file(rename=asset)
    cmds.file(save=True, type="mayaAscii")
    cmds.file(new=True, force=True)
    cmds.file(asset, reference=True, namespace="actor")
    port = "actor:ports.rotateX"
    cmds.setAttr(port, 17)
    for _ in range(2):
        node = cmds.createNode("unitConversion")
        cmds.connectAttr(port, node + ".input")
    cmds.file(rename=str(output_dir / "port-shot.ma"))
    cmds.file(save=True, type="mayaAscii")
    rows = publishedChannelAudit.inspect(["|actor:ports"])
    assert len(rows)==1 and all(word in rows[0] for word in ("Reference edit:", "setAttr", "2 output connections")), rows
    from HTools.system import rigPackageInspection
    cmds.select("actor:ports")
    window = launch("system.rigPackageInspection", "HToolsRigPackageInspection")
    click(window, "Inspect selected rig and scene dependencies")
    rows = rigPackageInspection.inspect("|actor:ports")
    assert any("turn:" in row and "rotateX" in row for row in rows)
    assert any("loaded, present" in row and "ports.ma" in row for row in rows)
    assert "Time unit: film" in rows and "Asset version: Not declared" in rows
    from HTools.system import presetSources
    relative = "attrPresets/transform/est3-source-test.mel"
    personal = Path(cmds.internalVar(userPrefDir=True)).parent / "presets" / relative
    personal.parent.mkdir(parents=True, exist_ok=True)
    personal.write_text("// personal", encoding="utf-8")
    for label in ("project-a", "project-b"):
        project = output_dir / label
        preset = project / "presets" / relative
        preset.parent.mkdir(parents=True)
        preset.write_text("// project", encoding="utf-8")
        (project/"workspace.mel").write_text("//Maya Project Definition", encoding="utf-8")
        cmds.workspace(str(project), openWorkspace=True)
        rows = presetSources.sources(relative)
        assert rows[:2]==[("Personal", personal.resolve()), ("Project", preset.resolve())], rows
    window = launch("system.presetSources", "HToolsPresetSources")
    field, = [item for item in cmds.lsUI(type="textFieldGrp", long=True) if item.startswith("HToolsPresetSources|")]
    cmds.textFieldGrp(field, edit=True, text=relative)
    click(window, "Resolve in current project")
    from HTools.rigging import rigFinish
    cmds.file(new=True, force=True)
    joint = cmds.joint()
    mesh = cmds.polyCube()[0]
    skin = cmds.skinCluster(joint, mesh)[0]
    before = cmds.xform(mesh+".vtx[*]", query=True, worldSpace=True, translation=True)
    weights = [cmds.skinPercent(skin, f"{mesh}.vtx[{i}]", query=True, value=True) for i in range(8)]
    shape, = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, fullPath=True)
    mats = shaderAssignments.capture(shape)
    window = launch("rigging.rigFinish", "HToolsRigFinish")
    menu, = [item for item in cmds.lsUI(type="optionMenu", long=True) if item.startswith("HToolsRigFinish|")]
    for rule,node in (("Hide bind joint drawing",joint),("Make render mesh unselectable",mesh),("Hide node from channel history",skin)):
        cmds.optionMenu(menu, edit=True, value=rule)
        cmds.select(node)
        click(window, "Diagnose selected rule")
        click(window, "Apply selected display rule")
        assert not rigFinish.inspect(node,rule)
        click(window, "Apply selected display rule")
    assert cmds.xform(mesh+".vtx[*]", query=True, worldSpace=True, translation=True) == before
    assert [cmds.skinPercent(skin, f"{mesh}.vtx[{i}]", query=True, value=True) for i in range(8)] == weights
    assert shaderAssignments.differences(mats) == []
    cmds.file(new=True, force=True)
    mesh = cmds.polyPlane(subdivisionsX=1, subdivisionsY=1)[0]
    ctl = cmds.createNode("transform", name="control")
    before = cmds.xform(mesh+".vtx[*]", query=True, worldSpace=True, translation=True)
    cmds.select(ctl)
    window = launch("rigging.vertexTweak", "HToolsVertexTweak")
    click(window, "Use selected control")
    menu, = [item for item in cmds.lsUI(type="optionMenu", long=True) if item.startswith("HToolsVertexTweak|")]
    for i,kind in enumerate(("Cluster","SoftMod")):
        cmds.select(f"{mesh}.vtx[{i}]")
        cmds.optionMenu(menu, edit=True, value=kind)
        click(window, "Create tweak on selected vertex")
    assert len(cmds.listRelatives(ctl, children=True))==2
    assert cmds.xform(mesh+".vtx[*]", query=True, worldSpace=True, translation=True)==before
    cmds.setAttr(ctl+".ty", 1)
    after = cmds.xform(mesh+".vtx[*]", query=True, worldSpace=True, translation=True)
    assert all(abs(after[3*i+1]-1)<1e-5 for i in (0,1)) and after[6:]==before[6:], after
    cmds.delete(cmds.ls(type="cluster"))
    assert cmds.objExists(ctl) and cmds.ls(type="softMod")
    assert abs(cmds.pointPosition(mesh+".vtx[1]", world=True)[1]-1)<1e-5
    cmds.file(new=True, force=True)
    mesh = cmds.polyPlane(width=3, height=1, subdivisionsX=6, subdivisionsY=2)[0]
    positions = cmds.xform(mesh+".vtx[7:13]", query=True, worldSpace=True, translation=True)[::3]
    cmds.sculpt(mesh, mode="flip", dropoffDistance=0, maxDisplacement=0)
    pushed = cmds.xform(mesh+".vtx[7:13]", query=True, worldSpace=True, translation=True)[::3]
    assert positions == [-1.5,-1,-0.5,0,0.5,1,1.5] and pushed == [-1.5,-1,-1,1,1,1,1.5]
    cmds.undo()
    assert cmds.xform(mesh+".vtx[7:13]", query=True, worldSpace=True, translation=True)[::3] == positions
    import mlib
    from mlrig.definition import RigDefinition, limb_definition
    from HTools.rigging import rigAssetExport
    cmds.file(new=True, force=True)
    root = cmds.createNode("transform", name="rig")
    cmds.addAttr(root, longName="mlrigDefinition", dataType="string")
    definition = limb_definition("leg")
    cmds.setAttr(root+".mlrigDefinition", json.dumps(definition.to_data()), type="string")
    cmds.select(root)
    window = launch("rigging.rigAssetExport", "HToolsTypedRigExport")
    click(window, "Inspect selected asset")
    path = rigAssetExport.export(root, output_dir/"limb.json")
    assert RigDefinition.from_data(json.loads(path.read_text(encoding="utf-8")))==definition
    cmds.select(clear=True)
    j1 = cmds.joint()
    j2 = cmds.joint(position=(2,0,0))
    mesh = cmds.polyCube()[0]
    skin = cmds.skinCluster(j1,j2,mesh)[0]
    cmds.skinPercent(skin, mesh+".vtx[0]", transformValue=[(j1,0.25),(j2,0.75)])
    cmds.select(skin)
    click(window, "Inspect selected asset")
    path = rigAssetExport.export(skin, output_dir/"skin.json")
    cmds.skinPercent(skin, mesh+".vtx[0]", transformValue=[(j1,1),(j2,0)])
    mlib.getNode(skin).importWeights(path)
    assert cmds.skinPercent(skin, mesh+".vtx[0]", query=True, value=True)==[0.25,0.75]
    from HTools.rigging import legacyRigInspection
    cmds.setAttr(j1+".segmentScaleCompensate", False)
    cmds.setKeyframe(j1, attribute="ry", time=1, value=0)
    cmds.setKeyframe(j1, attribute="ry", time=10, value=35)
    setPorts(j1, {"spin":{"path":"","attribute":"rotateY","kind":"default"}})
    ports = cmds.getAttr(j1+".mlrigPublishedChannels")
    before = cmds.xform(mesh+".vtx[*]", query=True, worldSpace=True, translation=True)
    weights = mlib.getNode(skin).getWeightsData()["weights"]
    cmds.select(j1)
    window = launch("rigging.legacyRigInspection", "HToolsLegacyRigInspection")
    click(window, "Preview top joint SSC")
    assert not cmds.getAttr(j1+".segmentScaleCompensate")
    click(window, "Enable SSC on selected top joints")
    assert not legacyRigInspection.pending([j1]) and cmds.getAttr(j1+".segmentScaleCompensate")
    assert cmds.keyframe(j1+".ry", query=True, valueChange=True)==[0,35]
    assert cmds.getAttr(j1+".mlrigPublishedChannels")==ports
    assert mlib.getNode(skin).getWeightsData()["weights"]==weights
    assert cmds.xform(mesh+".vtx[*]", query=True, worldSpace=True, translation=True)==before
    cmds.undo()
    assert not cmds.getAttr(j1+".segmentScaleCompensate")
    legacy = output_dir/"legacy.ma"
    legacy.write_text('//Maya ASCII 2027 scene\nrequires maya "2027";\n'
                      'requires -nodeType "eST3fakeRope" -nodeType "eST3flattenSurface" "absentLegacyFixture" "1.0";\n'
                      'createNode eST3fakeRope -n "rope";\ncreateNode eST3flattenSurface -n "flatten";\n'
                      'createNode multMatrix -n "follower_epConstMat_A";\n',encoding="ascii")
    cmds.file(str(legacy), reference=True, namespace="legacy", executeScriptNodes=False)
    click(window, "Inspect legacy setup markers")
    rows = legacyRigInspection.inventory()
    assert all(any(label in row for row in rows) for label in ("Fake Rope","Flatten:","Possible Exclusive Parent","Uniform:"))
    scenes = Path(__file__).resolve().parents[4] / "maya/external/eST3/samples/scenes"
    for name in ("bipedStandard.ma", "quadruped.ma"):
        markers = legacyRigInspection.inspectFile(scenes/name)
        assert any("Utility Node" in row for row in markers), name
        (output_dir / (name + "-markers.txt")).write_text("\n".join(markers), encoding="utf-8")
    from mlrig.limb import build_limb
    rebuilt = build_limb(RigDefinition.from_data(json.loads((output_dir/"limb.json").read_text(encoding="utf-8"))))
    assert cmds.objExists(rebuilt.root.getName(full=True) + ".mlrigDefinition")
    result = {"status": "passed", "cases": ["N03", "N11", "F09", "B1-03", "E1-02", "F02", "N16", "N02", "N09", "N04", "F06", "F07", "F08", "X07", "G20", "G21", "E2-01", "F03", "E1-07", "X06", "G22", "F01", "U07", "G15", "C07", "C06", "G24"]}
    (output_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    finished(result)


