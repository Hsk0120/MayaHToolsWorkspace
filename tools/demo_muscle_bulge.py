"""MuscleBulgeの曲げ角・膨らみの割合・補助骨の膨らみと押し出しを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_muscle_bulge.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPPER_LENGTH = 8.0
FORE_LENGTH = 7.0
START = 60.0
FULL = 140.0
BULGE = 0.6
PUSH = 0.8
POSITION = 0.5
SEGMENT = 30
# (肘のrotate X・Y・Z[度], 次の姿勢へ向かう段階名)。基準は0・0・0。
POSES = [
    ((0, 0, 0), "1 REST"),
    ((0, 0, 0), "2 BEND BELOW startAngle: NO BULGE"),
    ((0, 0, 50), "3 PAST startAngle 60: BULGE GROWS QUICKLY"),
    ((0, 0, 110), "4 REACH fullAngle 140: MAXIMUM"),
    ((0, 0, 150), "5 BEYOND fullAngle: STAYS AT MAXIMUM"),
    ((0, 0, 170), "6 RETURN TO REST"),
    ((0, 0, 0), "7 TWIST ONLY (rotateX): NO BULGE"),
    ((120, 0, 0), "8 TWIST BACK"),
    ((0, 0, 0), "9 DIAGONAL BEND (rotateY and rotateZ)"),
    ((0, -85, 85), "10 RETURN TO REST"),
    ((0, 0, 0), "10 RETURN TO REST"),
    ((0, 0, 0), "10 RETURN TO REST"),
]


def pose(frame):
    """フレームの肘の回転と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    rotate = [a + (b - a) * weight for a, b in zip(POSES[index][0], POSES[index + 1][0])]
    return rotate, POSES[index][1]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _bone(name, parent, group, length, radius):
    """parentのローカル+X方向へ長さlengthの円柱を作る。"""
    from maya import cmds
    rod = cmds.polyCylinder(name=name, axis=(1, 0, 0), height=length, radius=radius, subdivisionsX=24)[0]
    cmds.setAttr(rod + ".translate", length / 2, 0, 0)
    cmds.parent(rod, parent, relative=True)
    cmds.sets(rod, edit=True, forceElement=group)
    return rod


def _muscle(name, parent, group):
    """補助骨の膨らみを示す、上腕の上側(+Y)に沿った楕円体を作る。"""
    from maya import cmds
    sphere = cmds.polySphere(name=name, radius=1.0, subdivisionsAxis=24, subdivisionsHeight=16)[0]
    cmds.setAttr(sphere + ".translate", 0, 0.55, 0)
    cmds.setAttr(sphere + ".scale", 2.6, 0.75, 0.85)
    cmds.parent(sphere, parent, relative=True)
    cmds.sets(sphere, edit=True, forceElement=group)
    return sphere


