"""Pistonのシリンダーとロッドの相互エイム・伸縮量・ストローク超過を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_piston.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIVOT = (8.0, -2.0)
ARM_LENGTH = 5.0
MINIMUM = 6.5
MAXIMUM = 11.0
PART_LENGTH = 6.0
SEGMENT = 30
# (アームの角度[度、+Xから反時計回り], 次の姿勢へ向かう段階名)。基準は90度。
POSES = [
    (90, "1 REST"),
    (90, "2 ARM DOWN: ROD EXTENDS"),
    (60, "3 PAST MAXIMUM: OVERSTROKE > 0"),
    (30, "4 HOLD BEYOND MAXIMUM"),
    (30, "5 RETURN TO SAFE RANGE"),
    (90, "6 ARM UP: ROD RETRACTS"),
    (130, "7 PAST MINIMUM: OVERSTROKE < 0"),
    (160, "8 HOLD BEYOND MINIMUM"),
    (160, "9 RETURN TO REST"),
    (90, "9 RETURN TO REST"),
    (90, "9 RETURN TO REST"),
]


def pose(frame):
    """フレームのアーム角度と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    angle = POSES[index][0] + (POSES[index + 1][0] - POSES[index][0]) * weight
    return angle, POSES[index][1]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _part(name, parent, group, length, radius, z=0.0):
    """parentのローカル+X方向へ長さlengthの円柱を作る。zは奥行き方向へずらす量。"""
    from maya import cmds
    rod = cmds.polyCylinder(name=name, axis=(1, 0, 0), height=length, radius=radius, subdivisionsX=20)[0]
    cmds.setAttr(rod + ".translate", length / 2, 0, z)
    cmds.parent(rod, parent, relative=True)
    cmds.sets(rod, edit=True, forceElement=group)
    return rod


def _tipPosition(angle):
    """アーム角度(度)からロッドの取付け位置を返す。"""
    a = math.radians(angle)
    return (PIVOT[0] + ARM_LENGTH * math.cos(a), PIVOT[1] + ARM_LENGTH * math.sin(a), 0.0)


