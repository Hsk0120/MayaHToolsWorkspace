"""LimbPin(2関節の長さの slide と、肘を極ベクトルの操作子へ留める pin)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_limb_pin.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 30
#: 上腕・前腕の作成時の長さ(cm)と、作成時の肩・肘の曲げ(度)。
REST = (4.0, 4.0)
BEND = 25.0
# (slide, pin, 操作子X, 操作子Y, 目標X, 目標Y, 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, 0.0, 3.6, 3.0, 7.25, 0.0, "1 REST (PIN 0, SLIDE 0)"),
    (0.0, 0.0, 3.6, 3.0, 7.25, 0.0, "2 SLIDE +0.5 (UPPER ARM LONGER, SAME TOTAL)"),
    (0.5, 0.0, 3.6, 3.0, 7.25, 0.0, "3 SLIDE -0.5 (FOREARM LONGER)"),
    (-0.5, 0.0, 3.6, 3.0, 7.25, 0.0, "4 SLIDE 0 AND PIN ON (ELBOW GOES TO THE POLE)"),
    (0.0, 1.0, 3.6, 3.0, 7.25, 0.0, "5 MOVE THE POLE (ELBOW STAYS ON IT)"),
    (0.0, 1.0, 2.2, 2.0, 7.25, 0.0, "5 MOVE THE POLE (ELBOW STAYS ON IT)"),
    (0.0, 1.0, 5.0, 2.6, 7.25, 0.0, "6 MOVE THE TARGET"),
    (0.0, 1.0, 5.0, 2.6, 8.6, -1.6, "6 MOVE THE TARGET"),
    (0.0, 1.0, 5.0, 2.6, 6.0, 0.8, "7 PIN OFF AND RETURN TO REST"),
    (0.0, 0.0, 3.6, 3.0, 7.25, 0.0, "7 PIN OFF AND RETURN TO REST"),
    (0.0, 0.0, 3.6, 3.0, 7.25, 0.0, "7 PIN OFF AND RETURN TO REST"),
]


def pose(frame):
    """フレームの入力値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:6], POSES[index + 1][:6])]
    return values + [POSES[index][6]]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _ball(name, parent, group, radius):
    """parentの原点に球を置く。"""
    from maya import cmds
    ball = cmds.polySphere(name=name, radius=radius)[0]
    cmds.parent(ball, parent, relative=True)
    cmds.sets(ball, edit=True, forceElement=group)
    return ball


def buildScene():
    """検証シーンを作り、(panel, 腕のjoint, 操作子, 目標, 骨の箱, LimbPin, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import LimbPin
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    yellow = _shader("armYellow", (1.0, 0.85, 0.1))
    blue = _shader("poleBlue", (0.2, 0.45, 1.0))
    orange = _shader("targetOrange", (1.0, 0.45, 0.1))
    white = _shader("jointWhite", (0.9, 0.9, 0.9))
    shoulder = cmds.createNode("joint", name="shoulder_JNT")
    cmds.setAttr(shoulder + ".rotateZ", BEND)
    elbow = cmds.createNode("joint", name="elbow_JNT", parent=shoulder)
    cmds.setAttr(elbow + ".translateX", REST[0])
    cmds.setAttr(elbow + ".rotateZ", -2 * BEND)
    wrist = cmds.createNode("joint", name="wrist_JNT", parent=elbow)
    cmds.setAttr(wrist + ".translateX", REST[1])
    arm = [shoulder, elbow, wrist]
    pole = cmds.createNode("transform", name="pole_CTRL")
    target = cmds.createNode("transform", name="target_CTRL")
    _ball("pole_GEO", pole, blue, 0.42)
    _ball("target_GEO", target, orange, 0.42)
    cmds.setAttr(pole + ".translate", 3.6, 3.0, 0.0)
    cmds.setAttr(target + ".translate", 2 * REST[0] * math.cos(math.radians(BEND)), 0.0, 0.0)
    cmds.joint(shoulder, edit=True, setPreferredAngles=True, children=True)
    handle = cmds.ikHandle(startJoint=shoulder, endEffector=wrist, solver="ikRPsolver", name="arm_IK")[0]
    handle = cmds.parent(handle, target)[0]
    cmds.setAttr(handle + ".translate", 0.0, 0.0, 0.0)
    cmds.setAttr(handle + ".visibility", False)
    cmds.poleVectorConstraint(pole, handle)
    setup = LimbPin.create(shoulder, elbow, wrist, pole, target, name="limbPin")
    bones = []
    for joint in arm[:2]:
        box = cmds.polyCube(name=joint.replace("_JNT", "_GEO"), width=1.0, height=0.5, depth=0.5)[0]
        cmds.parent(box, joint, relative=True)
        cmds.sets(box, edit=True, forceElement=yellow)
        bones.append(box)
    for joint in arm:
        _ball(joint.replace("_JNT", "_ball_GEO"), joint, white, 0.32)
    camera, camera_shape = cmds.camera(name="limbPinCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(4.3, -0.6, 20), lookAt=(4.3, -0.6, 0))
    window = cmds.window("limbPinValidationWindow", title="LimbPin - elbow pin and slide",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("limbPinValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, ikHandles=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 7
    names = ["limbPinHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, arm, pole, target, bones, setup, values, names


def _position(node):
    """ノードのワールド位置。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    return om.MVector(cmds.getAttr(node + ".worldMatrix[0]")[12:15])


