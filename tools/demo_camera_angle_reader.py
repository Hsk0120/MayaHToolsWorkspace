"""CameraAngleReaderの、顔から見たカメラの角度と方向ごとの重みを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_camera_angle_reader.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
DISTANCE = 11.0
WEIGHTS = ("weightFront", "weightLeft", "weightRight", "weightAbove", "weightBelow", "weightBack")
LABELS = ("front", "left", "right", "above", "below", "back")
# (水平角(度、展開した値), 垂直角(度), 次の姿勢へ向かう段階名)。カメラは頭の周りを回り、真後ろを通って正面へ戻る。
POSES = [
    (0, 0, "1 FRONT -> LEFT"),
    (90, 0, "2 LEFT -> LEFT AND ABOVE"),
    (70, 45, "3 -> ABOVE (HIGH ANGLE)"),
    (0, 70, "4 ABOVE -> RIGHT AND ABOVE"),
    (-60, 30, "5 -> RIGHT AND BELOW (LOW ANGLE)"),
    (-100, -40, "6 -> BEHIND (RIGHT SIDE)"),
    (-150, 0, "7 CROSS THE BACK (-180 = +180)"),
    (-210, 0, "8 BEHIND (LEFT SIDE) -> LEFT"),
    (-270, 0, "9 LEFT -> FRONT"),
    (-360, 0, "9 LEFT -> FRONT"),
    (-360, 0, "9 LEFT -> FRONT"),
]
FRAMES = SEGMENT * (len(POSES) - 1) + 24


def pose(frame):
    """フレームの水平角・垂直角をsmoothstepで補間して返す。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    yaw = POSES[index][0] + (POSES[index + 1][0] - POSES[index][0]) * weight
    pitch = POSES[index][1] + (POSES[index + 1][1] - POSES[index][1]) * weight
    return yaw, pitch, POSES[index][2]


