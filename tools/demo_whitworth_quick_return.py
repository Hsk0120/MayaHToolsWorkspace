"""WhitworthQuickReturn(全周回るレバーと連接棒の早戻り機構)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_whitworth_quick_return.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RADIUS, DISTANCE, ARM, ROD = 3.0, 1.5, 3.0, 8.0
BETA = math.degrees(math.acos(DISTANCE / RADIUS))
REST_X = -math.sqrt(ROD * ROD - ARM * ARM)
# (始まりのフレーム, 終わりのフレーム, 始まりの角度[度], 終わりの角度[度], 補間, 段階名)。等速の区間は線形で補間する。
SEGMENTS = [
    (0, 24, 0.0, 0.0, "hold", "1 REST (PIN FARTHEST FROM THE PIVOT, LEVER UP)"),
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
    """試験側の独立な幾何。ピンへの向き(連続した角度、度)・溝の距離・ラムのワールドX(cm)・戻りかどうかを返す。"""
    theta = math.radians(degrees)
    x, y = RADIUS * math.sin(theta), DISTANCE + RADIUS * math.cos(theta)
    direction = math.degrees(math.atan2(x, y))
    direction += 360.0 * round((degrees - direction) / 360.0)
    phi = math.radians(direction)
    # rotateZ の +φ で +Y の腕の先は (-a sin φ, a cos φ)。ラムは原点を通るX軸上で、腕の先から L 離れた -X 側の点。
    ram = -ARM * math.sin(phi) - math.sqrt(ROD * ROD - (ARM * math.cos(phi)) ** 2)
    return direction, math.hypot(x, y), ram, y < 0.0


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
    from mlrig.setups import WhitworthQuickReturn
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("crankRed", (0.9, 0.15, 0.1)), "green": _shader("leverGreen", (0.15, 0.75, 0.25)),
              "gray": _shader("restGray", (0.45, 0.45, 0.45)), "mark": _shader("markWhite", (0.95, 0.95, 0.9))}
    # クランク(赤): ピボット(原点)の DISTANCE 上。白いピンは中心から RADIUS 上。ピボットは円の内側。
    crank = cmds.createNode("transform", name="crank_CRANK")
    cmds.setAttr(crank + ".translateY", DISTANCE)
    disk = cmds.polyCylinder(name="crank_DISK", radius=RADIUS + 0.5, height=0.2, axis=(0, 0, 1))[0]
    disk = cmds.parent(disk, crank, relative=True)[0]
    cmds.setAttr(disk + ".translateZ", -0.6)
    cmds.sets(disk, edit=True, forceElement=groups["red"])
    pin = cmds.polyCylinder(name="crank_PIN", radius=0.25, height=1.0, axis=(0, 0, 1))[0]
    pin = cmds.parent(pin, crank, relative=True)[0]
    cmds.setAttr(pin + ".translate", 0, RADIUS, 0.3)
    cmds.sets(pin, edit=True, forceElement=groups["mark"])
    # 灰色: ラムのレール(ピボットを通るX軸、動かない目印)と、ラムの行程の両端。
    _box("ram_RAIL", None, (ARM * 2 + 6.0, 0.12, 0.05), (REST_X, -0.5, -0.8), groups["gray"])
    for side in (-1, 1):
        _box("ram_END" + ("L" if side < 0 else "R"), None, (0.12, 1.2, 0.05), (REST_X + side * ARM, -0.5, -0.8), groups["gray"])
    # レバー(緑): 原点がピボット、+Y がレバーの向き。2本の棒の間が溝(ピンが通る線)。下へ伸びる腕の代わりに、
    # 上の溝と同じ向きの腕(長さ ARM)の先に連接棒をつなぐ。
    lever = cmds.createNode("transform", name="lever_LEVER")
    length = RADIUS + DISTANCE + 0.6
    for side in (-1, 1):
        _box("lever_GEO" + ("L" if side < 0 else "R"), lever, (0.2, length, 0.2), (side * 0.35, length / 2.0, 0), groups["green"])
    armEnd = cmds.createNode("transform", name="lever_ARMEND", parent=lever)
    cmds.setAttr(armEnd + ".translate", 0, ARM, 0.6)
    _box("lever_ARMMARK", armEnd, (0.4, 0.4, 0.4), (0, 0, 0), groups["mark"])
    # ラム(緑): ピボットを通るX軸の上を動く箱。rotateZ の +φ で腕の先は -X へ動くので ramDirection = -1。
    ram = cmds.createNode("transform", name="ram_RAM")
    cmds.setAttr(ram + ".translateX", REST_X)
    _box("ram_GEO", ram, (2.4, 0.9, 0.6), (0, 0, 0.6), groups["green"])
    graph = WhitworthQuickReturn.create(crank, lever, ram, RADIUS, DISTANCE, ARM, ROD, name="whitworth", axis="z",
                                        ramAxis="x", ramDirection=-1.0)
    owner = graph.container
    # 連接棒(白): 腕の先に置き、ラムへ向ける表示用の棒(リグの外。判定ではDGと独立に長さを測る)。
    rod = cmds.createNode("transform", name="rod_ROD")
    _box("rod_GEO", rod, (ROD, 0.16, 0.16), (ROD / 2.0, 0, 0), groups["mark"])
    cmds.pointConstraint(armEnd, rod)
    cmds.aimConstraint(ram, rod, aimVector=(1, 0, 0), upVector=(0, 0, 1), worldUpType="vector", worldUpVector=(0, 0, 1))
    camera, camera_shape = cmds.camera(name="wqrCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(-10.0, -1.0, 32), lookAt=(-10.0, -1.0, 0))
    window = cmds.window("wqrValidationWindow", title="WhitworthQuickReturn - full-turn lever and rod",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("wqrValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("whitworth", 8)
    scene = {"owner": owner, "crank": crank, "lever": lever, "ram": ram, "pin": pin, "armEnd": armEnd}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、レバー・ラムを試験側の幾何と、ピンとレバーの直線の距離・連接棒の長さで比較した診断を返す。"""
    from maya import cmds
    angle, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(scene["crank"] + ".rotateZ", angle)
    lean_expected, slot_expected, ram_expected, back = expected(angle)
    lean = cmds.getAttr(scene["lever"] + ".rotateZ")
    ram = cmds.getAttr(scene["ram"] + ".translateX")
    slot = cmds.getAttr(owner + ".slotDistance")
    lag = cmds.getAttr(owner + ".lag")
    speed = cmds.getAttr(owner + ".speedRatio")
    stroke = cmds.getAttr(owner + ".returnStroke")
    error = max(abs(lean - lean_expected), abs(slot - slot_expected), abs(ram - ram_expected))
    # 試験側で独立に: ピンのワールド位置が、ピボット(原点)からレバーの +Y 軸(ワールド)の向きの半直線の上にあるか。
    pin = cmds.xform(scene["pin"], query=True, worldSpace=True, translation=True)
    axis = cmds.xform(scene["lever"], query=True, worldSpace=True, matrix=True)[4:6]
    line_error = abs(pin[0] * axis[1] - pin[1] * axis[0]) / math.hypot(*axis)
    ahead = pin[0] * axis[0] + pin[1] * axis[1] > 0.0
    # 連接棒の長さ: 腕の先とラムのワールド位置の距離が L のまま。
    end = cmds.xform(scene["armEnd"], query=True, worldSpace=True, translation=True)
    rod_error = abs(math.hypot(end[0] - ram, end[1]) - ROD)
    values[:] = [
        "RED = crank (INPUT, rotateZ, white = pin)   GREEN = full-turn lever + ram (OUTPUT)   WHITE = rod   GRAY = rail / stroke ends   cm / deg",
        "STAGE: " + stage,
        "fixed: r = {:.1f}  d = {:.1f}  a = {:.1f}  L = {:.1f} cm   beta = acos(d/r) = {:.1f}   OUT = 360 - 2 beta = {:.0f}   BACK = 2 beta = {:.0f} deg".format(
            RADIUS, DISTANCE, ARM, ROD, BETA, 360.0 - 2.0 * BETA, 2.0 * BETA),
        "lag = atan2(-d sin(theta), r + d cos(theta))   phi = theta + lag   ram = -(a sin(phi) + sqrt(L^2 - a^2 cos^2(phi)))",
        "speedRatio = dphi/dtheta = r (r + d cos(theta)) / rho^2   ({:.3f} .. {:.3f})   timeRatio = {:.3f}   stroke = 2a = {:.1f} cm".format(
            RADIUS / (RADIUS + DISTANCE), RADIUS / (RADIUS - DISTANCE), (180.0 - BETA) / BETA, 2.0 * ARM),
        "INPUT theta = {:7.2f} deg   ({:6.2f} in the turn)   stroke = {}".format(
            angle, angle % 360.0, "BACK (fast)" if stroke > 0.5 else "OUT (slow)"),
        "OUTPUT (DG) phi = {:8.3f} deg   lag = {:7.3f} deg   rho = {:6.3f} cm   ram x = {:7.3f} cm   speedRatio = {:6.4f}".format(
            lean, lag, slot, ram, speed),
        "CHECK |DG - geometry| = {:.6f}   |pin - lever line| = {:.6f} cm   |rod - L| = {:.6f} cm".format(
            error, line_error, rod_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and line_error < 1e-4 and ahead and rod_error < 1e-4 and (stroke > 0.5) == back
    return {"frame": frame, "presentation_stage": stage, "input": {"crank": angle},
            "output": {"leverAngle": lean, "lag": lag, "slotDistance": slot, "ram": ram, "speedRatio": speed,
                       "returnStroke": stroke},
            "error": error, "line_error": line_error, "rod_error": rod_error, "ok": ok}


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
        folder = recordVideo("WhitworthQuickReturn: 全周回るレバーと連接棒の早戻り", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "whitworth_quick_return.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-whitworth-quick-return.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("whitworth-quick-return-%Y%m%d-%H%M%S")
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