def buildScene():
    """検証シーンを作り、(panel, アーム, 入力の両端, 出力の両端, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import Piston
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    world = cmds.createNode("transform", name="machine_GRP")
    arm = cmds.createNode("transform", name="arm_GRP", parent=world)
    cmds.setAttr(arm + ".translate", PIVOT[0], PIVOT[1], 0)
    cmds.setAttr(arm + ".rotateZ", 90)
    base = cmds.createNode("joint", name="input_cylinder_JNT", parent=world)
    tip = cmds.createNode("joint", name="input_rod_JNT", parent=arm)
    cmds.setAttr(tip + ".translateX", ARM_LENGTH)
    # 生成時は両端の部品の+Xが互いを向く姿勢にする(見やすさのため。一致は必須ではない)。
    rest = _tipPosition(90)
    heading = math.degrees(math.atan2(rest[1], rest[0]))
    cmds.setAttr(base + ".rotateZ", heading)
    cmds.setAttr(tip + ".rotateZ", heading + 180 - 90)
    graph = Piston.create(base, tip, name="piston", aimAxis="x", upAxis="y", minimum=MINIMUM, maximum=MAXIMUM)
    owner = graph.container
    out_base = cmds.createNode("transform", name="output_cylinder_GRP", parent=world)
    out_tip = cmds.createNode("transform", name="output_rod_GRP", parent=arm)
    owner.getPlug("baseMatrix").connectTo(out_base + ".offsetParentMatrix")
    owner.getPlug("tipMatrix").connectTo(out_tip + ".offsetParentMatrix")
    grey = _shader("machineGrey", (0.5, 0.5, 0.53))
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.6)
    green = _shader("outputGreen", (0.1, 0.8, 0.2))
    rod_green = _shader("outputRodGreen", (0.55, 0.95, 0.6))
    # 灰=アームと固定台、赤(半透明)=入力の向きのままの部品、緑=出力(シリンダーは濃い緑、ロッドは薄い緑)。
    _part("arm_GEO", arm, grey, ARM_LENGTH, 0.3, z=-1.2)
    mount = cmds.polyCube(name="mount_GEO", width=1.6, height=1.6, depth=1.6)[0]
    cmds.parent(mount, world, relative=True)
    cmds.sets(mount, edit=True, forceElement=grey)
    _part("inputCylinder_GEO", base, red, PART_LENGTH, 0.55, z=1.4)
    _part("inputRod_GEO", tip, red, PART_LENGTH, 0.25, z=1.4)
    _part("outputCylinder_GEO", out_base, green, PART_LENGTH, 0.55)
    _part("outputRod_GEO", out_tip, rod_green, PART_LENGTH, 0.25)
    camera, camera_shape = cmds.camera(name="pistonCamera", focalLength=35)
    # 正面(+Z)から少し上より。アームの回転とロッドの出入りが見える位置に固定する。
    cmds.viewPlace(camera_shape, eye=(6, 3, 27), lookAt=(6, 0.5, 0))
    cmds.setAttr(camera_shape + ".verticalFilmOffset", -0.16)
    window = cmds.window("pistonValidationWindow", title="Piston - cylinder and rod aim at each other",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("pistonValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 7
    names = ["pistonHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, arm, (base, tip), (out_base, out_tip), owner, values, names


def evaluate_frame(frame, arm, inputs, outputs, owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import Piston
    angle, stage = pose(frame)
    cmds.setAttr(arm + ".rotateZ", angle)
    base = om.MVector(cmds.xform(inputs[0], q=True, worldSpace=True, translation=True))
    tip = om.MVector(cmds.xform(inputs[1], q=True, worldSpace=True, translation=True))
    length = (tip - base).length()
    direction = (tip - base).normal()
    errors = []
    for out, target in ((outputs[0], direction), (outputs[1], -direction)):
        matrix = om.MMatrix(cmds.getAttr(out + ".worldMatrix[0]"))
        axis = om.MVector(matrix[0], matrix[1], matrix[2]).normal()
        errors.append(math.degrees(axis.angle(target)))
    position_error = max(
        (om.MVector(cmds.xform(o, q=True, worldSpace=True, translation=True)) - p).length()
        for o, p in ((outputs[0], base), (outputs[1], tip)))
    dg = {attr: owner.getPlug(attr).get() for attr in ("length", "restLength", "extension", "overStroke")}
    expected_over = Piston.overStroke(length, MINIMUM, MAXIMUM)
    if expected_over > 1e-6:
        state = "length > max 11 -> overStroke > 0 (value only, ends not moved)"
    elif expected_over < -1e-6:
        state = "length < min 6.5 -> overStroke < 0 (value only, ends not moved)"
    else:
        state = "inside stroke range -> overStroke = 0"
    values[:] = [
        "DARK GREEN = output cylinder   LIGHT GREEN = output rod   RED (transparent) = input parts   GREY = arm",
        "STAGE: " + stage,
        "fixed: restLength = {:.2f} cm   minimum = 6.5 cm   maximum = 11 cm   arm pivot (8, -2), radius 5 cm".format(
            dg["restLength"]),
        "each end: aimMatrix +X -> other end, +Y aligned to shared up   extension = length - rest   "
        "overStroke = max(L-max,0) - max(min-L,0)",
        "INPUT arm angle = {:6.1f} deg   end distance (independent) = {:6.3f} cm".format(angle, length),
        "OUTPUT length = {:6.3f}  extension = {:+6.3f}  overStroke = {:+6.3f} cm   {}".format(
            dg["length"], dg["extension"], dg["overStroke"], state),
        "CHECK aim error cylinder = {:.4f} deg  rod = {:.4f} deg   position error = {:.5f} cm".format(
            errors[0], errors[1], position_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (abs(dg["length"] - length) < 1e-3 and abs(dg["extension"] - (length - dg["restLength"])) < 1e-3
          and abs(dg["overStroke"] - expected_over) < 1e-3 and max(errors) < 0.01 and position_error < 1e-4)
    return {"frame": frame, "presentation_stage": stage, "input_arm_angle_degrees": angle,
            "independent_length_cm": length, "dg": dg, "expected_over_stroke_cm": expected_over,
            "aim_error_degrees": errors, "position_error_cm": position_error, "ok": ok}


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
        panel, arm, inputs, outputs, owner, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("Piston: シリンダーとロッドの相互エイムとストローク超過", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, arm, inputs, outputs, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "piston.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-piston.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("piston-%Y%m%d-%H%M%S")
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
