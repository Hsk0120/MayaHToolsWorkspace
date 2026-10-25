"""BoxRollの箱の縁から縁への転がりを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_box_roll.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
SIZE = 4.0
# (roll[度], 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, "1 REST"),
    (0.0, "2 ROLL FORWARD 3 TIMES (0 -> 270 deg)"),
    (270.0, "3 ROLL BACKWARD TO -90 deg"),
    (-90.0, "4 RETURN TO REST"),
    (0.0, "4 RETURN TO REST"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    return POSES[index][0] + (POSES[index + 1][0] - POSES[index][0]) * weight, POSES[index][1]


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


def _box(name, group, mark_group):
    """底の面の中心がローカル原点の一辺 SIZE の箱と、向きが分かる目印(1つの面の小さな板)を作る。"""
    from maya import cmds
    root = cmds.createNode("transform", name=name)
    cube = cmds.polyCube(name=name + "_cube", width=SIZE * 0.6, height=SIZE, depth=SIZE)[0]
    cmds.parent(cube, root, relative=True)
    cmds.setAttr(cube + ".translateY", SIZE / 2.0)
    cmds.sets(cube, edit=True, forceElement=group)
    mark = cmds.polyCube(name=name + "_mark", width=SIZE * 0.62, height=SIZE * 0.3, depth=SIZE * 0.3)[0]
    cmds.parent(mark, root, relative=True)
    cmds.setAttr(mark + ".translate", 0, SIZE * 0.8, SIZE * 0.3)
    cmds.sets(mark, edit=True, forceElement=mark_group)
    return root


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import BoxRoll
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    green, red = _shader("boxGreen", (0.15, 0.75, 0.25)), _shader("centerRed", (0.85, 0.15, 0.1), 0.6)
    mark = _shader("markDark", (0.1, 0.1, 0.12))
    floor = cmds.polyPlane(name="floor_GEO", width=8, height=44, subdivisionsX=1, subdivisionsY=11)[0]
    cmds.setAttr(floor + ".translate", 0, -0.02, 2)
    cmds.sets(floor, edit=True, forceElement=_shader("floorBlue", (0.35, 0.45, 0.6)))
    # 緑 = BoxRoll(前の下の縁を支点に転がり、90度ごとに次の縁へ)。赤 = 比較用に中心で回すだけ(床へ潜る)。
    target = cmds.createNode("transform", name="box_REST")
    graph = BoxRoll.create(target, SIZE, name="boxRoll")
    owner = graph.container
    box = _box("box_GREEN", green, mark)
    cmds.connectAttr(str(owner) + ".matrix", box + ".offsetParentMatrix")
    pivot = cmds.createNode("transform", name="centerPivot")
    cmds.setAttr(pivot + ".translate", 0.0, SIZE / 2.0, -9.0)
    compare = _box("box_RED", red, mark)
    cmds.parent(compare, pivot, relative=True)
    cmds.setAttr(compare + ".translateY", -SIZE / 2.0)
    camera, camera_shape = cmds.camera(name="boxRollCamera", focalLength=30)
    cmds.viewPlace(camera_shape, eye=(40, 6.0, 2.5), lookAt=(0, -2.5, 2.5))
    window = cmds.window("boxRollValidationWindow", title="BoxRoll - pivot switching", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("boxRollValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("boxRoll", 7)
    scene = {"owner": owner, "pivot": pivot}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、行列を式と、一番低い角を床と比べた診断を返す。"""
    from maya import cmds
    import maya.api.OpenMaya as om
    from mlrig.setups import BoxRoll
    roll, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(owner + ".roll", roll)
    cmds.setAttr(scene["pivot"] + ".rotateX", roll)
    matrix = om.MMatrix(cmds.getAttr(owner + ".matrix"))
    expected = om.MMatrix(list(BoxRoll.localMatrix(math.radians(roll), SIZE)))
    error = max(abs(matrix[i] - expected[i]) for i in range(16))
    half = SIZE / 2.0
    corners = [om.MPoint(0, y, z) * matrix for y in (0.0, SIZE) for z in (-half, half)]
    lowest = min(point.y for point in corners)
    step = cmds.getAttr(owner + ".step")
    partial = roll - 90.0 * step
    pivot = (step + 0.5) * SIZE
    touching = min(abs(point.z - pivot) for point in corners if abs(point.y) < 1e-4) if lowest > -1e-4 else 1e9
    values[:] = [
        "GREEN = BoxRoll (pivot switches to the next edge every 90 deg)   RED = rotate about the center only (sinks)",
        "STAGE: " + stage,
        "fixed: size = 4 cm   roll axis = X   rolls toward +Z (X x Y)   floor = Y 0   c = (0, 2, 0)   e = (0, 0, 2)",
        "n = floor(roll / 90)   phi = roll - n * 90   matrix = T(-c) Rx(n*90) T(c - e) Rx(phi) T(e + n * size * Z)",
        "INPUT roll = {:7.2f} deg   ->   n = {:2.0f}   phi = {:6.2f} deg".format(roll, step, partial),
        "OUTPUT pivot edge Z = (n + 1/2) * size = {:6.2f} cm   lowest corner Y = {:8.5f} cm".format(pivot, lowest),
        "CHECK max |matrix - formula| = {:.7f}   |touching corner Z - pivot edge Z| = {:.7f} cm".format(
            error, touching),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and lowest > -1e-4 and touching < 1e-4
    return {"frame": frame, "presentation_stage": stage, "input": {"roll": roll}, "step": step,
            "error": error, "lowest": lowest, "touching_error": touching, "ok": ok}


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
        folder = recordVideo("BoxRoll: 箱の縁から縁への転がり", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "box_roll.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-box-roll.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("box-roll-%Y%m%d-%H%M%S")
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
