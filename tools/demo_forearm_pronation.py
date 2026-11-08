"""ForearmPronationの回内・回外、可動域の超過、手のSwingの無視、尺骨の移動を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_forearm_pronation.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD = (0.3, 0.0, 0.9)
ULNA_HEAD = (10.0, 0.0, 0.0)
RADIUS_TIP = (10.0, 0.0, 2.6)
HAND = (10.8, 0.0, 0.0)
PRONATION_LIMIT = 80.0
SUPINATION_LIMIT = 85.0
SOFTNESS = 0.1
SEGMENT = 40
# (手のTwist[度], 手のSwing[度], 尺骨のrotateZ[度], 次の姿勢へ向かう段階名)
POSES = [
    (0.0, 0.0, 0.0, "1 REST -> PRONATE 50 (IN RANGE)"),
    (50.0, 0.0, 0.0, "2 PRONATE PAST THE LIMIT: 120 DEG INPUT"),
    (120.0, 0.0, 0.0, "3 HOLD PAST THE LIMIT"),
    (120.0, 0.0, 0.0, "4 BACK INTO RANGE, THEN SUPINATE 50"),
    (-50.0, 0.0, 0.0, "5 SUPINATE PAST THE LIMIT: -130 DEG INPUT"),
    (-130.0, 0.0, 0.0, "6 BACK TO TWIST 30, ADD WRIST SWING 35 (IGNORED)"),
    (30.0, 35.0, 0.0, "7 ELBOW BENDS 45: HAND MOVES WITH THE ULNA"),
    (30.0, 35.0, 45.0, "8 BACK TO REST"),
    (0.0, 0.0, 0.0, "9 BACK AT REST"),
    (0.0, 0.0, 0.0, "9 BACK AT REST"),
]


def pose(frame):
    """フレームの手のTwist・Swing・尺骨の回転・段階名をsmoothstepで補間して返す。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    start, end = POSES[index], POSES[index + 1]
    return tuple(start[i] + (end[i] - start[i]) * weight for i in range(3)) + (start[3],)


