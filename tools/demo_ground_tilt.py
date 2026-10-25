"""GroundTiltの4本の足の面に合わせた胴体の傾きと上下を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_ground_tilt.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEET = (("frontLeft", (4, 0, 1.5)), ("frontRight", (4, 0, -1.5)),
        ("backLeft", (-4, 0, 1.5)), ("backRight", (-4, 0, -1.5)))
BODY = (0.0, 5.0, 0.0)
SEGMENT = 30
# (4本の足の高さ[cm、左前・右前・左後・右後], tilt, 次の姿勢へ向かう段階名)。
POSES = [
    ((0, 0, 0, 0), 1.0, "1 REST"),
    ((0, 0, 0, 0), 1.0, "2 FRONT FEET UP: BODY PITCHES UP"),
    ((2, 2, 0, 0), 1.0, "3 BACK FEET UP: BODY PITCHES DOWN"),
    ((0, 0, 2, 2), 1.0, "4 LEFT FEET UP: BODY ROLLS"),
    ((1.5, 0, 1.5, 0), 1.0, "5 UNEVEN GROUND"),
    ((1.8, -0.5, 0.4, 1.2), 1.0, "6 FLAT LIFT: NO ROTATION, LIFT ONLY"),
    ((1.5, 1.5, 1.5, 1.5), 1.0, "7 FRONT FEET UP WITH tilt = 0.5"),
    ((2, 2, 0, 0), 0.5, "8 RETURN TO REST"),
    ((0, 0, 0, 0), 1.0, "8 RETURN TO REST"),
    ((0, 0, 0, 0), 1.0, "8 RETURN TO REST"),
]


def pose(frame):
    """フレームの足の高さ・tilt・段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    heights = [a + (b - a) * weight for a, b in zip(POSES[index][0], POSES[index + 1][0])]
    tilt = POSES[index][1] + (POSES[index + 1][1] - POSES[index][1]) * weight
    return heights, tilt, POSES[index][2]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _box(name, parent, group, size, translate=(0, 0, 0)):
    """parentの下に箱を作る。"""
    from maya import cmds
    box = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    cmds.setAttr(box + ".translate", *translate)
    cmds.parent(box, parent, relative=True)
    cmds.sets(box, edit=True, forceElement=group)
    return box


def _plane(points):
    """足の位置から、(面の向きの回転行列, 中心, 前後の向き, 左右の向き)を独立に計算する。"""
    from maya.api import OpenMaya as om
    front, back = (points[0] + points[1]) * 0.5, (points[2] + points[3]) * 0.5
    left, right = (points[0] + points[2]) * 0.5, (points[1] + points[3]) * 0.5
    center = (points[0] + points[1] + points[2] + points[3]) * 0.25
    x = (front - center).normal()
    z = (left - center) - x * ((left - center) * x)
    z.normalize()
    y = z ^ x
    rotation = om.MMatrix([x[0], x[1], x[2], 0, y[0], y[1], y[2], 0, z[0], z[1], z[2], 0, 0, 0, 0, 1])
    return rotation, center, (front - back).normal(), (left - right).normal()


def _move(vector):
    """位置だけの行列。"""
    from maya.api import OpenMaya as om
    return om.MMatrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, vector[0], vector[1], vector[2], 1])


