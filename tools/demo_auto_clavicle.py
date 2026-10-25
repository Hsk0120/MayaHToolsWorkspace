"""AutoClavicleの鎖骨への分配を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_auto_clavicle.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = 30.0
WEIGHT = 1.0 / 3.0
MAXIMUM = 35.0
CLAVICLE_LENGTH = 6.0
UPPERARM_LENGTH = 10.0
SEGMENT = 36
# (上腕のrotateX[Twist], rotateY[前後], rotateZ[上下], 段階名)。基準はTポーズ(+X)。
POSES = [
    (0, 0, 0, "1 REST (T-POSE)"),
    (0, 0, 0, "2 RAISE BELOW START: CLAVICLE STAYS"),
    (0, 0, 25, "3 RAISE PAST START: CLAVICLE SHARES"),
    (0, 0, 90, "4 RAISE FAR: CLAVICLE APPROACHES MAXIMUM"),
    (0, 0, 165, "5 HOLD BEYOND RANGE"),
    (0, 0, 165, "6 RETURN TO SAFE RANGE"),
    (0, 0, 15, "7 SWING FORWARD"),
    (0, -85, 15, "8 TWIST: NOT SHARED"),
    (80, -85, 15, "9 RETURN TO REST"),
    (0, 0, 0, "9 RETURN TO REST"),
    (0, 0, 0, "9 RETURN TO REST"),
]


def pose(frame):
    """フレームの入力(rx, ry, rz, 段階名)をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:3], POSES[index + 1][:3])]
    return values + [POSES[index][3]]


def _shader(name, color):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _bone(name, parent, group, length, radius, z):
    """+X方向へ長さlengthの棒と根元・先端の球をparent下に作る。zは手前へずらす量。"""
    from maya import cmds
    rod = cmds.polyCylinder(name=name + "_rod", axis=(1, 0, 0), height=length, radius=radius, subdivisionsX=16)[0]
    base = cmds.polySphere(name=name + "_base", radius=radius * 1.8)[0]
    tip = cmds.polySphere(name=name + "_tip", radius=radius * 1.8)[0]
    cmds.setAttr(rod + ".translate", length / 2, 0, z)
    cmds.setAttr(base + ".translate", 0, 0, z)
    cmds.setAttr(tip + ".translate", length, 0, z)
    for node in (rod, base, tip):
        cmds.parent(node, parent, relative=True)
        cmds.sets(node, edit=True, forceElement=group)


