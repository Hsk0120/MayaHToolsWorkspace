"""BeltDriveのベルト伝動(2つのプーリーの共通接線・巻き付け角・回転の比)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_belt_drive.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRIVER = 2.0
FRAMES = 480
#: 駆動プーリーの回転の速さ(度/フレーム)。24フレーム目から回し始める。
SPEED = 3.0
# (フレーム, distance, drivenRadius, crossed, その区間の段階名)。区間の間は線形に補間し、crossedは区間の始めの値。
KEYS = [
    (0, 6.0, 1.0, False, "1 OPEN BELT: r1 = 2, r2 = 1, d = 6"),
    (24, 6.0, 1.0, False, "2 TURN THE DRIVER: THE DRIVEN PULLEY TURNS x r1 / r2 = 2"),
    (96, 6.0, 1.0, False, "3 MOVE THE DRIVEN PULLEY AWAY: THE SPANS STAY TANGENT"),
    (144, 9.0, 1.0, False, "4 MOVE IT CLOSER"),
    (192, 5.5, 1.0, False, "5 GROW THE DRIVEN PULLEY TO r2 = 3: RATIO 2 / 3, WRAP MOVES TO IT"),
    (240, 5.5, 3.0, False, "6 PAST THE OPEN LIMIT d = |r1 - r2| = 1: STOPS, NEGATIVE EXCESS"),
    (276, 0.4, 3.0, False, "7 BACK INSIDE THE RANGE"),
    (312, 7.0, 3.0, True, "8 CROSSED BELT: THE DRIVEN PULLEY TURNS THE OTHER WAY, r2 = 1.5"),
    (348, 7.0, 1.5, True, "9 PAST THE CROSSED LIMIT d = r1 + r2 = 3.5: STOPS, NEGATIVE EXCESS"),
    (396, 2.0, 1.5, True, "10 BACK INSIDE THE RANGE"),
    (432, 6.0, 1.5, False, "11 BACK TO THE OPEN BELT, r2 = 1"),
    (468, 6.0, 1.0, False, "12 OPEN BELT"),
    (FRAMES, 6.0, 1.0, False, "12 OPEN BELT"),
]


def parameters(frame):
    """フレームの(rotation, distance, drivenRadius, crossed, 段階名)を返す。"""
    rotation = max(frame - 24, 0) * SPEED
    for start, end in zip(KEYS, KEYS[1:]):
        if frame <= end[0]:
            weight = (frame - start[0]) / float(end[0] - start[0])
            return (rotation, start[1] + (end[1] - start[1]) * weight, start[2] + (end[2] - start[2]) * weight,
                    start[3], start[4])
    return rotation, KEYS[-1][1], KEYS[-1][2], KEYS[-1][3], KEYS[-1][4]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _pulley(role, owner, group, mark):
    """行列の出力に追従し、半径のアトリビュートで大きさが変わる円板と、回転が見える白い印を作る。"""
    from maya import cmds
    node = cmds.createNode("transform", name="output_{}_GRP".format(role))
    owner.getPlug(role + "Matrix").connectTo(node + ".offsetParentMatrix")
    size = cmds.createNode("transform", name="{}Size_GRP".format(role), parent=node)
    for axis in "XY":
        cmds.connectAttr("{}.{}Radius".format(owner, role), "{}.scale{}".format(size, axis))
    disc = cmds.polyCylinder(name=role + "_GEO", axis=(0, 0, 1), height=0.3, radius=1.0, subdivisionsX=48)[0]
    cmds.parent(disc, size, relative=True)
    cmds.sets(disc, edit=True, forceElement=group)
    spoke = cmds.polyCube(name=role + "Mark_GEO", width=0.7, height=0.12, depth=0.36)[0]
    cmds.setAttr(spoke + ".translateX", 0.6)
    cmds.parent(spoke, size, relative=True)
    cmds.sets(spoke, edit=True, forceElement=mark)
    return node


def _span(role, owner, group):
    """行列の出力に追従し、spanLengthで伸び縮みするベルトの直線部(ローカル+Xへ伸びる棒)を作る。"""
    from maya import cmds
    node = cmds.createNode("transform", name="output_{}_GRP".format(role))
    owner.getPlug(role + "Matrix").connectTo(node + ".offsetParentMatrix")
    size = cmds.createNode("transform", name="{}Length_GRP".format(role), parent=node)
    cmds.connectAttr(str(owner) + ".spanLength", size + ".scaleX")
    rod = cmds.polyCube(name=role + "_GEO", width=1.0, height=0.12, depth=0.5)[0]
    cmds.setAttr(rod + ".translateX", 0.5)
    cmds.parent(rod, size, relative=True)
    cmds.sets(rod, edit=True, forceElement=group)
    return node


def buildScene():
    """検証シーンを作り、(panel, 部品の辞書, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import BeltDrive
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    base = cmds.createNode("transform", name="beltBase_GRP")
    graph = BeltDrive.create(base, driverRadius=DRIVER, drivenRadius=1.0, distance=6.0, name="beltDrive")
    owner = graph.container
    green = _shader("driverGreen", (0.1, 0.7, 0.2))
    blue = _shader("drivenBlue", (0.15, 0.4, 1.0))
    yellow = _shader("beltYellow", (1.0, 0.85, 0.1))
    white = _shader("markWhite", (0.95, 0.95, 0.95))
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.4)
    # 緑=駆動プーリー、青=従動プーリー、黄=ベルトの直線部(いずれも出力)、白=回転の印、
    # 赤(半透明)=入力のdistanceの位置(止める前の従動プーリーの中心)。
    scene = {"driver": _pulley("driver", owner, green, white), "driven": _pulley("driven", owner, blue, white),
             "upper": _span("upperSpan", owner, yellow), "lower": _span("lowerSpan", owner, yellow)}
    ring = cmds.polyTorus(name="inputDistance_GEO", axis=(0, 0, 1), radius=0.35, sectionRadius=0.07)[0]
    cmds.setAttr(ring + ".translateZ", 0.6)
    cmds.sets(ring, edit=True, forceElement=red)
    scene["ring"] = ring
    camera, camera_shape = cmds.camera(name="beltCamera", orthographic=True)
    # 回転軸(Z)の正面から、2つのプーリーとベルト全体を見る位置に固定する。
    # 左のHUDの文字と重ならないように、絵を右へ寄せる(駆動プーリーの左端が画面の中央の少し右)。
    cmds.setAttr(camera + ".translate", -2.45, -0.6, 40.0)
    cmds.setAttr(camera_shape + ".orthographicWidth", 27.0)
    window = cmds.window("beltDriveValidationWindow", title="BeltDrive - two pulleys and a belt",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("beltDriveValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 9
    names = ["beltDriveHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, scene, owner, values, names


def evaluate_frame(frame, scene, owner, values, names):
    """入力を更新し、DG出力を独立計算・接線の条件と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import BeltDrive
    rotation, distance, driven, crossed, stage = parameters(frame)
    owner.getPlug("rotation").set(rotation)
    owner.getPlug("distance").set(distance)
    owner.getPlug("drivenRadius").set(driven)
    owner.getPlug("crossed").set(crossed)
    # 赤の輪は入力のdistanceそのまま(止める前)の位置。
    cmds.setAttr(scene["ring"] + ".translateX", distance)
    clamped, excess, tangent, span, driverWrap, drivenWrap, length, ratio = BeltDrive.evaluate(
        distance, DRIVER, driven, crossed)
    expected = {"clampedDistance": clamped, "excess": excess, "spanLength": span, "beltLength": length,
                "ratio": ratio, "tangentAngle": tangent, "driverWrap": driverWrap, "drivenWrap": drivenWrap,
                "drivenRotation": ratio * rotation}
    dg = {attr: owner.getPlug(attr).get() for attr in expected}
    lengths = ("clampedDistance", "excess", "spanLength", "beltLength", "ratio")
    value_error = max(abs(dg[attr] - expected[attr]) for attr in lengths)
    angle_error = max(abs(dg[attr] - expected[attr]) for attr in ("tangentAngle", "driverWrap", "drivenWrap"))
    # 従動プーリーの回転は大きな角度になるので、比で割った駆動側の角度の差で比べる。
    turn_error = abs(dg["drivenRotation"] - expected["drivenRotation"]) / max(abs(ratio), 1.0)
    # 接線の条件(角度の式から独立): 直線部の両端が円周上にあり、半径が直線部に垂直。
    center = om.MPoint(cmds.xform(scene["driven"], q=True, worldSpace=True, translation=True))
    radial, perpendicular = [], []
    for key in ("upper", "lower"):
        matrix = om.MMatrix(cmds.getAttr(scene[key] + ".worldMatrix[0]"))
        start, end = om.MPoint() * matrix, om.MPoint(dg["spanLength"], 0, 0) * matrix
        along = om.MVector(1, 0, 0) * matrix
        radial += [abs(om.MVector(start).length() - DRIVER), abs((end - center).length() - driven)]
        perpendicular += [abs(om.MVector(start) * along), abs((end - center) * along)]
    tangent_error = max(radial + perpendicular)
    values[:] = [
        "GREEN = driver  BLUE = driven  YELLOW = belt spans (outputs)   RED ring = input distance (before the limit)",
        "STAGE: " + stage,
        "fixed: r1 = 2 cm   driver speed = 3 deg/frame   sign = +1 open, -1 crossed   k = r1 - sign * r2",
        "d = max(distance, |k|)   excess = distance - d   L = sqrt(d^2 - k^2)   theta = atan2(L, k)   ratio = sign * r1 / r2",
        "wrap1 = 360 - 2 theta   wrap2 = 2 theta (open) or 360 - 2 theta (crossed)   belt = 2 L + r1 wrap1 + r2 wrap2",
        "INPUT rotation = {:7.1f} deg  distance = {:5.2f} cm  r2 = {:4.2f} cm  crossed = {}".format(
            rotation, distance, driven, "ON" if crossed else "OFF"),
        "OUTPUT d = {:5.2f} cm  excess = {:+5.2f} cm  L = {:5.2f} cm  theta = {:5.1f} deg  wrap1 = {:5.1f}  wrap2 = {:5.1f} deg"
        .format(dg["clampedDistance"], dg["excess"], dg["spanLength"], dg["tangentAngle"], dg["driverWrap"],
                dg["drivenWrap"]),
        "OUTPUT ratio = {:+5.2f}  driven rotation = {:+8.1f} deg  belt length = {:6.2f} cm".format(
            dg["ratio"], dg["drivenRotation"], dg["beltLength"]),
        "CHECK |DG - formula| lengths {:.5f} cm  angles {:.5f} deg  |contact - circle|, radius . span max {:.5f} cm"
        .format(value_error, max(angle_error, turn_error), tangent_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = value_error < 2e-3 and angle_error < 0.1 and turn_error < 0.1 and tangent_error < 5e-3
    return {"frame": frame, "presentation_stage": stage, "rotation": rotation, "distance": distance,
            "drivenRadius": driven, "crossed": crossed, "dg": dg, "expected": expected,
            "value_error": value_error, "angle_error_degrees": angle_error, "turn_error_degrees": turn_error,
            "tangent_error": tangent_error, "ok": ok}


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
        panel, scene, owner, values, names = buildScene()
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("BeltDrive: ベルト伝動", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "belt-drive.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-belt-drive.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("belt-drive-%Y%m%d-%H%M%S")
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