def buildScene():
    """検証シーンを作り、(panel, 足, 出力, 胴体, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import GroundTilt
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    world = cmds.createNode("transform", name="creature_GRP")
    body = cmds.createNode("transform", name="body_CTRL", parent=world)
    cmds.setAttr(body + ".translate", *BODY)
    feet = []
    for role, position in FEET:
        foot = cmds.createNode("transform", name=role + "_FOOT", parent=world)
        cmds.setAttr(foot + ".translate", *position)
        feet.append(foot)
    graph = GroundTilt.create(body, *feet, name="groundTilt")
    owner = graph.container
    output = cmds.createNode("transform", name="output_body_GRP", parent=world)
    owner.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    grey = _shader("footGrey", (0.5, 0.5, 0.53))
    red = _shader("restRed", (0.9, 0.12, 0.1), transparency=0.7)
    green = _shader("outputGreen", (0.15, 0.8, 0.25))
    head = _shader("outputHead", (0.6, 1.0, 0.6))
    # 灰=足の接地点、赤(半透明)=入力の胴体(水平のまま)、緑=出力の胴体(頭側を明るい緑の箱で示す)。
    for foot in feet:
        _box(foot + "_GEO", foot, grey, (1.2, 0.4, 1.2), translate=(0, 0.2, 0))
    _box("inputBody_GEO", body, red, (9, 1.6, 3.6))
    _box("outputBody_GEO", output, green, (9, 1.6, 3.6))
    _box("outputHead_GEO", output, head, (1.6, 1.6, 2.0), translate=(5.3, 0.6, 0))
    camera, camera_shape = cmds.camera(name="tiltCamera", focalLength=35)
    # 斜め前・上から。前後の傾きと左右の傾きの両方が見える位置に固定する。
    cmds.viewPlace(camera_shape, eye=(15, 11, 27), lookAt=(0, 2.4, 0))
    window = cmds.window("groundTiltValidationWindow", title="GroundTilt - body follows the plane of four feet",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("groundTiltValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["groundTiltHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, feet, output, body, owner, values, names


def evaluate_frame(frame, feet, output, body, owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    heights, tilt, stage = pose(frame)
    for foot, y in zip(feet, heights):
        cmds.setAttr(foot + ".translateY", y)
    owner.getPlug("tilt").set(tilt)
    points = [om.MVector(cmds.xform(foot, q=True, worldSpace=True, translation=True)) for foot in feet]
    rotation, center, _, _ = _plane(points)
    rest_rotation, rest_center, forward, side = _plane([om.MVector(*position) for _, position in FEET])
    delta = rest_rotation.inverse() * rotation
    quaternion = om.MQuaternion.slerp(om.MQuaternion(), om.MTransformationMatrix(delta).rotation(True), tilt)
    lift = center.y - rest_center.y
    body_matrix = om.MMatrix(cmds.getAttr(body + ".worldMatrix[0]"))
    position = om.MVector(body_matrix[12], body_matrix[13], body_matrix[14])
    expected = (body_matrix * _move(-position) * quaternion.asMatrix() * _move(position)
                * _move(om.MVector(0, lift, 0)))
    actual = om.MMatrix(cmds.getAttr(output + ".worldMatrix[0]"))
    matrix_error = max(abs(a - e) for a, e in zip(actual, expected))
    angles = [math.degrees(math.asin((direction * delta).normal().y)) for direction in (forward, side)]
    dg = {attr: owner.getPlug(attr).get() for attr in ("pitch", "roll", "lift")}
    values[:] = [
        "GREEN = output body (light green box = head side)   RED (transparent) = input body   GREY = foot contacts",
        "STAGE: " + stage,
        "fixed: feet at x = +-4, z = +-1.5 cm   input body at (0, 5, 0)   height = 1",
        "F,B,L,R = mid points  C = mean  A = aimMatrix(+X to F, +Z to L)  D = A0^-1 A  "
        "out = Body T(-b) slerp(I, D, tilt) T(b) T(0, lift, 0)",
        "INPUT foot heights FL {:5.2f}  FR {:5.2f}  BL {:5.2f}  BR {:5.2f} cm   tilt = {:.2f}".format(
            heights[0], heights[1], heights[2], heights[3], tilt),
        "OUTPUT pitch = {:+6.2f} deg   roll = {:+6.2f} deg   lift = {:+6.3f} cm".format(
            dg["pitch"], dg["roll"], dg["lift"]),
        "CHECK pitch error = {:.5f} deg  roll error = {:.5f} deg  lift error = {:.6f}  body matrix error = {:.6f}".format(
            abs(dg["pitch"] - angles[0]), abs(dg["roll"] - angles[1]), abs(dg["lift"] - lift), matrix_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (abs(dg["pitch"] - angles[0]) < 1e-3 and abs(dg["roll"] - angles[1]) < 1e-3
          and abs(dg["lift"] - lift) < 1e-5 and matrix_error < 1e-4)
    return {"frame": frame, "presentation_stage": stage, "input_foot_heights_cm": heights, "tilt": tilt,
            "independent_pitch_roll_degrees": angles, "independent_lift_cm": lift, "dg": dg,
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
        panel, feet, output, body, owner, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("GroundTilt: 4本の足の面に合わせた胴体の傾き", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, feet, output, body, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "ground_tilt.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-ground-tilt.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("ground-tilt-%Y%m%d-%H%M%S")
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