def _curve(name, points, color, width=2.5):
    """表示色付きのNURBS曲線を作る。"""
    from maya import cmds
    curve = cmds.curve(name=name, degree=1, point=points)
    shape = cmds.listRelatives(curve, shapes=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideColor", color)
    cmds.setAttr(shape + ".lineWidth", width)
    return curve


def _ray(angle, length):
    """原点から+X基準でangle度上へ向けた点。"""
    a = math.radians(angle)
    return (length * math.cos(a), length * math.sin(a), 0)


def buildScene():
    """検証シーンを作り、(panel, 入力jointの組, 出力jointの組, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import AutoClavicle
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    chest = cmds.createNode("transform", name="chest_GRP")
    clavicle = cmds.createNode("joint", name="input_clavicle_JNT", parent=chest)
    upperarm = cmds.createNode("joint", name="input_upperarm_JNT", parent=clavicle)
    cmds.setAttr(upperarm + ".tx", CLAVICLE_LENGTH)
    graph = AutoClavicle.create(clavicle, upperarm, name="clavicleAuto", axis="x",
                                start=START, weight=WEIGHT, maximum=MAXIMUM)
    owner = graph.container
    out_clavicle = cmds.createNode("joint", name="output_clavicle_JNT", parent=chest)
    out_upperarm = cmds.createNode("joint", name="output_upperarm_JNT", parent=out_clavicle)
    owner.getPlug("clavicleMatrix").connectTo(out_clavicle + ".offsetParentMatrix")
    owner.getPlug("matrix").connectTo(out_upperarm + ".offsetParentMatrix")
    red, green = _shader("inputRed", (0.9, 0.12, 0.1)), _shader("outputGreen", (0.1, 0.85, 0.2))
    _bone("inputClavicle", clavicle, red, CLAVICLE_LENGTH, 0.14, 0.6)
    _bone("inputUpperarm", upperarm, red, UPPERARM_LENGTH, 0.14, 0.6)
    _bone("outputClavicle", out_clavicle, green, CLAVICLE_LENGTH, 0.26, 0)
    _bone("outputUpperarm", out_upperarm, green, UPPERARM_LENGTH, 0.26, 0)
    # 黄=鎖骨の上限角、灰=基準の向き。
    _curve("clavicleMax_CRV", [(0, 0, 0), _ray(MAXIMUM, CLAVICLE_LENGTH * 1.25)], 17, width=3)
    _curve("restAxis_CRV", [(0, 0, 0), (CLAVICLE_LENGTH + UPPERARM_LENGTH * 1.1, 0, 0)], 2)
    text = cmds.annotate(chest, text="clavicle max 35", point=_ray(MAXIMUM + 6, CLAVICLE_LENGTH * 1.35))
    cmds.setAttr(cmds.listRelatives(text, parent=True)[0] + ".displayArrow", False)
    camera, camera_shape = cmds.camera(name="autoClavicleCamera", focalLength=35)
    # 正面(+Z)から肩全体を見る。上げた腕と後ろへ回した腕が両方映る位置に固定する。
    cmds.viewPlace(camera_shape, eye=(10, 6, 52), lookAt=(5, 4, 0))
    cmds.setAttr(camera_shape + ".horizontalFilmOffset", -0.25)
    cmds.setAttr(camera_shape + ".verticalFilmOffset", -0.05)
    window = cmds.window("autoClavicleValidationWindow", title="AutoClavicle - share arm swing with clavicle",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("autoClavicleValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=True,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 7
    names = ["autoClavicleHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, (clavicle, upperarm), (out_clavicle, out_upperarm), owner, values, names


def _quaternion(matrix):
    """行列の回転をQuaternionで返す。"""
    from maya.api import OpenMaya as om
    return om.MTransformationMatrix(om.MMatrix(matrix)).rotation(asQuaternion=True)


def evaluate_frame(frame, inputs, outputs, owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import AutoClavicle
    rx, ry, rz, stage = pose(frame)
    cmds.setAttr(inputs[1] + ".rotate", rx, ry, rz)
    direction = om.MVector(1, 0, 0).rotateBy(om.MEulerRotation(*[math.radians(v) for v in (rx, ry, rz)]))
    theta = math.degrees(om.MVector(1, 0, 0).angle(direction))
    expected_c = AutoClavicle.clavicleAngle(theta, START, WEIGHT, MAXIMUM)
    dg_theta = owner.getPlug("swingAngle").get()
    dg_c = owner.getPlug("clavicleAngle").get()
    dg_rest = owner.getPlug("upperarmAngle").get()
    # 出力の上腕のワールド回転と入力の差(度)。0なら向きが保たれている。
    source = _quaternion(cmds.getAttr(inputs[1] + ".worldMatrix[0]"))
    actual = _quaternion(cmds.getAttr(outputs[1] + ".worldMatrix[0]"))
    dot = abs(source.x * actual.x + source.y * actual.y + source.z * actual.z + source.w * actual.w)
    direction_error = math.degrees(2 * math.acos(min(1.0, dot)))
    # 出力の鎖骨が入力から回った角度。
    clavicle_delta = _quaternion(cmds.getAttr(outputs[0] + ".worldMatrix[0]")) * _quaternion(
        cmds.getAttr(inputs[0] + ".worldMatrix[0]")).inverse()
    clavicle_turn = math.degrees(2 * math.acos(min(1.0, abs(clavicle_delta.w))))
    shoulder_in = om.MPoint(cmds.xform(inputs[1], q=True, worldSpace=True, translation=True))
    shoulder_out = om.MPoint(cmds.xform(outputs[1], q=True, worldSpace=True, translation=True))
    if theta <= START + 1e-6:
        state = "theta <= start -> clavicle fixed"
    elif expected_c > MAXIMUM * 0.9:
        state = "near maximum -> c approaches 35, never exceeds"
    else:
        state = "sharing: c ~ weight*(theta - start)"
    values[:] = [
        "RED = input (FK)  GREEN = output (auto clavicle)  YELLOW = clavicle maximum  GREY = rest",
        "STAGE: " + stage,
        "fixed: start = 30 deg   weight = 1/3   maximum = 35 deg   (theta = upperarm bend from rest)",
        "c = max*(1-exp(-weight*max(theta-start,0)/max))   k = c/theta   clavicle += S^k   upperarm keeps S^(1-k)",
        "INPUT rotate = ({:+6.1f}, {:+6.1f}, {:+6.1f}) deg   theta = {:6.2f} deg".format(rx, ry, rz, dg_theta),
        "OUTPUT c = {:6.2f} deg   upperarm theta-c = {:6.2f} deg   shoulder moved {:5.2f} cm   {}".format(
            dg_c, dg_rest, (shoulder_out - shoulder_in).length(), state),
        "CHECK upperarm world rotation vs input = {:.4f} deg   clavicle turn = {:6.2f} deg".format(
            direction_error, clavicle_turn),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (abs(dg_theta - theta) < 0.02 and abs(dg_c - expected_c) < 0.02 and abs(dg_rest - (theta - expected_c)) < 0.03
          and direction_error < 0.01 and abs(clavicle_turn - expected_c) < 0.02 and dg_c < MAXIMUM)
    return {"frame": frame, "presentation_stage": stage, "input_rotate_degrees": [rx, ry, rz],
            "expected_theta": theta, "dg_swing_angle": dg_theta, "dg_clavicle_angle": dg_c,
            "expected_clavicle_angle": expected_c, "dg_upperarm_angle": dg_rest,
            "upperarm_direction_error_degrees": direction_error, "clavicle_turn_degrees": clavicle_turn,
            "shoulder_offset_cm": (shoulder_out - shoulder_in).length(), "ok": ok}


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
        panel, inputs, outputs, owner, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("AutoClavicle: 上腕のSwingを鎖骨へ分配", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, inputs, outputs, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "auto-clavicle.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-auto-clavicle.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("auto-clavicle-%Y%m%d-%H%M%S")
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
