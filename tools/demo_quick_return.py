"""QuickReturn(クランクとスロット付きレバーの早戻り機構)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_quick_return.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RADIUS, DISTANCE, HEIGHT = 2.0, 5.0, 8.0
HALF = math.degrees(math.asin(RADIUS / DISTANCE))
# (始まりのフレーム, 終わりのフレーム, 始まりの角度[度], 終わりの角度[度], 補間, 段階名)。等速の区間は線形で補間する。
SEGMENTS = [
    (0, 24, 0.0, 0.0, "hold", "1 REST (PIN FARTHEST FROM THE PIVOT, LEVER CENTERED)"),
    (24, 264, 0.0, 720.0, "linear", "2 CRANK AT CONSTANT SPEED, 2 TURNS (SLOW OUT, FAST BACK)"),
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
    """試験側の独立な幾何。ピンの位置からレバーの振れ(度)・溝の距離・ラムの移動(cm)・戻りかどうかを返す。"""
    theta = math.radians(degrees)
    x, y = RADIUS * math.sin(theta), DISTANCE + RADIUS * math.cos(theta)
    back = math.cos(theta) < -RADIUS / DISTANCE
    return math.degrees(math.atan2(x, y)), math.hypot(x, y), HEIGHT * x / y, back


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
    from mlrig.setups import QuickReturn
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("crankRed", (0.9, 0.15, 0.1)), "green": _shader("leverGreen", (0.15, 0.75, 0.25)),
              "gray": _shader("restGray", (0.45, 0.45, 0.45)), "mark": _shader("markWhite", (0.95, 0.95, 0.9))}
    # クランク(赤): ピボット(原点)の DISTANCE 上。白いピンは中心から RADIUS 上。
    crank = cmds.createNode("transform", name="crank_CRANK")
    cmds.setAttr(crank + ".translateY", DISTANCE)
    disk = cmds.polyCylinder(name="crank_DISK", radius=RADIUS + 0.5, height=0.2, axis=(0, 0, 1))[0]
    disk = cmds.parent(disk, crank, relative=True)[0]
    cmds.setAttr(disk + ".translateZ", -0.4)
    cmds.sets(disk, edit=True, forceElement=groups["red"])
    pin = cmds.polyCylinder(name="crank_PIN", radius=0.25, height=0.6, axis=(0, 0, 1))[0]
    pin = cmds.parent(pin, crank, relative=True)[0]
    cmds.setAttr(pin + ".translate", 0, RADIUS, 0.3)
    cmds.sets(pin, edit=True, forceElement=groups["mark"])
    # 灰色: レバーの中央の位置と、ラムのレール(動かない目印)。
    _box("lever_REST", None, (0.12, HEIGHT + 1.0, 0.05), (0, (HEIGHT + 1.0) / 2.0, -0.8), groups["gray"])
    _box("ram_RAIL", None, (16.0, 0.12, 0.05), (0, HEIGHT + 0.45, -0.8), groups["gray"])
    # レバー(緑): 原点がピボット、+Y がレバーの向き。2本の棒の間が溝(ピンが通る線)。
    lever = cmds.createNode("transform", name="lever_LEVER")
    for side in (-1, 1):
        _box("lever_GEO" + ("L" if side < 0 else "R"), lever, (0.2, HEIGHT + 1.0, 0.2), (side * 0.35, (HEIGHT + 1.0) / 2.0, 0), groups["green"])
    # ラム(緑): 高さ HEIGHT の横の棒。rotateZ の +φ でレバーの先は -X へ倒れるので、ramHeight は負で与える。
    ram = cmds.createNode("transform", name="ram_RAM")
    cmds.setAttr(ram + ".translateY", HEIGHT)
    _box("ram_GEO", ram, (6.0, 0.6, 0.3), (0, 0.45, 0.4), groups["green"])
    graph = QuickReturn.create(crank, lever, ram, RADIUS, DISTANCE, -HEIGHT, name="quickReturn", axis="z",
                               ramAxis="x")
    owner = graph.container
    camera, camera_shape = cmds.camera(name="qrCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(-10.5, 3.0, 36), lookAt=(-10.5, 3.0, 0))
    window = cmds.window("qrValidationWindow", title="QuickReturn - slotted lever, slow out and fast back",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("qrValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("quickReturn", 8)
    scene = {"owner": owner, "crank": crank, "lever": lever, "ram": ram, "pin": pin}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、レバー・ラムを試験側の幾何と、ピンとレバーの直線の距離で比較した診断を返す。"""
    from maya import cmds
    angle, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(scene["crank"] + ".rotateZ", angle)
    lean_expected, slot_expected, ram_expected, back = expected(angle)
    lean = cmds.getAttr(scene["lever"] + ".rotateZ")
    ram = cmds.getAttr(scene["ram"] + ".translateX")
    slot = cmds.getAttr(owner + ".slotDistance")
    speed = cmds.getAttr(owner + ".speedRatio")
    stroke = cmds.getAttr(owner + ".returnStroke")
    # ramHeight を負で与えたので、ラムの translateX は -H tan φ。
    error = max(abs(lean - lean_expected), abs(slot - slot_expected), abs(-ram - ram_expected))
    # 試験側で独立に: ピンのワールド位置と、ピボット(原点)を通るレバーの +Y 軸(ワールド)の直線の距離。
    pin = cmds.xform(scene["pin"], query=True, worldSpace=True, translation=True)
    axis = cmds.xform(scene["lever"], query=True, worldSpace=True, matrix=True)[4:6]
    line_error = abs(pin[0] * axis[1] - pin[1] * axis[0]) / math.hypot(*axis)
    values[:] = [
        "RED = crank (INPUT, rotateZ, white = pin)   GREEN = slotted lever + ram (OUTPUT)   GRAY = center / rail   cm / deg",
        "STAGE: " + stage,
        "fixed: r = {:.1f} cm   d = {:.1f} cm   H = {:.1f} cm   alpha = asin(r/d) = {:.2f}   OUT = 180 + 2 alpha = {:.1f}   BACK = {:.1f} deg".format(
            RADIUS, DISTANCE, HEIGHT, HALF, 180.0 + 2.0 * HALF, 180.0 - 2.0 * HALF),
        "x = r sin(theta)   y = d + r cos(theta)   phi = atan2(x, y)   rho = sqrt(x^2 + y^2)   ram = H x / y = H tan(phi)",
        "speedRatio = dphi/dtheta = r (r + d cos(theta)) / rho^2   (< 0 = BACK stroke)   timeRatio = {:.3f}".format(
            (180.0 + 2.0 * HALF) / (180.0 - 2.0 * HALF)),
        "INPUT theta = {:7.2f} deg   ({:6.2f} in the turn)   stroke = {}".format(
            angle, angle % 360.0, "BACK (fast)" if stroke > 0.5 else "OUT (slow)"),
        "OUTPUT (DG) phi = {:7.3f} deg   rho = {:6.3f} cm   ram = {:7.3f} cm   speedRatio = {:7.4f}".format(
            lean, slot, -ram, speed),
        "CHECK |DG - geometry| = {:.6f}   |pin - lever line| = {:.6f} cm".format(error, line_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and line_error < 1e-4 and (stroke > 0.5) == back
    return {"frame": frame, "presentation_stage": stage, "input": {"crank": angle},
            "output": {"leverAngle": lean, "slotDistance": slot, "ram": ram, "speedRatio": speed,
                       "returnStroke": stroke},
            "error": error, "line_error": line_error, "ok": ok}


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
        folder = recordVideo("QuickReturn: クランクとスロット付きレバーの早戻り", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "quick_return.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-quick-return.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("quick-return-%Y%m%d-%H%M%S")
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
