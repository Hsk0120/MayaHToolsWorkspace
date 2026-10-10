"""Maya GUIで補正前後を比較し、viewport画像と検証用シーンを保存する。"""

import json
import math
from pathlib import Path
import traceback

from maya import cmds
from maya.api import OpenMaya as om
import maya.OpenMaya as om1
import maya.OpenMayaUI as omui

from hlib import logger
from hrig.setups import RootDirectionLimit


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".maya-output/root-limit-gui"
STATE = {}
POSES = (
    ("01_neutral", "NEUTRAL", 0, 0, 0, 0),
    ("02_arm_twist", "ARM TWIST 165 DEG", 0, 0, 165, 0),
    ("03_forward_bend", "TORSO FORWARD BEND + ARM TWIST", 45, 30, 165, 0),
    ("04_side_bend", "TORSO SIDE BEND + ARM SWEEP", 0, 0, 165, 15),
)


def material(name, color):
    """検証用の単色マテリアルを作成する。

    Args:
        name (str): 名前。
        color (tuple): RGB。

    Returns:
        str: shadingGroup。
    """
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def sphere(name, parent, scale, group, position=(0, 0, 0)):
    """guideに追従する胴体またはマーカーを表示する。

    Args:
        name (str): 名前。
        parent (str): 親。
        scale (tuple): 寸法。
        group (str): マテリアル。
        position (tuple): ローカル位置。

    Returns:
        str: メッシュTransform。
    """
    node = cmds.polySphere(name=name, subdivisionsX=40, subdivisionsY=24, constructionHistory=False)[0]
    cmds.parent(node, parent, relative=True)
    cmds.setAttr(node + ".translate", *position)
    cmds.setAttr(node + ".scale", *scale)
    cmds.sets(node, edit=True, forceElement=group)
    return node


def cylinder(name, parent, axis, length, radius, position, group):
    """骨に追従する比較用の棒を表示する。

    Args:
        name (str): 名前。
        parent (str): 親。
        axis (tuple): 長手軸。
        length (float): 長さcm。
        radius (float): 半径cm。
        position (tuple): 中心のローカル位置。
        group (str): マテリアル。

    Returns:
        str: メッシュTransform。
    """
    node = cmds.polyCylinder(name=name, axis=axis, height=length, radius=radius,
                             subdivisionsX=24, constructionHistory=False)[0]
    cmds.parent(node, parent, relative=True)
    cmds.setAttr(node + ".translate", *position)
    cmds.sets(node, edit=True, forceElement=group)
    return node


