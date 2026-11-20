"""PeaucellierLinkage(円運動を厳密な直線運動へ変えるポーセリエ・リプキン機構)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_peaucellier_linkage.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RADIUS = 2.0
ARM = 5.0
SIDE = 2.0
CONSTANT = ARM * ARM - SIDE * SIDE
LINE = CONSTANT / (2.0 * RADIUS)
LIMIT = math.degrees(2.0 * math.acos((ARM - SIDE) / (2.0 * RADIUS)))
# (始まりのフレーム, 終わりのフレーム, 始まりの角度[度], 終わりの角度[度], 補間, 段階名)。
SEGMENTS = [
    (0, 24, 0.0, 0.0, "hold", "1 REST (P FARTHEST FROM O, PEN ON THE CENTER LINE)"),
    (24, 96, 0.0, LIMIT, "smooth", "2 TURN THE CRANK UP TO THE LIMIT (RHOMBUS CLOSES, O-A-P-B IN ONE LINE)"),
    (96, 144, LIMIT, LIMIT + 40.0, "linear", "3 INPUT BEYOND THE LIMIT (LINKAGE STOPS, excess grows)"),
    (144, 264, LIMIT + 40.0, -LIMIT - 40.0, "smooth", "4 SWEEP TO THE OTHER SIDE AND BEYOND"),
    (264, 324, -LIMIT - 40.0, 0.0, "smooth", "5 BACK INTO THE SAFE RANGE AND TO REST"),
    (324, 348, 0.0, 0.0, "hold", "5 BACK INTO THE SAFE RANGE AND TO REST"),
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
    """containerの出力の2点 (first, second) を結ぶ直線のカーブを作る。first・second は "p"・"a" などか定数の (x, y)。"""
    from maya import cmds
    curve = cmds.curve(name=name, degree=1, point=[(0, 0, 0.6), (1, 0, 0.6)])
    shape = cmds.listRelatives(curve, shapes=True)[0]
    for index, point in enumerate((first, second)):
        if isinstance(point, str):
            for axis in ("x", "y"):
                cmds.connectAttr("{}.{}{}".format(owner, point, axis.upper()),
                                 "{}.controlPoints[{}].{}Value".format(shape, index, axis))
        else:
            cmds.setAttr("{}.controlPoints[{}]".format(shape, index), point[0], point[1], 0.6, type="double3")
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideRGBColors", True)
    cmds.setAttr(shape + ".overrideColorRGB", *color, type="double3")
    cmds.setAttr(shape + ".lineWidth", width)
    return curve


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import PeaucellierLinkage
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("crankRed", (0.9, 0.15, 0.1)), "green": _shader("penGreen", (0.15, 0.8, 0.25)),
              "gray": _shader("pivotGray", (0.5, 0.5, 0.5)), "blue": _shader("armBlue", (0.2, 0.45, 0.95))}
    # 灰色: 固定点 O とクランクの中心 C。灰色のカーブ: P が回る円とペンが動くはずの直線(動かない目印)。
    for name, x in (("pivot_O", 0.0), ("pivot_C", RADIUS)):
        cylinder = cmds.polyCylinder(name=name, radius=0.25, height=0.2, axis=(0, 0, 1))[0]
        cmds.setAttr(cylinder + ".translate", x, 0, -0.5)
        cmds.sets(cylinder, edit=True, forceElement=groups["gray"])
    circle = cmds.circle(name="circle_GUIDE", normal=(0, 0, 1), center=(RADIUS, 0, 0), radius=RADIUS, sections=64)[0]
    line = cmds.curve(name="line_GUIDE", degree=1, point=[(LINE, -6.5, 0), (LINE, 6.5, 0)])
    for guide in (circle, line):
        cmds.setAttr(guide + ".overrideEnabled", True)
        cmds.setAttr(guide + ".overrideColor", 2)
    # クランク(赤): 入力の transform。C に置き、+X へ r の腕。
    crank = cmds.createNode("transform", name="crank_INPUT")
    cmds.setAttr(crank + ".translateX", RADIUS)
    _box("crank_GEO", crank, (RADIUS, 0.35, 0.2), (RADIUS * 0.5, 0, -0.3), groups["red"])
    # 腕(青): O に置き、θ = 0 の向き ±α0 へ a の長さ。
    rest = PeaucellierLinkage.motion(0.0, RADIUS, ARM, SIDE)
    arms = []
    for label in ("A", "B"):
        arm = cmds.createNode("transform", name="arm_" + label)
        cmds.setAttr(arm + ".rotateZ", math.degrees(rest["armAngle" + label]))
        _box("arm_{}GEO".format(label), arm, (ARM, 0.22, 0.2), (ARM * 0.5, 0, 0.0), groups["blue"])
        arms.append(arm)
    # ペン(緑): 直線の上の Q。
    pen = cmds.createNode("transform", name="pen_Q")
    cmds.setAttr(pen + ".translateX", LINE)
    sphere = cmds.polySphere(name="pen_GEO", radius=0.35)[0]
    sphere = cmds.parent(sphere, pen, relative=True)[0]
    cmds.setAttr(sphere + ".translateZ", 0.8)
    cmds.sets(sphere, edit=True, forceElement=groups["green"])
    graph = PeaucellierLinkage.create(crank, pen, arms[0], arms[1], RADIUS, ARM, SIDE, name="peaucellierLinkage",
                                      axis="z", penAxis="y")
    owner = str(graph.container)
    # 水色: 菱形の4辺(DGの出力の点を結ぶ)。橙: 止めた後の実際のクランク C→P。
    for first, second in (("a", "p"), ("a", "q"), ("b", "p"), ("b", "q")):
        _bar("side_{}{}".format(first.upper(), second.upper()), owner, first, second, (0.3, 0.85, 0.95), 4.0)
    _bar("crank_LINK", owner, (RADIUS, 0.0), "p", (1.0, 0.55, 0.1), 5.0)
    camera, camera_shape = cmds.camera(name="plCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(2.8, -0.6, 27), lookAt=(2.8, -0.6, 0))
    window = cmds.window("plValidationWindow", title="PeaucellierLinkage - crank circle to exact straight line",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("plValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("peaucellierLinkage", 8)
    scene = {"owner": owner, "crank": crank, "pen": pen, "arms": arms}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、棒の長さ・直線・反転・Python版との一致を試験側で独立に確かめた診断を返す。"""
    from maya import cmds
    from mlrig.setups import PeaucellierLinkage
    angle, stage = pose(frame)
    owner = scene["owner"]
    cmds.setAttr(scene["crank"] + ".rotateZ", angle)

    def get(attribute):
        """containerの出力の値。"""
        return cmds.getAttr(owner + "." + attribute)

    points = {name: (get(name.lower() + "X"), get(name.lower() + "Y")) for name in ("P", "Q", "A", "B")}
    origin, center = (0.0, 0.0), (RADIUS, 0.0)

    def distance(first, second):
        """2点の距離。"""
        return math.hypot(first[0] - second[0], first[1] - second[1])

    # 試験側で独立に: 8本の棒の長さ(腕 a・菱形 b・クランク r)と、Q が直線 x = k/(2r) の上にあること。
    bars = [distance(origin, points["A"]) - ARM, distance(origin, points["B"]) - ARM,
            distance(center, points["P"]) - RADIUS]
    bars += [distance(points[arm], points[joint]) - SIDE for arm in ("A", "B") for joint in ("P", "Q")]
    bar_error = max(abs(value) for value in bars)
    line_error = abs(points["Q"][0] - LINE)
    product = distance(origin, points["P"]) * distance(origin, points["Q"])
    result = PeaucellierLinkage.motion(math.radians(angle), RADIUS, ARM, SIDE)
    formula_error = max(abs(get(name) - result[name]) for name in ("pX", "pY", "qX", "qY", "aX", "aY", "bX", "bY"))
    excess = get("excessAngle")
    formula_error = max(formula_error, abs(excess - math.degrees(result["excessAngle"])))
    pen_y = cmds.getAttr(scene["pen"] + ".translateY")
    pen_error = abs(pen_y - points["Q"][1])
    arm_world = cmds.xform(scene["arms"][0], query=True, worldSpace=True, matrix=True)
    arm_error = math.hypot(ARM * arm_world[0] - points["A"][0], ARM * arm_world[1] - points["A"][1])
    values[:] = [
        "RED = crank (INPUT rotateZ)   ORANGE = crank link C-P   BLUE = arms O-A, O-B   CYAN = rhombus   GREEN = pen Q (OUTPUT)   GRAY = circle / expected line   cm / deg",
        "STAGE: " + stage,
        "fixed: r = {:.1f}  a = {:.1f}  b = {:.1f}   k = a^2 - b^2 = {:.1f}   line x = k / 2r = {:.3f}   limit = +-{:.2f} deg".format(
            RADIUS, ARM, SIDE, CONSTANT, LINE, LIMIT),
        "theta' = clamp(theta, +-limit)   |OP| = 2r cos(theta'/2)   |OQ| = k / |OP|   Q = |OQ| (cos, sin)(theta'/2)",
        "INPUT theta = {:8.2f} deg   used theta' = {:7.2f} deg   excess = {:7.2f} deg".format(
            angle, get("crankAngle"), excess),
        "OUTPUT (DG) Q x = {:7.4f}  Q y = {:7.3f}   |OP| = {:6.3f}  |OQ| = {:6.3f}   |OP||OQ| = {:7.4f}   pen y = {:7.3f}".format(
            points["Q"][0], points["Q"][1], get("opDistance"), get("oqDistance"), product, pen_y),
        "CHECK max |bar length - a, b, r| = {:.6f} cm   |Q x - k/2r| = {:.6f} cm".format(bar_error, line_error),
        "CHECK |DG - python| = {:.6f}   |pen - Q y| = {:.6f}   |arm tip - A| = {:.6f} cm".format(
            formula_error, pen_error, arm_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (bar_error < 1e-4 and line_error < 1e-4 and abs(product - CONSTANT) < 1e-3 and formula_error < 1e-3
          and pen_error < 1e-5 and arm_error < 1e-4)
    return {"frame": frame, "presentation_stage": stage, "input": {"crank": angle},
            "output": {"points": points, "crankAngle": get("crankAngle"), "excessAngle": excess, "penY": pen_y,
                       "product": product},
            "bar_error": bar_error, "line_error": line_error, "formula_error": formula_error,
            "pen_error": pen_error, "arm_error": arm_error, "ok": ok}


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
        folder = recordVideo("PeaucellierLinkage: 円運動を厳密な直線運動へ変える反転リンク", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "peaucellier_linkage.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-peaucellier-linkage.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("peaucellier-linkage-%Y%m%d-%H%M%S")
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
