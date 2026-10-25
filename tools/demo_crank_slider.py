"""CrankSliderのクランクとピストンの連動を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_crank_slider.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 48
RADIUS = 2.0
LENGTH = 6.0
START = 30.0
# (クランクの角度[度], rodLength[cm], 次の姿勢へ向かう段階名)。
POSES = [
    (START, LENGTH, "1 REST"),
    (START, LENGTH, "2 TURN THE CRANK ONE REVOLUTION"),
    (START + 360.0, LENGTH, "3 TURN THE CRANK ONE MORE REVOLUTION"),
    (START + 720.0, LENGTH, "4 rodLength ATTR 6 -> 8 cm WHILE TURNING HALF A REVOLUTION (DRAWN ROD STAYS 6 cm)"),
    (START + 900.0, 8.0, "5 RETURN rodLength TO 6 cm AND TURN BACK"),
    (START + 720.0, LENGTH, "6 HOLD"),
    (START + 720.0, LENGTH, "6 HOLD"),
]


def height(degrees, length):
    """クランクの角度(+Yから+Z回り)でのピストンのピンの高さ(閉じた式)。"""
    angle = math.radians(degrees)
    return RADIUS * math.cos(angle) + math.sqrt(max(length * length - (RADIUS * math.sin(angle)) ** 2, 0.0))


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:2], POSES[index + 1][:2])]
    return values[0], values[1], POSES[index][2]


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


def _box(name, size, group, parent=None, translate=(0, 0, 0)):
    """単色の箱を作る。"""
    from maya import cmds
    box = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    if parent is not None:
        box = cmds.parent(box, parent, relative=True)[0]
    cmds.setAttr(box + ".translate", *translate)
    cmds.sets(box, edit=True, forceElement=group)
    return box


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import CrankSlider
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    green, gray = _shader("crankGreen", (0.15, 0.75, 0.25)), _shader("frameGray", (0.55, 0.56, 0.6))
    input_color = _shader("crankBlue", (0.25, 0.45, 0.85))
    engine = cmds.createNode("transform", name="engine")
    crank = cmds.createNode("transform", name="crank", parent=engine)
    pin = cmds.createNode("transform", name="crankPin", parent=crank)
    cmds.setAttr(pin + ".translateY", RADIUS)
    cmds.setAttr(crank + ".rotateZ", START)
    piston = cmds.createNode("transform", name="piston_REST", parent=engine)
    cmds.setAttr(piston + ".translateY", height(START, LENGTH))
    graph = CrankSlider.create(pin, piston, name="crankSlider", axis="y")
    owner = graph.container
    # 青 = 入力のクランク(円板と腕)。緑 = CrankSliderの出力(ロッドとピストン)。灰 = シリンダーの壁(固定)。
    disc = cmds.polyCylinder(name="crankDisc", radius=RADIUS + 0.5, height=0.3, axis=(0, 0, 1))[0]
    cmds.parent(disc, crank, relative=True)
    cmds.setAttr(disc + ".translateZ", -0.6)
    cmds.sets(disc, edit=True, forceElement=_shader("discDark", (0.22, 0.22, 0.25)))
    _box("crankArm", (0.6, RADIUS, 0.4), input_color, crank, (0, RADIUS / 2.0, -0.3))
    _box("crankPinGeo", (0.5, 0.5, 0.9), input_color, pin)
    rod = cmds.createNode("transform", name="rod_GREEN")
    _box("rodGeo", (LENGTH, 0.35, 0.3), green, rod, (LENGTH / 2.0, 0, 0.2))
    cmds.connectAttr(str(owner) + ".rodMatrix", rod + ".offsetParentMatrix")
    head = cmds.createNode("transform", name="piston_GREEN")
    _box("pistonGeo", (1.8, 1.6, 1.2), green, head, (0, 0.5, 0))
    cmds.connectAttr(str(owner) + ".pistonMatrix", head + ".offsetParentMatrix")
    for side in (-1, 1):
        _box("cylinderWall{}".format(side + 1), (0.25, 6.0, 1.4), gray, None, (side * 1.05, 8.2, 0))
    camera, camera_shape = cmds.camera(name="crankSliderCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(-6.0, 4.2, 34.0), lookAt=(-6.0, 4.2, 0))
    window = cmds.window("crankSliderValidationWindow", title="CrankSlider - crank and piston", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("crankSliderValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("crankSlider", 7)
    scene = {"owner": owner, "crank": crank, "pin": pin}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、ピストンの位置を閉じた式と、ピンとの距離をロッドの長さと比べた診断を返す。"""
    from maya import cmds
    import maya.api.OpenMaya as om
    angle, length, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(scene["crank"] + ".rotateZ", angle)
    cmds.setAttr(owner + ".rodLength", length)
    piston = om.MMatrix(cmds.getAttr(owner + ".pistonMatrix"))
    rod = om.MMatrix(cmds.getAttr(owner + ".rodMatrix"))
    pin = om.MMatrix(cmds.getAttr(scene["pin"] + ".worldMatrix[0]"))
    expected = height(angle, length)
    position = om.MPoint(piston[12], piston[13], piston[14])
    pin_point = om.MPoint(pin[12], pin[13], pin[14])
    position_error = (position - om.MPoint(0, expected, 0)).length()
    distance = (position - pin_point).length()
    toward = (position - pin_point).normal()
    aim_error = 1.0 - om.MVector(rod[0], rod[1], rod[2]).normal() * toward
    rod_origin_error = (om.MPoint(rod[12], rod[13], rod[14]) - pin_point).length()
    stroke = cmds.getAttr(owner + ".stroke")
    theta = angle % 360.0
    values[:] = [
        "BLUE = crank (input, rotateZ)   GREEN = CrankSlider output (rod and piston)   GRAY = cylinder (fixed)",
        "STAGE: " + stage,
        "fixed: crank radius r = 2 cm   cylinder axis = +Y   rest crank angle = 30 deg",
        "piston Y = r cos(theta) + sqrt(L^2 - r^2 sin^2(theta))   stroke = Y - Y(rest)   rod aims from pin to piston",
        "INPUT crank theta = {:6.1f} deg   rodLength L = {:5.2f} cm".format(theta, length),
        "OUTPUT piston Y = {:7.4f} cm   formula = {:7.4f} cm   stroke = {:7.4f} cm   |pin - piston| = {:7.4f} cm".format(
            position.y, expected, stroke, distance),
        "CHECK |piston - formula| = {:.7f} cm   |distance - L| = {:.7f} cm   rod aim error = {:.7f}".format(
            position_error, abs(distance - length), aim_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (position_error < 1e-4 and abs(distance - length) < 1e-4 and aim_error < 1e-6 and rod_origin_error < 1e-4
          and abs(stroke - (expected - height(START, LENGTH))) < 1e-4)
    return {"frame": frame, "presentation_stage": stage, "input": {"angle": angle, "rodLength": length},
            "position_error": position_error, "distance_error": abs(distance - length), "aim_error": aim_error,
            "stroke": stroke, "ok": ok}


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
        folder = recordVideo("CrankSlider: クランクとピストン", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "crank_slider.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-crank-slider.json").write_text(
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
    from run_mlib_gui_versions import run_version
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("crank-slider-%Y%m%d-%H%M%S")
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
