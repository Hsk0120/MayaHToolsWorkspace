"""DifferentialGear(デフケース・左右のサイドギヤ・スパイダーの差動歯車)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_differential_gear.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIDE, SPIDER = 16.0, 10.0
OFFSET = 1.5  # サイドギヤの中心の車軸方向の距離 = スパイダーのピッチ半径(cm)
RADIUS = OFFSET * SIDE / SPIDER  # スパイダーの中心の車軸からの距離 = サイドギヤのピッチ半径(cm)
# (始まりのフレーム, 終わりのフレーム, ケースの始まり, 終わり, 右の始まり, 終わり[度], 補間, 段階名)
SEGMENTS = [
    (0, 24, 0.0, 0.0, 0.0, 0.0, "hold", "1 REST"),
    (24, 144, 0.0, 180.0, 0.0, 0.0, "linear", "2 RIGHT HELD: CASE 180 deg -> LEFT 360 deg, SPIDERS SPIN"),
    (144, 240, 180.0, 360.0, 0.0, 180.0, "linear", "3 STRAIGHT: CASE AND RIGHT TOGETHER -> LEFT THE SAME, SPIDERS STOP"),
    (240, 336, 360.0, 360.0, 180.0, -90.0, "smooth", "4 CASE HELD: RIGHT BACK -> LEFT TURNS THE OTHER WAY"),
    (336, 408, 360.0, 0.0, -90.0, 0.0, "smooth", "5 BACK TO REST"),
    (408, 432, 0.0, 0.0, 0.0, 0.0, "hold", "5 BACK TO REST"),
]
FRAMES = SEGMENTS[-1][1]


def pose(frame):
    """フレームの (ケースの角度, 右の角度, 段階名) を返す(linear 以外はsmoothstep)。"""
    for start, end, case0, case1, right0, right1, mode, stage in SEGMENTS:
        if frame <= end:
            weight = 0.0 if end == start else min(max((frame - start) / float(end - start), 0.0), 1.0)
            if mode == "smooth":
                weight = weight * weight * (3 - 2 * weight)
            return case0 + (case1 - case0) * weight, right0 + (right1 - right0) * weight, stage
    return 0.0, 0.0, SEGMENTS[-1][7]


def expected(case, right):
    """試験側の独立な式。ケースから見て左右が逆向きに同じ量だけ回る (L - C) = -(R - C) を解いた左と、
    左の接点の弧長の一致 a φ = b (L - C) から求めたスパイダーの自転 [度]。"""
    left = 2.0 * case - right
    return left, RADIUS / OFFSET * (left - case)


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


def _piece(kind, name, parent, group, translate=(0, 0, 0), rotate=(0, 0, 0), **flags):
    """parent の下に形状を作って色を付ける。"""
    from maya import cmds
    create = {"cylinder": cmds.polyCylinder, "cube": cmds.polyCube}[kind]
    node = create(name=name, **flags)[0]
    node = cmds.parent(node, parent, relative=True)[0]
    cmds.setAttr(node + ".translate", *translate)
    cmds.setAttr(node + ".rotate", *rotate)
    cmds.sets(node, edit=True, forceElement=group)
    return node


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import DifferentialGear
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("leftRed", (0.9, 0.15, 0.1)), "green": _shader("caseGreen", (0.15, 0.75, 0.25)),
              "gray": _shader("rightGray", (0.55, 0.55, 0.55)), "blue": _shader("spiderBlue", (0.2, 0.45, 0.95)),
              "white": _shader("markWhite", (0.95, 0.95, 0.95)), "dark": _shader("markDark", (0.1, 0.1, 0.1))}
    # 左右のサイドギヤ(円板・車軸・車輪)と、回転が分かる目印。
    sides = {}
    for key, sign, color, mark in (("left", -1.0, "red", "white"), ("right", 1.0, "gray", "dark")):
        gear = cmds.createNode("transform", name=key + "_GEAR")
        cmds.setAttr(gear + ".translateX", sign * OFFSET)
        _piece("cylinder", key + "_GEO", gear, groups[color], (sign * 0.15, 0, 0), (0, 0, 90),
               radius=RADIUS - 0.2, height=0.3, subdivisionsAxis=48)
        _piece("cylinder", key + "_AXLE", gear, groups[color], (sign * 3.0, 0, 0), (0, 0, 90),
               radius=0.25, height=6.0, subdivisionsAxis=16)
        _piece("cylinder", key + "_WHEEL", gear, groups[color], (sign * 6.0, 0, 0), (0, 0, 90),
               radius=2.2, height=0.6, subdivisionsAxis=48)
        _piece("cube", key + "_MARK", gear, groups[mark], (sign * 0.35, RADIUS * 0.5, 0), width=0.2,
               height=RADIUS * 0.9, depth=0.45)
        _piece("cube", key + "_WHEELMARK", gear, groups[mark], (sign * 6.35, 1.2, 0), width=0.2, height=2.0,
               depth=0.5)
        sides[key] = gear
    # デフケース(緑の十字軸と輪)と、ケースの子のスパイダー(青、jointOrientで十字軸の向きにする)。
    case = cmds.createNode("transform", name="case_ARM")
    _piece("cylinder", "case_PIN", case, groups["green"], radius=0.18, height=2.0 * RADIUS + 1.6,
           subdivisionsAxis=16)
    pipe = cmds.polyPipe(name="case_FRAME", radius=RADIUS + 1.4, thickness=0.35, height=0.5, axis=(1, 0, 0),
                         subdivisionsAxis=48)[0]
    pipe = cmds.parent(pipe, case, relative=True)[0]
    cmds.sets(pipe, edit=True, forceElement=groups["green"])
    spiders = []
    for index, (height, orient) in enumerate(((RADIUS, 0.0), (-RADIUS, 180.0))):
        spider = cmds.createNode("joint", name="spider{}_GEAR".format(index), parent=case)
        cmds.setAttr(spider + ".drawStyle", 2)
        cmds.setAttr(spider + ".translateY", height)
        cmds.setAttr(spider + ".jointOrientZ", orient)
        _piece("cylinder", "spider{}_GEO".format(index), spider, groups["blue"], radius=OFFSET - 0.15, height=0.3,
               subdivisionsAxis=40)
        _piece("cube", "spider{}_MARK".format(index), spider, groups["white"], (0, 0.2, OFFSET * 0.5), width=0.45,
               height=0.2, depth=OFFSET * 0.9)
        spiders.append(cmds.ls(spider, long=True)[0])
    graph = DifferentialGear.create(sides["left"], sides["right"], case, spiders, SIDE, SPIDER, driven="left",
                                    name="differentialGear", axis="x", spiderAxis="y")
    owner = graph.container
    camera, camera_shape = cmds.camera(name="dgCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(9.0, 9.0, 24.0), lookAt=(0.0, -1.2, 0.0))
    window = cmds.window("dgValidationWindow", title="DifferentialGear - case, side gears and spiders",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("dgValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("differentialGear", 8)
    scene = {"owner": owner, "left": sides["left"], "right": sides["right"], "case": case, "spiders": spiders}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、左とスパイダーの回転を試験側の式と、接点の弧長の一致で比較した診断を返す。"""
    from maya import cmds
    case, right, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(scene["case"] + ".rotateX", case)
    cmds.setAttr(scene["right"] + ".rotateX", right)
    left_expected, spin_expected = expected(case, right)
    left = cmds.getAttr(scene["left"] + ".rotateX")
    spins = [cmds.getAttr(spider + ".rotateY") for spider in scene["spiders"]]
    side_spin = cmds.getAttr(owner + ".sideSpin")
    spider_spin = cmds.getAttr(owner + ".spiderSpin")
    error = max(abs(left - left_expected), abs(spider_spin - spin_expected),
                max(abs(value - spin_expected) for value in spins))
    # 試験側で独立に: シーンの回転から、スパイダー0と左右のサイドギヤの接点の弧長の差(cm)を求める
    left_arc_error = abs(math.radians(OFFSET * spins[0] - RADIUS * (left - case)))
    right_arc_error = abs(math.radians(OFFSET * spins[0] + RADIUS * (right - case)))
    values[:] = [
        "GREEN = case (INPUT)   GRAY = right (INPUT)   RED = left (OUTPUT)   BLUE = spiders (OUTPUT)   marks = gear angle   deg",
        "STAGE: " + stage,
        "fixed: side gears Zs = {:.0f}   spiders Zp = {:.0f}   (side pitch radius {:.1f} cm, spider {:.1f} cm)".format(
            SIDE, SPIDER, RADIUS, OFFSET),
        "left = 2 case - right   (case = average of left and right)   spider spin = (Zs / Zp)(left - case)",
        "INPUT case = {:8.2f} deg   right = {:8.2f} deg".format(case, right),
        "OUTPUT (DG) left = {:8.2f} deg   left - case = {:8.2f} deg   spider spin = {:8.2f} deg".format(
            left, side_spin, spider_spin),
        "CHECK arc at left contact {:.6f} cm   arc at right contact {:.6f} cm   (0 = meshing, no slip)".format(
            left_arc_error, right_arc_error),
        "CHECK |DG - formula| = {:.6f} deg".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and left_arc_error < 1e-5 and right_arc_error < 1e-5
    return {"frame": frame, "presentation_stage": stage, "input": {"case": case, "right": right},
            "output": {"left": left, "sideSpin": side_spin, "spiderSpin": spider_spin, "spiders": spins},
            "error": error, "left_arc_error": left_arc_error, "right_arc_error": right_arc_error, "ok": ok}


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
        folder = recordVideo("DifferentialGear: デフケース・左右のサイドギヤ・スパイダー", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "differential_gear.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-differential-gear.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("differential-gear-%Y%m%d-%H%M%S")
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
