"""StewartPlatform(天板の位置と向きから6本の脚の長さを求めるパラレルリンクの台)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_stewart_platform.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_RADIUS = 3.0
TOP_RADIUS = 2.0
HEIGHT = 4.0
MINIMUM = 3.0
MAXIMUM = 6.0
BASE_ANGLES = (15, 105, 135, 225, 255, 345)
TOP_ANGLES = (45, 75, 165, 195, 285, 315)
# (始まりのフレーム, 終わりのフレーム, 始まりの (移動X, 高さの変化, 傾きZ[度], ひねりY[度]), 終わり, 補間, 段階名)。
SEGMENTS = [
    (0, 24, (0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), "hold", "1 REST (ALL SIX LEGS THE SAME LENGTH)"),
    (24, 72, (0.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), "smooth",
     "2 HEAVE: RAISE THE PLATFORM (ALL LEGS EXTEND THE SAME)"),
    (72, 120, (0.0, 1.0, 0.0, 0.0), (1.2, 0.3, 12.0, 0.0), "smooth", "3 SURGE + TILT (EACH LEG GETS ITS OWN LENGTH)"),
    (120, 168, (1.2, 0.3, 12.0, 0.0), (0.0, 0.3, 0.0, 35.0), "smooth", "4 TWIST (YAW): LEGS ALTERNATE LONG / SHORT"),
    (168, 228, (0.0, 0.3, 0.0, 35.0), (0.0, 2.6, 8.0, 0.0), "smooth",
     "5 BEYOND THE MAXIMUM (RODS STOP AT 6.0, TIPS LEAVE THE ORANGE ANCHORS)"),
    (228, 288, (0.0, 2.6, 8.0, 0.0), (0.0, -1.8, 0.0, 0.0), "smooth",
     "6 BELOW THE MINIMUM (RODS STOP AT 3.0, excess < 0)"),
    (288, 336, (0.0, -1.8, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), "smooth", "7 BACK INTO THE SAFE RANGE AND TO REST"),
    (336, 360, (0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), "hold", "7 BACK INTO THE SAFE RANGE AND TO REST"),
]
FRAMES = SEGMENTS[-1][1]


def pose(frame):
    """フレームの天板の移動X・高さの変化・傾きZ(度)・ひねりY(度)と段階名を返す。"""
    for start, end, first, last, mode, stage in SEGMENTS:
        if frame <= end:
            weight = 0.0 if end == start else min(max((frame - start) / float(end - start), 0.0), 1.0)
            if mode == "smooth":
                weight = weight * weight * (3 - 2 * weight)
            return [a + (b - a) * weight for a, b in zip(first, last)] + [stage]
    return [0.0, 0.0, 0.0, 0.0, SEGMENTS[-1][5]]


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


def _rod(name, parent, radius, low, high, group):
    """parentの下へ、ローカルの Y が low〜high の細い円柱を作り、色を付けて返す。"""
    from maya import cmds
    node = cmds.polyCylinder(name=name, radius=radius, height=high - low, subdivisionsX=16)[0]
    node = cmds.parent(node, parent, relative=True)[0]
    cmds.setAttr(node + ".translateY", (low + high) * 0.5)
    cmds.sets(node, edit=True, forceElement=group)
    return node


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import StewartPlatform
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("platformRed", (0.9, 0.15, 0.1)), "green": _shader("rodGreen", (0.15, 0.8, 0.25)),
              "gray": _shader("baseGray", (0.55, 0.55, 0.55)), "orange": _shader("anchorOrange", (1.0, 0.55, 0.1)),
              "blue": _shader("cylinderBlue", (0.2, 0.45, 0.95))}
    # 台座(灰色)と天板(赤、入力)。
    base = cmds.createNode("transform", name="base")
    disc = cmds.polyCylinder(name="base_GEO", radius=BASE_RADIUS + 0.5, height=0.2, subdivisionsX=48)[0]
    disc = cmds.parent(disc, base, relative=True)[0]
    cmds.setAttr(disc + ".translateY", -0.1)
    cmds.sets(disc, edit=True, forceElement=groups["gray"])
    platform = cmds.createNode("transform", name="platform_INPUT")
    cmds.setAttr(platform + ".translateY", HEIGHT)
    disc = cmds.polyCylinder(name="platform_GEO", radius=TOP_RADIUS + 0.4, height=0.15, subdivisionsX=6)[0]
    disc = cmds.parent(disc, platform, relative=True)[0]
    cmds.setAttr(disc + ".translateY", 0.3)
    cmds.sets(disc, edit=True, forceElement=groups["red"])
    bases, tops, cylinders, rods = [], [], [], []
    for index, (low, high) in enumerate(zip(BASE_ANGLES, TOP_ANGLES)):
        low, high = math.radians(low), math.radians(high)
        anchor = cmds.createNode("transform", name="baseAnchor{}".format(index), parent=base)
        cmds.setAttr(anchor + ".translate", BASE_RADIUS * math.cos(low), 0.0, -BASE_RADIUS * math.sin(low))
        bases.append(anchor)
        anchor = cmds.createNode("transform", name="platformAnchor{}".format(index), parent=platform)
        cmds.setAttr(anchor + ".translate", TOP_RADIUS * math.cos(high), 0.0, -TOP_RADIUS * math.sin(high))
        # 橙: 天板側の取り付け点。範囲を超えると緑のロッドの先がここから離れる。
        ball = cmds.polySphere(name="platformAnchor{}_GEO".format(index), radius=0.2)[0]
        ball = cmds.parent(ball, anchor, relative=True)[0]
        cmds.sets(ball, edit=True, forceElement=groups["orange"])
        tops.append(anchor)
        # 青: シリンダー(原点から MINIMUM まで)。緑: ロッド(原点から手前へ MINIMUM まで)。出力。
        cylinder = cmds.createNode("transform", name="cylinder{}_OUTPUT".format(index))
        _rod("cylinder{}_GEO".format(index), cylinder, 0.16, 0.0, MINIMUM, groups["blue"])
        rod = cmds.createNode("transform", name="rod{}_OUTPUT".format(index), parent=cylinder)
        _rod("rod{}_GEO".format(index), rod, 0.08, -MINIMUM, 0.0, groups["green"])
        cylinders.append(cylinder)
        rods.append(rod)
    graph = StewartPlatform.create(bases, tops, cylinders, rods, MINIMUM, MAXIMUM, name="stewartPlatform")
    owner = str(graph.container)
    camera, camera_shape = cmds.camera(name="spCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(6.15, 9.5, 19.65), lookAt=(-5.85, 3.4, 4.65))
    window = cmds.window("spValidationWindow", title="StewartPlatform - six legs follow a free platform",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("spValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=True,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("stewartPlatform", 10)
    scene = {"owner": owner, "platform": platform, "bases": bases, "tops": tops, "cylinders": cylinders, "rods": rods}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、脚の長さ・ロッドの先の離れ・シリンダーの向き・Python版との一致を試験側で独立に確かめた診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    from mlrig.setups import StewartPlatform
    surge, heave, tilt, twist, stage = pose(frame)
    owner = scene["owner"]
    cmds.setAttr(scene["platform"] + ".translate", surge, HEIGHT + heave, 0.0)
    cmds.setAttr(scene["platform"] + ".rotate", 0.0, twist, tilt)

    def get(attribute, index=None):
        """containerの出力の値。"""
        return cmds.getAttr(owner + "." + attribute + ("" if index is None else "[{}]".format(index)))

    def point(node):
        """ノードのワールド位置。"""
        return om2.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))

    base_points = [point(node) for node in scene["bases"]]
    top_points = [point(node) for node in scene["tops"]]
    result = StewartPlatform.legs([tuple(p) for p in base_points], [tuple(p) for p in top_points], MINIMUM, MAXIMUM)
    length_error = gap_error = aim_error = formula_error = 0.0
    rows = []
    for index in range(6):
        length, clamped = get("length", index), get("clampedLength", index)
        excess, stroke = get("excess", index), get("stroke", index)
        # 試験側で独立に: 長さ = 取り付け点のワールドの距離、ロッドの先と取り付け点の距離 = |excess|、
        # シリンダーの +Y = 脚の向き。
        span = top_points[index] - base_points[index]
        length_error = max(length_error, abs(length - span.length()))
        gap = (point(scene["rods"][index]) - top_points[index]).length()
        gap_error = max(gap_error, abs(gap - abs(excess)))
        matrix = cmds.xform(scene["cylinders"][index], query=True, worldSpace=True, matrix=True)
        aim_error = max(aim_error, (om2.MVector(matrix[4], matrix[5], matrix[6]) - span.normal()).length(),
                        (point(scene["cylinders"][index]) - base_points[index]).length())
        formula_error = max(formula_error, abs(length - result["length"][index]),
                            abs(clamped - result["clampedLength"][index]), abs(excess - result["excess"][index]),
                            abs(stroke - result["stroke"][index]))
        rows.append((length, clamped, excess, stroke))
    worst, reachable = get("maxExcess"), get("reachable")
    formula_error = max(formula_error, abs(worst - result["maxExcess"]), abs(reachable - result["reachable"]))
    values[:] = [
        "RED = platform (INPUT: move / rotate freely)   BLUE = cylinders, GREEN = rods (OUTPUT)   "
        "ORANGE = platform anchors   GRAY = base   cm / deg",
        "STAGE: " + stage,
        "fixed: base radius {:.1f}  platform radius {:.1f}  rest height {:.1f}   leg range: minimum = {:.1f}  "
        "maximum = {:.1f} cm (rest {:.3f})".format(BASE_RADIUS, TOP_RADIUS, HEIGHT, MINIMUM, MAXIMUM,
                                                   get("restLength", 0)),
        "length_i = |P_i - B_i|   rod = clamp(length_i, min, max)   excess_i = length_i - rod   "
        "stroke_i = (length_i - min) / (max - min)",
        "INPUT surge X = {:5.2f} cm   heave Y = {:5.2f} cm   tilt Z = {:5.2f} deg   twist Y = {:5.2f} deg".format(
            surge, heave, tilt, twist),
    ]
    for first in (0, 2, 4):
        values.append("OUTPUT (DG) " + "     ".join(
            "leg {}: length = {:6.3f}  rod = {:5.3f}  excess = {:6.3f}  stroke = {:5.2f}".format(
                index, rows[index][0], rows[index][1], rows[index][2], rows[index][3]) for index in (first, first + 1)))
    values.append("OUTPUT (DG) maxExcess = {:.3f} cm   reachable = {:.0f}     CHECK max |length - world distance| = "
                  "{:.6f}   max |rod tip gap - |excess|| = {:.6f} cm".format(worst, reachable, length_error, gap_error))
    values.append("CHECK max |cylinder axis - leg direction| = {:.6f}   max |DG - python| = {:.6f}".format(
        aim_error, formula_error))
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (length_error < 1e-5 and gap_error < 1e-5 and aim_error < 1e-5 and formula_error < 1e-5
          and all(MINIMUM - 1e-9 <= row[1] <= MAXIMUM + 1e-9 for row in rows))
    return {"frame": frame, "presentation_stage": stage,
            "input": {"surge": surge, "heave": heave, "tiltZ": tilt, "twistY": twist},
            "output": {"length": [row[0] for row in rows], "clampedLength": [row[1] for row in rows],
                       "excess": [row[2] for row in rows], "stroke": [row[3] for row in rows],
                       "maxExcess": worst, "reachable": reachable},
            "length_error": length_error, "gap_error": gap_error, "aim_error": aim_error,
            "formula_error": formula_error, "ok": ok}


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
        folder = recordVideo("StewartPlatform: 天板の位置と向きから6本の脚の長さを求める", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "stewartPlatform.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-stewart-platform.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("stewart-platform-%Y%m%d-%H%M%S")
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
