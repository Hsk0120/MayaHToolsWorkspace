"""RockerRollの丸い底の転がりを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_rocker_roll.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
RADIUS = 4.0
# (roll[度], radius[cm], 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, RADIUS, "1 REST"),
    (0.0, RADIUS, "2 ROLL FORWARD +40 deg"),
    (40.0, RADIUS, "3 ROLL BACKWARD TO -35 deg"),
    (-35.0, RADIUS, "4 radius ATTR 4 -> 6 cm AND ROLL +30 deg (DRAWN RUNNER STAYS 4 cm)"),
    (30.0, 6.0, "5 RETURN TO REST"),
    (0.0, RADIUS, "5 RETURN TO REST"),
    (0.0, RADIUS, "5 RETURN TO REST"),
]


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


def _chair(name, group, seat_group, x):
    """円弧の脚(細い円環の一部の代わりに小さな箱を円弧に並べる)と座面の箱を、1つのtransformの下に作る。"""
    from maya import cmds
    root = cmds.createNode("transform", name=name)
    cmds.setAttr(root + ".translateX", x)
    for index in range(21):
        angle = math.radians(-60 + 6 * index)
        piece = cmds.polyCube(name="{}_runner{}".format(name, index), width=0.3, height=0.18, depth=0.45)[0]
        cmds.parent(piece, root, relative=True)
        cmds.setAttr(piece + ".translate", 0, RADIUS - RADIUS * math.cos(angle) + 0.09, RADIUS * math.sin(angle))
        cmds.setAttr(piece + ".rotateX", -math.degrees(angle))
        cmds.sets(piece, edit=True, forceElement=group)
    seat = cmds.polyCube(name=name + "_seat", width=0.6, height=0.3, depth=3.0)[0]
    cmds.parent(seat, root, relative=True)
    cmds.setAttr(seat + ".translateY", 2.2)
    cmds.sets(seat, edit=True, forceElement=seat_group)
    back = cmds.polyCube(name=name + "_back", width=0.6, height=2.6, depth=0.3)[0]
    cmds.parent(back, root, relative=True)
    cmds.setAttr(back + ".translate", 0, 3.5, -1.4)
    cmds.sets(back, edit=True, forceElement=seat_group)
    return root


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import RockerRoll
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    green, red = _shader("rockerGreen", (0.15, 0.75, 0.25)), _shader("pivotRed", (0.85, 0.15, 0.1))
    seat = _shader("seatGray", (0.6, 0.6, 0.62))
    floor = cmds.polyPlane(name="floor_GEO", width=8, height=30, subdivisionsX=1, subdivisionsY=30)[0]
    cmds.setAttr(floor + ".translate", 0, -0.02, 0)
    cmds.sets(floor, edit=True, forceElement=_shader("floorBlue", (0.35, 0.45, 0.6)))
    # 緑 = RockerRoll(接地点が円弧の上を移る)。赤 = 比較用に円弧の中心で回すだけ(床から浮く・沈む)。
    target = cmds.createNode("transform", name="rocker_REST")
    graph = RockerRoll.create(target, RADIUS, name="rockerRoll")
    owner = graph.container
    rocker = _chair("rocker_GREEN", green, seat, 0.0)
    cmds.connectAttr(str(owner) + ".matrix", rocker + ".offsetParentMatrix")
    pivot = cmds.createNode("transform", name="centerPivot")
    cmds.setAttr(pivot + ".translate", 0.0, RADIUS, -8.0)
    compare = _chair("rocker_RED", red, seat, 0.0)
    cmds.parent(compare, pivot, relative=True)
    cmds.setAttr(compare + ".translateY", -RADIUS)
    camera, camera_shape = cmds.camera(name="rockerRollCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(22, 1.6, -4.0), lookAt=(0, 1.6, -4.0))
    window = cmds.window("rockerRollValidationWindow", title="RockerRoll - rolling pivot", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("rockerRollValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("rockerRoll", 7)
    scene = {"owner": owner, "pivot": pivot}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、行列を式と、接地点を床と転がった弧の長さと比べた診断を返す。"""
    from maya import cmds
    import maya.api.OpenMaya as om
    from mlrig.setups import RockerRoll
    roll, radius, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(owner + ".roll", roll)
    cmds.setAttr(owner + ".radius", radius)
    cmds.setAttr(scene["pivot"] + ".rotateX", roll)
    rad = math.radians(roll)
    matrix = om.MMatrix(cmds.getAttr(owner + ".matrix"))
    expected = om.MMatrix(list(RockerRoll.localMatrix(rad, radius)))
    error = max(abs(matrix[i] - expected[i]) for i in range(16))
    # 角度 roll の位置の円弧の点(生成時のローカル)は、床の z = radius * roll に触れる。
    touching = om.MPoint(0, radius - radius * math.cos(rad), radius * math.sin(rad)) * matrix
    contact_error = (touching - om.MPoint(0, 0, radius * rad)).length()
    travel = cmds.getAttr(owner + ".travel")
    values[:] = [
        "GREEN = RockerRoll (pivot moves to the contact point)   RED = rotate about the arc center only (lifts and sinks)",
        "STAGE: " + stage,
        "fixed: runner arc center c = (0, radius, 0)   roll axis = X   rolls toward +Z (X x Y)   floor = Y 0",
        "matrix = T(-c) * Rx(roll) * T(0, 0, radius * roll_rad) * T(c)   travel = radius * roll_rad (no slipping)",
        "INPUT roll = {:7.2f} deg   radius = {:5.2f} cm".format(roll, radius),
        "OUTPUT travel = {:7.3f} cm   contact point Y = {:8.5f} cm   Z = {:7.3f} cm".format(
            travel, touching.y, touching.z),
        "CHECK max |matrix - formula| = {:.7f}   |contact - (0, 0, radius * roll)| = {:.7f} cm".format(
            error, contact_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and contact_error < 1e-4 and abs(travel - radius * rad) < 1e-4
    return {"frame": frame, "presentation_stage": stage, "input": {"roll": roll, "radius": radius},
            "error": error, "contact_error": contact_error, "travel": travel, "ok": ok}


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
        folder = recordVideo("RockerRoll: 丸い底の転がり", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "rocker_roll.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-rocker-roll.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("rocker-roll-%Y%m%d-%H%M%S")
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
