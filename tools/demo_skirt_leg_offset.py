"""SkirtLegOffsetのスカートの脚よけを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_skirt_leg_offset.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 36
COUNT = 8
RADIUS = 2.2
TIP = (1.2, -4.5)
CLEARANCE = 10.0
MAX_ANGLE = 80.0
SPREAD = 75.0
# (左の股関節のrotateX, 左のrotateZ, 右のrotateX[度], 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, 0.0, 0.0, "1 REST"),
    (0.0, 0.0, 0.0, "2 LIFT THE LEFT LEG FORWARD TO 90 deg"),
    (-90.0, 0.0, 0.0, "3 SWING THE LEFT LEG OUT TO THE SIDE"),
    (-25.0, 55.0, 0.0, "4 LEFT LEG DOWN, RIGHT LEG BACK 45 deg"),
    (0.0, 0.0, 45.0, "5 RIGHT LEG FORWARD 70 deg"),
    (0.0, 0.0, -70.0, "6 RETURN TO REST"),
    (0.0, 0.0, 0.0, "6 RETURN TO REST"),
    (0.0, 0.0, 0.0, "6 RETURN TO REST"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:3], POSES[index + 1][:3])]
    return values, POSES[index][3]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _hud(prefix, count):
    """上段2行・下段の残りの行のHUDを作り、(値の列, HUD名)を返す。"""
    from maya import cmds
    values = [""] * count
    names = ["{}HUD{}".format(prefix, i) for i in range(count)]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (count - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return values, names


def _limb(name, parent, length, radius, group):
    """parentから-Yへlengthだけ伸びる円柱を作り、parentの子にする。"""
    from maya import cmds
    body = cmds.polyCylinder(name=name, radius=radius, height=length, axis=(0, 1, 0))[0]
    cmds.parent(body, parent, relative=True)
    cmds.setAttr(body + ".translateY", -length / 2.0)
    cmds.sets(body, edit=True, forceElement=group)
    return body


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import SkirtLegOffset
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("legRed", (0.9, 0.15, 0.1)), "green": _shader("skirtGreen", (0.15, 0.75, 0.25)),
              "ghost": _shader("restGhost", (0.6, 0.6, 0.65), 0.75), "body": _shader("bodyGray", (0.5, 0.5, 0.55))}
    pelvis = cmds.createNode("transform", name="pelvis")
    cmds.setAttr(pelvis + ".translateY", 10)
    hipBox = cmds.polyCube(name="pelvis_GEO", width=4.0, height=1.4, depth=2.6)[0]
    cmds.parent(hipBox, pelvis, relative=True)
    cmds.setAttr(hipBox + ".translateY", 0.6)
    cmds.sets(hipBox, edit=True, forceElement=groups["body"])
    legs, hips = [], []
    for side, x in (("L", 1.2), ("R", -1.2)):
        cmds.select(clear=True)
        hip = cmds.joint(name="hip" + side)
        cmds.parent(hip, pelvis, relative=True)
        cmds.setAttr(hip + ".translate", x, -0.5, 0)
        knee = cmds.joint(name="knee" + side)
        cmds.setAttr(knee + ".translate", 0, -4.5, 0)
        _limb("thigh{}_GEO".format(side), hip, 4.5, 0.75, groups["red"])
        _limb("shin{}_GEO".format(side), knee, 4.5, 0.55, groups["red"])
        hip, knee = cmds.ls(hip, long=True)[0], cmds.ls(knee, long=True)[0]
        legs.append((hip, knee))
        hips.append(hip)
    skirts = []
    length = math.hypot(*TIP)
    for index in range(COUNT):
        angle = 2 * math.pi * index / COUNT
        out = (math.sin(angle), math.cos(angle))
        cmds.select(clear=True)
        skirt = cmds.joint(name="skirt{}".format(index))
        cmds.parent(skirt, pelvis, relative=True)
        cmds.setAttr(skirt + ".translate", RADIUS * out[0], 0, RADIUS * out[1])
        tip = cmds.joint(name="skirtTip{}".format(index))
        cmds.setAttr(tip + ".translate", TIP[0] * out[0], TIP[1], TIP[0] * out[1])
        skirt = cmds.ls(skirt, long=True)[0]
        for role, parent, group in (("panel", skirt, "green"), ("ghost", pelvis, "ghost")):
            panel = cmds.polyCube(name="skirt{}_{}_GEO".format(index, role), width=1.75, height=length,
                                  depth=0.08)[0]
            cmds.xform(panel, worldSpace=True, translation=cmds.xform(skirt, query=True, worldSpace=True,
                                                                         translation=True))
            cmds.move(0, -length / 2.0, 0, panel + ".vtx[*]", relative=True, objectSpace=True)
            cmds.delete(cmds.aimConstraint(tip, panel, aimVector=(0, -1, 0), upVector=(0, 0, 1),
                                           worldUpType="vector", worldUpVector=(out[0], 0, out[1])))
            cmds.parent(panel, parent)
            cmds.sets(panel, edit=True, forceElement=groups[group])
        skirts.append(skirt)
    graph = SkirtLegOffset.create(pelvis, skirts, legs, name="skirtLegOffset", clearance=CLEARANCE,
                                  maxAngle=MAX_ANGLE, spread=SPREAD, connect=True)
    inverse = _matrix(pelvis).inverse()
    rest = []
    for skirt in skirts:
        local = _matrix(skirt) * inverse
        tip = _matrix(skirt + "|" + skirt.rsplit("|", 1)[-1].replace("skirt", "skirtTip")) * inverse
        rest.append((local, _position(local), _position(tip)))
    camera, camera_shape = cmds.camera(name="skirtLegCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(27, 7.5, 10), lookAt=(0, 5.6, 1.8))
    window = cmds.window("skirtLegValidationWindow", title="SkirtLegOffset - skirt and legs", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("skirtLegValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=True,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("skirtLeg", 7)
    scene = {"owner": str(graph.container), "pelvis": pelvis, "legs": legs, "hips": hips, "skirts": skirts,
             "rest": rest}
    return panel, scene, values, names


def _matrix(node):
    """ノードのワールド行列。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    return om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _position(matrix):
    """行列の位置。"""
    from maya.api import OpenMaya as om
    return om.MVector(matrix[12], matrix[13], matrix[14])