def evaluate_frame(frame, arm, pole, target, bones, setup, values, names):
    """入力を更新し、長さが独立計算と一致し、pin=1 で肘が操作子・手首が目標に来ることを確かめる。"""
    from maya import cmds
    slide, pin, px, py, tx, ty, stage = pose(frame)
    owner = str(setup.container)
    cmds.setAttr(owner + ".slide", slide)
    cmds.setAttr(owner + ".pin", pin)
    cmds.setAttr(pole + ".translate", px, py, 0.0)
    cmds.setAttr(target + ".translate", tx, ty, 0.0)
    # 独立計算(肩はワールドの原点に固定)。
    shoulder, pole_point, target_point = _position(arm[0]), _position(pole), _position(target)
    near, far = (pole_point - shoulder).length(), (target_point - pole_point).length()
    delta = slide * (REST[1] if slide >= 0.0 else REST[0])
    upper, lower = REST[0] + delta, REST[1] - delta
    upper, lower = upper + pin * (near - upper), lower + pin * (far - lower)
    got = (cmds.getAttr(owner + ".upperLength"), cmds.getAttr(owner + ".lowerLength"))
    joints = (cmds.getAttr(arm[1] + ".translateX"), cmds.getAttr(arm[2] + ".translateX"))
    error = max(abs(got[0] - upper), abs(got[1] - lower), abs(joints[0] - upper), abs(joints[1] - lower))
    # 表示用: 骨の箱を出力の長さへ合わせる(判定には使わない)。
    for box, length in zip(bones, joints):
        cmds.setAttr(box + ".scaleX", max(length, 1e-3))
        cmds.setAttr(box + ".translateX", length / 2)
    elbow_gap = (_position(arm[1]) - pole_point).length()
    wrist_gap = (_position(arm[2]) - target_point).length()
    values[:] = [
        "upper and lower bone lengths are driven; the IK solver is untouched (U0 = L0 = 4.00 cm)",
        "YELLOW = arm (ikRPsolver + poleVectorConstraint)   BLUE = pole control   ORANGE = IK target   STAGE: " + stage,
        "slide s: d = s*L0 (s >= 0), s*U0 (s < 0)   U' = U0 + d   L' = L0 - d   pin w: U = U' + w*(|P-R| - U')   L = L' + w*(|T-P| - L')",
        "INPUT slide = {:+5.2f}   pin = {:4.2f}   pole P = ({:5.2f}, {:5.2f})   target T = ({:5.2f}, {:5.2f}) cm".format(
            slide, pin, px, py, tx, ty),
        "OUTPUT upper U = {:5.2f}   lower L = {:5.2f}   U + L = {:5.2f} cm   |P-R| = {:5.2f}   |T-P| = {:5.2f} cm".format(
            got[0], got[1], got[0] + got[1], near, far),
        "elbow to pole = {:5.3f} cm   wrist to target = {:5.3f} cm   (both 0 when pin = 1)".format(elbow_gap, wrist_gap),
        "CHECK lengths vs independent calculation: max error {:.2e} cm".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-5
    if pin > 1.0 - 1e-9:
        ok = ok and elbow_gap < 1e-3 and wrist_gap < 1e-3
    return {"frame": frame, "presentation_stage": stage, "input": [slide, pin, px, py, tx, ty],
            "upper": got[0], "lower": got[1], "max_error": error, "elbow_to_pole": elbow_gap,
            "wrist_to_target": wrist_gap, "ok": ok}


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
        scene = buildScene()
        panel = scene[0]
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("LimbPin: 2関節の長さの slide と、肘を極ベクトルの操作子へ留める pin", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, *scene[1:]),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "limb_pin.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-limb-pin.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("limb-pin-%Y%m%d-%H%M%S")
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
