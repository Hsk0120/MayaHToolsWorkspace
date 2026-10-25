"""TwistLimitの非対称なTwist制限を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_twist_limit.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINIMUM = -30.0
MAXIMUM = 70.0
SOFTNESS = 0.3
LENGTH = 10.0
DIAL_X = 1.0
DIAL_RADIUS = 3.2
SEGMENT = 36
# (入力のTwist[度], 曲げる向きφ[度、0=+Y側・90=+Z側], 入力の曲げ角θ[度], 段階名)
POSES = [
    (0, 0, 0, "1 REST"),
    (0, 0, 0, "2 TWIST + INSIDE RANGE"),
    (40, 0, 0, "3 TWIST + PAST MAXIMUM"),
    (150, 0, 0, "4 HOLD PAST MAXIMUM"),
    (150, 0, 0, "5 RETURN TO SAFE RANGE"),
    (10, 0, 0, "6 TWIST - INSIDE RANGE"),
    (-10, 0, 0, "7 TWIST - PAST MINIMUM"),
    (-130, 0, 0, "8 HOLD PAST MINIMUM"),
    (-130, 0, 0, "9 RETURN TO SAFE RANGE"),
    (0, 0, 0, "10 BEND: SWING IS NOT LIMITED"),
    (0, 90, 45, "11 TWIST WHILE BENT"),
    (120, 90, 45, "11 TWIST WHILE BENT"),
    (-100, 90, 45, "12 RETURN TO REST"),
    (0, 90, 0, "12 RETURN TO REST"),
    (0, 90, 0, "12 RETURN TO REST"),
]


def pose(frame):
    """フレームの入力(twist, φ, θ, 段階名)をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:3], POSES[index + 1][:3])]
    return values + [POSES[index][3]]


def swingQuaternion(phi, theta):
    """+X軸をφの向きへθだけ曲げるSwing。"""
    from maya.api import OpenMaya as om
    axis = om.MVector(0, -math.sin(math.radians(phi)), math.cos(math.radians(phi)))
    return om.MQuaternion(math.radians(theta), axis)


def twistQuaternion(twist):
    """+X軸まわりのTwist。"""
    from maya.api import OpenMaya as om
    return om.MQuaternion(math.radians(twist), om.MVector(1, 0, 0))


def _shader(name, color):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _bone(name, parent, group, radius, needle):
    """+X方向へ長さLENGTHの棒と、Twistを示す+Y向きの針をparent下に作る。"""
    from maya import cmds
    rod = cmds.polyCylinder(name=name + "_rod", axis=(1, 0, 0), height=LENGTH, radius=radius, subdivisionsX=16)[0]
    tip = cmds.polySphere(name=name + "_tip", radius=radius * 2.2)[0]
    cmds.setAttr(rod + ".tx", LENGTH / 2)
    cmds.setAttr(tip + ".tx", LENGTH)
    # 文字盤の位置で+Y方向へ伸びる針。Twistの角度を文字盤で読めるようにする。
    pointer = cmds.polyCube(name=name + "_needle", width=needle, height=DIAL_RADIUS, depth=needle)[0]
    cmds.setAttr(pointer + ".translate", DIAL_X, DIAL_RADIUS / 2, 0)
    knob = cmds.polySphere(name=name + "_needleTip", radius=needle * 1.6)[0]
    cmds.setAttr(knob + ".translate", DIAL_X, DIAL_RADIUS, 0)
    for node in (rod, tip, pointer, knob):
        cmds.parent(node, parent, relative=True)
        cmds.sets(node, edit=True, forceElement=group)


