"""TelescopicCylinderの各段の伸び(外側から順・均等)と行程の超過を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_telescopic_cylinder.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOSED = 6.0
STROKES = (4.0, 3.0, 2.5)
SEGMENT = 40
# (先端までの距離 D[cm], 仰角[度], sequence, 次の姿勢へ向かう段階名)
POSES = [
    (6.0, 20.0, 1.0, "1 CLOSED -> EXTEND IN ORDER (OUTER STAGE FIRST)"),
    (13.0, 45.0, 1.0, "2 RETRACT IN ORDER"),
    (8.0, 30.0, 1.0, "3 SWITCH sequence 1 -> 0 (SAME LENGTH, STAGES REDISTRIBUTE)"),
    (8.0, 30.0, 0.0, "4 EXTEND UNIFORMLY (ALL STAGES TOGETHER)"),
    (14.0, 50.0, 0.0, "5 PULL BEYOND THE TOTAL STROKE (9.5 CM)"),
    (18.0, 55.0, 0.5, "6 BACK INTO RANGE, sequence -> 1"),
    (12.0, 40.0, 1.0, "7 BACK TO CLOSED"),
    (6.0, 20.0, 1.0, "8 BACK AT REST"),
    (6.0, 20.0, 1.0, "8 BACK AT REST"),
]


def pose(frame):
    """フレームの距離・仰角・sequence・段階名をsmoothstepで補間して返す。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    start, end = POSES[index], POSES[index + 1]
    values = [start[i] + (end[i] - start[i]) * weight for i in range(3)]
    return values[0], values[1], values[2], start[3]


def expected_stages(extension, sequence):
    """各段の伸びを式どおりに求める(セットアップのコードとは独立に書く)。"""
    total = min(max(extension, 0.0), sum(STROKES))
    result = []
    used = 0.0
    for stroke in STROKES:
        ordered = min(max(total - used, 0.0), stroke)
        uniform = total * stroke / sum(STROKES)
        result.append(uniform + sequence * (ordered - uniform))
        used += stroke
    return total, result


