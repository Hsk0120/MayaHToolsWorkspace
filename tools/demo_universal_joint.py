"""UniversalJointの単独の継手の揺れと、二重継手の等速を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_universal_joint.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
# (曲げ角β[度], 次の姿勢へ向かう段階名)。入力軸は-X側から原点の継手へ、中間軸は原点から上へβだけ曲げ、
# 出力軸は中間軸の先から+Xへ(入力と平行、Z配置)。
POSES = [
    (0.0, "1 STRAIGHT: ALL SHAFTS TURN TOGETHER"),
    (0.0, "2 BEND TO 45 DEG: MIDDLE SHAFT SPEEDS UP AND SLOWS DOWN"),
    (45.0, "3 HOLD 45 DEG"),
    (45.0, "4 BEND TO 80 DEG: CLOSE TO LOCK (90 DEG)"),
    (80.0, "5 HOLD 80 DEG: STRONG RIPPLE, OUTPUT STILL CONSTANT"),
    (80.0, "6 BACK TO A SAFE 30 DEG"),
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
    """parentの下へ、X方向に start から LENGTH の軸と、+Y側の目印の板(ピンの向き)を作る。"""
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


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import UniversalJoint
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    shaft = cmds.createNode("transform", name="inputShaft_JNT")
    middleEnd = cmds.createNode("transform", name="middleEnd_LOC")
    cmds.setAttr(middleEnd + ".translateX", LENGTH)
    first = UniversalJoint.create(shaft, middleEnd, name="joint1", atTarget=True)
    middle = cmds.createNode("transform", name="middleShaft_OUT")
    first.container.getPlug("matrix").connectTo(middle + ".offsetParentMatrix")
    outputEnd = cmds.createNode("transform", name="outputEnd_LOC", parent=middleEnd)
    cmds.setAttr(outputEnd + ".translateX", LENGTH)
    second = UniversalJoint.create(middle, outputEnd, name="joint2", pinAxis="z")
    output = cmds.createNode("transform", name="outputShaft_OUT")
    second.container.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    red = _shader("inputRed", (0.9, 0.15, 0.1))
    blue = _shader("middleBlue", (0.2, 0.45, 0.95))
    green = _shader("outputGreen", (0.15, 0.85, 0.25))
    white = _shader("flagWhite", (0.95, 0.95, 0.9))
    yellow = _shader("crossYellow", (0.95, 0.8, 0.1))
    _shaft("input", shaft, -LENGTH, red, white)
    _shaft("middle", middle, -LENGTH, blue, white)
    _shaft("output", output, 0.0, green, white)
    for name, parent in (("cross1", shaft), ("cross2", middleEnd)):
        ball = cmds.polySphere(name=name + "_GEO", radius=0.45)[0]
        cmds.parent(ball, parent, relative=True)
        cmds.sets(ball, edit=True, forceElement=yellow)
    camera, camera_shape = cmds.camera(name="universalJointCamera", focalLength=35)
    # 斜め前から。曲げ平面(XY)と、軸まわりの目印の回転の両方が見えるようにし、左下のHUDと重ならないよう右上へ寄せる。
    cmds.viewPlace(camera_shape, eye=(-6.8, 5.2, 39.0), lookAt=(-2.3, -0.7, 0.0))
    window = cmds.window("universalJointValidationWindow", title="UniversalJoint - single and double cardan",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("universalJointValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["universalJointHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"joint1": str(first.container), "joint2": str(second.container), "shaft": shaft,
             "middleEnd": middleEnd, "middle": middle, "output": output}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた式と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import UniversalJoint
    bend, spin, stage = pose(frame)
    radians = math.radians(bend)
    cmds.setAttr(scene["middleEnd"] + ".translate", LENGTH * math.cos(radians), LENGTH * math.sin(radians), 0)
    cmds.setAttr(scene["shaft"] + ".rotateX", spin)
    middle = om.MMatrix(cmds.getAttr(scene["middle"] + ".worldMatrix[0]"))
    output = om.MMatrix(cmds.getAttr(scene["output"] + ".worldMatrix[0]"))
    pin = om.MVector(middle[4], middle[5], middle[6]).normal()
    in_plane = om.MVector(-math.sin(radians), math.cos(radians), 0)
    middle_angle = math.degrees(math.atan2(pin.z, pin * in_plane))
    out_pin = om.MVector(output[4], output[5], output[6]).normal()
    output_angle = math.degrees(math.atan2(out_pin.z, out_pin.y))
    expected_middle = UniversalJoint.outputAngle(wrap(spin), bend)
    middle_error = abs(wrap(middle_angle - expected_middle))
    output_error = abs(wrap(output_angle - spin))
    owner = scene["joint1"]
    dg_bend = cmds.getAttr(owner + ".bendAngle")
    ratio = cmds.getAttr(owner + ".speedRatio")
    expected_ratio = UniversalJoint.speedRatio(wrap(spin), bend)
    cosine = math.cos(radians)
    values[:] = [
        "RED = input shaft   BLUE = middle shaft (after 1 joint)   GREEN = output shaft (after 2 joints)   WHITE = marker",
        "STAGE: " + stage,
        "input spin = {:.0f} deg / frame (fixed)   shaft length = {:.0f} cm (fixed)   2nd joint pinAxis = z (in phase)".format(
            SPIN_PER_FRAME, LENGTH),
        "tan g2 = tan g1 / cos b     speedRatio = cos b / (1 - sin^2 b cos^2 g1)   range cos b .. 1/cos b",
        "INPUT g1 = {:7.1f} deg   bend b = {:5.1f} deg (DG {:5.1f})   cos b = {:5.3f}".format(
            wrap(spin), bend, dg_bend, cosine),
        "MIDDLE g2 = {:7.1f} deg (formula {:7.1f})   lag g2 - g1 = {:6.1f} deg   speedRatio = {:5.2f} (formula {:5.2f})".format(
            middle_angle, expected_middle, wrap(middle_angle - spin), ratio, expected_ratio),
        "OUTPUT after 2 joints = {:7.1f} deg   output - input = {:6.3f} deg  (constant velocity)".format(
            output_angle, wrap(output_angle - spin)),
        "CHECK |g2 - formula| = {:.5f} deg   |output - input| = {:.5f} deg   |ratio - formula| = {:.6f}".format(
            middle_error, output_error, abs(ratio - expected_ratio)),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (middle_error < 1e-3 and output_error < 1e-3 and abs(dg_bend - bend) < 1e-3
          and abs(ratio - expected_ratio) < 1e-4 * max(1.0, expected_ratio))
    return {"frame": frame, "presentation_stage": stage, "input": {"bend": bend, "spin": wrap(spin)},
            "middle_angle": middle_angle, "expected_middle": expected_middle, "output_angle": output_angle,
            "bend_angle": dg_bend, "speed_ratio": ratio, "expected_ratio": expected_ratio,
            "middle_error": middle_error, "output_error": output_error, "ok": ok}


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
        folder = recordVideo("UniversalJoint: 単独の継手の揺れと二重継手の等速", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "universal_joint.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-universal-joint.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("universal-joint-%Y%m%d-%H%M%S")
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
