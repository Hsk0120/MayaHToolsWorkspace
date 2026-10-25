"""FootRollの逆足(かかと・母指球・つま先・内外の縁の支点)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_foot_roll.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BREAK_ANGLE = 30.0
SEGMENT = 30
PIVOTS = {"toe": (0, 0, 7), "heel": (0, 0, -1.5), "inner": (1.5, 0, 3), "outer": (-1.5, 0, 3)}
ANKLE = (0, 4, 0)
BALL = (0, 0.8, 4)
# (roll, bank, swivel, toeTap[度], 次の姿勢へ向かう段階名)。
POSES = [
    (0, 0, 0, 0, "1 REST"),
    (0, 0, 0, 0, "2 ROLL < 0: HEEL PIVOT"),
    (-25, 0, 0, 0, "3 HOLD ON HEEL"),
    (-25, 0, 0, 0, "4 BACK TO REST"),
    (0, 0, 0, 0, "5 0 < ROLL <= BREAK: BALL PIVOT"),
    (30, 0, 0, 0, "6 ROLL > BREAK: TOE PIVOT"),
    (65, 0, 0, 0, "7 HOLD ON TOE TIP"),
    (65, 0, 0, 0, "8 BACK TO REST"),
    (0, 0, 0, 0, "9 BANK > 0: OUTER EDGE"),
    (0, 25, 0, 0, "10 BANK < 0: INNER EDGE"),
    (0, -25, 0, 0, "11 BACK TO REST"),
    (0, 0, 0, 0, "12 SWIVEL AROUND BALL"),
    (0, 0, 35, 0, "13 BACK TO REST"),
    (0, 0, 0, 0, "14 TOE TAP (ANKLE STAYS)"),
    (0, 0, 0, -30, "15 RETURN TO REST"),
    (0, 0, 0, 0, "15 RETURN TO REST"),
    (0, 0, 0, 0, "15 RETURN TO REST"),
]


def pose(frame):
    """フレームのroll・bank・swivel・toeTapと段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:4], POSES[index + 1][:4])]
    return values + [POSES[index][4]]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _box(name, parent, group, center, size):
    """parentのローカルのcenterに大きさsizeの箱を作る。"""
    from maya import cmds
    box = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    cmds.setAttr(box + ".translate", *center)
    cmds.parent(box, parent, relative=True)
    cmds.sets(box, edit=True, forceElement=group)
    return box


def _footGeometry(prefix, ankle, ball, group):
    """足首の空間に足の甲、母指球の空間につま先の箱を作る(どちらも生成時の位置に合わせる)。"""
    _box(prefix + "Foot_GEO", ankle, group, (0, -2.4, 1.5), (2.6, 3.2, 6.0))
    _box(prefix + "Toe_GEO", ball, group, (0, -0.4, 1.5), (2.4, 0.8, 3.0))
    _box(prefix + "Shin_GEO", ankle, group, (0, 1.0, 0), (1.4, 4.4, 1.4))