def buildScene():
    """検証シーンを作り、(panel, 上腕, 肘, 補助骨, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import MuscleBulge
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    world = cmds.createNode("transform", name="arm_GRP")
    upper = cmds.createNode("joint", name="upperArm_JNT", parent=world)
    elbow = cmds.createNode("joint", name="elbow_JNT", parent=upper)
    cmds.setAttr(elbow + ".translateX", UPPER_LENGTH)
    graph = MuscleBulge.create(upper, elbow, name="bicepsBulge", axis="x", pushAxis="y", position=POSITION,
                               startAngle=START, fullAngle=FULL, bulge=BULGE, push=PUSH)
    owner = graph.container
    helper = cmds.createNode("transform", name="helper_GRP", parent=upper)
    owner.getPlug("matrix").connectTo(helper + ".offsetParentMatrix")
    ghost = cmds.createNode("transform", name="restHelper_GRP", parent=upper)
    cmds.setAttr(ghost + ".translateX", UPPER_LENGTH * POSITION)
    grey = _shader("boneGrey", (0.55, 0.55, 0.58))
    red = _shader("restRed", (0.9, 0.12, 0.1), transparency=0.7)
    green = _shader("outputGreen", (0.15, 0.8, 0.25), transparency=0.15)
    # 灰=上腕と前腕、赤(半透明)=生成時の補助骨(膨らまない)、緑=出力の補助骨。
    _bone("upperArm_GEO", upper, grey, UPPER_LENGTH, 0.45)
    _bone("forearm_GEO", elbow, grey, FORE_LENGTH, 0.4)
    _muscle("restMuscle_GEO", ghost, red)
    _muscle("outputMuscle_GEO", helper, green)
    camera, camera_shape = cmds.camera(name="bulgeCamera", focalLength=35)
    # 正面(+Z)から少し上・斜めより。肘の曲げと補助骨の膨らみが見える位置に固定する。
    cmds.viewPlace(camera_shape, eye=(8.5, 2.5, 28), lookAt=(7.5, 1.0, 0))
    window = cmds.window("muscleBulgeValidationWindow", title="MuscleBulge - helper bulges with the elbow bend",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("muscleBulgeValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["muscleBulgeHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, upper, elbow, helper, owner, values, names


def evaluate_frame(frame, upper, elbow, helper, owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import MuscleBulge
    rotate, stage = pose(frame)
    cmds.setAttr(elbow + ".rotate", *rotate)
    upper_world = om.MMatrix(cmds.getAttr(upper + ".worldMatrix[0]"))
    elbow_world = om.MMatrix(cmds.getAttr(elbow + ".worldMatrix[0]"))
    relative = elbow_world * upper_world.inverse()
    direction = om.MVector(relative[0], relative[1], relative[2]).normal()
    angle = math.degrees(om.MVector(1, 0, 0).angle(direction))
    weight = MuscleBulge.response(angle, START, FULL)
    scale = 1 + BULGE * weight
    offset = PUSH * weight
    local = om.MMatrix([1, 0, 0, 0, 0, scale, 0, 0, 0, 0, scale, 0,
                        UPPER_LENGTH * POSITION, offset, 0, 1])
    expected = local * upper_world
    actual = om.MMatrix(cmds.getAttr(helper + ".worldMatrix[0]"))
    matrix_error = max(abs(a - b) for a, b in zip(actual, expected))
    dg = {attr: owner.getPlug(attr).get() for attr in ("bendAngle", "weight", "scale", "offset")}
    if angle < START:
        state = "bend < startAngle -> weight = 0"
    elif angle < FULL:
        state = "startAngle < bend < fullAngle -> smoothstep"
    else:
        state = "bend >= fullAngle -> weight = 1"
    values[:] = [
        "GREEN = output helper (bulge)   RED (transparent) = rest helper   GREY = upper arm and forearm",
        "STAGE: " + stage,
        "fixed: startAngle = 60 deg   fullAngle = 140 deg   bulge = 0.6   push = 0.8 cm (+Y)   position = 0.5",
        "bend = angle(rest forearm +X, current forearm +X) in upper arm space (twist ignored)   "
        "t = clamp((bend-60)/80, 0, 1)   weight = t*t*(3-2t)",
        "INPUT elbow rotate = ({:6.1f}, {:6.1f}, {:6.1f}) deg   bend (independent) = {:6.2f} deg   {}".format(
            rotate[0], rotate[1], rotate[2], angle, state),
        "OUTPUT bendAngle = {:6.2f} deg   weight = {:.3f}   scale Y/Z = 1 + 0.6*w = {:.3f}   offset = 0.8*w = {:.3f} cm".format(
            dg["bendAngle"], dg["weight"], dg["scale"], dg["offset"]),
        "CHECK |bendAngle error| = {:.5f} deg   |weight error| = {:.6f}   helper matrix error = {:.6f}".format(
            abs(dg["bendAngle"] - angle), abs(dg["weight"] - weight), matrix_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (abs(dg["bendAngle"] - angle) < 1e-3 and abs(dg["weight"] - weight) < 1e-5
          and abs(dg["scale"] - scale) < 1e-5 and abs(dg["offset"] - offset) < 1e-5 and matrix_error < 1e-4)
    return {"frame": frame, "presentation_stage": stage, "input_elbow_rotate_degrees": rotate,
            "independent_bend_degrees": angle, "expected_weight": weight, "dg": dg,
            "matrix_error": matrix_error, "ok": ok}


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
        panel, upper, elbow, helper, owner, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("MuscleBulge: 肘の曲げ角による補助骨の膨らみ", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, upper, elbow, helper, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "muscle_bulge.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-muscle-bulge.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("muscle-bulge-%Y%m%d-%H%M%S")
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