def build():
    """隔離GUIの新規シーンに胴体・腕・比較用尻尾を構築する。"""
    if "rootLimitValidationPanel" in cmds.getPanel(allPanels=True):
        cmds.deleteUI("rootLimitValidationPanel", panel=True)
    if cmds.window("rootLimitValidationWindow", exists=True):
        cmds.deleteUI("rootLimitValidationWindow", window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg")
    body_material = material("bodyGrey", (0.24, 0.29, 0.36))
    red = material("uncorrectedRed", (0.92, 0.12, 0.08))
    green = material("correctedGreen", (0.03, 0.65, 0.03))
    arm_material = material("armBlue", (0.1, 0.15, 0.45))
    gold = material("guideGold", (1.0, 0.67, 0.08))
    guides = []
    for index, name in enumerate(("pelvisGuide", "abdomenGuide", "chestGuide")):
        node = cmds.createNode("transform", name=name, parent=guides[-1]) if guides else cmds.createNode("transform", name=name)
        cmds.setAttr(node + ".ty", 5 if index else 0)
        guides.append(node)
        sphere(name + "Marker", node, (0.18, 0.18, 0.18), gold)
    meshes = [sphere("pelvisBody", guides[0], (2.3, 2.8, 1.6), body_material),
              sphere("abdomenBody", guides[1], (2.15, 3.4, 1.5), body_material),
              sphere("chestBody", guides[2], (2.9, 3.2, 1.8), body_material, (0, -0.5, 0))]
    shoulder = cmds.createNode("transform", name="shoulder", parent=guides[2])
    cmds.setAttr(shoulder + ".tx", 3.7)
    arm_pose = cmds.createNode("transform", name="armPose", parent=shoulder)
    arm = cmds.createNode("transform", name="armDriver", parent=arm_pose)
    cylinder("upperArm", arm, (0, 1, 0), 5, 0.28, (0, -2.5, 0), arm_material)
    elbow = cmds.createNode("transform", name="elbowSocket", parent=arm)
    cmds.setAttr(elbow + ".ty", -5)
    sphere("elbowMarker", elbow, (0.3, 0.3, 0.3), gold)
    cylinder("forearm", elbow, (0, 1, 0), 4, 0.23, (0, -2, 0), arm_material)
    graph = RootDirectionLimit.create(elbow, guides, name="tailRootAvoidance", angle=45)
    # 変更する出力は根元1骨の向きだけ。末端のローカル位置/回転は固定する。
    root_joint = cmds.createNode("joint", name="tailRoot_joint", parent=graph.output.getFullName())
    tip_joint = cmds.createNode("joint", name="tailTip_joint", parent=root_joint)
    cmds.setAttr(tip_joint + ".tx", 6)
    cylinder("correctedTail", root_joint, (1, 0, 0), 6, 0.16, (3, 0, 0), green)
    cylinder("uncorrectedTail", elbow, (1, 0, 0), 6, 0.10, (3, 0, 0), red)
    camera, camera_shape = cmds.camera(name="verificationCamera", orthographic=True)
    cmds.setAttr(camera_shape + ".orthographicWidth", 38)
    cmds.setAttr(camera + ".translate", 27, 18, 34)
    temporary = cmds.aimConstraint(guides[1], camera, aimVector=(0, 0, -1), upVector=(0, 1, 0), worldUpType="vector")[0]
    cmds.delete(temporary)
    window = cmds.window("rootLimitValidationWindow", title="Root Direction Limit - Maya 2027 Validation", widthHeight=(1280, 850))
    layout = cmds.columnLayout(adjustableColumn=True)
    cmds.text(label="RED: uncorrected tail   |   GREEN: root rotation corrected   |   GOLD: body guides", height=30)
    title = cmds.text(label="", height=28)
    pane = cmds.paneLayout(parent=layout, height=740)
    panel = cmds.modelPanel("rootLimitValidationPanel", parent=pane, camera=camera,
                             menuBarVisible=False, label="Pose-free root direction limit")
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default",
                     grid=False, selectionHiliteDisplay=False, cameras=False, joints=False,
                     headsUpDisplay=True, manipulators=False)
    for hud in ("rootLimitLegendHUD", "rootLimitPoseHUD"):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
    cmds.headsUpDisplay("rootLimitLegendHUD", section=2, block=cmds.headsUpDisplay(nextFreeBlock=2),
                        label="RED: before  |  GREEN: root corrected  |  Body guides follow torso", labelFontSize="large")
    cmds.headsUpDisplay("rootLimitPoseHUD", section=2, block=cmds.headsUpDisplay(nextFreeBlock=2), label="", labelFontSize="large")
    cmds.showWindow(window)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    STATE.update(guides=guides, arm=arm, arm_pose=arm_pose, elbow=elbow, graph=graph, meshes=meshes,
                 panel=panel, title=title, root=root_joint, tip=tip_joint, camera=camera)


def intersections(direction, length=6.0):
    """検証時だけ実メッシュと中心線の交差を確認する。

    リグの評価には使わない独立した検証oracle。collisionノードは作らない。

    Args:
        direction (MVector): ワールド単位方向。
        length (float): 検証する中心線の長さ。cm。

    Returns:
        list[str]: 指定した中心線が交差する胴体メッシュ。
    """
    position = cmds.xform(STATE["elbow"], query=True, worldSpace=True, translation=True)
    hits = []
    for mesh in STATE["meshes"]:
        selection = om.MSelectionList()
        selection.add(mesh)
        dag = selection.getDagPath(0)
        dag.extendToShape()
        fn = om.MFnMesh(dag)
        hit = fn.closestIntersection(om.MFloatPoint(*position), om.MFloatVector(*direction),
                                     om.MSpace.kWorld, length, False)
        if hit is not None:
            hits.append(mesh)
    return hits


