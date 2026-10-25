"""膝が横にずれた脚で、HingeIK・PlanarIKの膝が1軸で曲がることを専用Maya GUIで録画する検証デモ。

赤は普通のRotate Plane IK(比較用)、緑は ``mlrig.setups.HingeIK`` 、青は ``mlrig.setups.PlanarIK`` 。
3本の脚は同じ形(付け根・膝・足首が一平面に並ばない)で、足首の目標を同じように動かす。
膝の黄色い線は膝のヒンジ軸(ローカルZ)で、赤は膝が多軸で回るため線が振れる。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_offset_leg_ik.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
SPACING = 9.0
#: 付け根・膝・足首(と青の途中のずれた骨)の位置。膝が横(+X)へずれていて、3点は一平面に並ばない。
HIP, THIGH_OFFSET, KNEE, SHIN_OFFSET, ANKLE = (0, 10, 0), (1.6, 7.6, 0.6), (1.2, 5, 1.0), (1.7, 2.6, 1.3), (0, 0, 0.5)
# (足首の目標の移動量, ポールベクターの回転[度。付け根→足首の軸まわり], 段階名)
POSES = [
    ((0, 0, 0), 0, "1 REST"),
    ((0, 2, 2), 0, "2 FOOT FORWARD"),
    ((2, 3, 1), 0, "3 FOOT OUT"),
    ((-1.5, 3, 1), 0, "4 FOOT IN"),
    ((1, 4, -2), 0, "5 KNEE UP, FOOT BACK"),
    ((-2, 2, -1), 0, "6 FOOT IN AND BACK"),
    ((0, 3, 1.5), 0, "7 SWING POLE (KNEE DIRECTION)"),
    ((0, 3, 1.5), 40, "7 SWING POLE (KNEE DIRECTION)"),
    ((0, 3, 1.5), -40, "7 SWING POLE (KNEE DIRECTION)"),
    ((0, 3, 1.5), 0, "8 RETURN TO REST"),
    ((0, 0, 0), 0, "8 RETURN TO REST"),
]


def _shader(name, color):
    """単色のsurfaceShaderを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("surfaceShader", asShader=True, name=name)
    cmds.setAttr(shader + ".outColor", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _bone(name, start, end, shading, radius):
    """2つのjointの間に骨の形のメッシュを作り、startの子にする。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    a = om.MVector(cmds.xform(start, query=True, worldSpace=True, translation=True))
    b = om.MVector(cmds.xform(end, query=True, worldSpace=True, translation=True))
    mesh = cmds.polyCylinder(name=name, radius=radius, height=(b - a).length(), subdivisionsAxis=8,
                             constructionHistory=False)[0]
    middle = (a + b) * 0.5
    rotation = om.MQuaternion(om.MVector(0, 1, 0), (b - a).normal()).asEulerRotation()
    cmds.xform(mesh, worldSpace=True, translation=(middle.x, middle.y, middle.z),
               rotation=[math.degrees(v) for v in (rotation.x, rotation.y, rotation.z)])
    cmds.sets(mesh, edit=True, forceElement=shading)
    cmds.parent(mesh, start)
    return mesh


def _axisLine(name, joint, color):
    """jointのローカルZ(膝のヒンジ軸)に沿った短い線をjointの子に作る。"""
    from maya import cmds
    curve = cmds.curve(name=name, degree=1, point=[(0, 0, -1.6), (0, 0, 1.6)])
    shape = cmds.listRelatives(curve, shapes=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideRGBColors", True)
    cmds.setAttr(shape + ".overrideColorRGB", *color)
    cmds.setAttr(shape + ".lineWidth", 4)
    cmds.parent(curve, joint, relative=True)
    return curve


def _leg(prefix, offset, offsets=False):
    """1本の脚のjointを作る。offsets=Trueなら途中にずれた骨を挟む(PlanarIK用)。"""
    from maya import cmds
    cmds.select(clear=True)
    points = [HIP, THIGH_OFFSET, KNEE, SHIN_OFFSET, ANKLE] if offsets else [HIP, KNEE, ANKLE]
    names = ["hip", "thighOffset", "knee", "shinOffset", "ankle"] if offsets else ["hip", "knee", "ankle"]
    joints = [cmds.joint(name="{}_{}".format(prefix, n), position=(p[0] + offset, p[1], p[2]), radius=0.4)
              for n, p in zip(names, points)]
    cmds.joint(joints[0], edit=True, orientJoint="xyz", secondaryAxisOrient="zup", children=True, zeroScaleOrient=True)
    return joints


def buildScene():
    """3本の脚・IK・表示用のメッシュ・カメラ・専用パネル・HUDを作る。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import HingeIK, PlanarIK
    from mlrig.setups.hingeIK import createRotatePlaneHandle

    for panel in ("offsetLegIKPanel",):
        if panel in cmds.getPanel(allPanels=True):
            cmds.deleteUI(panel, panel=True)
    if cmds.window("offsetLegIKWindow", exists=True):
        cmds.deleteUI("offsetLegIKWindow", window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")
    colors = {"red": (1.0, 0.25, 0.2), "green": (0.25, 0.95, 0.35), "blue": (0.3, 0.6, 1.0)}
    shading = {key: _shader(key + "Bone", value) for key, value in colors.items()}
    yellow = (1.0, 0.85, 0.1)

    red = _leg("red", -SPACING)
    green = _leg("green", 0.0)
    blue = _leg("blue", SPACING, offsets=True)
    legs = {"red": red, "green": green, "blue": blue}
    for key, joints in legs.items():
        for index, (a, b) in enumerate(zip(joints, joints[1:])):
            _bone("{}_bone{}".format(key, index), a, b, shading[key], 0.45 if key != "blue" or index % 2 == 0 else 0.3)

    # 赤: 普通のRotate Plane IK(膝の自由度は3軸のまま)。HingeIKと同じポールベクターの置き方。
    cmds.joint(red[0], edit=True, setPreferredAngles=True, children=True)
    red_handle, _, red_pole = createRotatePlaneHandle(red[0], red[2], "redIK")
    hinge = HingeIK.create(green[0], green[1], green[2], name="greenHingeIK")
    planar = PlanarIK.create(blue[0], blue[2], blue[4], name="bluePlanarIK", showDrivers=True)
    for joint in planar.drivers:
        cmds.setAttr(joint + ".radius", 0.25)
    for key, knee in (("red", red[1]), ("green", green[1]), ("blue", planar.drivers[1])):
        _axisLine(key + "_hingeAxis", knee, yellow)

    handles = {"red": (red_handle, red_pole), "green": (hinge.handle, hinge.pole), "blue": (planar.handle, planar.pole)}
    rest = {key: (om.MVector(cmds.xform(h, query=True, worldSpace=True, translation=True)),
                  om.MVector(cmds.xform(p, query=True, worldSpace=True, translation=True)))
            for key, (h, p) in handles.items()}
    cmds.select(clear=True)

    camera, camera_shape = cmds.camera(name="offsetLegCamera", focalLength=40)
    cmds.setAttr(camera + ".translate", 26, 13, 46)
    cmds.setAttr(camera + ".rotate", -8, 30, 0)
    window = cmds.window("offsetLegIKWindow", title="Offset leg IK: knee on one axis", widthHeight=(1280, 760))
    layout = cmds.columnLayout(adjustableColumn=True)
    cmds.text(label="RED = plain RP IK | GREEN = HingeIK | BLUE = PlanarIK | YELLOW = knee hinge axis (local Z)",
              height=28)
    pane = cmds.paneLayout(parent=layout, height=720)
    panel = cmds.modelPanel("offsetLegIKPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=True,
                     selectionHiliteDisplay=False, cameras=False, joints=True, locators=True, ikHandles=False,
                     headsUpDisplay=True, manipulators=False)
    cmds.showWindow(window)
    cmds.setFocus(panel)
    values = [""] * 8
    names = ["offsetLegHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0, block=i, blockSize="small", dataFontSize="large",
                            command=lambda row=i: values[row])
    return panel, legs, planar, handles, rest, hinge, values, names


def pose(frame):
    """フレームの足首の移動量・ポールベクターの回転・段階名を補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    (a, pole_a, _), (b, pole_b, label) = POSES[index], POSES[index + 1]
    move = [x + (y - x) * weight for x, y in zip(a, b)]
    return move, pole_a + (pole_b - pole_a) * weight, POSES[index + 1][2] if weight > 0.5 else POSES[index][2]


def evaluate_frame(frame, legs, planar, handles, rest, hinge, values, names):
    """姿勢を更新し、緑と青の膝が1軸だけで足首が届くことを独立に検査する。"""
    from maya import cmds
    from maya.api import OpenMaya as om

    move, pole_angle, label = pose(frame)
    for key, (handle, pole) in handles.items():
        hip = om.MVector(cmds.xform(legs[key][0], query=True, worldSpace=True, translation=True))
        target = rest[key][0] + om.MVector(*move)
        axis = (target - hip).normal()
        pole_position = hip + (rest[key][1] - hip).rotateBy(om.MQuaternion(math.radians(pole_angle), axis))
        cmds.xform(handle, worldSpace=True, translation=(target.x, target.y, target.z))
        cmds.xform(pole, worldSpace=True, translation=(pole_position.x, pole_position.y, pole_position.z))

    def reach(ankle, handle):
        a = om.MVector(cmds.xform(ankle, query=True, worldSpace=True, translation=True))
        b = om.MVector(cmds.xform(handle, query=True, worldSpace=True, translation=True))
        return (a - b).length()

    red_rotate = cmds.getAttr(legs["red"][1] + ".rotate")[0]
    green_rotate = cmds.getAttr(legs["green"][1] + ".rotate")[0]
    blue_rotate = cmds.getAttr(planar.drivers[1] + ".rotate")[0]
    errors = {"red": reach(legs["red"][2], handles["red"][0]), "green": reach(legs["green"][2], handles["green"][0]),
              "blue": reach(legs["blue"][4], handles["blue"][0])}
    off_axis = {"red": math.hypot(red_rotate[0], red_rotate[1]), "green": math.hypot(green_rotate[0], green_rotate[1]),
                "blue": math.hypot(blue_rotate[0], blue_rotate[1])}
    # 青: 元の膝の生成時からの曲げ(付け根の回転を除いたもの)の軸が、平面の法線と平行か。
    hip_delta = planar_rest["hip"].inverse() * _rotation(legs["blue"][0])
    knee_delta = planar_rest["knee"].inverse() * _rotation(legs["blue"][2])
    axis, angle = (knee_delta * hip_delta.inverse()).asAxisAngle()
    bend_alignment = abs(axis.normal() * planar.normal) if abs(angle) > 1e-3 else 1.0
    n = planar.normal
    values[:] = [
        "PHASE: {}".format(label),
        "knee hinge n = normalize((K - P) x (A - K)) at creation (fixed)",
        "GREEN HingeIK: knee DOF = Z only (jointType z)   n = ({:+.2f}, {:+.2f}, {:+.2f})".format(*hinge.hinge),
        "BLUE PlanarIK: driver chain on plane, bind joints orientConstraint   n = ({:+.2f}, {:+.2f}, {:+.2f})"
        .format(n.x, n.y, n.z),
        "RED   knee rotate  X {:+7.2f}  Y {:+7.2f}  Z {:+7.2f}   ankle error {:.4f} cm".format(*red_rotate, errors["red"]),
        "GREEN knee rotate  X {:+7.2f}  Y {:+7.2f}  Z {:+7.2f}   ankle error {:.4f} cm"
        .format(*green_rotate, errors["green"]),
        "BLUE  driver knee  X {:+7.2f}  Y {:+7.2f}  Z {:+7.2f}   ankle error {:.4f} cm"
        .format(*blue_rotate, errors["blue"]),
        "BLUE  bind knee bend axis . n = {:.5f}  (1 = bends only about n)".format(bend_alignment),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (off_axis["green"] < 1e-3 and off_axis["blue"] < 1e-3 and errors["green"] < 1e-3 and errors["blue"] < 1e-3
          and bend_alignment > 1 - 1e-4)
    return {"frame": frame, "phase": label, "target_move_cm": move, "pole_degrees": pole_angle,
            "red_knee_rotate": red_rotate, "green_knee_rotate": green_rotate, "blue_driver_knee_rotate": blue_rotate,
            "off_axis_degrees": off_axis, "ankle_error_cm": errors, "blue_bend_alignment": bend_alignment, "ok": ok}


planar_rest = {}


def _rotation(node):
    """transformのワールドの回転をQuaternionで返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    matrix = om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))
    return om.MTransformationMatrix(matrix).rotation(asQuaternion=True)


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
        panel, legs, planar, handles, rest, hinge, values, names = buildScene()
        planar_rest.update({"hip": _rotation(legs["blue"][0]), "knee": _rotation(legs["blue"][2])})
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("HingeIK / PlanarIK: 膝が横にずれた脚で膝を1軸に曲げる", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, legs, planar, handles, rest, hinge, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "offset-leg-ik.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-offset-leg-ik.json").write_text(
            json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
        failed = [f["frame"] for f in record["frames"] if f.get("ok") is not True]
        red = max(max(f["off_axis_degrees"]["red"] for f in record["frames"]), 0.0)
        result = {"status": "passed" if record["ok"] else "failed", "folder": str(folder), "failed_frames": failed[:50],
                  "red_max_off_axis_degrees": red}
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
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maya/inhouse/mlib/__tests__"))
    from runGui import run_version
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("offset-leg-ik-%Y%m%d-%H%M%S")
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