def _curve(name, points, color, closed=False, width=2.5):
    """表示色付きのNURBS曲線を作る。"""
    from maya import cmds
    if closed:
        points = points + points[:1]
    curve = cmds.curve(name=name, degree=1, point=points)
    shape = cmds.listRelatives(curve, shapes=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideColor", color)
    cmds.setAttr(shape + ".lineWidth", width)
    return curve


def _dial(angle, radius=DIAL_RADIUS):
    """文字盤上のTwist角(度)の点。+Yが0度、+Zが+90度。"""
    a = math.radians(angle)
    return (DIAL_X, radius * math.cos(a), radius * math.sin(a))


def buildScene():
    """検証シーンを作り、(panel, 入力joint, 出力joint, container, HUD値リスト, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import TwistLimit
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    root = cmds.createNode("transform", name="forearm_GRP")
    source = cmds.createNode("joint", name="input_JNT", parent=root)
    output = cmds.createNode("joint", name="limited_JNT", parent=root)
    graph = TwistLimit.create(source, name="forearmTwistLimit", axis="x",
                              minimum=MINIMUM, maximum=MAXIMUM, softness=SOFTNESS)
    owner = graph.container
    owner.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    _bone("input", source, _shader("inputRed", (0.9, 0.12, 0.1)), 0.12, 0.12)
    _bone("limited", output, _shader("limitedGreen", (0.1, 0.85, 0.2)), 0.22, 0.24)
    width = TwistLimit.softWidth(MINIMUM, MAXIMUM, SOFTNESS)
    _curve("dial_CRV", [_dial(a) for a in range(0, 360, 6)], 1, closed=True, width=1.5)
    _curve("allowedArc_CRV", [_dial(a, DIAL_RADIUS * 1.08) for a in range(int(MINIMUM), int(MAXIMUM) + 1, 2)], 17,
           width=4)
    for label, angle, color in (("max", MAXIMUM, 17), ("min", MINIMUM, 17),
                                ("softMax", MAXIMUM - width, 3), ("softMin", MINIMUM + width, 3)):
        _curve(label + "Ray_CRV", [(DIAL_X, 0, 0), _dial(angle, DIAL_RADIUS * 1.25)], color, width=3)
    _curve("restAxis_CRV", [(0, 0, 0), (LENGTH * 1.15, 0, 0)], 2)
    for label, angle in (("max +70", MAXIMUM), ("min -30", MINIMUM), ("0", 0)):
        text = cmds.annotate(root, text=label, point=_dial(angle, DIAL_RADIUS * 1.45))
        cmds.setAttr(cmds.listRelatives(text, parent=True)[0] + ".displayArrow", False)
    camera, camera_shape = cmds.camera(name="twistLimitCamera", focalLength=30)
    # 骨の後ろ(-X側)から長手軸に沿って見て、文字盤を正面に近い向きで映す。
    cmds.viewPlace(camera_shape, eye=(-13, 3.0, 3.5), lookAt=(1, 0.6, 0.6))
    # 左側のHUD文字と重ならないよう、画面上で文字盤を右へ寄せる。
    cmds.setAttr(camera_shape + ".horizontalFilmOffset", -0.36)
    cmds.setAttr(camera_shape + ".verticalFilmOffset", -0.02)
    window = cmds.window("twistLimitValidationWindow", title="TwistLimit - asymmetric twist range",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("twistLimitValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=True,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 7
    names = ["twistLimitHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, source, output, owner, values, names


def evaluate_frame(frame, source, output, owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import TwistLimit
    twist, phi, theta, stage = pose(frame)
    swing = swingQuaternion(phi, theta)
    euler = (twistQuaternion(twist) * swing).asEulerRotation()
    cmds.setAttr(source + ".rotate", *[math.degrees(v) for v in euler])
    dg_twist = owner.getPlug("twist").get()
    limited = owner.getPlug("limitedTwist").get()
    excess = owner.getPlug("excessTwist").get()
    expected_limited = TwistLimit.softTwist(twist, MINIMUM, MAXIMUM, SOFTNESS)
    width = TwistLimit.softWidth(MINIMUM, MAXIMUM, SOFTNESS)
    expected = (twistQuaternion(expected_limited) * swing).asMatrix()
    actual = om.MMatrix(cmds.getAttr(output + ".worldMatrix[0]"))
    matrix_error = max(abs(actual.getElement(r, c) - expected.getElement(r, c)) for r in range(3) for c in range(3))
    if twist > MAXIMUM - width + 1e-6:
        state = "SOFT ZONE (max side) -> approaches max, never exceeds"
    elif twist < MINIMUM + width - 1e-6:
        state = "SOFT ZONE (min side) -> approaches min, never exceeds"
    else:
        state = "INSIDE (output = input)"
    values[:] = [
        "RED = input  GREEN = limited output  YELLOW = range min..max  GREY = soft start",
        "STAGE: " + stage,
        "fixed: min = -30 deg  max = +70 deg  softness = 0.3  w = 0.3*(max-min)/2 = {:.1f} deg".format(width),
        "hi = max - w = {:.1f}   lo = min + w = {:.1f}   twist angle about bone X, 0 = rest (+Y)".format(
            MAXIMUM - width, MINIMUM + width),
        "t' = hi + w(1-exp(-(t-hi)/w)) if t > hi;  lo - w(1-exp(-(lo-t)/w)) if t < lo;  else t",
        "INPUT twist t = {:+7.2f} deg   input bend = {:5.1f} deg (swing not limited)".format(dg_twist, theta),
        "OUTPUT t' = {:+7.2f} deg   excess t - t' = {:+7.2f} deg   {}".format(limited, excess, state),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (abs(dg_twist - twist) < 0.02 and abs(limited - expected_limited) < 0.02
          and abs(excess - (twist - expected_limited)) < 0.03 and matrix_error < 1e-3
          and MINIMUM - 1e-4 <= limited <= MAXIMUM + 1e-4)
    return {"frame": frame, "presentation_stage": stage, "input_twist_degrees": twist, "phi_degrees": phi,
            "input_bend_degrees": theta, "dg_twist": dg_twist, "dg_limited_twist": limited,
            "dg_excess_twist": excess, "expected_limited_twist": expected_limited,
            "matrix_error": matrix_error, "ok": ok}


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
        panel, source, output, owner, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("TwistLimit: 非対称なTwistのソフト制限", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, source, output, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "twist-limit.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-twist-limit.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("twist-limit-%Y%m%d-%H%M%S")
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
