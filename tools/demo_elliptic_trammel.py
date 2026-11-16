"""EllipticTrammel(直交する溝の2つのスライダーと棒で楕円を描く楕円トランメル)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_elliptic_trammel.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LENGTH = 4.0
PEN = 6.0
# (始まりのフレーム, 終わりのフレーム, 始まりの角度[度], 終わりの角度[度], 補間, 段階名)。等速の区間は線形で補間する。
SEGMENTS = [
    (0, 24, 0.0, 0.0, "hold", "1 REST (ROD LIES ON THE X SLOT, A AT +L, B AT THE CROSSING)"),
    (24, 264, 0.0, 720.0, "linear", "2 CRANK AT CONSTANT SPEED, 2 TURNS (ROD TURNS THE OTHER WAY, PEN DRAWS THE ELLIPSE)"),
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
    """試験側の独立な式。スライダーAのx、スライダーBのy、棒の角度(度)、棒の上の点のx・yを返す。"""
    theta = math.radians(degrees)
    return (LENGTH * math.cos(theta), LENGTH * math.sin(theta), 180.0 - degrees,
            (LENGTH - PEN) * math.cos(theta), PEN * math.sin(theta))


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
    from mlrig.setups import EllipticTrammel
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("crankRed", (0.9, 0.15, 0.1)), "green": _shader("sliderGreen", (0.15, 0.75, 0.25)),
              "gray": _shader("slotGray", (0.45, 0.45, 0.45)), "blue": _shader("rodBlue", (0.2, 0.45, 0.95)),
              "yellow": _shader("penYellow", (0.95, 0.85, 0.1))}
    # 灰色: 横(X)と縦(Y)の溝。交点が原点。
    _box("slot_X", None, (2.0 * PEN + 2.0, 0.25, 0.05), (0, 0, -1.0), groups["gray"])
    _box("slot_Y", None, (0.25, 2.0 * PEN + 2.0, 0.05), (0, 0, -1.0), groups["gray"])
    # 灰色のカーブ: 棒の上の点が描くはずの楕円(半軸 |L - d|・d、動かない目印)。
    ellipse = cmds.circle(name="ellipse_GUIDE", normal=(0, 0, 1), radius=1.0, sections=64)[0]
    cmds.setAttr(ellipse + ".scale", abs(LENGTH - PEN), PEN, 1.0)
    cmds.setAttr(ellipse + ".overrideEnabled", True)
    cmds.setAttr(ellipse + ".overrideColor", 2)
    # クランク(赤): 原点から棒の中点(L/2)への腕。
    crank = cmds.createNode("transform", name="crank_CRANK")
    _box("crank_ARM", crank, (LENGTH * 0.5, 0.3, 0.2), (LENGTH * 0.25, 0, -0.5), groups["red"])
    # スライダー(緑): Aは横の溝の +L、Bは交点。
    slider_a = cmds.createNode("transform", name="slider_A")
    cmds.setAttr(slider_a + ".translateX", LENGTH)
    _box("slider_AGEO", slider_a, (1.0, 0.7, 0.4), (0, 0, 0), groups["green"])
    slider_b = cmds.createNode("transform", name="slider_B")
    _box("slider_BGEO", slider_b, (0.7, 1.0, 0.4), (0, 0, 0), groups["green"])
    # 棒(青): Aの子。rotateZ = 180 で -X(Bの向き)へ伸び、先(Aから d)に黄色の点。
    rod = cmds.createNode("transform", name="rod_ROD", parent=slider_a)
    cmds.setAttr(rod + ".rotateZ", 180.0)
    _box("rod_GEO", rod, (PEN, 0.18, 0.2), (PEN * 0.5, 0, 0.3), groups["blue"])
    pen = cmds.polySphere(name="rod_PEN", radius=0.35)[0]
    pen = cmds.parent(pen, rod, relative=True)[0]
    cmds.setAttr(pen + ".translate", PEN, 0, 0.4)
    cmds.sets(pen, edit=True, forceElement=groups["yellow"])
    graph = EllipticTrammel.create(crank, slider_a, slider_b, rod, LENGTH, PEN, name="ellipticTrammel", axis="z",
                                   aAxis="x", bAxis="y")
    owner = graph.container
    camera, camera_shape = cmds.camera(name="etCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(-3.5, -0.3, 32), lookAt=(-3.5, -0.3, 0))
    window = cmds.window("etValidationWindow", title="EllipticTrammel - two sliders draw an ellipse",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("etValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("ellipticTrammel", 8)
    scene = {"owner": owner, "crank": crank, "a": slider_a, "b": slider_b, "rod": rod, "pen": pen}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、スライダー・棒・点を試験側の式と、棒の長さ・楕円の式で比較した診断を返す。"""
    from maya import cmds
    angle, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(scene["crank"] + ".rotateZ", angle)
    a_expected, b_expected, rod_expected, x_expected, y_expected = expected(angle)
    a = cmds.getAttr(scene["a"] + ".translateX")
    b = cmds.getAttr(scene["b"] + ".translateY")
    rod = cmds.getAttr(scene["rod"] + ".rotateZ")
    pen_x = cmds.getAttr(owner + ".penX")
    pen_y = cmds.getAttr(owner + ".penY")
    rod_angle = cmds.getAttr(owner + ".rodAngle")
    error = max(abs(a - a_expected), abs(b - b_expected), abs(rod - rod_expected), abs(rod_angle + angle),
                abs(pen_x - (x_expected - (LENGTH - PEN))), abs(pen_y - y_expected))
    # 試験側で独立に: |AB| = L、点のワールド位置は楕円の上で、A (a, 0) と B (0, b) を通る直線の上。
    pen = cmds.xform(scene["pen"], query=True, worldSpace=True, translation=True)
    length_error = abs(math.hypot(a, b) - LENGTH)
    ellipse_error = abs((pen[0] / (LENGTH - PEN)) ** 2 + (pen[1] / PEN) ** 2 - 1.0)
    line_error = abs((pen[0] - a) * b + pen[1] * a) / LENGTH
    values[:] = [
        "RED = crank (INPUT, rotateZ)   GREEN = sliders A (x) / B (y) (OUTPUT)   BLUE = rod   YELLOW = pen   GRAY = slots / expected ellipse   cm / deg",
        "STAGE: " + stage,
        "fixed: L = {:.1f} cm (A to B)   d = {:.1f} cm (A to pen)   semi axes |L - d| = {:.1f} cm (x), d = {:.1f} cm (y)".format(
            LENGTH, PEN, abs(LENGTH - PEN), PEN),
        "A x = L cos(theta)   B y = L sin(theta)   rod = 180 - theta   pen = ((L - d) cos(theta), d sin(theta))",
        "INPUT theta = {:7.2f} deg   ({:6.2f} in the turn)".format(angle, angle % 360.0),
        "OUTPUT (DG) A x = {:7.3f}   B y = {:7.3f}   rod = {:8.2f} deg   pen x = {:7.3f}   pen y = {:7.3f} cm".format(
            a, b, rod, pen[0], pen[1]),
        "CHECK |AB| - L = {:.6f} cm   (x/(L-d))^2 + (y/d)^2 - 1 = {:.6f}".format(length_error, ellipse_error),
        "CHECK |DG - formula| = {:.6f}   pen distance from line AB = {:.6f} cm".format(error, line_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and length_error < 1e-4 and ellipse_error < 1e-4 and line_error < 1e-4
    return {"frame": frame, "presentation_stage": stage, "input": {"crank": angle},
            "output": {"a": a, "b": b, "rod": rod, "rodAngle": rod_angle, "penX": pen_x, "penY": pen_y,
                       "penWorld": pen},
            "error": error, "length_error": length_error, "ellipse_error": ellipse_error, "line_error": line_error,
            "ok": ok}


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
        folder = recordVideo("EllipticTrammel: 2つのスライダーと棒で描く楕円", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "elliptic_trammel.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-elliptic-trammel.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("elliptic-trammel-%Y%m%d-%H%M%S")
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
