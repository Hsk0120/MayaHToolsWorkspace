"""ConstantVelocityJointの等速と、同じ曲げ角の十字軸継手(UniversalJoint)の揺れを専用Maya GUIで並べて録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_constant_velocity_joint.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LENGTH = 6.0
SPIN_PER_FRAME = 6.0
SEGMENT = 48
# 十字軸継手の組を等速ジョイントの組の下へ置く距離(cm)。
LOWER = -11.0
BALLS = 6
# (曲げ角β[度], 次の姿勢へ向かう段階名)。入力軸は-X側から継手へ、出力軸は継手から上へβだけ曲げる。
POSES = [
    (0.0, "1 STRAIGHT: BOTH OUTPUTS TURN WITH THE INPUT"),
    (0.0, "2 BEND TO 45 DEG: CV STAYS IN STEP, CARDAN SPEEDS UP AND SLOWS DOWN"),
    (45.0, "3 HOLD 45 DEG (TYPICAL CV LIMIT)"),
    (45.0, "4 BEND TO 70 DEG: BEYOND A REAL CV JOINT, MATH STILL CONSTANT"),
    (70.0, "5 HOLD 70 DEG: CAGE TILTS 35 DEG"),
    (70.0, "6 BACK TO A SAFE 30 DEG"),
    (30.0, "7 HOLD 30 DEG"),
    (30.0, "8 BACK TO STRAIGHT"),
    (0.0, "9 BACK AT REST"),
    (0.0, "9 BACK AT REST"),
]


def pose(frame):
    """フレームの曲げ角と段階名をsmoothstepで補間し、入力の回転角(度)と共に返す。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    start, end = POSES[index][0], POSES[index + 1][0]
    return start + (end - start) * weight, frame * SPIN_PER_FRAME, POSES[index][1]


def wrap(angle):
    """角度を-180〜180度へ丸める。"""
    return (angle + 180.0) % 360.0 - 180.0


def _shader(name, color):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _shaft(name, parent, start, shader, flag):
    """parentの下へ、X方向に start から LENGTH の軸と、+Y側の目印の板を作る。"""
    from maya import cmds
    rod = cmds.polyCylinder(name=name + "_GEO", radius=0.25, height=LENGTH, axis=(1, 0, 0))[0]
    cmds.parent(rod, parent, relative=True)
    cmds.setAttr(rod + ".translateX", start + LENGTH * 0.5)
    cmds.sets(rod, edit=True, forceElement=shader)
    mark = cmds.polyCube(name=name + "Flag_GEO", width=1.2, height=1.4, depth=0.12)[0]
    cmds.parent(mark, parent, relative=True)
    cmds.setAttr(mark + ".translate", start + LENGTH * 0.5, 0.95, 0)
    cmds.sets(mark, edit=True, forceElement=flag)
    return rod


