"""RollUpChainの端からの巻き取り(関節ごとに曲がり始める時期をずらした回転)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_roll_up_chain.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNT = 10
SEGMENT_LENGTH = 1.5
ANGLE = 55.0
FRAMES = 396
# (フレーム, roll, decay, width, その区間の段階名)。区間の間は線形に補間する。
KEYS = [
    (0, 0.0, 0.88, 1.0, "1 REST: ROLL 0 (NO JUMP)"),
    (24, 0.0, 0.88, 1.0, "2 ROLL UP FROM THE TIP, ONE JOINT AT A TIME"),
    (144, 10.0, 0.88, 1.0, "3 PAST THE LIMIT 10: STOPS, EXCESS GROWS"),
    (180, 12.5, 0.88, 1.0, "4 BACK INSIDE THE RANGE"),
    (216, 7.0, 0.88, 1.0, "5 DECAY 0.88 -> 1 (EQUAL ANGLES, TIGHT CIRCLE)"),
    (252, 7.0, 1.0, 1.0, "6 DECAY BACK TO 0.88, WIDTH 1 -> 4 (SMOOTH)"),
    (300, 7.0, 0.88, 4.0, "7 BELOW ZERO: STOPS, NEGATIVE EXCESS"),
    (348, -2.0, 0.88, 4.0, "8 BACK TO ZERO: MATCHES INPUT"),
    (372, 0.0, 0.88, 4.0, "9 REST"),
    (FRAMES, 0.0, 0.88, 4.0, "9 REST"),
]


def parameters(frame):
    """フレームの(roll, decay, width, 段階名)を返す。"""
    for start, end in zip(KEYS, KEYS[1:]):
        if frame <= end[0]:
            weight = (frame - start[0]) / float(end[0] - start[0])
            return [a + (b - a) * weight for a, b in zip(start[1:4], end[1:4])] + [start[4]]
    return list(KEYS[-1][1:4]) + [KEYS[-1][4]]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _segment(name, parent, group, radius, z=0.0):
    """parentのローカル+X方向へ1区間ぶんの円柱と根元の球を作る。"""
    from maya import cmds
    rod = cmds.polyCylinder(name=name, axis=(1, 0, 0), height=SEGMENT_LENGTH, radius=radius, subdivisionsX=16)[0]
    ball = cmds.polySphere(name=name + "_ball", radius=radius * 1.6)[0]
    cmds.setAttr(rod + ".translate", SEGMENT_LENGTH / 2, 0, z)
    cmds.setAttr(ball + ".translate", 0, 0, z)
    for node in (rod, ball):
        cmds.parent(node, parent, relative=True)
        cmds.sets(node, edit=True, forceElement=group)


def buildScene():
    """検証シーンを作り、(panel, 入力のjoint列, 出力のtransform列, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import RollUpChain
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    hip = cmds.createNode("transform", name="hip_GRP")
    joints, parent = [], hip
    for index in range(COUNT):
        joint = cmds.createNode("joint", name="input_tail{}_JNT".format(index), parent=parent)
        cmds.setAttr(joint + ".translateX", SEGMENT_LENGTH if index else 0)
        joints.append(joint)
        parent = joint
    graph = RollUpChain.create(joints, name="tailRoll", axis="z", angle=ANGLE, decay=0.88, width=1.0)
    owner = graph.container
    outputs, parent = [], hip
    for index in range(COUNT):
        out = cmds.createNode("transform", name="output_tail{}_GRP".format(index), parent=parent)
        owner.getPlug("matrix" + str(index)).connectTo(out + ".offsetParentMatrix")
        outputs.append(out)
        parent = out
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.5)
    green = _shader("outputGreen", (0.1, 0.8, 0.2))
    # 赤(半透明)=入力の尻尾(まっすぐのまま)、緑=出力の尻尾(巻き取ったもの)。
    for index in range(COUNT):
        _segment("inputTail{}_GEO".format(index), joints[index], red, 0.1, z=-0.6)
        _segment("outputTail{}_GEO".format(index), outputs[index], green, 0.2)
    camera, camera_shape = cmds.camera(name="rollCamera", focalLength=35)
    # 正面(+Z)から、XY平面で巻き上がる尻尾全体を見る位置に固定する。
    cmds.viewPlace(camera_shape, eye=(7.5, 3.2, 28), lookAt=(7.5, 3.2, 0))
    cmds.setAttr(camera_shape + ".verticalFilmOffset", -0.12)
    window = cmds.window("rollUpChainValidationWindow", title="RollUpChain - roll a joint chain up from the tip",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("rollUpChainValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["rollUpChainHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, joints, outputs, owner, values, names


def evaluate_frame(frame, joints, outputs, owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import RollUpChain
    roll, decay, width, stage = parameters(frame)
    for attr, value in (("roll", roll), ("decay", decay), ("width", width)):
        owner.getPlug(attr).set(value)
    expected, rolled, excess = RollUpChain.rollAngles(COUNT, roll, ANGLE, decay, width)
    dg = [owner.getPlug("angle" + str(i)).get() for i in range(COUNT)]
    dg_rolled, dg_excess, dg_total = (owner.getPlug(attr).get() for attr in ("rolled", "excess", "totalAngle"))
    # 出力の各区間のワールドでの向きを、入力のまっすぐな尻尾に角度の累積を重ねた期待値と比べる(度)。
    rotation_errors = []
    total = 0.0
    for index, out in enumerate(outputs):
        total += expected[index]
        matrix = om.MMatrix(cmds.getAttr(out + ".worldMatrix[0]"))
        heading = math.degrees(math.atan2(matrix[1], matrix[0]))
        rotation_errors.append(abs((heading - total + 180) % 360 - 180))
    # 赤の入力は動かしていないので、出力とのずれ(各関節の位置の差の最大)が0なら入力と一致している。
    offset = max((om.MVector(cmds.xform(o, q=True, worldSpace=True, translation=True))
                  - om.MVector(cmds.xform(j, q=True, worldSpace=True, translation=True))).length()
                 for o, j in zip(outputs, joints))
    angle_error = max(abs(a - b) for a, b in zip(dg, expected))
    value_error = max(abs(dg_rolled - rolled), abs(dg_excess - excess), abs(dg_total - sum(expected)))
    values[:] = [
        "GREEN = output tail (rolled)   RED (transparent) = input tail (straight)   10 joints, rotate about local Z",
        "STAGE: " + stage,
        "fixed: N = 10   angle = 55 deg   order j = 9 - i (tip first)   limit = N - 1 + width",
        "rolled = clamp(roll, 0, limit)   excess = roll - rolled   w_i = clamp((rolled - j)/width, 0, 1)",
        "theta_i = angle * decay^j * w_i (deg)   output_i = Rz(theta_i) * input local matrix",
        "INPUT roll = {:+6.2f} joints   decay = {:4.2f}   width = {:4.2f} joints   limit = {:5.2f}".format(
            roll, decay, width, COUNT - 1 + width),
        "OUTPUT rolled = {:5.2f}  excess = {:+5.2f}  total = {:6.1f} deg  theta0..9 = ".format(
            dg_rolled, dg_excess, dg_total) + " ".join("{:2.0f}".format(v) for v in dg),
        "CHECK |DG - formula| theta {:.5f} deg  rolled/excess/total {:.5f}  heading {:.5f} deg  |out - in| {:5.2f} cm"
        .format(angle_error, value_error, max(rotation_errors), offset),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = angle_error < 0.01 and value_error < 0.01 and max(rotation_errors) < 0.01
    if roll <= 0.0:
        # roll が0以下(生成時・0より下で止まっている間・最後)では、出力が入力と重なる。
        ok = ok and offset < 1e-4
    return {"frame": frame, "presentation_stage": stage, "roll": roll, "decay": decay, "width": width,
            "rolled": dg_rolled, "excess": dg_excess, "total_angle": dg_total, "dg_angles": dg,
            "expected_angles": expected, "expected_rolled": rolled, "expected_excess": excess,
            "heading_errors_degrees": rotation_errors, "offset_from_input": offset, "ok": ok}


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
        panel, joints, outputs, owner, values, names = buildScene()
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("RollUpChain: 端からの巻き取り", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, joints, outputs, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "roll-up-chain.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-roll-up-chain.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("roll-up-chain-%Y%m%d-%H%M%S")
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
