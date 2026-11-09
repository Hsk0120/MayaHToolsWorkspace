"""RibBreathingの吸う・吐く・範囲の超過・胸椎の曲げを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_rib_breathing.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUMP = 18.0
BUCKET = 18.0
LIMITS = (-0.5, 1.5)
SOFTNESS = 0.1
UP = (0.0, 1.0, 0.0)
LEVELS = 5
SEGMENT = 44
# (breath, 胸椎の曲げ[度], 次の姿勢へ向かう段階名)
POSES = [
    (0.0, 0.0, "1 REST -> INHALE TO 1.0 (IN RANGE)"),
    (1.0, 0.0, "2 DEEP BREATH PAST THE LIMIT: INPUT 2.6"),
    (2.6, 0.0, "3 HOLD PAST MAX"),
    (2.6, 0.0, "4 EXHALE PAST THE LIMIT: INPUT -1.4"),
    (-1.4, 0.0, "5 HOLD PAST MIN"),
    (-1.4, 0.0, "6 BACK TO 0 (SAFE RANGE)"),
    (0.0, 0.0, "7 SPINE BENDS 30 DEG"),
    (0.0, 30.0, "8 INHALE WHILE BENT"),
    (1.0, 30.0, "9 BACK TO REST"),
    (0.0, 0.0, "10 BACK AT REST"),
    (0.0, 0.0, "10 BACK AT REST"),
]


def pose(frame):
    """フレームの呼吸・胸椎の曲げ・段階名をsmoothstepで補間して返す。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    start, end = POSES[index], POSES[index + 1]
    return tuple(start[i] + (end[i] - start[i]) * weight for i in range(2)) + (start[2],)


def softLimit(value):
    """呼吸の柔らかい制限を、DGとは別に式どおり計算する。"""
    minimum, maximum = LIMITS
    width = max(SOFTNESS * (maximum - minimum) * 0.5, 1e-3)
    upper, lower = maximum - width, minimum + width
    if value > upper:
        return upper + width * (1 - math.exp(-(value - upper) / width))
    if value < lower:
        return lower - width * (1 - math.exp(-(lower - value) / width))
    return value


def ribPoints():
    """左右の肋骨の(根元, 中央, 胸骨側の端)をspineの空間で返す。"""
    ribs = []
    for level in range(LEVELS):
        height = 6.0 - 3.0 * level
        for side in (1, -1):
            ribs.append(((side * 1.0, height, 0.0),
                         (side * (7.5 + 0.4 * level), height - 1.2, 4.2),
                         (side * (1.3 + 0.3 * level), height - 3.4 - 0.2 * level, 8.5 - 0.4 * level)))
    return ribs