def pose(index, save=False):
    """指定姿勢の数値・viewport画像を保存する。

    Args:
        index (int): POSESの番号。
        save (bool): 画像とシーンを保存するか。

    Returns:
        dict: 姿勢の診断と交差数。
    """
    name, label, bend, chest_bend, twist, sweep = POSES[index]
    cmds.setAttr(STATE["guides"][1] + ".rotate", bend, 0, 35 if index == 3 else 0)
    cmds.setAttr(STATE["guides"][2] + ".rotate", chest_bend, 0, 20 if index == 3 else 0)
    cmds.setAttr(STATE["arm_pose"] + ".rotate", -chest_bend, 0, -20 if index == 3 else 0)
    cmds.setAttr(STATE["arm"] + ".rotate", 0, twist, sweep)
    graph = STATE["graph"]
    input_dot = graph.container.getPlug("inputDot").get()
    result_dot = graph.container.getPlug("resultDot").get()
    input_angle = math.degrees(math.acos(max(-1, min(1, input_dot))))
    output_angle = math.degrees(math.acos(max(-1, min(1, result_dot))))
    raw_matrix = om.MMatrix(cmds.getAttr(STATE["elbow"] + ".worldMatrix[0]"))
    safe_matrix = om.MMatrix(cmds.getAttr(STATE["root"] + ".worldMatrix[0]"))
    raw_direction = om.MVector(*tuple(raw_matrix)[:3]).normal()
    safe_direction = om.MVector(*tuple(safe_matrix)[:3]).normal()
    raw_hits, safe_hits = intersections(raw_direction), intersections(safe_direction)
    delta = (om.MVector(*tuple(raw_matrix)[12:15]) - om.MVector(*tuple(safe_matrix)[12:15])).length()
    result = {"pose": name, "input_angle": input_angle, "output_angle": output_angle,
              "root_position_error_cm": delta, "raw_intersections": raw_hits,
              "corrected_intersections": safe_hits,
              "tip_local_translate": cmds.getAttr(STATE["tip"] + ".translate")[0],
              "tip_local_rotate": cmds.getAttr(STATE["tip"] + ".rotate")[0]}
    cmds.text(STATE["title"], edit=True, label="{}   |   Before {:.1f} deg / After {:.1f} deg   |   Limit 45 deg".format(label, input_angle, output_angle))
    cmds.headsUpDisplay("rootLimitPoseHUD", edit=True,
                        label="{}  |  {:.1f} -> {:.1f} deg  |  Limit 45 deg".format(label, input_angle, output_angle))
    cmds.refresh(force=True)
    if save:
        image = om1.MImage()
        view = omui.M3dView()
        omui.M3dView.getM3dViewFromModelPanel(STATE["panel"], view)
        view.refresh(False, True)
        view.readColorBuffer(image, True)
        image.writeToFile(str(OUTPUT / (name + ".png")), "png")
        cmds.file(rename=str(OUTPUT / (name + ".ma")))
        cmds.file(save=True, type="mayaAscii")
        result["image"] = str(OUTPUT / (name + ".png"))
    return result


def main():
    """GUI idle後に比較シーンと4枚の実viewport画像を作成する。"""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    try:
        build()
        results = [pose(index, save=True) for index in range(len(POSES))]
        assert all(r["output_angle"] <= 45.002 for r in results)
        assert all(not r["corrected_intersections"] for r in results)
        assert any(r["raw_intersections"] for r in results[1:])
        assert all(r["root_position_error_cm"] < 1e-4 for r in results)
        assert all(r["tip_local_translate"] == (6, 0, 0) and r["tip_local_rotate"] == (0, 0, 0) for r in results)
        record = {"ok": True, "maya": cmds.about(version=True), "poses": results,
                  "node_count": len(STATE["graph"].container.getMembers()),
                  "runtime_collision_nodes": cmds.ls(type="closestPointOnMesh"),
                  "runtime_expressions": cmds.ls(type="expression")}
        (OUTPUT / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        if (OUTPUT / "error.txt").exists():
            (OUTPUT / "error.txt").unlink()
        pose(2)
        logger.info("根元方向制限のGUI検証と4枚の画像を保存しました。")
    except Exception:
        (OUTPUT / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        logger.error("根元方向制限のGUI検証でエラーが発生しました。")
        raise


if __name__ == "__main__":
    main()