def expected_weights(yaw, pitch, yawRange=90.0, pitchRange=60.0, backFade=30.0):
    """十字の5点の区分線形の補間と後ろへの移行を、実装とは独立に場合分けで求める。"""
    a = min(abs(yaw) / yawRange, 1.0)
    b = min(abs(pitch) / pitchRange, 1.0)
    if a + b <= 1.0:
        front, side, level = 1.0 - a - b, a, b
    else:
        front, side, level = 0.0, a / (a + b), b / (a + b)
    values = dict.fromkeys(WEIGHTS, 0.0)
    values["weightFront"] = front
    values["weightLeft" if yaw >= 0 else "weightRight"] = side
    values["weightAbove" if pitch >= 0 else "weightBelow"] = level
    k = 1.0 if abs(yaw) <= 180.0 - backFade else max(0.0, (180.0 - abs(yaw)) / backFade)
    for key in values:
        values[key] *= k
    values["weightBack"] = 1.0 - k
    return values


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import CameraAngleReader
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    # 頭: 少し回した球と、正面(+Z)を示す鼻。
    head = cmds.createNode("joint", name="head_JNT")
    cmds.setAttr(head + ".rotateY", 20)
    skull = cmds.polySphere(name="head_GEO", radius=2.0)[0]
    nose = cmds.polyCone(name="nose_GEO", radius=0.5, height=1.4, axis=(0, 0, 1))[0]
    cmds.setAttr(nose + ".translateZ", 2.3)
    for geo in (skull, nose):
        cmds.parent(geo, head, relative=True)
    cmds.sets(skull, edit=True, forceElement=_shader("skinColor", (0.85, 0.7, 0.6)))
    cmds.sets(nose, edit=True, forceElement=_shader("noseColor", (0.9, 0.3, 0.3)))
    target = cmds.createNode("transform", name="shotCamera_POS")
    body = cmds.polyCube(name="shotCamera_GEO", width=1.2, height=0.9, depth=1.6)[0]
    lens = cmds.polyCylinder(name="shotLens_GEO", radius=0.35, height=0.6, axis=(0, 0, 1))[0]
    cmds.setAttr(lens + ".translateZ", -1.0)
    yellow = _shader("cameraYellow", (0.95, 0.8, 0.1))
    for geo in (body, lens):
        cmds.parent(geo, target, relative=True)
        cmds.sets(geo, edit=True, forceElement=yellow)
    graph = CameraAngleReader.create(head, target, name="cameraAngleReader")
    owner = graph.container
    # 方向ごとの重みを、頭の空間の前・左・右・上・下・後ろに置いた緑の球の大きさで示す。
    green = _shader("weightGreen", (0.15, 0.8, 0.25))
    places = ((0, 0, 4.2), (4.2, 0, 0), (-4.2, 0, 0), (0, 4.2, 0), (0, -4.2, 0), (0, 0, -4.2))
    for attr, place in zip(WEIGHTS, places):
        holder = cmds.createNode("transform", name=attr + "_GRP", parent=head)
        cmds.setAttr(holder + ".translate", *place)
        ball = cmds.polySphere(name=attr + "_GEO", radius=1.0)[0]
        cmds.parent(ball, holder, relative=True)
        cmds.sets(ball, edit=True, forceElement=green)
        for axis in "XYZ":
            owner.getPlug(attr).connectTo(holder + ".scale" + axis)
    camera, camera_shape = cmds.camera(name="cameraAngleCamera", focalLength=35)
    # 斜め上から固定。カメラの模型が頭の周りを回っても枠に収まる位置。
    cmds.viewPlace(camera_shape, eye=(30, 18, 34), lookAt=(0, -0.5, 0))
    window = cmds.window("cameraAngleValidationWindow", title="CameraAngleReader - face and camera",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("cameraAngleValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["cameraAngleHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"owner": owner, "head": head, "camera": target}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """カメラの模型を動かし、DGの角度・重みを独立に求めた値と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    yaw, pitch, stage = pose(frame)
    head, target, owner = scene["head"], scene["camera"], scene["owner"]
    world = om.MMatrix(cmds.getAttr(head + ".worldMatrix[0]"))
    local = om.MPoint(DISTANCE * math.cos(math.radians(pitch)) * math.sin(math.radians(yaw)),
                      DISTANCE * math.sin(math.radians(pitch)),
                      DISTANCE * math.cos(math.radians(pitch)) * math.cos(math.radians(yaw)))
    point = local * world
    cmds.xform(target, worldSpace=True, translation=(point.x, point.y, point.z))
    # 模型のレンズ(-Z)を頭へ向ける(見た目だけ。重みには位置だけを使う)。
    cmds.xform(target, worldSpace=True, rotation=(-pitch, yaw + 20, 0))
    inverse = om.MMatrix(cmds.getAttr(head + ".worldInverseMatrix[0]"))
    vector = om.MVector(point * inverse)
    expectedYaw = math.degrees(math.atan2(vector.x, vector.z))
    expectedPitch = math.degrees(math.atan2(vector.y, math.hypot(vector.x, vector.z)))
    expected = expected_weights(expectedYaw, expectedPitch)
    actualYaw = owner.getPlug("yaw").get()
    actualPitch = owner.getPlug("pitch").get()
    actual = {name: owner.getPlug(name).get() for name in WEIGHTS}
    difference = math.radians(actualYaw - expectedYaw)
    angleError = max(abs(math.degrees(math.atan2(math.sin(difference), math.cos(difference)))),
                     abs(actualPitch - expectedPitch))
    weightError = max(abs(actual[name] - expected[name]) for name in WEIGHTS)
    total = sum(actual.values())
    values[:] = [
        "YELLOW = camera (moves around the head)   GREEN ball size = weight of that direction   RED = nose (front)",
        "STAGE: " + stage,
        "fixed: yawRange = 90 deg   pitchRange = 60 deg   backFade = 30 deg   (camera position in head space)",
        "a = clamp(|yaw|/yawRange)  b = clamp(|pitch|/pitchRange)  front = max(1-a-b, 0)  side = a/max(a+b, 1)"
        "  k = clamp((180-|yaw|)/backFade)",
        "INPUT yaw = {:+7.2f} deg   pitch = {:+6.2f} deg   (DG output)".format(actualYaw, actualPitch),
        "OUTPUT " + "  ".join("{} {:.3f}".format(label, actual[name]) for label, name in zip(LABELS, WEIGHTS))
        + "   sum {:.4f}".format(total),
        "CHECK angle error = {:.6f} deg   weight error = {:.7f}".format(angleError, weightError),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = angleError < 1e-3 and weightError < 1e-4 and abs(total - 1.0) < 1e-5
    return {"frame": frame, "presentation_stage": stage, "yaw": actualYaw, "pitch": actualPitch,
            "weights": actual, "angle_error": angleError, "weight_error": weightError, "ok": ok}


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
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("CameraAngleReader: 顔から見たカメラの角度と補正の重み", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "camera_angle_reader.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-camera-angle-reader.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("camera-angle-reader-%Y%m%d-%H%M%S")
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
