"""ScissorLiftの腕・台・滑る足を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_scissor_lift.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
LENGTH = 6.0
STAGES = 3
# (台の高さ[cm], 次の姿勢へ向かう段階名)。
POSES = [
    (9.0, "1 REST (height 9 = 30 deg)"),
    (9.0, "2 RAISE height -> 16"),
    (16.0, "3 LOWER height -> 3"),
    (3.0, "4 RAISE NEAR MAX height -> 17.9 (n*L = 18)"),
    (17.9, "5 OVER MAX height -> 22 (CLAMPED, ARMS VERTICAL)"),
    (22.0, "6 RETURN TO REST"),
    (9.0, "6 RETURN TO REST"),
    (9.0, "6 RETURN TO REST"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    return POSES[index][0] + (POSES[index + 1][0] - POSES[index][0]) * weight, POSES[index][1]


def expected(height):
    """判定用の独立計算: 1段の高さ h(範囲で止める)と滑る側の距離 w(三平方)。"""
    stage = min(max(height / STAGES, 0.0), LENGTH)
    return stage, math.sqrt(max(LENGTH * LENGTH - stage * stage, 0.0))


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


def _follow(name, plug):
    """行列のplugへ offsetParentMatrix でつながるtransformを作る。"""
    from maya import cmds
    node = cmds.createNode("transform", name=name)
    cmds.connectAttr(plug, node + ".offsetParentMatrix")
    return node


def _point(matrix, x=0.0):
    """行列のローカルの点 (x, 0, 0) のワールド位置。"""
    from maya.api import OpenMaya as om2
    return om2.MPoint(x, 0.0, 0.0) * om2.MMatrix(matrix)


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import ScissorLift
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"green": _shader("armGreen", (0.15, 0.75, 0.25)), "dark": _shader("armDark", (0.08, 0.45, 0.15)),
              "platform": _shader("platformBlue", (0.25, 0.45, 0.9)),
              "slider": _shader("sliderOrange", (0.95, 0.55, 0.1)),
              "pin": _shader("pinWhite", (0.95, 0.95, 0.95)), "floor": _shader("floorGray", (0.35, 0.35, 0.4))}
    base = cmds.createNode("transform", name="liftBase")
    _box("floor_GEO", base, (16.0, 0.3, 3.0), (3.0, -0.45, 0.0), groups["floor"])
    graph = ScissorLift.create(base, LENGTH, STAGES, height=9.0, name="lift")
    owner = str(graph.container)
    for index in range(STAGES):
        for side, z, group in (("A", 0.35, groups["green"]), ("B", -0.35, groups["dark"])):
            arm = _follow("arm{}{}".format(index, side), "{}.arm{}{}Matrix".format(owner, index, side))
            _box(arm + "_GEO", arm, (LENGTH + 0.4, 0.35, 0.25), (LENGTH * 0.5, 0, z), group)
    platform = _follow("platform", owner + ".platformMatrix")
    _box("platform_GEO", platform, (9.0, 0.5, 2.0), (3.5, 0.45, 0.0), groups["platform"])
    for role in ("baseSlider", "topSlider"):
        slider = _follow(role, "{}.{}Matrix".format(owner, role))
        _box(role + "_GEO", slider, (1.0, 0.5, 1.4), (0, 0.0, 0.0), groups["slider"])
    # 判定用の独立計算で置く支点(白)。腕の端がこの上に乗る。リグには含めない。
    pins = []
    for level in range(STAGES + 1):
        for side in (0, 1):
            pin = cmds.polySphere(name="pin{}_{}_GEO".format(level, side), radius=0.28)[0]
            cmds.sets(pin, edit=True, forceElement=groups["pin"])
            pins.append((level, side, pin))
    camera, camera_shape = cmds.camera(name="liftCamera", orthographic=True, orthographicWidth=56)
    cmds.viewPlace(camera_shape, eye=(-9, 8.5, 60), lookAt=(-9, 8.5, 0), up=(0, 1, 0))
    window = cmds.window("liftValidationWindow", title="ScissorLift - arms and platform", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("liftValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("lift", 7)
    return panel, {"owner": owner, "pins": pins}, values, names


def evaluate_frame(frame, scene, values, names):
    """台の高さを更新し、腕の両端・交点・台・滑る足を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    height, stage_name = pose(frame)
    owner = scene["owner"]
    cmds.setAttr(owner + ".height", height)
    stage, spread = expected(height)
    for level, side, pin in scene["pins"]:
        cmds.setAttr(pin + ".translate", spread * side, level * stage, 0.0)
    error, cross, length_error = 0.0, 0.0, 0.0
    for index in range(STAGES):
        arm_a = cmds.getAttr("{}.arm{}AMatrix".format(owner, index))
        arm_b = cmds.getAttr("{}.arm{}BMatrix".format(owner, index))
        pairs = ((_point(arm_a), (0.0, index * stage)), (_point(arm_a, LENGTH), (spread, (index + 1) * stage)),
                 (_point(arm_b), (0.0, (index + 1) * stage)), (_point(arm_b, LENGTH), (spread, index * stage)))
        for actual, (x, y) in pairs:
            error = max(error, (actual - om2.MPoint(x, y, 0.0)).length())
        cross = max(cross, (_point(arm_a, LENGTH * 0.5) - _point(arm_b, LENGTH * 0.5)).length())
        for arm in (arm_a, arm_b):
            length_error = max(length_error, abs((_point(arm, LENGTH) - _point(arm)).length() - LENGTH))
    for role, (x, y) in (("platform", (0.0, STAGES * stage)), ("baseSlider", (spread, 0.0)),
                         ("topSlider", (spread, STAGES * stage))):
        matrix = cmds.getAttr("{}.{}Matrix".format(owner, role))
        error = max(error, (_point(matrix) - om2.MPoint(x, y, 0.0)).length())
    angle = cmds.getAttr(owner + ".angle")
    actual_stage = cmds.getAttr(owner + ".stageHeight")
    values[:] = [
        "GREEN = arms A (front) / B (back)   BLUE = platform   ORANGE = sliding feet   "
        "WHITE = pivots from the formula (not part of the rig)",
        "STAGE: " + stage_name,
        "fixed: armLength L = {:.1f} cm   stages n = {}   left pivots fixed at x = 0, right pivots slide".format(
            LENGTH, STAGES),
        "h = clamp(H / n, 0, L)   w = sqrt(L^2 - h^2)   angle = atan2(h, w)   platform y = n * h",
        "INPUT height H = {:6.2f} cm".format(height),
        "OUTPUT h = {:6.3f} cm   w = {:6.3f} cm   angle = {:6.2f} deg   platform y = {:6.2f} cm".format(
            actual_stage, cmds.getAttr(owner + ".spread"), angle, STAGES * actual_stage),
        "CHECK max |pivot - formula| = {:.2e} cm   max arm crossing gap = {:.2e} cm   "
        "max |arm length - L| = {:.2e} cm".format(error, cross, length_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and cross < 1e-4 and length_error < 1e-4
    return {"frame": frame, "presentation_stage": stage_name, "input": {"height": height}, "error": error,
            "cross": cross, "length_error": length_error, "angle": angle, "ok": ok}


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
        folder = recordVideo("ScissorLift: シザーリフトの腕と台", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "scissor_lift.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-scissor-lift.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("scissor-lift-%Y%m%d-%H%M%S")
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
