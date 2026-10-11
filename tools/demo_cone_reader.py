"""mlrig.setups.ConeReader の一致度(0〜1)を、腕の動きで録画して検証する。

肩(shoulder)と上腕(upperArm)のジョイントに ConeReader を付け、上腕のX軸を矢印、
コーンを肩に追従させる。コーンは肩の空間で前下方へ向ける。段階は次のとおり。

1. 腕をコーンの中に通す(中心で1、縁で0)。
2. コーンの軸から30度の向きのまま、軸の周りを一周する(左右に関係なく0.5)。
3. coneAngle を 60→30→90 に変える(表示のコーンも開閉する)。
4. 肩を回す(コーンも追従し、値は変わらない)。
5. falloff を smooth にして、もう一度通す。

リグは標準ノードのみ。Pythonは入力アニメーションと、行列から求めた独立計算による検査用。
"""

import json
import math
import os
from pathlib import Path

from maya import cmds
import maya.api.OpenMaya as om
from mlib import logger
from mlrig.setups import ConeReader
from verification_video import recordVideo
import demo_interactive

WINDOW = "coneReaderDemoWindow"
PANEL = "coneReaderDemoPanel"
CONE_YAW = -45.0
CONE_PITCH = -20.0
SEGMENT_FRAMES = 48

# (段階名, フレーム数)
STAGES = [("1 SWEEP THROUGH THE CONE", 96), ("2 CIRCLE AT 30 DEG FROM AXIS", 96),
          ("3 CONE ANGLE 60 -> 30 -> 90", 96), ("4 SHOULDER ROTATES (CONE FOLLOWS)", 72),
          ("5 SMOOTH FALLOFF SWEEP", 96)]


def _rotationTo(direction):
    """ローカル +X を direction へ向ける回転(度、xyz)。"""
    q = om.MVector(1, 0, 0).rotateTo(om.MVector(*direction).normal())
    e = q.asEulerRotation()
    return [math.degrees(v) for v in (e.x, e.y, e.z)]


def _rotate(vector, axis, degrees):
    """vector を axis まわりに回す。"""
    q = om.MQuaternion(math.radians(degrees), om.MVector(*axis).normal())
    return list(om.MVector(*vector).rotateBy(q))


