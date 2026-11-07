"""TripodJointのプランジ(シャフトの長さを保ってハウジングの軸に沿って滑る)と範囲の超過を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_tripod_joint.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LENGTH = 8.0
LIMIT = 0.8
SPIN_PER_FRAME = 3.0
SEGMENT = 40
# (外側の継手の軸方向のずれ dx[cm], 高さ dy[cm], 次の姿勢へ向かう段階名)。生成時は (LENGTH, 0, 0)。
POSES = [
    (0.0, 0.0, "1 STRAIGHT: PLUNGE 0"),
    (0.0, 0.0, "2 WHEEL UP 3 CM: SPIDER SLIDES OUT, SHAFT KEEPS 8 CM"),
    (0.0, 3.0, "3 WHEEL DOWN 3 CM (STILL IN RANGE)"),
    (0.0, -3.0, "4 PULL OUT 1.5 CM: HITS MAX PLUNGE, SHAFT STRETCHES"),
    (1.5, 0.0, "5 PUSH IN 1.5 CM: HITS MIN PLUNGE, SHAFT SHRINKS"),
    (-1.5, 0.0, "6 BACK INTO RANGE (WHEEL UP 2 CM)"),
    (0.0, 2.0, "7 BACK TO STRAIGHT"),
    (0.0, 0.0, "8 BACK AT REST"),
    (0.0, 0.0, "8 BACK AT REST"),
]


def pose(frame):
    """フレームの外側の継手のずれ・段階名をsmoothstepで補間し、ハウジングの回転角(度)と共に返す。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    start, end = POSES[index], POSES[index + 1]
    dx = start[0] + (end[0] - start[0]) * weight
    dy = start[1] + (end[1] - start[1]) * weight
    return dx, dy, frame * SPIN_PER_FRAME, start[2]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _cylinder(name, parent, start, length, radius, shader):
    """parentの下へ、X方向に start から length の円柱を作る。"""
    from maya import cmds
    rod = cmds.polyCylinder(name=name + "_GEO", radius=radius, height=length, axis=(1, 0, 0), subdivisionsAxis=24)[0]
    cmds.parent(rod, parent, relative=True)
    cmds.setAttr(rod + ".translateX", start + length * 0.5)
    cmds.sets(rod, edit=True, forceElement=shader)
    return rod


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import TripodJoint
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    red = _shader("housingRed", (0.9, 0.15, 0.1))
    glass = _shader("housingGlass", (0.9, 0.3, 0.25), 0.75)
    green = _shader("shaftGreen", (0.15, 0.85, 0.25))
    white = _shader("markWhite", (0.95, 0.95, 0.9))
    yellow = _shader("outerYellow", (0.95, 0.8, 0.1))
    housing = cmds.createNode("transform", name="housing_JNT")
    outer = cmds.createNode("transform", name="outerJoint_LOC")
    cmds.setAttr(outer + ".translateX", LENGTH)
    setup = TripodJoint.create(housing, outer, name="tripodJoint", length=LENGTH, minPlunge=-LIMIT, maxPlunge=LIMIT)
    owner = str(setup.container)
    # ハウジング: 入力軸(赤)と、スパイダーが滑る半透明の筒。白い板は回転の目印。
    _cylinder("housingShaft", housing, -5.0, 4.0, 0.3, red)
    _cylinder("housingCup", housing, -1.0, 1.0 + LIMIT + 1.4, 1.3, glass)
    flag = cmds.polyCube(name="housingFlag_GEO", width=1.0, height=1.0, depth=0.1)[0]
    cmds.parent(flag, housing, relative=True)
    cmds.setAttr(flag + ".translate", -3.0, 0.75, 0)
    cmds.sets(flag, edit=True, forceElement=white)
    # 範囲の端(minPlunge・maxPlunge)の白い輪。回転させないため親なしで軸上に置く。
    for label, value in (("min", -LIMIT), ("max", LIMIT)):
        ring = cmds.polyTorus(name="limit{}_GEO".format(label), radius=1.35, sectionRadius=0.05, axis=(1, 0, 0),
                              subdivisionsAxis=32, subdivisionsHeight=6)[0]
        cmds.setAttr(ring + ".translateX", value)
        cmds.sets(ring, edit=True, forceElement=white)
    # スパイダー(3本のトラニオン)とシャフト(緑)
    spider = cmds.createNode("transform", name="spider_OUT")
    cmds.connectAttr(owner + ".matrix", spider + ".offsetParentMatrix")
    _cylinder("shaft", spider, 0.0, LENGTH, 0.3, green)
    for index in range(3):
        angle = 2.0 * math.pi * index / 3
        trunnion = cmds.polyCylinder(name="trunnion{}_GEO".format(index), radius=0.22, height=2.2,
                                     axis=(0, math.cos(angle), math.sin(angle)))[0]
        cmds.parent(trunnion, spider, relative=True)
        cmds.setAttr(trunnion + ".translate", 0, 0.55 * math.cos(angle), 0.55 * math.sin(angle))
        cmds.sets(trunnion, edit=True, forceElement=green)
    hub = cmds.polySphere(name="outer_GEO", radius=0.6)[0]
    cmds.parent(hub, outer, relative=True)
    cmds.sets(hub, edit=True, forceElement=yellow)
    camera, camera_shape = cmds.camera(name="tripodJointCamera", focalLength=35)
    # 正面寄りの斜めから。曲げ(XY)と軸方向の滑りが見え、左側のHUDと重ならないよう右へ寄せる。
    cmds.viewPlace(camera_shape, eye=(-2.0, 3.0, 30.0), lookAt=(1.5, -2.0, 0.0))
    window = cmds.window("tripodJointValidationWindow", title="TripodJoint - plunge", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("tripodJointValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["tripodJointHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"housing": housing, "outer": outer, "spider": spider, "joint": owner}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた式と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    dx, dy, spin, stage = pose(frame)
    cmds.setAttr(scene["outer"] + ".translate", LENGTH + dx, dy, 0)
    cmds.setAttr(scene["housing"] + ".rotateX", spin)
    joint = scene["joint"]
    plunge = cmds.getAttr(joint + ".plunge")
    over = cmds.getAttr(joint + ".overPlunge")
    shaft_length = cmds.getAttr(joint + ".shaftLength")
    stretch = cmds.getAttr(joint + ".stretch")
    bend = cmds.getAttr(joint + ".bendAngle")
    # 独立の計算: ハウジングは原点・X軸なので a = LENGTH + dx、b = |dy|。
    a, b = LENGTH + dx, abs(dy)
    raw = a - math.sqrt(max(LENGTH * LENGTH - b * b, 0.0))
    expected = min(max(raw, -LIMIT), LIMIT)
    center = om.MPoint(expected, 0, 0)
    target = om.MPoint(LENGTH + dx, dy, 0)
    expected_length = (target - center).length()
    spider = om.MMatrix(cmds.getAttr(scene["spider"] + ".worldMatrix[0]"))
    position_error = (om.MPoint(spider[12], spider[13], spider[14]) - center).length()
    housing = om.MMatrix(cmds.getAttr(scene["housing"] + ".worldMatrix[0]"))
    aim = (target - center).normal()
    turn = om.MTransformationMatrix(housing).rotation(asQuaternion=True) * om.MQuaternion(om.MVector(1, 0, 0), aim)
    actual = om.MTransformationMatrix(spider).rotation(asQuaternion=True)
    rotation_error = math.degrees((actual * turn.inverse()).asAxisAngle()[1]) % 360.0
    rotation_error = min(rotation_error, 360.0 - rotation_error)
    errors = {
        "plunge": abs(plunge - expected), "overPlunge": abs(over - (raw - expected)),
        "shaftLength": abs(shaft_length - expected_length), "stretch": abs(stretch - (expected_length - LENGTH)),
        "position": position_error, "rotation": rotation_error,
    }
    in_range = -LIMIT <= raw <= LIMIT
    status = "IN RANGE" if in_range else ("PULLED OUT TOO FAR" if raw > 0 else "PUSHED IN TOO FAR")
    values[:] = [
        "RED housing (spins {:.0f} deg/frame)  GREEN spider + shaft  YELLOW outer joint  WHITE rings = plunge limits".format(
            SPIN_PER_FRAME),
        "STAGE: " + stage,
        "d = W - H,  a = d.u,  b^2 = |d|^2 - a^2,  p = a - sqrt(L^2 - b^2),  plunge = clamp(p, min, max)",
        "FIXED: shaft length L = {:.1f} cm   min = {:.1f} cm   max = {:.1f} cm   spider c = H + u * plunge".format(
            LENGTH, -LIMIT, LIMIT),
        "INPUT outer joint: dx = {:+6.2f} cm  dy = {:+6.2f} cm   ->  a = {:6.3f} cm  b = {:6.3f} cm".format(dx, dy, a, b),
        "p (raw) = {:+7.3f} cm   DG plunge = {:+7.3f} cm   DG overPlunge = {:+7.3f} cm   [{}]".format(
            raw, plunge, over, status),
        "DG shaftLength = {:7.3f} cm   DG stretch = {:+7.3f} cm   DG bendAngle = {:6.2f} deg".format(
            shaft_length, stretch, bend),
        "CHECK |plunge - formula| = {:.6f} cm   |shaftLength - |W-c|| = {:.6f} cm   |rotation - R x Q(u->v)| = {:.5f} deg".format(
            errors["plunge"], errors["shaftLength"], rotation_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = all(value < 1e-3 for value in errors.values())
    if in_range:
        ok = ok and abs(shaft_length - LENGTH) < 1e-3
    return {"frame": frame, "presentation_stage": stage, "input": {"dx": dx, "dy": dy, "spin": spin},
            "raw_plunge": raw, "plunge": plunge, "over_plunge": over, "shaft_length": shaft_length,
            "stretch": stretch, "bend_angle": bend, "in_range": in_range, "errors": errors, "ok": ok}


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
        folder = recordVideo("TripodJoint: シャフトの長さを保つプランジと範囲の超過", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "tripod_joint.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-tripod-joint.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("tripod-joint-%Y%m%d-%H%M%S")
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
