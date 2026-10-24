"""EyelidFollowのまぶたの追従・まばたき・交差防止を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_eyelid_follow.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPPER_FOLLOW = 0.8
LOWER_FOLLOW = 0.2
YAW_FOLLOW = 0.15
OPEN_ANGLE = 30.0
BLINK_HEIGHT = 0.2
EYE_RADIUS = 1.2
LID_RADIUS = 1.32
RAY_LENGTH = 3.2
SEGMENT = 30
# (目のrotateX[Pitch、+で下], rotateY[Yaw], blink, 次の姿勢へ向かう段階名)。基準は正面(+Z)を見た姿勢。
POSES = [
    (0, 0, 0, "1 REST: LIDS OPEN 30 DEG"),
    (0, 0, 0, "2 LOOK DOWN: UPPER x0.8, LOWER x0.2"),
    (25, 0, 0, "3 LOOK UP"),
    (-25, 0, 0, "4 LOOK SIDE: LIDS YAW x0.15"),
    (0, 30, 0, "4 LOOK SIDE: LIDS YAW x0.15"),
    (0, -30, 0, "5 BLINK: MEET AT HEIGHT 0.2"),
    (0, 0, 0, "5 BLINK: MEET AT HEIGHT 0.2"),
    (0, 0, 1, "5 BLINK: MEET AT HEIGHT 0.2"),
    (0, 0, 0, "6 BLINK WHILE LOOKING DOWN"),
    (20, 0, 0, "6 BLINK WHILE LOOKING DOWN"),
    (20, 0, 1, "6 BLINK WHILE LOOKING DOWN"),
    (20, 0, 0, "7 EXTREME LOOK DOWN: GAP CLAMPED AT 0"),
    (70, 0, 0, "8 HOLD BEYOND (LIDS WOULD CROSS)"),
    (70, 0, 0, "9 RETURN TO REST"),
    (0, 0, 0, "9 RETURN TO REST"),
    (0, 0, 0, "9 RETURN TO REST"),
]


def pose(frame):
    """フレームの入力(rx, ry, blink, 段階名)をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:3], POSES[index + 1][:3])]
    return values + [POSES[index][3]]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _curve(name, points, color, parent=None, width=3.0):
    """表示色付きのNURBS曲線を作る。"""
    from maya import cmds
    curve = cmds.curve(name=name, degree=1, point=points)
    shape = cmds.listRelatives(curve, shapes=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideColor", color)
    cmds.setAttr(shape + ".lineWidth", width)
    if parent:
        cmds.parent(curve, parent, relative=True)
    return curve


def _lid(name, parent, group, upper):
    """縁がローカル+Z、上まぶたは上・下まぶたは下へ広がる球殻をparent下に作る。"""
    from maya import cmds
    shell = cmds.sphere(name=name, axis=(1, 0, 0), startSweep=0, endSweep=95 if upper else 70,
                        radius=LID_RADIUS, sections=12, spans=8)[0]
    # 初期の球殻は縁が-Z、-Y側へ広がる。上はX、下はYまわりに180度回して縁を+Zへ向ける。
    cmds.setAttr(shell + (".rotateX" if upper else ".rotateY"), 180)
    cmds.parent(shell, parent, relative=True)
    cmds.sets(shell, edit=True, forceElement=group)
    return shell


def buildScene():
    """検証シーンを作り、(panel, 目, 入力のまぶた, 出力のまぶた, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import EyelidFollow
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    socket = cmds.createNode("transform", name="eyeSocket_GRP")
    eye = cmds.createNode("joint", name="eye_JNT", parent=socket)
    upper = cmds.createNode("joint", name="input_upperLid_JNT", parent=socket)
    lower = cmds.createNode("joint", name="input_lowerLid_JNT", parent=socket)
    cmds.setAttr(upper + ".rotateX", -OPEN_ANGLE / 2)
    cmds.setAttr(lower + ".rotateX", OPEN_ANGLE / 2)
    graph = EyelidFollow.create(eye, upper, lower, name="eyelidFollow", pitchAxis="x", yawAxis="y",
                                closeDirection=1, upperFollow=UPPER_FOLLOW, lowerFollow=LOWER_FOLLOW,
                                yawFollow=YAW_FOLLOW, openAngle=OPEN_ANGLE, blinkHeight=BLINK_HEIGHT)
    owner = graph.container
    outputs = []
    for role in ("upper", "lower"):
        out = cmds.createNode("transform", name="output_" + role + "Lid_GRP", parent=socket)
        owner.getPlug(role + "Matrix").connectTo(out + ".offsetParentMatrix")
        outputs.append(out)
    white, black = _shader("eyeWhite", (0.85, 0.85, 0.8)), _shader("pupilBlack", (0.02, 0.02, 0.05))
    green = _shader("outputLidGreen", (0.1, 0.75, 0.2))
    ball = cmds.polySphere(name="eyeball_GEO", radius=EYE_RADIUS, subdivisionsX=32, subdivisionsY=24)[0]
    pupil = cmds.polySphere(name="pupil_GEO", radius=0.35)[0]
    # 黒目は眼球の表面より少し前、まぶたの球殻より内側に置く。
    cmds.setAttr(pupil + ".translateZ", EYE_RADIUS - 0.1)
    cmds.setAttr(pupil + ".scaleZ", 0.4)
    for node, group in ((ball, white), (pupil, black)):
        cmds.parent(node, eye, relative=True)
        cmds.sets(node, edit=True, forceElement=group)
    # 黄=視線、赤=入力(セットアップなし)のまぶたの縁、緑=出力のまぶたの球殻と縁。
    _curve("gaze_CRV", [(0, 0, 0), (0, 0, RAY_LENGTH * 0.8)], 17, parent=eye, width=3)
    for lid in (upper, lower):
        _curve(lid + "_edge_CRV", [(0, 0, 0), (0, 0, RAY_LENGTH)], 13, parent=lid, width=2)
    for out, is_upper in zip(outputs, (True, False)):
        _lid(out.replace("_GRP", "_GEO"), out, green, is_upper)
        _curve(out + "_edge_CRV", [(0, 0, 0), (0, 0, RAY_LENGTH)], 14, parent=out, width=4)
    camera, camera_shape = cmds.camera(name="eyelidCamera", focalLength=45)
    # 斜め前(+X・+Z)から目を見る。上下の開閉・左右の向き・視線が同時にわかる位置に固定する。
    cmds.viewPlace(camera_shape, eye=(7, 2.5, 12), lookAt=(0, 0, 1.0))
    cmds.setAttr(camera_shape + ".verticalFilmOffset", -0.12)
    window = cmds.window("eyelidFollowValidationWindow", title="EyelidFollow - eyelids follow the eye",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("eyelidFollowValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 7
    names = ["eyelidFollowHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, eye, (upper, lower), outputs, owner, values, names


def _quaternion(matrix):
    """行列の回転をQuaternionで返す。"""
    from maya.api import OpenMaya as om
    return om.MTransformationMatrix(om.MMatrix(matrix)).rotation(asQuaternion=True)


def evaluate_frame(frame, eye, inputs, outputs, owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import EyelidFollow
    rx, ry, blink, stage = pose(frame)
    cmds.setAttr(eye + ".rotate", rx, ry, 0)
    owner.getPlug("blink").set(blink)
    # 目は基準回転なし・rotateOrder xyzなので、Pitch=rotateX、Yaw=rotateYとなる。
    expected = EyelidFollow.lidAngles(rx, ry, UPPER_FOLLOW, LOWER_FOLLOW, YAW_FOLLOW, OPEN_ANGLE, blink,
                                      BLINK_HEIGHT, 1)
    dg = {attr: owner.getPlug(attr).get() for attr in
          ("eyePitch", "eyeYaw", "upperAngle", "lowerAngle", "lidYaw", "gap")}
    # 出力のまぶたのワールド回転を、入力のまぶたにPitch・Yawを重ねた期待値と比べる(度)。
    errors = []
    for lid, out, attr in ((inputs[0], outputs[0], "upperAngle"), (inputs[1], outputs[1], "lowerAngle")):
        follow = om.MEulerRotation(math.radians(expected[attr]), math.radians(expected["lidYaw"]), 0).asMatrix()
        target = om.MTransformationMatrix(
            om.MMatrix(cmds.getAttr(lid + ".matrix")) * follow
            * om.MMatrix(cmds.getAttr(lid + ".parentMatrix[0]"))).rotation(asQuaternion=True)
        actual = _quaternion(cmds.getAttr(out + ".worldMatrix[0]"))
        dot = abs(target.x * actual.x + target.y * actual.y + target.z * actual.z + target.w * actual.w)
        errors.append(math.degrees(2 * math.acos(min(1.0, dot))))
    closing = rx
    raw_gap = OPEN_ANGLE + LOWER_FOLLOW * closing - UPPER_FOLLOW * closing
    if raw_gap < 0:
        state = "raw gap {:+.1f} < 0 -> lids meet, never cross".format(raw_gap)
    elif blink > 0.995:
        state = "blink = 1 -> closed at height 0.2"
    else:
        state = "open: gap = (1-blink)*max(l-u,0)"
    values[:] = [
        "GREEN = output eyelids   RED = input lid edges (no setup)   YELLOW = gaze   (3/4 view, +Z = forward)",
        "STAGE: " + stage,
        "fixed: upperFollow 0.8  lowerFollow 0.2  yawFollow 0.15  openAngle 30 deg  blinkHeight 0.2  (deg, + = down)",
        "u = 0.8*pitch   l = 30 + 0.2*pitch   meet = l - 0.2*(l-u)   upper = meet - (1-blink)*0.8*max(l-u,0)",
        "INPUT eye pitch = {:+6.1f} deg  yaw = {:+6.1f} deg  blink = {:4.2f}   DG eyePitch = {:+6.2f}  eyeYaw = {:+6.2f}".format(
            rx, ry, blink, dg["eyePitch"], dg["eyeYaw"]),
        "OUTPUT upperAngle = {:+6.2f}  lowerAngle = {:+6.2f}  lidYaw = {:+5.2f}  gap = {:5.2f} deg   {}".format(
            dg["upperAngle"], dg["lowerAngle"], dg["lidYaw"], dg["gap"], state),
        "CHECK |DG - formula| max = {:.4f} deg   lid world rotation error = {:.4f} / {:.4f} deg".format(
            max(abs(dg[k] - expected[k]) for k in ("upperAngle", "lowerAngle", "lidYaw", "gap")), *errors),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (abs(dg["eyePitch"] - rx) < 0.01 and abs(dg["eyeYaw"] - ry) < 0.01
          and all(abs(dg[k] - expected[k]) < 0.01 for k in ("upperAngle", "lowerAngle", "lidYaw", "gap"))
          and dg["gap"] >= -1e-6 and max(errors) < 0.01)
    return {"frame": frame, "presentation_stage": stage, "input_eye_rotate_degrees": [rx, ry, 0],
            "input_blink": blink, "dg": dg, "expected": expected, "raw_gap": raw_gap,
            "lid_world_rotation_error_degrees": errors, "ok": ok}


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
        panel, eye, inputs, outputs, owner, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("EyelidFollow: 目の向きに追従するまぶた・まばたき・交差防止", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, eye, inputs, outputs, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "eyelid-follow.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-eyelid-follow.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("eyelid-follow-%Y%m%d-%H%M%S")
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