def buildScene():
    """検証シーンを作り、(panel, container, 状態, HUD値, HUD名)を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import FootRoll
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    control = cmds.createNode("transform", name="foot_CTRL")
    pivots = {}
    for role, position in PIVOTS.items():
        node = cmds.createNode("transform", name=role + "_PIV", parent=control)
        cmds.setAttr(node + ".translate", *position)
        pivots[role] = node
    ankle = cmds.createNode("joint", name="input_ankle_JNT")
    cmds.setAttr(ankle + ".translate", *ANKLE)
    ball = cmds.createNode("joint", name="input_ball_JNT", parent=ankle)
    cmds.xform(ball, worldSpace=True, translation=BALL)
    graph = FootRoll.create(control, ankle, ball, pivots["toe"], pivots["heel"], pivots["inner"], pivots["outer"],
                            name="footRoll", rollAxis="x", bankAxis="z", breakAngle=BREAK_ANGLE)
    owner = graph.container
    out_ankle = cmds.createNode("transform", name="output_ankle_GRP")
    out_ball = cmds.createNode("transform", name="output_ball_GRP")
    owner.getPlug("ankleMatrix").connectTo(out_ankle + ".offsetParentMatrix")
    owner.getPlug("ballMatrix").connectTo(out_ball + ".offsetParentMatrix")
    grey = _shader("groundGrey", (0.42, 0.42, 0.45))
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.7)
    green = _shader("outputGreen", (0.1, 0.8, 0.2))
    toe_green = _shader("outputToeGreen", (0.55, 0.95, 0.6))
    yellow = _shader("pivotYellow", (1.0, 0.85, 0.1))
    ground = cmds.polyPlane(name="ground_GEO", width=24, height=24, subdivisionsX=1, subdivisionsY=1)[0]
    cmds.setAttr(ground + ".translate", 0, -0.02, 2)
    cmds.sets(ground, edit=True, forceElement=grey)
    # 赤(半透明)=生成時の足、緑=出力の足首(濃い緑)と母指球から先(薄い緑)、黄=支点。
    _footGeometry("input", ankle, ball, red)
    _box("outputFoot_GEO", out_ankle, green, (0, -2.4, 1.5), (2.6, 3.2, 6.0))
    _box("outputShin_GEO", out_ankle, green, (0, 1.0, 0), (1.4, 4.4, 1.4))
    _box("outputToe_GEO", out_ball, toe_green, (0, -0.4, 1.5), (2.4, 0.8, 3.0))
    for role, node in list(pivots.items()) + [("ball", ball)]:
        marker = cmds.polySphere(name=role + "Pivot_GEO", radius=0.3)[0]
        cmds.xform(marker, worldSpace=True, translation=cmds.xform(node, q=True, worldSpace=True, translation=True))
        cmds.sets(marker, edit=True, forceElement=yellow)
    camera, camera_shape = cmds.camera(name="footCamera", focalLength=35)
    # 外側(-X)の斜め前から。rollとbankの両方が見える位置に固定する。
    cmds.viewPlace(camera_shape, eye=(-30, 13, 21), lookAt=(0, 4, 2.5))
    cmds.setAttr(camera_shape + ".verticalFilmOffset", -0.12)
    window = cmds.window("footRollValidationWindow", title="FootRoll - reverse foot pivots",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("footRollValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    state = {
        "ankleRest": om.MMatrix(cmds.getAttr(ankle + ".worldMatrix[0]")),
        "ballRest": om.MMatrix(cmds.getAttr(ball + ".worldMatrix[0]")),
        "points": {role: om.MPoint(*cmds.xform(node, q=True, worldSpace=True, translation=True))
                   for role, node in list(pivots.items()) + [("ball", ball)]},
    }
    values = [""] * 7
    names = ["footRollHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, owner, state, values, names


def evaluate_frame(frame, owner, state, values, names):
    """roll・bankを更新し、角度と接地している支点の位置を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import FootRoll
    roll, bank, swivel, tap, stage = pose(frame)
    for attr, value in (("roll", roll), ("bank", bank), ("swivel", swivel), ("toeTap", tap)):
        owner.getPlug(attr).set(value)
    expected = FootRoll.angles(roll, bank, BREAK_ANGLE)
    dg = {role: owner.getPlug(role + "Angle").get() for role in expected}
    angle_error = max(abs(dg[role] - expected[role]) for role in expected)
    ankle_delta = state["ankleRest"].inverse() * om.MMatrix(owner.getPlug("ankleMatrix").get())
    ball_delta = state["ballRest"].inverse() * om.MMatrix(owner.getPlug("ballMatrix").get())
    # 接地している支点(このデモでは値を1つずつ動かす)。swivelは母指球、toeTapは足首が動かず母指球の位置が残る。
    if abs(swivel) > 1e-6:
        contact, delta = "ball", ankle_delta
    elif abs(tap) > 1e-6:
        contact, delta = "ball", ball_delta
    elif bank > 1e-6:
        contact, delta = "outer", ankle_delta
    elif bank < -1e-6:
        contact, delta = "inner", ankle_delta
    elif roll < -1e-6:
        contact, delta = "heel", ankle_delta
    elif roll > BREAK_ANGLE + 1e-6:
        contact, delta = "toe", ball_delta
    elif roll > 1e-6:
        contact, delta = "ball", ankle_delta
    else:
        contact, delta = "rest", ankle_delta
    if contact == "rest" or abs(tap) > 1e-6:
        # 基準の姿勢、またはtoeTapだけのときは足首の出力が生成時と一致する。
        pivot_error = max(abs(a - b) for a, b in zip(ankle_delta, om.MMatrix()))
        if contact != "rest":
            point = state["points"]["ball"]
            pivot_error = max(pivot_error, (point * ball_delta - point).length())
    else:
        point = state["points"][contact]
        pivot_error = (point * delta - point).length()
    values[:] = [
        "DARK GREEN = output ankle   LIGHT GREEN = output toe (ball)   RED (transparent) = rest foot   YELLOW = pivots",
        "STAGE: " + stage,
        "fixed: breakAngle = 30 deg   roll axis = control X   bank axis = control Z   heel(0,0,-1.5) ball(0,0.8,4) "
        "toe(0,0,7) inner(1.5,0,3) outer(-1.5,0,3) cm",
        "heel = min(roll,0)   ball = clamp(roll,0,break)   toe = max(roll-break,0)   outer = max(bank,0)   "
        "inner = min(bank,0)   swivel, toeTap: around ball",
        "INPUT roll = {:+6.1f}   bank = {:+6.1f}   swivel = {:+6.1f}   toeTap = {:+6.1f} deg".format(
            roll, bank, swivel, tap),
        "OUTPUT heel = {:+6.1f}  ball = {:+6.1f}  toe = {:+6.1f}  outer = {:+6.1f}  inner = {:+6.1f} deg".format(
            dg["heel"], dg["ball"], dg["toe"], dg["outer"], dg["inner"]),
        "CHECK angle error = {:.5f} deg   contact pivot = {}   pivot drift = {:.5f} cm".format(
            angle_error, contact, pivot_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = angle_error < 1e-4 and pivot_error < 1e-3
    return {"frame": frame, "presentation_stage": stage, "input_roll_degrees": roll, "input_bank_degrees": bank,
            "input_swivel_degrees": swivel, "input_toe_tap_degrees": tap,
            "dg_angles": dg, "expected_angles": expected, "contact_pivot": contact,
            "pivot_drift_cm": pivot_error, "angle_error_degrees": angle_error, "ok": ok}


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
        panel, owner, state, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("FootRoll: かかと・母指球・つま先・内外の縁を支点にした逆足", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, owner, state, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "foot_roll.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-foot-roll.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("foot-roll-%Y%m%d-%H%M%S")
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
