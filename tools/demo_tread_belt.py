"""TreadBeltの履帯の巡回を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_tread_belt.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
COUNT = 16
RADIUS = 1.2
STRETCH = 3.0
# (車体のZ[cm], phase, 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, 0.0, "1 REST"),
    (0.0, 0.0, "2 DRIVE FORWARD +8 cm"),
    (8.0, 0.0, "3 HOLD (VEHICLE STOPPED)"),
    (8.0, 0.0, "4 DRIVE BACKWARD TO -4 cm"),
    (-4.0, 0.0, "5 phase 0 -> 0.25 (SHIFT ALL PLATES A QUARTER LOOP)"),
    (-4.0, 0.25, "6 RETURN TO REST"),
    (0.0, 0.0, "6 RETURN TO REST"),
    (0.0, 0.0, "6 RETURN TO REST"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:2], POSES[index + 1][:2])]
    return values[0], values[1], POSES[index][2]


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


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import TreadBelt
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"green": _shader("plateGreen", (0.15, 0.75, 0.25)), "gray": _shader("bodyGray", (0.55, 0.55, 0.58)),
              "dark": _shader("wheelDark", (0.25, 0.25, 0.28)), "floor": _shader("floorBlue", (0.35, 0.45, 0.6)),
              "white": _shader("markWhite", (0.95, 0.95, 0.9))}
    floor = cmds.polyPlane(name="floor_GEO", width=4, height=40, subdivisionsX=1, subdivisionsY=40)[0]
    cmds.setAttr(floor + ".translate", -1.0, -0.07, 2.0)
    cmds.sets(floor, edit=True, forceElement=groups["floor"])
    vehicle = cmds.createNode("transform", name="vehicle")
    body = cmds.polyCube(name="body_GEO", width=1.6, height=1.4, depth=RADIUS * 2 * STRETCH - 0.6)[0]
    cmds.parent(body, vehicle, relative=True)
    cmds.setAttr(body + ".translate", -1.4, RADIUS + 1.4, 0)
    cmds.sets(body, edit=True, forceElement=groups["gray"])
    path = cmds.circle(name="treadPath", normal=(1, 0, 0), radius=RADIUS, sections=24, constructionHistory=False)[0]
    cmds.scale(1, 1, STRETCH, path + ".cv[*]", relative=True)
    cmds.parent(path, vehicle, relative=True)
    cmds.setAttr(path + ".translateY", RADIUS + 0.06)
    wheels = []
    for index, z in enumerate((-RADIUS * (STRETCH - 1), 0.0, RADIUS * (STRETCH - 1))):
        wheel = cmds.polyCylinder(name="wheel{}_GEO".format(index), radius=RADIUS * 0.8, height=0.8, axis=(1, 0, 0),
                                  subdivisionsX=16)[0]
        cmds.parent(wheel, vehicle, relative=True)
        cmds.setAttr(wheel + ".translate", -0.5, RADIUS + 0.06, z * 0.95)
        cmds.sets(wheel, edit=True, forceElement=groups["dark"])
        mark = cmds.polyCube(name="wheel{}_mark".format(index), width=0.82, height=RADIUS * 0.7, depth=0.15)[0]
        cmds.parent(mark, wheel, relative=True)
        cmds.setAttr(mark + ".translateY", RADIUS * 0.35)
        cmds.sets(mark, edit=True, forceElement=groups["white"])
        wheels.append(wheel)
    graph = TreadBelt.create(path, COUNT, name="treadBelt", normal=(1, 0, 0), driver=vehicle + ".translateZ")
    owner = graph.container
    for index in range(COUNT):
        plate = cmds.polyCube(name="plate{}_GEO".format(index), width=0.55, height=0.12, depth=1.0)[0]
        cmds.connectAttr("{}.matrix{}".format(owner, index), plate + ".offsetParentMatrix")
        cmds.sets(plate, edit=True, forceElement=groups["white" if index == 0 else "green"])
    camera, camera_shape = cmds.camera(name="treadBeltCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(21, 0.6, 2.0), lookAt=(0, 0.6, 2.0))
    window = cmds.window("treadBeltValidationWindow", title="TreadBelt - tank tread", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("treadBeltValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("treadBelt", 7)
    scene = {"owner": owner, "vehicle": vehicle, "path": path, "wheels": wheels}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、各板の位置・向きを弧長からの独立計算と比較した診断を返す。"""
    from maya import cmds
    import maya.api.OpenMaya as om
    from mlrig.setups import TreadBelt
    z, phase, stage = pose(frame)
    owner, path = str(scene["owner"]), scene["path"]
    cmds.setAttr(scene["vehicle"] + ".translateZ", z)
    cmds.setAttr(owner + ".phase", phase)
    for wheel in scene["wheels"]:
        # 車輪は見た目だけ(デモ側で回す)。履帯と同じ送り量 / 車輪の半径。
        cmds.setAttr(wheel + ".rotateX", math.degrees(z / RADIUS))
    selection = om.MSelectionList()
    selection.add(path)
    fn = om.MFnNurbsCurve(selection.getDagPath(0).extendToShape())
    length = fn.length()
    world = om.MMatrix(cmds.getAttr(path + ".worldMatrix[0]"))
    normal = (om.MVector(1, 0, 0) * world).normal()
    distance = cmds.getAttr(owner + ".distance")
    fractions = TreadBelt.fractions(COUNT, z, length, phase)
    error = tangent_error = 0.0
    minimum = 1.0
    lowest = None
    for index, fraction in enumerate(fractions):
        matrix = om.MMatrix(cmds.getAttr("{}.matrix{}".format(owner, index)))
        param = fn.findParamFromLength(fraction * length)
        point = fn.getPointAtParam(param, om.MSpace.kWorld)
        tangent = fn.tangent(param, om.MSpace.kWorld).normal()
        position = om.MPoint(matrix[12], matrix[13], matrix[14])
        front = om.MVector(matrix[0], matrix[1], matrix[2])
        top = om.MVector(matrix[8], matrix[9], matrix[10])
        error = max(error, (position - point).length())
        tangent_error = max(tangent_error, (front - tangent).length())
        minimum = min(minimum, top * normal)
        if lowest is None or position.y < lowest[1]:
            lowest = (index, position.y, position.z)
    values[:] = [
        "GREEN = tread plates (16)   WHITE = plate 0   GRAY = vehicle body   BLUE = floor   outputs are world matrices",
        "STAGE: " + stage,
        "fixed: plates = 16   curve length L = {:.3f} cm   up axis = belt plane normal (never flips)".format(length),
        "fraction_i = frac(i / 16 + phase + distance / L)   distance = vehicle.translateZ - rest   placed by arc length",
        "INPUT vehicle Z = {:6.2f} cm   distance = {:6.2f} cm   phase = {:4.2f}   plate0 fraction = {:.4f}".format(
            z, distance, phase, cmds.getAttr(owner + ".fraction0")),
        "OUTPUT lowest plate = {:2d}   world Z = {:6.2f} cm (ground side stays while driving)".format(
            lowest[0], lowest[2]),
        "CHECK max |position - arc length| = {:.6f} cm   max |front - tangent| = {:.6f}   min up.normal = {:.5f}".format(
            error, tangent_error, minimum),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-3 and tangent_error < 1e-3 and minimum > 0.999 and abs(distance - z) < 1e-4
    return {"frame": frame, "presentation_stage": stage, "input": {"vehicleZ": z, "phase": phase},
            "fractions": fractions, "error": error, "tangent_error": tangent_error, "min_up_dot": minimum,
            "lowest": list(lowest), "ok": ok}


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
        folder = recordVideo("TreadBelt: 履帯の巡回", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "tread_belt.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-tread-belt.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("tread-belt-%Y%m%d-%H%M%S")
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
