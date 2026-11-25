"""Pantograph(なぞる点の動きを固定点を中心に一定の倍率で写す平行四辺形リンク)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_pantograph.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARM = 4.0
LINK = 3.0
RATIO = 1.5
NEAREST = ARM - LINK
FARTHEST = ARM + LINK
START = (4.0, 2.0)
SQUARE = [(4.0, 2.0), (5.0, 2.0), (5.0, 4.0), (3.0, 4.0), (3.0, 2.0), (4.0, 2.0)]
# (始まりのフレーム, 終わりのフレーム, 始まりの位置, 終わりの位置, 補間, 段階名)。位置は固定点から見たなぞる点の (u, v) cm。
SEGMENTS = [(0, 24, START, START, "hold", "1 REST (TRACER INSIDE THE REACH)")]
for index in range(5):
    SEGMENTS.append((24 + 20 * index, 44 + 20 * index, SQUARE[index], SQUARE[index + 1], "linear",
                     "2 TRACE A SQUARE (PEN DRAWS THE SAME SQUARE 1.5 TIMES LARGER)"))
SEGMENTS += [
    (124, 172, START, (10.0, 5.0), "linear", "3 TRACER BEYOND THE FAR LIMIT a + b (LINKAGE STOPS STRAIGHT, excess > 0)"),
    (172, 220, (10.0, 5.0), (-2.0, 9.0), "smooth", "4 SWEEP OUTSIDE (LINKAGE FOLLOWS THE DIRECTION ON THE LIMIT CIRCLE)"),
    (220, 280, (-2.0, 9.0), (0.3, 0.3), "smooth", "5 THROUGH THE REACH TO INSIDE THE NEAR LIMIT |a - b| (excess < 0)"),
    (280, 304, (0.3, 0.3), (0.5, -0.4), "linear", "5 THROUGH THE REACH TO INSIDE THE NEAR LIMIT |a - b| (excess < 0)"),
    (304, 352, (0.5, -0.4), START, "smooth", "6 BACK INTO THE REACH AND TO REST"),
    (352, 376, START, START, "hold", "6 BACK INTO THE REACH AND TO REST"),
]
FRAMES = SEGMENTS[-1][1]


def pose(frame):
    """フレームのなぞる点の位置 (u, v) と段階名を返す(等速の区間は線形、それ以外はsmoothstep)。"""
    for start, end, first, last, mode, stage in SEGMENTS:
        if frame <= end:
            weight = 0.0 if end == start else min(max((frame - start) / float(end - start), 0.0), 1.0)
            if mode == "smooth":
                weight = weight * weight * (3 - 2 * weight)
            return (first[0] + (last[0] - first[0]) * weight, first[1] + (last[1] - first[1]) * weight), stage
    return SEGMENTS[-1][3], SEGMENTS[-1][5]


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


def _bar(name, owner, first, second, color, width):
    """containerの出力の2点 (first, second) を結ぶ直線のカーブを作る。first・second は "p"・"a" など。"""
    from maya import cmds
    curve = cmds.curve(name=name, degree=1, point=[(0, 0, 0.6), (1, 0, 0.6)])
    shape = cmds.listRelatives(curve, shapes=True)[0]
    for index, point in enumerate((first, second)):
        for axis, coordinate in (("x", "U"), ("y", "V")):
            cmds.connectAttr("{}.{}{}".format(owner, point, coordinate),
                             "{}.controlPoints[{}].{}Value".format(shape, index, axis))
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideRGBColors", True)
    cmds.setAttr(shape + ".overrideColorRGB", *color, type="double3")
    cmds.setAttr(shape + ".lineWidth", width)
    return curve


def _guide(name, points=None, radius=None):
    """動かない灰色の目印(折れ線か円)を作る。"""
    from maya import cmds
    if radius is not None:
        guide = cmds.circle(name=name, normal=(0, 0, 1), radius=radius, sections=64)[0]
    else:
        guide = cmds.curve(name=name, degree=1, point=[(u, v, 0.0) for u, v in points])
    cmds.setAttr(guide + ".overrideEnabled", True)
    cmds.setAttr(guide + ".overrideColor", 2)
    return guide


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import Pantograph
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("tracerRed", (0.9, 0.15, 0.1)), "green": _shader("penGreen", (0.15, 0.8, 0.25)),
              "gray": _shader("pivotGray", (0.5, 0.5, 0.5)), "blue": _shader("armBlue", (0.2, 0.45, 0.95))}
    # 灰色: 固定点 O、P が届く範囲の2つの円、なぞる四角と、ペンが描くはずの k 倍の四角(動かない目印)。
    pivot = cmds.polyCylinder(name="pivot_O", radius=0.3, height=0.2, axis=(0, 0, 1))[0]
    cmds.setAttr(pivot + ".translateZ", -0.5)
    cmds.sets(pivot, edit=True, forceElement=groups["gray"])
    _guide("nearLimit_GUIDE", radius=NEAREST)
    _guide("farLimit_GUIDE", radius=FARTHEST)
    _guide("square_GUIDE", points=SQUARE)
    _guide("scaledSquare_GUIDE", points=[(RATIO * u, RATIO * v) for u, v in SQUARE])
    rest = Pantograph.motion(START[0], START[1], ARM, LINK, RATIO)
    # なぞる点(赤): 入力の transform。
    tracer = cmds.createNode("transform", name="tracer_INPUT")
    cmds.setAttr(tracer + ".translate", START[0], START[1], 0.0)
    sphere = cmds.parent(cmds.polySphere(name="tracer_GEO", radius=0.3)[0], tracer, relative=True)[0]
    cmds.setAttr(sphere + ".translateZ", 1.0)
    cmds.sets(sphere, edit=True, forceElement=groups["red"])
    # 腕 O-A と、その子の棒 A-P (青)。生成時の向きを Python 版の角度に合わせる。
    arm = cmds.createNode("transform", name="arm_OA")
    cmds.setAttr(arm + ".rotateZ", math.degrees(rest["armAngle"]))
    _box("arm_GEO", arm, (ARM, 0.25, 0.2), (ARM * 0.5, 0, 0.0), groups["blue"])
    link = cmds.createNode("transform", name="link_AP", parent=arm)
    cmds.setAttr(link + ".translateX", ARM)
    cmds.setAttr(link + ".rotateZ", math.degrees(rest["linkAngle"] - rest["armAngle"]))
    _box("link_GEO", link, (LINK, 0.25, 0.2), (LINK * 0.5, 0, 0.2), groups["blue"])
    link_tip = cmds.createNode("transform", name="link_TIP", parent=link)
    cmds.setAttr(link_tip + ".translateX", LINK)
    # ペン(緑): Q = k P。
    pen = cmds.createNode("transform", name="pen_Q")
    cmds.setAttr(pen + ".translate", rest["qU"], rest["qV"], 0.0)
    sphere = cmds.parent(cmds.polySphere(name="pen_GEO", radius=0.4)[0], pen, relative=True)[0]
    cmds.setAttr(sphere + ".translateZ", 1.0)
    cmds.sets(sphere, edit=True, forceElement=groups["green"])
    graph = Pantograph.create(tracer, pen, arm, link, ARM, LINK, RATIO, name="pantograph", plane="xy",
                              linkRelative=True)
    owner = str(graph.container)
    # 水色: 腕の延長 A-B と、平行四辺形の残りの棒 B-Q・P-C (DGの出力の点を結ぶ)。
    for first, second in (("a", "b"), ("b", "q"), ("p", "c")):
        _bar("bar_{}{}".format(first.upper(), second.upper()), owner, first, second, (0.3, 0.85, 0.95), 4.0)
    camera, camera_shape = cmds.camera(name="pgCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(1.5, 1.5, 44), lookAt=(1.5, 1.5, 0))
    window = cmds.window("pgValidationWindow", title="Pantograph - pen copies the tracer at a fixed ratio",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("pgValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("pantograph", 8)
    scene = {"owner": owner, "tracer": tracer, "pen": pen, "arm": arm, "linkTip": link_tip, "link": link}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、棒の長さ・k 倍・シーンとの一致・Python版との一致を試験側で独立に確かめた診断を返す。"""
    from maya import cmds
    from mlrig.setups import Pantograph
    (u, v), stage = pose(frame)
    owner = scene["owner"]
    cmds.setAttr(scene["tracer"] + ".translate", u, v, 0.0)

    def get(attribute):
        """containerの出力の値。"""
        return cmds.getAttr(owner + "." + attribute)

    def world(node):
        """ノードのワールド位置 (x, y)。"""
        position = cmds.xform(node, query=True, worldSpace=True, translation=True)
        return position[0], position[1]

    def distance(first, second):
        """2点の距離。"""
        return math.hypot(first[0] - second[0], first[1] - second[1])

    points = {name: (get(name.lower() + "U"), get(name.lower() + "V")) for name in "PQABC"}
    origin = (0.0, 0.0)
    # 試験側で独立に: 7本の棒の長さと、Q = k P。
    lengths = ((origin, "A", ARM), ("A", "P", LINK), (origin, "B", RATIO * ARM), ("B", "Q", RATIO * LINK),
               ("P", "C", (RATIO - 1.0) * ARM), ("B", "C", LINK), ("C", "Q", (RATIO - 1.0) * LINK))
    bar_error = max(abs(distance(points.get(first, first), points[second]) - length)
                    for first, second, length in lengths)
    ratio_error = distance(points["Q"], (RATIO * points["P"][0], RATIO * points["P"][1]))
    result = Pantograph.motion(u, v, ARM, LINK, RATIO)
    names_checked = ("pU", "pV", "qU", "qV", "aU", "aV", "bU", "bV", "cU", "cV", "excess", "clampedDistance")
    formula_error = max(abs(get(name) - result[name]) for name in names_checked)
    excess = get("excess")
    # 試験側で独立に: 範囲の中ならなぞる点と P が一致、外なら P は端の円の上で同じ向き。
    expected_distance = min(max(math.hypot(u, v), NEAREST), FARTHEST)
    reach_error = abs(distance(origin, points["P"]) - expected_distance)
    if abs(excess) < 1e-9:
        reach_error = max(reach_error, distance(points["P"], (u, v)))
    pen_error = distance(world(scene["pen"]), points["Q"])
    link_error = max(distance(world(scene["linkTip"]), points["P"]), distance(world(scene["link"]), points["A"]))
    values[:] = [
        "RED = tracer (INPUT translate)   BLUE = arm O-A and link A-P   CYAN = bars A-B, B-Q, P-C   GREEN = pen Q (OUTPUT)   GRAY = reach circles / squares   cm / deg",
        "STAGE: " + stage,
        "fixed: a = {:.1f}  b = {:.1f}  k = {:.1f}   reach of P: {:.1f} <= d <= {:.1f} cm   pivot O = (0, 0)".format(
            ARM, LINK, RATIO, NEAREST, FARTHEST),
        "d = |tracer - O|   d' = clamp(d, |a-b|, a+b)   P = d' (cos psi, sin psi)   Q = k P   m = d'/2 + (a^2-b^2)/(2d')   h = sqrt(a^2-m^2)",
        "INPUT tracer = ({:7.3f}, {:7.3f})   d = {:7.3f}   used d' = {:6.3f}   excess = {:7.3f} cm".format(
            u, v, get("tracerDistance"), get("clampedDistance"), excess),
        "OUTPUT (DG) P = ({:6.3f}, {:6.3f})   Q = ({:7.3f}, {:7.3f})   armAngle = {:7.2f}   linkAngle = {:7.2f} deg".format(
            points["P"][0], points["P"][1], points["Q"][0], points["Q"][1], get("armAngle"), get("linkAngle")),
        "CHECK max |bar length - a, b, ka, kb, (k-1)a| = {:.6f} cm   |Q - k P| = {:.6f} cm   |d' - expected| = {:.6f} cm".format(
            bar_error, ratio_error, reach_error),
        "CHECK |DG - python| = {:.6f}   |pen - Q| = {:.6f}   |arm tip - A|, |link tip - P| = {:.6f} cm".format(
            formula_error, pen_error, link_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (bar_error < 1e-4 and ratio_error < 1e-5 and reach_error < 1e-4 and formula_error < 1e-4
          and pen_error < 1e-4 and link_error < 1e-4)
    return {"frame": frame, "presentation_stage": stage, "input": {"tracer": [u, v]},
            "output": {"points": points, "excess": excess, "clampedDistance": get("clampedDistance"),
                       "armAngle": get("armAngle"), "linkAngle": get("linkAngle")},
            "bar_error": bar_error, "ratio_error": ratio_error, "reach_error": reach_error,
            "formula_error": formula_error, "pen_error": pen_error, "link_error": link_error, "ok": ok}


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
        folder = recordVideo("Pantograph: なぞる点の動きを固定点を中心に k 倍で写す平行四辺形リンク", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "pantograph.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-pantograph.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("pantograph-%Y%m%d-%H%M%S")
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