def _assembly(prefix, offset, kind, shaders):
    """offsetの高さに入力軸・先の点・継手・出力軸を作り、(入力軸, 先の点, 出力, container名, ケージ)を返す。"""
    from maya import cmds
    from mlrig.setups import ConstantVelocityJoint, UniversalJoint
    red, color, white, yellow = shaders
    shaft = cmds.createNode("transform", name=prefix + "InputShaft_JNT")
    cmds.setAttr(shaft + ".translateY", offset)
    target = cmds.createNode("transform", name=prefix + "Target_LOC")
    if kind == "cv":
        setup = ConstantVelocityJoint.create(shaft, target, name=prefix + "Joint")
    else:
        setup = UniversalJoint.create(shaft, target, name=prefix + "Joint")
    output = cmds.createNode("transform", name=prefix + "OutputShaft_OUT")
    setup.container.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    _shaft(prefix + "Input", shaft, -LENGTH, red, white)
    _shaft(prefix + "Output", output, 0.0, color, white)
    cage = None
    if kind == "cv":
        cage = cmds.createNode("transform", name=prefix + "Cage_OUT")
        setup.container.getPlug("cageMatrix").connectTo(cage + ".offsetParentMatrix")
        ring = cmds.polyTorus(name=prefix + "Cage_GEO", radius=1.0, sectionRadius=0.08, subdivisionsAxis=32,
                              subdivisionsHeight=8, axis=(1, 0, 0))[0]
        cmds.parent(ring, cage, relative=True)
        cmds.sets(ring, edit=True, forceElement=yellow)
        for index in range(BALLS):
            angle = 2.0 * math.pi * index / BALLS
            ball = cmds.polySphere(name="{}Ball{}_GEO".format(prefix, index), radius=0.28)[0]
            cmds.parent(ball, cage, relative=True)
            cmds.setAttr(ball + ".translate", 0, math.cos(angle), math.sin(angle))
            cmds.sets(ball, edit=True, forceElement=yellow)
    else:
        ball = cmds.polySphere(name=prefix + "Cross_GEO", radius=0.45)[0]
        cmds.parent(ball, shaft, relative=True)
        cmds.sets(ball, edit=True, forceElement=yellow)
    return shaft, target, output, str(setup.container), cage


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    red = _shader("inputRed", (0.9, 0.15, 0.1))
    blue = _shader("cardanBlue", (0.2, 0.45, 0.95))
    green = _shader("cvGreen", (0.15, 0.85, 0.25))
    white = _shader("flagWhite", (0.95, 0.95, 0.9))
    yellow = _shader("cageYellow", (0.95, 0.8, 0.1))
    cv = _assembly("cv", 0.0, "cv", (red, green, white, yellow))
    uj = _assembly("uj", LOWER, "uj", (red, blue, white, yellow))
    camera, camera_shape = cmds.camera(name="constantVelocityJointCamera", focalLength=35)
    # 斜め前から。曲げ平面(XY)と軸まわりの目印の回転が見えるようにし、左側のHUDと重ならないよう右へ寄せる。
    cmds.viewPlace(camera_shape, eye=(-9.0, 4.0, 46.0), lookAt=(-4.0, -3.0, 0.0))
    window = cmds.window("constantVelocityJointValidationWindow", title="ConstantVelocityJoint - CV and cardan",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("constantVelocityJointValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 8
    names = ["constantVelocityJointHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"cvShaft": cv[0], "cvTarget": cv[1], "cvOutput": cv[2], "cvJoint": cv[3], "cvCage": cv[4],
             "ujShaft": uj[0], "ujTarget": uj[1], "ujOutput": uj[2], "ujJoint": uj[3]}
    return panel, scene, values, names


def _spin(matrix, radians):
    """出力の目印(Y行)の角度を、曲げ平面内の基準の向きから出力軸まわりに測る(度)。"""
    from maya.api import OpenMaya as om
    pin = om.MVector(matrix[4], matrix[5], matrix[6]).normal()
    in_plane = om.MVector(-math.sin(radians), math.cos(radians), 0)
    return math.degrees(math.atan2(pin.z, pin * in_plane))


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた式と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import UniversalJoint
    bend, spin, stage = pose(frame)
    radians = math.radians(bend)
    for prefix, offset in (("cv", 0.0), ("uj", LOWER)):
        cmds.setAttr(scene[prefix + "Target"] + ".translate", LENGTH * math.cos(radians),
                     offset + LENGTH * math.sin(radians), 0)
        cmds.setAttr(scene[prefix + "Shaft"] + ".rotateX", spin)
    cv_matrix = om.MMatrix(cmds.getAttr(scene["cvOutput"] + ".worldMatrix[0]"))
    uj_matrix = om.MMatrix(cmds.getAttr(scene["ujOutput"] + ".worldMatrix[0]"))
    cage = om.MMatrix(cmds.getAttr(scene["cvCage"] + ".worldMatrix[0]"))
    shaft = om.MMatrix(cmds.getAttr(scene["cvShaft"] + ".worldMatrix[0]"))
    cv_angle = _spin(cv_matrix, radians)
    uj_angle = _spin(uj_matrix, radians)
    cage_axis = om.MVector(cage[0], cage[1], cage[2]).normal()
    input_axis = om.MVector(shaft[0], shaft[1], shaft[2]).normal()
    cage_tilt = math.degrees(math.acos(max(-1.0, min(1.0, cage_axis * input_axis))))
    dg_bend = cmds.getAttr(scene["cvJoint"] + ".bendAngle")
    expected_uj = UniversalJoint.outputAngle(wrap(spin), bend)
    cv_error = abs(wrap(cv_angle - spin))
    uj_error = abs(wrap(uj_angle - expected_uj))
    cage_error = abs(cage_tilt - bend * 0.5)
    values[:] = [
        "TOP: RED input -> GREEN constant velocity joint (YELLOW = cage, 6 balls)   BOTTOM: RED input -> BLUE cardan",
        "STAGE: " + stage,
        "input spin = {:.0f} deg / frame (fixed)   shaft length = {:.0f} cm (fixed)   WHITE flags show the spin".format(
            SPIN_PER_FRAME, LENGTH),
        "CV: matrix = R x Q(u->v)   cage = R x Q(u->h), h = normalize(u + v)   cardan: tan g2 = tan g1 / cos b",
        "INPUT g1 = {:7.1f} deg   bend b = {:5.1f} deg (DG bendAngle {:5.1f})   cage tilt = {:5.2f} deg (b/2 = {:5.2f})".format(
            wrap(spin), bend, dg_bend, cage_tilt, bend * 0.5),
        "GREEN CV output = {:7.1f} deg   CV - input = {:7.3f} deg   (constant velocity)".format(
            cv_angle, wrap(cv_angle - spin)),
        "BLUE cardan output = {:7.1f} deg (formula {:7.1f})   cardan - input = {:6.1f} deg  (ripples)".format(
            uj_angle, expected_uj, wrap(uj_angle - spin)),
        "CHECK |CV - input| = {:.5f} deg   |cage tilt - b/2| = {:.5f} deg   |cardan - formula| = {:.5f} deg".format(
            cv_error, cage_error, uj_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = cv_error < 1e-3 and cage_error < 1e-3 and uj_error < 1e-3 and abs(dg_bend - bend) < 1e-3
    return {"frame": frame, "presentation_stage": stage, "input": {"bend": bend, "spin": wrap(spin)},
            "cv_angle": cv_angle, "cardan_angle": uj_angle, "expected_cardan": expected_uj, "cage_tilt": cage_tilt,
            "bend_angle": dg_bend, "cv_error": cv_error, "cage_error": cage_error, "cardan_error": uj_error,
            "ok": ok}


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
        folder = recordVideo("ConstantVelocityJoint: 等速ジョイントと十字軸継手の比較", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "constant_velocity_joint.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-constant-velocity-joint.json").write_text(
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
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maya/inhouse/mlib/__tests__"))
    from runGui import run_version
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("constant-velocity-joint-%Y%m%d-%H%M%S")
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
