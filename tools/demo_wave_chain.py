"""WaveChainの尻尾のうねり(位相をずらした正弦波の回転)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_wave_chain.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNT = 8
SEGMENT_LENGTH = 2.0
ROOT_WEIGHT = 0.2
PHASE_SPEED = 15.0
FRAMES = 336
# (フレーム, amplitude, wavelength, tipWeight, その区間の段階名)。区間の間は線形に補間する。
KEYS = [
    (0, 0.0, 5.0, 1.0, "1 REST: AMPLITUDE 0 (NO JUMP)"),
    (24, 0.0, 5.0, 1.0, "2 AMPLITUDE RAMPS UP"),
    (72, 25.0, 5.0, 1.0, "3 WAVE TRAVELS ROOT -> TIP"),
    (168, 25.0, 5.0, 1.0, "4 LONGER WAVELENGTH 5 -> 9 JOINTS"),
    (216, 25.0, 9.0, 1.0, "5 TIP WEIGHT 1 -> 0.3"),
    (264, 25.0, 9.0, 0.3, "6 AMPLITUDE BACK TO 0: RETURNS TO INPUT"),
    (312, 0.0, 9.0, 0.3, "7 REST"),
    (FRAMES, 0.0, 9.0, 0.3, "7 REST"),
]


def parameters(frame):
    """フレームの(phase, amplitude, wavelength, tipWeight, 段階名)を返す。"""
    for start, end in zip(KEYS, KEYS[1:]):
        if frame <= end[0]:
            weight = (frame - start[0]) / float(end[0] - start[0])
            values = [a + (b - a) * weight for a, b in zip(start[1:4], end[1:4])]
            return [PHASE_SPEED * frame] + values + [start[4]]
    return [PHASE_SPEED * frame] + list(KEYS[-1][1:4]) + [KEYS[-1][4]]


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
    from mlrig.setups import WaveChain
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    hip = cmds.createNode("transform", name="hip_GRP")
    joints, parent = [], hip
    for index in range(COUNT):
        joint = cmds.createNode("joint", name="input_tail{}_JNT".format(index), parent=parent)
        cmds.setAttr(joint + ".translateX", SEGMENT_LENGTH if index else 0)
        joints.append(joint)
        parent = joint
    graph = WaveChain.create(joints, name="tailWave", axis="z", amplitude=0.0, wavelength=5.0,
                             rootWeight=ROOT_WEIGHT, tipWeight=1.0)
    owner = graph.container
    outputs, parent = [], hip
    for index in range(COUNT):
        out = cmds.createNode("transform", name="output_tail{}_GRP".format(index), parent=parent)
        owner.getPlug("matrix" + str(index)).connectTo(out + ".offsetParentMatrix")
        outputs.append(out)
        parent = out
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.5)
    green = _shader("outputGreen", (0.1, 0.8, 0.2))
    # 赤(半透明)=入力の尻尾(まっすぐのまま)、緑=出力の尻尾(波を重ねたもの)。
    for index in range(COUNT):
        _segment("inputTail{}_GEO".format(index), joints[index], red, 0.12, z=-0.6)
        _segment("outputTail{}_GEO".format(index), outputs[index], green, 0.25)
    camera, camera_shape = cmds.camera(name="waveCamera", focalLength=35)
    # 正面(+Z)から、XY平面でうねる尻尾全体を見る位置に固定する。
    cmds.viewPlace(camera_shape, eye=(8, 1.0, 21), lookAt=(8, 0.3, 0))
    cmds.setAttr(camera_shape + ".verticalFilmOffset", -0.12)
    window = cmds.window("waveChainValidationWindow", title="WaveChain - travelling sine wave on a joint chain",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("waveChainValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["waveChainHUD{}".format(i) for i in range(len(values))]
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
    from mlrig.setups import WaveChain
    phase, amplitude, wavelength, tip_weight, stage = parameters(frame)
    for attr, value in (("phase", phase), ("amplitude", amplitude), ("wavelength", wavelength),
                        ("tipWeight", tip_weight)):
        owner.getPlug(attr).set(value)
    expected = WaveChain.waveAngles(COUNT, phase, amplitude, wavelength, ROOT_WEIGHT, tip_weight)
    dg = [owner.getPlug("angle" + str(i)).get() for i in range(COUNT)]
    # 出力の各区間のワールドでの向きを、入力のまっすぐな尻尾に角度の累積を重ねた期待値と比べる(度)。
    rotation_errors = []
    total = 0.0
    for index, out in enumerate(outputs):
        total += expected[index]
        matrix = om.MMatrix(cmds.getAttr(out + ".worldMatrix[0]"))
        heading = math.degrees(math.atan2(matrix[1], matrix[0]))
        rotation_errors.append(abs((heading - total + 180) % 360 - 180))
    angle_error = max(abs(a - b) for a, b in zip(dg, expected))
    tip = om.MVector(cmds.xform(outputs[-1], q=True, worldSpace=True, translation=True))
    values[:] = [
        "GREEN = output tail (wave)   RED (transparent) = input tail (straight)   8 joints, rotate about local Z",
        "STAGE: " + stage,
        "fixed: rootWeight = 0.2   phase = 15 deg/frame   w_i = rootWeight + (tipWeight-rootWeight)*i/7",
        "theta_i = amplitude * w_i * sin(phase - 360*i/wavelength)    output_i = Rz(theta_i) * input local matrix",
        "INPUT phase = {:7.1f} deg   amplitude = {:5.1f} deg   wavelength = {:4.2f} joints   tipWeight = {:4.2f}".format(
            phase, amplitude, wavelength, tip_weight),
        "OUTPUT theta0..7 = " + " ".join("{:+5.1f}".format(v) for v in dg) + "   tip y = {:+5.2f} cm".format(tip.y),
        "CHECK |DG theta - formula| max = {:.5f} deg   accumulated heading error max = {:.5f} deg".format(
            angle_error, max(rotation_errors)),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = angle_error < 0.01 and max(rotation_errors) < 0.01
    return {"frame": frame, "presentation_stage": stage, "phase": phase, "amplitude": amplitude,
            "wavelength": wavelength, "tip_weight": tip_weight, "dg_angles": dg, "expected_angles": expected,
            "heading_errors_degrees": rotation_errors, "ok": ok}


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
        folder = recordVideo("WaveChain: 尻尾のうねり(位相をずらした正弦波)", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, joints, outputs, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "wave-chain.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-wave-chain.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("wave-chain-%Y%m%d-%H%M%S")
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
