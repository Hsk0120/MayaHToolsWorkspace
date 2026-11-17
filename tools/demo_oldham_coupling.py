"""OldhamCoupling(平行にずれた2本の軸を中間の円板でつなぐオルダム継手)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_oldham_coupling.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OFFSET = 3.0
# (始まりのフレーム, 終わりのフレーム, 始まりの角度[度], 終わりの角度[度], 補間, 段階名)。等速の区間は線形で補間する。
SEGMENTS = [
    (0, 24, 0.0, 0.0, "hold", "1 REST (INPUT SLOT UPRIGHT, DISC CENTER ON THE INPUT AXIS)"),
    (24, 264, 0.0, 720.0, "linear", "2 INPUT AT CONSTANT SPEED, 2 TURNS (OUTPUT TURNS THE SAME, CENTER ORBITS TWICE AS FAST)"),
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
    """試験側の独立な式。円板の中心の x・y、出力軸の角度(度)、入力の溝・出力の溝の中の位置を返す。"""
    theta = math.radians(degrees)
    return (OFFSET * math.sin(theta) ** 2, -OFFSET * math.sin(theta) * math.cos(theta), degrees,
            -OFFSET * math.sin(theta), -OFFSET * math.cos(theta))


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
    from mlrig.setups import OldhamCoupling
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("inputRed", (0.9, 0.15, 0.1)), "green": _shader("outputGreen", (0.15, 0.75, 0.25)),
              "gray": _shader("slotGray", (0.45, 0.45, 0.45)), "blue": _shader("discBlue", (0.2, 0.45, 0.95)),
              "yellow": _shader("centerYellow", (0.95, 0.85, 0.1))}
    # 灰色のカーブ: 円板の中心が描くはずの円(中心 (e/2, 0)、半径 e/2。動かない目印)。
    orbit = cmds.circle(name="orbit_GUIDE", normal=(0, 0, 1), center=(OFFSET * 0.5, 0, 0), radius=OFFSET * 0.5,
                        sections=64)[0]
    cmds.setAttr(orbit + ".overrideEnabled", True)
    cmds.setAttr(orbit + ".overrideColor", 2)
    # 入力軸(赤): 原点の軸と、+Y に伸びる入力の溝(灰色、軸と一緒に回る)。
    input_shaft = cmds.createNode("transform", name="input_SHAFT")
    _box("input_HUB", input_shaft, (0.8, 0.8, 0.3), (0, 0, -1.0), groups["red"])
    _box("input_SLOT", input_shaft, (0.2, 2.0 * OFFSET + 1.0, 0.05), (0, 0, -0.8), groups["gray"])
    # 出力軸(緑): +X に e ずれた軸と、+X に伸びる出力の溝(灰色、軸と一緒に回る)と、回転が分かる目印。
    output_shaft = cmds.createNode("transform", name="output_SHAFT")
    cmds.setAttr(output_shaft + ".translateX", OFFSET)
    _box("output_HUB", output_shaft, (0.8, 0.8, 0.3), (0, 0, -1.0), groups["green"])
    _box("output_SLOT", output_shaft, (2.0 * OFFSET + 1.0, 0.2, 0.05), (0, 0, -0.8), groups["gray"])
    _box("output_MARK", output_shaft, (0.2, 1.4, 0.3), (0, 0.7, -0.6), groups["green"])
    # 中間の円板(青): 生成時に入力軸の中心。直交する2本の突起と、中心(黄)。
    disc = cmds.createNode("transform", name="disc_DISC")
    _box("disc_TONGUE_IN", disc, (0.35, 2.4, 0.2), (0, 0, 0.2), groups["blue"])
    _box("disc_TONGUE_OUT", disc, (2.4, 0.35, 0.2), (0, 0, 0.4), groups["blue"])
    center = cmds.polySphere(name="disc_CENTER", radius=0.3)[0]
    center = cmds.parent(center, disc, relative=True)[0]
    cmds.setAttr(center + ".translateZ", 0.6)
    cmds.sets(center, edit=True, forceElement=groups["yellow"])
    graph = OldhamCoupling.create(input_shaft, output_shaft, disc, OFFSET, name="oldhamCoupling", axis="z",
                                  offsetAxis="x")
    owner = graph.container
    camera, camera_shape = cmds.camera(name="ocCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(1.5, -0.6, 22), lookAt=(1.5, -0.6, 0))
    window = cmds.window("ocValidationWindow", title="OldhamCoupling - offset shafts turn together",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("ocValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("oldhamCoupling", 8)
    scene = {"owner": owner, "input": input_shaft, "output": output_shaft, "disc": disc}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、円板・出力軸・溝の位置を試験側の式と、2本の溝の線・公転の円で比較した診断を返す。"""
    from maya import cmds
    angle, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(scene["input"] + ".rotateZ", angle)
    x_expected, y_expected, out_expected, in_slide_expected, out_slide_expected = expected(angle)
    x = cmds.getAttr(scene["disc"] + ".translateX")
    y = cmds.getAttr(scene["disc"] + ".translateY")
    output = cmds.getAttr(scene["output"] + ".rotateZ")
    disc_rotate = cmds.getAttr(scene["disc"] + ".rotateZ")
    in_slide = cmds.getAttr(owner + ".inputSlide")
    out_slide = cmds.getAttr(owner + ".outputSlide")
    orbit_angle = cmds.getAttr(owner + ".orbitAngle")
    error = max(abs(x - x_expected), abs(y - y_expected), abs(output - out_expected), abs(disc_rotate - angle),
                abs(in_slide - in_slide_expected), abs(out_slide - out_slide_expected), abs(orbit_angle - 2.0 * angle))
    # 試験側で独立に: 入力の溝の向き s をシーンの入力軸の行列(Y軸)から読み、中心が O1 を通る s の線と、
    # O2 を通る s に直交する線(出力の溝)の上にあるか、公転の円の上にあるかを判定する。
    matrix = cmds.xform(scene["input"], query=True, worldSpace=True, matrix=True)
    slot = (matrix[4], matrix[5])
    input_line_error = abs(x * slot[1] - y * slot[0])
    output_line_error = abs((x - OFFSET) * slot[0] + y * slot[1])
    orbit_error = abs(math.hypot(x - OFFSET * 0.5, y) - OFFSET * 0.5)
    values[:] = [
        "RED = input shaft (INPUT, rotateZ)   GREEN = output shaft (OUTPUT)   BLUE = disc   YELLOW = disc center   GRAY = slots / expected orbit   cm / deg",
        "STAGE: " + stage,
        "fixed: e = {:.1f} cm (input axis to output axis)   orbit radius e/2 = {:.1f} cm".format(OFFSET, OFFSET * 0.5),
        "center = (e sin^2(theta), -e sin(theta) cos(theta))   output = disc = theta   orbit = 2 theta   in slot = -e sin   out slot = -e cos",
        "INPUT theta = {:7.2f} deg   ({:6.2f} in the turn)".format(angle, angle % 360.0),
        "OUTPUT (DG) center x = {:6.3f} y = {:6.3f} cm   output = {:7.2f} deg   orbit = {:7.2f} deg   slots in {:6.3f} out {:6.3f} cm".format(
            x, y, output, orbit_angle, in_slide, out_slide),
        "CHECK center on input slot {:.6f}   on output slot {:.6f}   |C - M| - e/2 = {:.6f} cm".format(
            input_line_error, output_line_error, orbit_error),
        "CHECK |DG - formula| = {:.6f}".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and input_line_error < 1e-4 and output_line_error < 1e-4 and orbit_error < 1e-4
    return {"frame": frame, "presentation_stage": stage, "input": {"input": angle},
            "output": {"x": x, "y": y, "output": output, "discRotate": disc_rotate, "inputSlide": in_slide,
                       "outputSlide": out_slide, "orbitAngle": orbit_angle},
            "error": error, "input_line_error": input_line_error, "output_line_error": output_line_error,
            "orbit_error": orbit_error, "ok": ok}


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
        folder = recordVideo("OldhamCoupling: ずれた2本の軸を円板でつなぐ継手", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "oldham_coupling.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-oldham-coupling.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("oldham-coupling-%Y%m%d-%H%M%S")
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
