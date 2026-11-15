"""ScotchYoke(溝付きのヨークを単振動で往復させるスコッチヨーク)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_scotch_yoke.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RADIUS = 3.0
# (始まりのフレーム, 終わりのフレーム, 始まりの角度[度], 終わりの角度[度], 補間, 段階名)。等速の区間は線形で補間する。
SEGMENTS = [
    (0, 24, 0.0, 0.0, "hold", "1 REST (PIN ON +X, YOKE AT THE + END OF THE STROKE)"),
    (24, 264, 0.0, 720.0, "linear", "2 CRANK AT CONSTANT SPEED, 2 TURNS (PURE HARMONIC, SAME SPEED OUT AND BACK)"),
    (264, 324, 720.0, 540.0, "smooth", "3 REVERSE HALF A TURN (SAME PATH BACKWARD)"),
    (324, 384, 540.0, 720.0, "smooth", "4 FORWARD TO 720 deg = REST"),
    (384, 408, 720.0, 720.0, "hold", "4 FORWARD TO 720 deg = REST"),
]
FRAMES = SEGMENTS[-1][1]


def pose(frame):
    """フレームのクランクの角度と段階名を返す(等速の区間は線形、それ以外はsmoothstep)。"""
    for start, end, first, last, mode, stage in SEGMENTS:
        if frame <= end:
            weight = 0.0 if end == start else min(max((frame - start) / float(end - start), 0.0), 1.0)
            if mode == "smooth":
                weight = weight * weight * (3 - 2 * weight)
            return first + (last - first) * weight, stage
    return SEGMENTS[-1][3], SEGMENTS[-1][5]


def expected(degrees):
    """試験側の独立な式。ピンの位置 x・y、速さ、加速度、戻りかどうかを返す。"""
    theta = math.radians(degrees)
    x, y = RADIUS * math.cos(theta), RADIUS * math.sin(theta)
    return x, y, -RADIUS * math.sin(theta), -RADIUS * math.cos(theta), math.sin(theta) < 0.0


def _shader(name, color):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
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


def _box(name, parent, size, translate, group):
    """parent(Noneならワールド)の下へ箱を作り、色を付けて返す。"""
    from maya import cmds
    node = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    if parent:
        node = cmds.parent(node, parent, relative=True)[0]
    cmds.setAttr(node + ".translate", *translate)
    cmds.sets(node, edit=True, forceElement=group)
    return node


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import ScotchYoke
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("crankRed", (0.9, 0.15, 0.1)), "green": _shader("yokeGreen", (0.15, 0.75, 0.25)),
              "gray": _shader("restGray", (0.45, 0.45, 0.45)), "mark": _shader("markWhite", (0.95, 0.95, 0.9)),
              "dark": _shader("blockDark", (0.05, 0.4, 0.12))}
    # クランク(赤): 原点。白いピンは中心から RADIUS の +X(θ = 0)。
    crank = cmds.createNode("transform", name="crank_CRANK")
    disk = cmds.polyCylinder(name="crank_DISK", radius=RADIUS + 0.5, height=0.2, axis=(0, 0, 1))[0]
    disk = cmds.parent(disk, crank, relative=True)[0]
    cmds.setAttr(disk + ".translateZ", -0.8)
    cmds.sets(disk, edit=True, forceElement=groups["red"])
    pin = cmds.polyCylinder(name="crank_PIN", radius=0.25, height=1.4, axis=(0, 0, 1))[0]
    pin = cmds.parent(pin, crank, relative=True)[0]
    cmds.setAttr(pin + ".translate", RADIUS, 0, 0.2)
    cmds.sets(pin, edit=True, forceElement=groups["mark"])
    # 灰色: ヨークの行程の両端(x = -RADIUS・+RADIUS、動かない目印)。
    for side in (-1, 1):
        _box("stroke_END" + ("L" if side < 0 else "R"), None, (0.1, 2.0 * RADIUS + 3.0, 0.05),
             (side * RADIUS, 0, -1.2), groups["gray"])
    # ヨーク(緑): 原点が溝の中心線。2本の縦の棒の間が溝(ピンが通る)、右へ伸びる棒がヨークの軸。
    yoke = cmds.createNode("transform", name="yoke_YOKE")
    cmds.setAttr(yoke + ".translateX", RADIUS)
    height = 2.0 * RADIUS + 1.2
    for side in (-1, 1):
        _box("yoke_GEO" + ("L" if side < 0 else "R"), yoke, (0.2, height, 0.3), (side * 0.45, 0, 0), groups["green"])
        _box("yoke_CAP" + ("B" if side < 0 else "T"), yoke, (1.1, 0.2, 0.3), (0, side * height / 2.0, 0),
             groups["green"])
    _box("yoke_SHAFT", yoke, (8.0, 0.35, 0.3), (4.55, 0, 0), groups["green"])
    # ブロック(濃い緑): ヨークの子。溝の中をピンと一緒に Y へ動く。
    block = cmds.createNode("transform", name="yoke_BLOCK", parent=yoke)
    _box("yoke_BLOCKGEO", block, (0.65, 0.9, 0.5), (0, 0, 0.1), groups["dark"])
    graph = ScotchYoke.create(crank, yoke, block, RADIUS, name="scotchYoke", axis="z", yokeAxis="x", blockAxis="y")
    owner = graph.container
    camera, camera_shape = cmds.camera(name="syCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(3.0, -3.2, 38), lookAt=(3.0, -3.2, 0))
    window = cmds.window("syValidationWindow", title="ScotchYoke - pure harmonic slotted yoke", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("syValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("scotchYoke", 8)
    scene = {"owner": owner, "crank": crank, "yoke": yoke, "block": block, "pin": pin}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、ヨーク・ブロックを試験側の式と、ピンのワールド位置(溝の中心線・ブロックの中心)で比較した診断を返す。"""
    from maya import cmds
    angle, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(scene["crank"] + ".rotateZ", angle)
    x_expected, y_expected, velocity_expected, acceleration_expected, back = expected(angle)
    yoke = cmds.getAttr(scene["yoke"] + ".translateX")
    block = cmds.getAttr(scene["block"] + ".translateY")
    velocity = cmds.getAttr(owner + ".velocity")
    acceleration = cmds.getAttr(owner + ".acceleration")
    travel = cmds.getAttr(owner + ".travel")
    stroke = cmds.getAttr(owner + ".returnStroke")
    error = max(abs(yoke - x_expected), abs(block - y_expected), abs(velocity - velocity_expected),
                abs(acceleration - acceleration_expected), abs(travel - (RADIUS - x_expected) / (2.0 * RADIUS)))
    # 試験側で独立に: ピンのワールド位置が、ヨークの溝の中心線(ワールドX)の上と、ブロックの中心にあるか。
    pin = cmds.xform(scene["pin"], query=True, worldSpace=True, translation=True)
    centre = cmds.xform(scene["block"], query=True, worldSpace=True, translation=True)
    slot_error = abs(pin[0] - cmds.xform(scene["yoke"], query=True, worldSpace=True, translation=True)[0])
    block_error = math.hypot(pin[0] - centre[0], pin[1] - centre[1])
    values[:] = [
        "RED = crank (INPUT, rotateZ, white = pin)   GREEN = yoke (OUTPUT, translateX)   DARK GREEN = block in the slot   GRAY = stroke ends   cm / deg",
        "STAGE: " + stage,
        "fixed: r = {:.1f} cm   stroke = 2r = {:.1f} cm   out = back = 180 deg (no quick return)".format(RADIUS, 2.0 * RADIUS),
        "yoke x = r cos(theta)   block y = r sin(theta)   velocity = dx/dtheta = -r sin(theta)   acceleration = -r cos(theta)",
        "travel = (1 - cos(theta)) / 2   returnStroke = (sin(theta) < 0)",
        "INPUT theta = {:7.2f} deg   ({:6.2f} in the turn)   stroke = {}".format(
            angle, angle % 360.0, "BACK to + end" if stroke > 0.5 else "OUT to - end"),
        "OUTPUT (DG) yoke x = {:7.3f} cm   block y = {:7.3f} cm   velocity = {:7.3f}   acceleration = {:7.3f}   travel = {:5.3f}".format(
            yoke, block, velocity, acceleration, travel),
        "CHECK |DG - formula| = {:.6f}   |pin - slot centre line| = {:.6f} cm   |pin - block| = {:.6f} cm".format(
            error, slot_error, block_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and slot_error < 1e-4 and block_error < 1e-4 and (stroke > 0.5) == back
    return {"frame": frame, "presentation_stage": stage, "input": {"crank": angle},
            "output": {"yoke": yoke, "block": block, "velocity": velocity, "acceleration": acceleration,
                       "travel": travel, "returnStroke": stroke},
            "error": error, "slot_error": slot_error, "block_error": block_error, "ok": ok}


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
        folder = recordVideo("ScotchYoke: 溝付きのヨークの単振動", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "scotch_yoke.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-scotch-yoke.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("scotch-yoke-%Y%m%d-%H%M%S")
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