def expected(scene):
    """骨ごとの開く角度・面へ写した脚と骨の角度を、atan2・asinで独立に求める。"""
    inverse = _matrix(scene["pelvis"]).inverse()
    directions = []
    for hip, knee in scene["legs"]:
        directions.append(_position(_matrix(knee) * inverse) - _position(_matrix(hip) * inverse))
    angles = []
    for local, position, tip in scene["rest"]:
        s = (tip - position).normal()
        t = (s ^ position).normal()
        n = t ^ s
        best = 0.0
        for leg in directions:
            plane = math.degrees(math.atan2(leg * n, leg * s))
            lateral = math.degrees(math.asin(max(-1.0, min(1.0, (leg * t) / leg.length()))))
            falloff = min(max(1.0 - abs(lateral) / SPREAD, 0.0), 1.0)
            best = max(best, min(max((plane + CLEARANCE) * falloff, 0.0), MAX_ANGLE))
        angles.append(best)
    return angles, directions


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、開く角度と骨のワールド行列を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    (leftX, leftZ, rightX), stage = pose(frame)
    cmds.setAttr(scene["hips"][0] + ".rotate", leftX, 0, leftZ)
    cmds.setAttr(scene["hips"][1] + ".rotate", rightX, 0, 0)
    owner = scene["owner"]
    actual = [cmds.getAttr("{}.angle{}".format(owner, i)) for i in range(COUNT)]
    angles, directions = expected(scene)
    angle_error = max(abs(a - b) for a, b in zip(actual, angles))
    world = _matrix(scene["pelvis"])
    matrix_error = 0.0
    for index, (local, position, tip) in enumerate(scene["rest"]):
        s = (tip - position).normal()
        t = (s ^ position).normal()
        move = om.MTransformationMatrix()
        move.setTranslation(-position, om.MSpace.kTransform)
        back = om.MTransformationMatrix()
        back.setTranslation(position, om.MSpace.kTransform)
        target = local * move.asMatrix() * om.MQuaternion(math.radians(angles[index]), t).asMatrix() \
            * back.asMatrix() * world
        matrix_error = max(matrix_error, max(abs(a - b) for a, b in zip(_matrix(scene["skirts"][index]), target)))
    # 左前の骨(0番)と左脚の、骨の開く面での角度(開いた後の骨から脚まで)。押されている間は clearance になる。
    local, position, tip = scene["rest"][0]
    s = (tip - position).normal()
    t = (s ^ position).normal()
    n = t ^ s
    leg = directions[0]
    gap = math.degrees(math.atan2(leg * n, leg * s)) - angles[0]
    values[:] = [
        "RED = legs (input)   GREEN = skirt bones with offset (output)   GRAY = skirt at rest (reference)",
        "STAGE: " + stage,
        "fixed: clearance = {:.0f} deg   maxAngle = {:.0f} deg   spread = {:.0f} deg   8 bones, front = 0, left = 2".format(
            CLEARANCE, MAX_ANGLE, SPREAD),
        "push = clamp((planeAngle + clearance) * clamp(1 - |lateralAngle| / spread), 0, maxAngle)   angle_i = max over legs",
        "INPUT left hip rotX = {:7.2f}  rotZ = {:6.2f}   right hip rotX = {:7.2f} deg".format(leftX, leftZ, rightX),
        "OUTPUT angle: front {:6.2f}  frontL {:6.2f}  left {:6.2f}  back {:6.2f}  frontR {:6.2f}   front-bone to left-leg {:7.2f} deg".format(
            actual[0], actual[1], actual[2], actual[4], actual[7], gap),
        "CHECK max |angle - formula| = {:.6f} deg   max |bone world matrix - formula| = {:.2e}".format(
            angle_error, matrix_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = angle_error < 1e-3 and matrix_error < 1e-4
    return {"frame": frame, "presentation_stage": stage, "input": {"leftX": leftX, "leftZ": leftZ, "rightX": rightX},
            "angles": actual, "expected": angles, "angle_error": angle_error, "matrix_error": matrix_error,
            "front_gap": gap, "ok": ok}


def main(output_dir=None, finished=None):
    """検証シーンを作って録画し、シーンと最新ポインタを保存する。

    Args:
        output_dir (str | Path | None): 使い捨てGUIランナーの結果フォルダ。
        finished (callable | None): ランナーへ終了を伝える関数。
    """
    from maya import cmds
    sys.path.insert(0, str(ROOT / "tools"))
    from verification_video import recordVideo
    result = {"status": "error"}
    try:
        panel, scene, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("SkirtLegOffset: スカートの脚よけ", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "skirt_leg_offset.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-skirt-leg-offset.json").write_text(
            json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
        failed = [f["frame"] for f in record["frames"] if f.get("ok") is not True]
        result = {"status": "passed" if record["ok"] else "failed", "folder": str(folder), "failed_frames": failed[:50]}
    except BaseException:
        import traceback
        result = {"status": "error", "error": traceback.format_exc()}
    if output_dir is not None:
        Path(output_dir, "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if finished is not None:
        finished(result)
    return result


def launch():
    """使い捨ての隔離Maya 2027 GUIを起動して録画する。作業中のMayaには触れない。"""
    from datetime import datetime
    sys.path.insert(0, str(ROOT / "tools"))
    from run_mlib_gui_versions import run_version
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("skirt-leg-offset-%Y%m%d-%H%M%S")
    environment = {"PYTHONPATH": os.pathsep.join([str(ROOT / "maya/inhouse"), str(ROOT / "tools")])}
    ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
    if ffmpeg:
        environment["MAYA_VERIFICATION_FFMPEG"] = ffmpeg
    install = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Autodesk"
    result = run_version("2027", directory, install, 900, suite_path=Path(__file__).resolve(), environment=environment)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", action="store_true", help="使い捨ての隔離GUIを起動して録画する")
    if parser.parse_args().launch:
        sys.exit(launch())
    main()