def _arc(head, middle, tip):
    """3点を通る2次ベジェ曲線の折れ線の点を返す(スクリーン上の肋骨の形)。"""
    from maya.api import OpenMaya as om
    first, second, third = om.MVector(head), om.MVector(middle), om.MVector(tip)
    control = second * 2 - (first + third) * 0.5
    points = []
    for step in range(9):
        t = step / 8.0
        points.append(first * (1 - t) * (1 - t) + control * 2 * t * (1 - t) + third * t * t)
    return points


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _bone(name, parent, start, end, radius, shader):
    """parentの下へ start から end への円柱を作る。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    first, last = om.MVector(start), om.MVector(end)
    direction = last - first
    bone = cmds.polyCylinder(name=name + "_GEO", radius=radius, height=direction.length(),
                             axis=(direction.x, direction.y, direction.z), subdivisionsAxis=10)[0]
    cmds.parent(bone, parent, relative=True)
    middle = (first + last) * 0.5
    cmds.setAttr(bone + ".translate", middle.x, middle.y, middle.z)
    cmds.sets(bone, edit=True, forceElement=shader)
    return bone


def _polyline(prefix, parent, points, radius, shader):
    """折れ線の各区間に円柱を作る。"""
    for index in range(len(points) - 1):
        _bone("{}_{}".format(prefix, index), parent, tuple(points[index]), tuple(points[index + 1]), radius, shader)


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import RibBreathing
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    gray = _shader("spineGray", (0.55, 0.55, 0.55))
    green = _shader("ribGreen", (0.15, 0.85, 0.25))
    red = _shader("restRed", (0.9, 0.15, 0.1), 0.6)
    yellow = _shader("sternumYellow", (0.95, 0.8, 0.1))
    bend = cmds.createNode("transform", name="bend_GRP")
    cmds.setAttr(bend + ".translateY", -8.0)
    spine = cmds.createNode("transform", name="spine_JNT", parent=bend)
    cmds.setAttr(spine + ".translateY", 8.0)
    _bone("spine", spine, (0, 7.5, -0.4), (0, -9.5, -0.4), 0.7, gray)
    points = ribPoints()
    ribs = []
    for index, (head, middle, tip) in enumerate(points):
        names = []
        for label, position in (("H", head), ("M", middle), ("T", tip)):
            node = cmds.createNode("transform", name="rib{}{}_JNT".format(index, label), parent=spine)
            cmds.setAttr(node + ".translate", *position)
            names.append(node)
        ribs.append(names)
    sternum_position = (0.0, 0.5, 9.0)
    sternum_node = cmds.createNode("transform", name="sternum_JNT", parent=spine)
    cmds.setAttr(sternum_node + ".translate", *sternum_position)
    # 最下段の2本は浮遊肋として胸骨へ付けない。
    owner = str(RibBreathing.create(spine, ribs, name="ribBreathing", sternum=sternum_node,
                                    sternalRibs=list(range(2 * (LEVELS - 1))), pumpAngle=PUMP, bucketAngle=BUCKET,
                                    minBreath=LIMITS[0], maxBreath=LIMITS[1], softness=SOFTNESS).container)
    for index, (head, middle, tip) in enumerate(points):
        arc = _arc(head, middle, tip)
        relative = [point - om.MVector(head) for point in arc]
        out = cmds.createNode("transform", name="rib{}_OUT".format(index))
        cmds.connectAttr("{}.ribMatrix[{}]".format(owner, index), out + ".offsetParentMatrix")
        _polyline("rib{}".format(index), out, relative, 0.26, green)
        _polyline("rest{}".format(index), spine, arc, 0.13, red)
    sternum_out = cmds.createNode("transform", name="sternum_OUT")
    cmds.connectAttr(owner + ".sternumMatrix", sternum_out + ".offsetParentMatrix")
    bar = ((0, 5.5, 0), (0, -6.5, 0))
    _bone("sternum", sternum_out, bar[0], bar[1], 0.75, yellow)
    _bone("sternumRest", spine, (sternum_position[0], sternum_position[1] + 5.5, sternum_position[2]),
          (sternum_position[0], sternum_position[1] - 6.5, sternum_position[2]), 0.3, red)
    camera, camera_shape = cmds.camera(name="ribCamera", focalLength=35)
    # 斜め前から見て、上段の前への動きと下段の中央の持ち上がりの両方を見せる。
    cmds.viewPlace(camera_shape, eye=(36.0, 7.0, 34.0), lookAt=(1.0, -2.5, 3.0))
    window = cmds.window("ribValidationWindow", title="RibBreathing", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("ribValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["ribHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"owner": owner, "bend": bend, "spine": spine, "ribs": points, "sternum": sternum_position}
    return panel, scene, values, names


def expectedRib(rib, level, effective):
    """1本の肋骨の(中央, 端)をspineの空間で独立に計算する。levelは最上段0・最下段1。"""
    from maya.api import OpenMaya as om
    up = om.MVector(UP)
    head, middle, tip = [om.MVector(item) for item in rib]
    chord = tip - head
    bucket_axis = chord.normal()
    offset = middle - head
    offset = offset - bucket_axis * (offset * bucket_axis)
    sign = 1.0 if ((bucket_axis ^ offset) * up) > 0 else -1.0
    pump_axis = (chord ^ up).normal()
    bucket_rotation = om.MQuaternion(math.radians(effective * BUCKET * (0.5 + 0.5 * level) * sign), bucket_axis)
    pump_rotation = om.MQuaternion(math.radians(effective * PUMP * (1 - 0.5 * level)), pump_axis)
    result = []
    for point in (middle, tip):
        result.append(head + (point - head).rotateBy(bucket_rotation).rotateBy(pump_rotation))
    return result


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた式と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    breath, bend, stage = pose(frame)
    owner = scene["owner"]
    cmds.setAttr(owner + ".breath", breath)
    cmds.setAttr(scene["bend"] + ".rotateX", bend)
    effective = cmds.getAttr(owner + ".effectiveBreath")
    excess = cmds.getAttr(owner + ".excessBreath")
    expansion = cmds.getAttr(owner + ".expansion")
    lift = cmds.getAttr(owner + ".sternumLift")
    expected = softLimit(breath)
    world = om.MMatrix(cmds.getAttr(scene["spine"] + ".worldMatrix[0]"))
    total, shift = 0.0, om.MVector()
    worst_mid, worst_tip = 0.0, 0.0
    sternal = 2 * (LEVELS - 1)
    for index, rib in enumerate(scene["ribs"]):
        level = (index // 2) / float(LEVELS - 1)
        mid_local, tip_local = expectedRib(rib, level, expected)
        total += (mid_local - om.MVector(rib[1])).length()
        if index < sternal:
            shift += (tip_local - om.MVector(rib[2])) * (1.0 / sternal)
        for attribute, point in (("midMatrix", mid_local), ("tipMatrix", tip_local)):
            actual = om.MMatrix(cmds.getAttr("{}.{}[{}]".format(owner, attribute, index)))
            error = (om.MPoint(actual[12], actual[13], actual[14]) - om.MPoint(point) * world).length()
            if attribute == "midMatrix":
                worst_mid = max(worst_mid, error)
            else:
                worst_tip = max(worst_tip, error)
    sternum_matrix = om.MMatrix(cmds.getAttr(owner + ".sternumMatrix"))
    sternum_point = om.MPoint(om.MVector(scene["sternum"]) + shift) * world
    errors = {
        "effective": abs(effective - expected), "excess": abs(excess - (breath - expected)),
        "mid": worst_mid, "tip": worst_tip, "expansion": abs(expansion - total / len(scene["ribs"])),
        "sternum": (om.MPoint(sternum_matrix[12], sternum_matrix[13], sternum_matrix[14]) - sternum_point).length(),
        "lift": abs(lift - shift * om.MVector(UP)),
    }
    status = "IN RANGE" if abs(excess) < 0.005 else ("PAST MAX BREATH" if excess > 0 else "PAST MIN BREATH")
    values[:] = [
        "GREEN ribs  YELLOW sternum  RED thin = rest pose (breath 0)  GRAY spine",
        "STAGE: " + stage,
        "rp = effectiveBreath * pumpAngle * pumpWeight   rb = effectiveBreath * bucketAngle * bucketWeight (deg)",
        "FIXED: pumpAngle = {:.0f}  bucketAngle = {:.0f} deg   range {:+.1f} .. {:+.1f}   softness {:.1f}   top rib pump/bucket 1/0.5  bottom 0.5/1".format(
            PUMP, BUCKET, LIMITS[0], LIMITS[1], SOFTNESS),
        "INPUT breath = {:+6.3f}   spine bend = {:5.1f} deg".format(breath, bend),
        "DG effectiveBreath = {:+6.3f}   DG excessBreath = {:+6.3f}   [{}]".format(effective, excess, status),
        "DG expansion = {:6.3f} cm   DG sternumLift = {:+6.3f} cm".format(expansion, lift),
        "CHECK |effective - formula| = {:.5f}   |rib tip - rotations| = {:.6f} cm   |sternum - mean| = {:.6f} cm".format(
            errors["effective"], errors["tip"], errors["sternum"]),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = all(value < 1e-3 for value in errors.values())
    return {"frame": frame, "presentation_stage": stage, "input": {"breath": breath, "bend": bend},
            "effective": effective, "excess": excess, "expansion": expansion, "sternum_lift": lift,
            "errors": errors, "ok": ok}


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
        folder = recordVideo("RibBreathing: 肋骨の呼吸と範囲の超過", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "rib_breathing.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-rib-breathing.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("rib-breathing-%Y%m%d-%H%M%S")
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
