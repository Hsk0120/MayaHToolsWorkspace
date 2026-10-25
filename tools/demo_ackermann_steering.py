"""AckermannSteeringの前輪の切れ角を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_ackermann_steering.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
WHEEL_BASE = 8.0
TRACK = 5.0
#: 比較用(左右を同じ角度で切る)の赤い車の位置(緑の車の前方)。
RED_OFFSET = 11.5
LINE = 30.0
# (中央の切れ角[度], ackermann, 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, 1.0, "1 REST"),
    (0.0, 1.0, "2 STEER LEFT 25 deg"),
    (25.0, 1.0, "3 STEER RIGHT -25 deg"),
    (-25.0, 1.0, "4 STEER LEFT 40 deg (SMALL TURN RADIUS)"),
    (40.0, 1.0, "5 ackermann 1 -> 0 (PARALLEL, AXLES NO LONGER MEET)"),
    (40.0, 0.0, "6 RETURN TO REST"),
    (0.0, 1.0, "6 RETURN TO REST"),
    (0.0, 1.0, "6 RETURN TO REST"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:2], POSES[index + 1][:2])]
    return values[0], values[1], POSES[index][2]


def expected_angles(steer, ackermann):
    """旋回半径 R = L/tanδ から求めた左右の角度(判定用の独立計算。内輪 atan(L/(R-T/2))、外輪 atan(L/(R+T/2)))。"""
    if abs(steer) < 1e-9:
        return 0.0, 0.0
    radius = WHEEL_BASE / math.tan(math.radians(steer))
    exact = [math.degrees(math.atan(WHEEL_BASE / (radius - side * TRACK * 0.5))) for side in (1.0, -1.0)]
    # atan は (-90, 90) を返す。内輪が90度を超える範囲(このデモでは使わない)は扱わない。
    return tuple(steer + ackermann * (value - steer) for value in exact)


def axle_hit(x, z, angle):
    """車輪(位置 x, z、rotateY = angle)の車軸の延長が後輪の軸(z=0)と交わるxを返す。平行ならNone。"""
    radian = math.radians(angle)
    if abs(math.sin(radian)) < 1e-6:
        return None
    return x + z * math.cos(radian) / math.sin(radian)


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _hud(prefix, count):
    """上段2行・下段の残りの行のHUDを作り、(値の列, HUD名)を返す。"""
    from maya import cmds
    values = [""] * count
    names = ["{}HUD{}".format(prefix, i) for i in range(count)]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (count - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return values, names


def _box(name, parent, size, offset, group):
    """parentの子に箱を作り、色を付ける。"""
    from maya import cmds
    box = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    box = cmds.parent(box, parent, relative=True)[0]
    cmds.setAttr(box + ".translate", *offset)
    cmds.sets(box, edit=True, forceElement=group)
    return box


def _car(prefix, z, wheel_group, groups):
    """車体と4つの車輪を作り、(前左, 前右)の車輪のtransformを返す。"""
    from maya import cmds
    car = cmds.createNode("transform", name=prefix + "_CAR")
    cmds.setAttr(car + ".translateZ", z)
    _box(prefix + "_body", car, (3.4, 0.4, 10.0), (0, 0.6, WHEEL_BASE * 0.5), groups["body"])
    wheels = []
    for role, x, front in (("frontLeft", TRACK * 0.5, True), ("frontRight", -TRACK * 0.5, True),
                           ("rearLeft", TRACK * 0.5, False), ("rearRight", -TRACK * 0.5, False)):
        wheel = cmds.createNode("transform", name="{}_{}".format(prefix, role), parent=car)
        cmds.setAttr(wheel + ".translate", x, 0, WHEEL_BASE if front else 0.0)
        _box(wheel + "_GEO", wheel, (0.8, 1.0, 2.2), (0, 0.5, 0), wheel_group if front else groups["rear"])
        wheels.append(wheel)
    return car, wheels


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import AckermannSteering
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"green": _shader("ackermannGreen", (0.15, 0.75, 0.25)), "red": _shader("parallelRed", (0.9, 0.15, 0.1)),
              "body": _shader("bodyGray", (0.35, 0.35, 0.4), 0.3), "rear": _shader("rearDark", (0.2, 0.2, 0.22)),
              "line": _shader("lineYellow", (0.95, 0.85, 0.2)), "hit": _shader("hitWhite", (0.95, 0.95, 0.95))}
    green_car, green = _car("ackermann", 0.0, groups["green"], groups)
    red_car, red = _car("parallel", RED_OFFSET, groups["red"], groups)
    # 緑の車の前輪の車軸の延長線(旋回中心の側だけ表示)と、後輪の軸の延長線。
    lines = {}
    for side in (1, -1):
        for key, wheel in (("left", green[0]), ("right", green[1])):
            lines[(key, side)] = _box("{}_axle{}".format(key, "Plus" if side > 0 else "Minus"), wheel,
                                      (LINE, 0.12, 0.12), (side * LINE * 0.5, 0.3, 0), groups["line"])
        lines[("rear", side)] = _box("rear_axle{}".format("Plus" if side > 0 else "Minus"), green_car,
                                     (LINE, 0.12, 0.12), (side * LINE * 0.5, 0.3, 0), groups["line"])
    hit = cmds.polySphere(name="turnCenter_GEO", radius=0.45)[0]
    cmds.sets(hit, edit=True, forceElement=groups["hit"])
    graph = AckermannSteering.create(green[0], green[1], WHEEL_BASE, name="steering", axis="y")
    owner = str(graph.container)
    camera, camera_shape = cmds.camera(name="ackermannCamera", orthographic=True, orthographicWidth=76)
    cmds.viewPlace(camera_shape, eye=(0, 60, 5.5), lookAt=(0, 0, 5.5), up=(0, 0, 1))
    window = cmds.window("ackermannValidationWindow", title="AckermannSteering - front wheels",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("ackermannValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("ackermann", 7)
    scene = {"owner": owner, "green": green, "red": red, "lines": lines, "hit": hit}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、前輪の角度と旋回中心の一致を独立計算と比較した診断を返す。"""
    from maya import cmds
    steer, ackermann, stage = pose(frame)
    owner, green, red = scene["owner"], scene["green"], scene["red"]
    cmds.setAttr(owner + ".steer", steer)
    cmds.setAttr(owner + ".ackermann", ackermann)
    for wheel in red[:2]:
        cmds.setAttr(wheel + ".rotateY", steer)
    actual = (cmds.getAttr(green[0] + ".rotateY"), cmds.getAttr(green[1] + ".rotateY"))
    expected = expected_angles(steer, ackermann)
    error = max(abs(a - b) for a, b in zip(actual, expected))
    side = 1 if steer >= 0 else -1
    for (key, line_side), line in scene["lines"].items():
        cmds.setAttr(line + ".visibility", abs(steer) > 0.5 and line_side == side)
    hits = [axle_hit(TRACK * 0.5, WHEEL_BASE, actual[0]), axle_hit(-TRACK * 0.5, WHEEL_BASE, actual[1])]
    red_hits = [axle_hit(TRACK * 0.5, WHEEL_BASE, steer), axle_hit(-TRACK * 0.5, WHEEL_BASE, steer)]
    if None in hits:
        gap, red_gap, radius = 0.0, 0.0, None
        cmds.setAttr(scene["hit"] + ".visibility", False)
    else:
        gap = abs(hits[0] - hits[1])
        red_gap = abs(red_hits[0] - red_hits[1])
        radius = WHEEL_BASE / math.tan(math.radians(steer))
        cmds.setAttr(scene["hit"] + ".visibility", True)
        cmds.setAttr(scene["hit"] + ".translate", hits[0], 0.3, 0)
    radius_text = "inf" if radius is None else "{:7.2f}".format(radius)
    values[:] = [
        "GREEN = AckermannSteering front wheels   RED = parallel steering (both wheels = steer)   YELLOW = axle lines   WHITE = left axle hit",
        "STAGE: " + stage,
        "fixed: wheelBase L = {:.1f} cm   trackWidth T = {:.1f} cm   left = +X (screen left)   angles in deg".format(
            WHEEL_BASE, TRACK),
        "R = L / tan(steer)   inner = atan(L / (R - T/2))   outer = atan(L / (R + T/2))   out = ack * exact + (1 - ack) * steer",
        "INPUT steer = {:7.2f} deg   ackermann = {:4.2f}   R = {} cm".format(steer, ackermann, radius_text),
        "OUTPUT left = {:7.2f} deg   right = {:7.2f} deg   axle hits on rear axle: GREEN gap = {:6.3f} cm   RED gap = {:6.3f} cm".format(
            actual[0], actual[1], gap, red_gap),
        "CHECK max |angle - formula| = {:.6f} deg   GREEN gap (judged only when ackermann = 1) = {}".format(
            error, "{:.6f} cm".format(gap) if ackermann > 0.999 else "n/a"),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-3 and (ackermann < 0.999 or gap < 1e-3)
    return {"frame": frame, "presentation_stage": stage, "input": {"steer": steer, "ackermann": ackermann},
            "angles": actual, "expected": expected, "error": error, "gap": gap, "red_gap": red_gap, "ok": ok}


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
        folder = recordVideo("AckermannSteering: 前輪の切れ角", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "ackermann_steering.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-ackermann-steering.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("ackermann-steering-%Y%m%d-%H%M%S")
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