def softLimit(angle):
    """回内80度・回外85度・softness 0.1の柔らかい制限を、DGとは別に式どおり計算する。"""
    width = max(SOFTNESS * (PRONATION_LIMIT + SUPINATION_LIMIT) * 0.5, 1e-3)
    upper = PRONATION_LIMIT - width
    lower = -SUPINATION_LIMIT + width
    if angle > upper:
        return upper + width * (1 - math.exp(-(angle - upper) / width))
    if angle < lower:
        return lower - width * (1 - math.exp(-(lower - angle) / width))
    return angle


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _bone(name, parent, start, end, radius, shader):
    """parentの下へ start から end への円柱を作る。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    first, last = om.MVector(start), om.MVector(end)
    direction = last - first
    bone = cmds.polyCylinder(name=name + "_GEO", radius=radius, height=direction.length(),
                             axis=(direction.x, direction.y, direction.z), subdivisionsAxis=24)[0]
    cmds.parent(bone, parent, relative=True)
    middle = (first + last) * 0.5
    cmds.setAttr(bone + ".translate", middle.x, middle.y, middle.z)
    cmds.sets(bone, edit=True, forceElement=shader)
    return bone


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import ForearmPronation
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    gray = _shader("ulnaGray", (0.55, 0.55, 0.55))
    green = _shader("radiusGreen", (0.15, 0.85, 0.25))
    red = _shader("radiusRed", (0.9, 0.15, 0.1), 0.55)
    yellow = _shader("handYellow", (0.95, 0.8, 0.1), 0.7)
    white = _shader("markWhite", (0.95, 0.95, 0.9))
    ulna = cmds.createNode("transform", name="ulna_JNT")
    cmds.setAttr(ulna + ".translateX", -5.0)
    nodes = {"ulna": ulna}
    for label, position in (("ulnaTip", ULNA_HEAD), ("radius", HEAD), ("radiusTip", RADIUS_TIP), ("hand", HAND)):
        nodes[label] = cmds.createNode("transform", name=label + "_JNT", parent=ulna)
        cmds.setAttr(nodes[label] + ".translate", *position)
    arguments = (ulna, nodes["ulnaTip"], nodes["radius"], nodes["radiusTip"], nodes["hand"])
    limited = str(ForearmPronation.create(*arguments, name="forearmPronation", pronationLimit=PRONATION_LIMIT,
                                          supinationLimit=SUPINATION_LIMIT, softness=SOFTNESS).container)
    unlimited = str(ForearmPronation.create(*arguments, name="forearmUnlimited", pronationLimit=179.0,
                                            supinationLimit=179.0, softness=0.0).container)
    _bone("ulna", ulna, (0, 0, 0), ULNA_HEAD, 0.35, gray)
    axis_end = om.MVector(ULNA_HEAD)
    axis_start = om.MVector(HEAD)
    # 回転軸(橈骨の頭→尺骨の頭)を白い細い線で示す。
    _bone("axis", ulna, tuple(axis_start), tuple(axis_end), 0.06, white)
    offset = om.MVector(RADIUS_TIP) - axis_start
    for owner, label, shader, thickness in ((limited, "radiusOut", green, 0.34), (unlimited, "radiusRaw", red, 0.24)):
        out = cmds.createNode("transform", name=label + "_OUT")
        cmds.connectAttr(owner + ".matrix", out + ".offsetParentMatrix")
        _bone(label, out, (0, 0, 0), (offset.x, offset.y, offset.z), thickness, shader)
    palm = cmds.polyCube(name="hand_GEO", width=2.6, height=0.3, depth=2.2)[0]
    cmds.parent(palm, nodes["hand"], relative=True)
    cmds.setAttr(palm + ".translateX", 1.4)
    cmds.sets(palm, edit=True, forceElement=yellow)
    camera, camera_shape = cmds.camera(name="forearmCamera", focalLength=35)
    # 手首側から前腕の軸に近い向きで見て、尺骨の周りを橈骨の先が回るのを見せる。
    cmds.viewPlace(camera_shape, eye=(24.0, 7.0, 13.0), lookAt=(2.0, -1.5, -3.0))
    window = cmds.window("forearmValidationWindow", title="ForearmPronation", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("forearmValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["forearmHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"ulna": ulna, "hand": nodes["hand"], "limited": limited, "unlimited": unlimited}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた式と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    twist, swing, elbow, stage = pose(frame)
    head = om.MVector(HEAD)
    tip = om.MVector(RADIUS_TIP)
    axis = (om.MVector(ULNA_HEAD) - head).normal()
    side = (axis ^ om.MVector(0, 1, 0)).normal()
    rotation = om.MQuaternion(math.radians(twist), axis) * om.MQuaternion(math.radians(swing), side)
    euler = rotation.asEulerRotation()
    cmds.setAttr(scene["hand"] + ".rotate", *[math.degrees(value) for value in (euler.x, euler.y, euler.z)])
    cmds.setAttr(scene["ulna"] + ".rotateZ", elbow)
    owner = scene["limited"]
    hand_twist = cmds.getAttr(owner + ".handTwist")
    pronation = cmds.getAttr(owner + ".pronation")
    excess = cmds.getAttr(owner + ".excessPronation")
    pronation_weight = cmds.getAttr(owner + ".pronationWeight")
    supination_weight = cmds.getAttr(owner + ".supinationWeight")
    distance = cmds.getAttr(owner + ".interosseousDistance")
    # 独立の計算: 軸まわりの回転で橈骨の先を求め、尺骨の行列でワールドへ移す。
    expected = softLimit(twist)
    local_tip = head + (tip - head).rotateBy(om.MQuaternion(math.radians(expected), axis))
    ulna_world = om.MMatrix(cmds.getAttr(scene["ulna"] + ".worldMatrix[0]"))
    world_tip = om.MPoint(local_tip) * ulna_world
    world_head = om.MPoint(head) * ulna_world
    actual = om.MMatrix(cmds.getAttr(owner + ".tipMatrix"))
    actual_head = om.MMatrix(cmds.getAttr(owner + ".matrix"))
    expected_distance = ((head + local_tip) * 0.5 - om.MVector(ULNA_HEAD) * 0.5).length()
    errors = {
        "handTwist": abs(hand_twist - twist), "pronation": abs(pronation - expected),
        "excess": abs(excess - (twist - expected)),
        "tip": (om.MPoint(actual[12], actual[13], actual[14]) - world_tip).length(),
        "head": (om.MPoint(actual_head[12], actual_head[13], actual_head[14]) - world_head).length(),
        "interosseous": abs(distance - expected_distance),
    }
    status = "IN RANGE" if abs(excess) < 0.005 else ("PAST PRONATION LIMIT" if excess > 0 else "PAST SUPINATION LIMIT")
    values[:] = [
        "GRAY ulna  WHITE axis (radial head -> ulnar head)  GREEN radius with limits  RED radius without limits  YELLOW hand",
        "STAGE: " + stage,
        "handTwist = twist of the hand about the axis, seen from the ulna   raw = sign * handTwist * weight",
        "FIXED: pronationLimit = {:.0f} deg   supinationLimit = {:.0f} deg   softness = {:.1f}   sign = +1   weight = 1".format(
            PRONATION_LIMIT, SUPINATION_LIMIT, SOFTNESS),
        "INPUT hand twist = {:+7.2f} deg   wrist swing = {:6.2f} deg   elbow rotateZ = {:6.2f} deg".format(twist, swing, elbow),
        "DG handTwist = {:+7.2f}   DG pronation = {:+7.2f}   DG excess = {:+7.2f} deg   [{}]".format(
            hand_twist, pronation, excess, status),
        "DG pronationWeight = {:5.3f}   DG supinationWeight = {:5.3f}   DG interosseous = {:6.3f} cm".format(
            pronation_weight, supination_weight, distance),
        "CHECK |pronation - formula| = {:.5f} deg   |radius tip - axis rotation| = {:.6f} cm".format(
            errors["pronation"], errors["tip"]),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = all(value < 1e-3 for value in errors.values())
    return {"frame": frame, "presentation_stage": stage, "input": {"twist": twist, "swing": swing, "elbow": elbow},
            "hand_twist": hand_twist, "pronation": pronation, "excess": excess, "pronation_weight": pronation_weight,
            "supination_weight": supination_weight, "interosseous": distance, "errors": errors, "ok": ok}


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
        folder = recordVideo("ForearmPronation: 回内・回外と可動域の超過", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "forearm_pronation.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-forearm-pronation.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("forearm-pronation-%Y%m%d-%H%M%S")
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