def main(record=True):
    """専用GUIでシーンを作り、録画して検証する。

    Args:
        record (bool): False なら録画せず、タイムラインで確認できるシーンを作る。
    """
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    if PANEL in cmds.getPanel(allPanels=True):
        cmds.deleteUI(PANEL, panel=True)
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW, window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")

    shoulder = cmds.createNode("joint", name="shoulder")
    arm = cmds.createNode("joint", name="upperArm", parent=shoulder)
    cmds.setAttr(arm+".tx", 0.001)
    tip = cmds.createNode("joint", name="upperArmTip", parent=arm)
    cmds.setAttr(tip+".tx", 4)
    for node in (shoulder, arm, tip):
        cmds.setAttr(node+".radius", 0.25)
    reader = ConeReader.create(arm, shoulder, name="armReader", coneAngle=60, size=4)
    cmds.setAttr(reader.cone+".rotate", 0, CONE_YAW, CONE_PITCH)
    owner = reader.container.getFullName()
    cone_axis = [v for v in om.MVector(1, 0, 0).rotateBy(om.MEulerRotation(
        0, math.radians(CONE_YAW), math.radians(CONE_PITCH)))]

    # 出力の大きさを棒の長さで見せる(検証表示用。リグ本体ではない)。
    bar = cmds.polyCube(name="weightBar", width=0.4, height=1, depth=0.4, constructionHistory=False)[0]
    cmds.xform(bar, pivots=(0, -0.5, 0))
    cmds.setAttr(bar+".translate", -3, 0.5, 0)
    frame_bar = cmds.polyCube(name="weightBarFull", width=0.5, height=4, depth=0.05, constructionHistory=False)[0]
    cmds.setAttr(frame_bar+".translate", -3, 2, -0.3)
    scale = cmds.createNode("multDoubleLinear", name="weightBarScale")
    cmds.setAttr(scale+".input2", 4)
    cmds.connectAttr(owner+".weight", scale+".input1")
    cmds.connectAttr(scale+".output", bar+".scaleY")
    for node, color in ((bar, (0.2, 1, 0.3)), (frame_bar, (0.25, 0.25, 0.25))):
        shader = cmds.shadingNode("lambert", asShader=True, name=node+"Material")
        cmds.setAttr(shader+".color", *color, type="double3")
        group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
        cmds.connectAttr(shader+".outColor", group+".surfaceShader")
        cmds.sets(node, edit=True, forceElement=group)

    # 入力アニメーション。腕の向きは肩の空間で決めて、上腕の回転へ変換する。
    stages, frame = [], 0
    side = list(om.MVector(*cone_axis) ^ om.MVector(0, 1, 0))
    for name, length in STAGES:
        for i in range(length):
            u = i/(length-1)
            w = u*u*(3-2*u)
            angle_value, falloff, shoulder_rot = 60.0, 0, (0, 0, 0)
            if name.startswith("1") or name.startswith("5"):
                direction = _rotate(cone_axis, side, -90+180*w)
                falloff = 1 if name.startswith("5") else 0
            elif name.startswith("2"):
                direction = _rotate(_rotate(cone_axis, side, 30), cone_axis, 360*u)
            elif name.startswith("3"):
                direction = _rotate(cone_axis, side, 25)
                angle_value = 60-30*min(1, 2*u)/1 if u < 0.5 else 30+60*(2*u-1)
            else:
                direction = _rotate(cone_axis, side, 25)
                shoulder_rot = (40*math.sin(math.tau*u), 60*math.sin(math.pi*u), -30*math.sin(math.tau*u))
            rotation = _rotationTo(direction)
            for attr, value in zip(("rx", "ry", "rz"), rotation):
                cmds.setKeyframe(arm, attribute=attr, time=frame+1, value=value)
            for attr, value in zip(("rx", "ry", "rz"), shoulder_rot):
                cmds.setKeyframe(shoulder, attribute=attr, time=frame+1, value=value)
            cmds.setKeyframe(owner, attribute="coneAngle", time=frame+1, value=angle_value)
            cmds.setKeyframe(owner, attribute="falloff", time=frame+1, value=falloff)
            stages.append(name)
            frame += 1
    count = frame
    cmds.keyTangent(owner, attribute="falloff", outTangentType="step")
    cmds.playbackOptions(minTime=1, maxTime=count)

    camera, camera_shape = cmds.camera(name="coneReaderCamera")
    cmds.setAttr(camera+".translate", 9, 7, 13)
    cmds.setAttr(camera+".rotate", -24, 34, 0)
    cmds.setAttr(camera_shape+".focalLength", 30)
    if cmds.windowPref(WINDOW, exists=True):
        cmds.windowPref(WINDOW, remove=True)
    window = cmds.window(WINDOW, widthHeight=(1280, 720))
    pane = cmds.paneLayout(parent=window)
    panel = cmds.modelPanel(PANEL, parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", grid=True, cameras=False,
                     joints=True, headsUpDisplay=True, manipulators=False, selectionHiliteDisplay=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1280, 720))
    cmds.setFocus(panel)
    cmds.select(clear=True)
    demo_interactive.clearHuds(window)
    texts = {}
    rows = [("coneTop", 0, 4), ("coneBottom", 5, 3)]
    for prefix, section, size in rows:
        for row in range(size):
            name = "{}{}".format(prefix, row)
            texts[name] = ""
            cmds.headsUpDisplay(name, section=section, block=row, blockSize="large", dataFontSize="large",
                                command=lambda n=name: texts[n])

    def evaluate(index):
        """DGの weight・angle を、行列から求めた独立計算と比べる。"""
        demo_interactive.setTime(index)
        m = cmds.xform(reader.driver, query=True, worldSpace=True, matrix=True)
        c = cmds.xform(reader.cone, query=True, worldSpace=True, matrix=True)
        a, b = om.MVector(*m[0:3]).normal(), om.MVector(*c[0:3]).normal()
        angle = math.degrees(a.angle(b))
        cone_angle = cmds.getAttr(owner+".coneAngle")
        falloff = ("linear", "smooth")[cmds.getAttr(owner+".falloff")]
        expected = ConeReader.weight(angle, cone_angle, falloff)
        weight = cmds.getAttr(owner+".weight")
        dg_angle = cmds.getAttr(owner+".angle")
        arm_dir = om.MVector(*cmds.xform(arm, query=True, worldSpace=True, matrix=True)[0:3]).normal()
        ok = abs(weight-expected) < 1e-4 and abs(dg_angle-angle) < 1e-3 and (a-arm_dir).length() < 1e-5
        formula = ("weight = clamp(1 - angle / coneAngle, 0, 1)" if falloff == "linear"
                   else "t = clamp(1 - angle / coneAngle, 0, 1),  weight = t^2 (3 - 2t)")
        texts["coneTop0"] = "ConeReader (mlrig.setups): arrow = upperArm X, cone follows shoulder"
        texts["coneTop1"] = formula
        texts["coneTop2"] = "angle = {:.1f} deg   coneAngle = {:.1f} deg   falloff = {}".format(
            dg_angle, cone_angle, falloff)
        texts["coneTop3"] = "weight (DG) = {:.3f}   expected = {:.3f}   {}".format(
            weight, expected, "OK" if ok else "MISMATCH")
        texts["coneBottom0"] = "green bar = weight (full height = 1)"
        texts["coneBottom1"] = "yellow arrow = driver, cyan cone = coneAngle"
        texts["coneBottom2"] = stages[index]
        for name in texts:
            cmds.headsUpDisplay(name, refresh=True)
        return {"frame": index, "stage": stages[index], "angle_degrees": dg_angle,
                "reference_angle_degrees": angle, "cone_angle_degrees": cone_angle, "falloff": falloff,
                "weight": weight, "expected_weight": expected, "ok": ok}

    if not record:
        demo_interactive.attachInteractive(window, count, evaluate)
        logger.info("ConeReaderのシーンを作成しました。タイムラインで確認できます。")
        return
    folder = recordVideo("mlrig ConeReader: コーンの一致度（0〜1）", count, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1280, height=720)
    cmds.file(rename=str(folder/"cone-reader.ma"))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-cone-reader.json").write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("ConeReaderの検証に失敗: {}".format(folder))
    logger.info("ConeReaderの検証を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