def _shader(name, color):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _cylinder(name, parent, start, end, radius, shader):
    """parentの下へ、X方向に start から end までの円柱を作る。"""
    from maya import cmds
    rod = cmds.polyCylinder(name=name + "_GEO", radius=radius, height=end - start, axis=(1, 0, 0),
                            subdivisionsAxis=24)[0]
    cmds.parent(rod, parent, relative=True)
    cmds.setAttr(rod + ".translateX", (start + end) * 0.5)
    cmds.sets(rod, edit=True, forceElement=shader)
    return rod


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import TelescopicCylinder
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    red = _shader("mountRed", (0.9, 0.15, 0.1))
    yellow = _shader("tipYellow", (0.95, 0.8, 0.1))
    greens = [_shader("stage{}Green".format(i), color) for i, color in enumerate(
        ((0.05, 0.35, 0.12), (0.1, 0.55, 0.2), (0.25, 0.75, 0.3), (0.55, 0.95, 0.5)))]
    base = cmds.createNode("transform", name="mount_JNT")
    tip = cmds.createNode("transform", name="tip_LOC")
    cmds.setAttr(tip + ".translate", CLOSED * math.cos(math.radians(20)), CLOSED * math.sin(math.radians(20)), 0)
    setup = TelescopicCylinder.create(base, tip, name="telescope", stages=3, stroke=list(STROKES))
    owner = str(setup.container)
    mount = cmds.polyCube(name="mount_GEO", width=1.6, height=0.8, depth=1.6)[0]
    cmds.parent(mount, base, relative=True)
    cmds.setAttr(mount + ".translateY", -0.6)
    cmds.sets(mount, edit=True, forceElement=red)
    hub = cmds.polySphere(name="tip_GEO", radius=0.45)[0]
    cmds.parent(hub, tip, relative=True)
    cmds.sets(hub, edit=True, forceElement=yellow)
    # 各段の筒: 外側ほど太く、閉じると原点(取り付け)へ重なり、最後の段の端が CLOSED に来る。
    stages = []
    for index in range(4):
        stage = cmds.createNode("transform", name="stage{}_OUT".format(index))
        cmds.connectAttr("{}.matrix[{}]".format(owner, index), stage + ".offsetParentMatrix")
        _cylinder("stage{}".format(index), stage, 0.3 * index, CLOSED - 0.1 * (3 - index), 0.9 - 0.2 * index,
                  greens[index])
        stages.append(stage)
    camera, camera_shape = cmds.camera(name="telescopeCamera", focalLength=35)
    # 正面から。左側のHUDと重ならないよう、シリンダーが画面の右寄りに来るように向ける。
    cmds.viewPlace(camera_shape, eye=(-4.0, 6.5, 40.0), lookAt=(-4.0, 6.5, 0.0))
    window = cmds.window("telescopeValidationWindow", title="TelescopicCylinder", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("telescopeValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 8
    names = ["telescopeHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"base": base, "tip": tip, "stages": stages, "owner": owner}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた式と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    distance, elevation, sequence, stage = pose(frame)
    aim = om.MVector(math.cos(math.radians(elevation)), math.sin(math.radians(elevation)), 0)
    target = om.MPoint(0, 0, 0) + aim * distance
    cmds.setAttr(scene["tip"] + ".translate", target.x, target.y, 0)
    owner = scene["owner"]
    cmds.setAttr(owner + ".sequence", sequence)
    actual = [cmds.getAttr("{}.stageExtension[{}]".format(owner, i)) for i in range(3)]
    extension = cmds.getAttr(owner + ".extension")
    over = cmds.getAttr(owner + ".overExtension")
    length = cmds.getAttr(owner + ".length")
    raw = distance - CLOSED
    total, expected = expected_stages(raw, sequence)
    position_error = 0.0
    rotation_error = 0.0
    travelled = 0.0
    turn = om.MQuaternion(om.MVector(1, 0, 0), aim)
    for index, node in enumerate(scene["stages"]):
        matrix = om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))
        point = om.MPoint(matrix[12], matrix[13], matrix[14])
        position_error = max(position_error, (point - (om.MPoint(0, 0, 0) + aim * travelled)).length())
        rotation = om.MTransformationMatrix(matrix).rotation(asQuaternion=True)
        angle = math.degrees((rotation * turn.inverse()).asAxisAngle()[1]) % 360.0
        rotation_error = max(rotation_error, min(angle, 360.0 - angle))
        if index < 3:
            travelled += expected[index]
    errors = {
        "stages": max(abs(a - e) for a, e in zip(actual, expected)), "extension": abs(extension - total),
        "overExtension": abs(over - (raw - total)), "length": abs(length - distance),
        "position": position_error, "rotation": rotation_error,
    }
    in_range = 0.0 <= raw <= sum(STROKES)
    status = "IN RANGE" if in_range else ("BEYOND TOTAL STROKE" if raw > 0 else "SHORTER THAN CLOSED")
    values[:] = [
        "RED mount  GREEN barrel + 3 stages (darker = outer)  YELLOW tip target",
        "STAGE: " + stage,
        "E = D - C,  total = clamp(E, 0, sum s),  o_k = clamp(total - sum_{j<k} s_j, 0, s_k),  "
        "g_k = total*s_k/sum s,  e_k = g_k + seq*(o_k - g_k)",
        "FIXED: closed length C = {:.1f} cm   strokes s = {:.1f} / {:.1f} / {:.1f} cm   sum s = {:.1f} cm".format(
            CLOSED, *STROKES, sum(STROKES)),
        "INPUT: D = {:6.2f} cm   elevation = {:5.1f} deg   sequence = {:4.2f}   ->  E = {:+6.2f} cm".format(
            distance, elevation, sequence, raw),
        "DG e1 = {:5.2f}  e2 = {:5.2f}  e3 = {:5.2f} cm   (formula {:5.2f} / {:5.2f} / {:5.2f})".format(
            *(actual + expected)),
        "DG extension = {:5.2f} cm   DG overExtension = {:+6.2f} cm   [{}]".format(extension, over, status),
        "CHECK max|e - formula| = {:.6f} cm   max stage position error = {:.6f} cm   rotation error = {:.5f} deg".format(
            errors["stages"], position_error, rotation_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = all(value < 1e-3 for value in errors.values())
    return {"frame": frame, "presentation_stage": stage,
            "input": {"distance": distance, "elevation": elevation, "sequence": sequence},
            "raw_extension": raw, "stage_extensions": actual, "expected": expected, "extension": extension,
            "over_extension": over, "in_range": in_range, "errors": errors, "ok": ok}


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
        folder = recordVideo("TelescopicCylinder: 多段シリンダーの順番・均等の伸びと行程の超過", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "telescopic_cylinder.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-telescopic-cylinder.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("telescopic-cylinder-%Y%m%d-%H%M%S")
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
