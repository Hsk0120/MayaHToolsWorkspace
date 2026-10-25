"""PoleVectorPlacementのポールの位置(曲がる平面上で付け根-先端の線に垂直)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_pole_vector_placement.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPPER = 10.0
LOWER = 9.0
DISTANCE = 8.0
SEGMENT = 36
# (肩のrotateX, rotateY, rotateZ, 肘のrotateY, 次の姿勢へ向かう段階名)。
POSES = [
    (0, 0, 0, 40, "1 REST: ELBOW BENT 40 DEG"),
    (0, 0, 0, 40, "2 RAISE ARM"),
    (0, 0, 60, 40, "3 TWIST UPPER ARM: POLE TURNS WITH THE BEND PLANE"),
    (90, 0, 60, 40, "4 BEND MORE"),
    (90, 0, 60, 110, "5 STRAIGHTEN: POLE COLLAPSES TO ELBOW AT 0 DEG"),
    (90, 0, 60, 0, "6 BEND AGAIN"),
    (90, 0, 60, 50, "7 RETURN TO REST"),
    (0, 0, 0, 40, "7 RETURN TO REST"),
    (0, 0, 0, 40, "7 RETURN TO REST"),
]


def pose(frame):
    """フレームの入力(肩rx, ry, rz, 肘ry, 段階名)をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:4], POSES[index + 1][:4])]
    return values + [POSES[index][4]]


def _shader(name, color):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _bone(name, parent, group, length):
    """parentのローカル+X方向へ長さlengthの棒と根元の球を作る。"""
    from maya import cmds
    rod = cmds.polyCylinder(name=name, axis=(1, 0, 0), height=length, radius=0.35, subdivisionsX=16)[0]
    ball = cmds.polySphere(name=name + "_ball", radius=0.6)[0]
    cmds.setAttr(rod + ".translateX", length / 2)
    for node in (rod, ball):
        cmds.parent(node, parent, relative=True)
        cmds.sets(node, edit=True, forceElement=group)


def _line(name, color, width):
    """2点を結ぶ表示用の直線。点は毎フレームCVの位置で更新する。"""
    from maya import cmds
    curve = cmds.curve(name=name, degree=1, point=[(0, 0, 0), (1, 0, 0)])
    shape = cmds.listRelatives(curve, shapes=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideColor", color)
    cmds.setAttr(shape + ".lineWidth", width)
    return curve


def buildScene():
    """検証シーンを作り、(panel, 関節3つ, ポールの印, 線2本, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import PoleVectorPlacement
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    chest = cmds.createNode("transform", name="chest_GRP")
    shoulder = cmds.createNode("joint", name="shoulder_JNT", parent=chest)
    elbow = cmds.createNode("joint", name="elbow_JNT", parent=shoulder)
    cmds.setAttr(elbow + ".translateX", UPPER)
    wrist = cmds.createNode("joint", name="wrist_JNT", parent=elbow)
    cmds.setAttr(wrist + ".translateX", LOWER)
    cmds.setAttr(elbow + ".rotateY", 40)
    owner = PoleVectorPlacement.create(shoulder, elbow, wrist, name="armPole", distance=DISTANCE).container
    marker = cmds.polySphere(name="pole_GEO", radius=0.8)[0]
    owner.getPlug("matrix").connectTo(marker + ".offsetParentMatrix")
    blue, green, white = (_shader("armBlue", (0.25, 0.45, 0.9)), _shader("poleGreen", (0.1, 0.85, 0.2)),
                          _shader("wristWhite", (0.9, 0.9, 0.9)))
    cmds.sets(marker, edit=True, forceElement=green)
    _bone("upperArm_GEO", shoulder, blue, UPPER)
    _bone("forearm_GEO", elbow, blue, LOWER)
    hand = cmds.polySphere(name="wrist_GEO", radius=0.6)[0]
    cmds.parent(hand, wrist, relative=True)
    cmds.sets(hand, edit=True, forceElement=white)
    # 黄=付け根と先端を結ぶ線、緑=中間関節からポールへの線。
    lines = (_line("startEnd_CRV", 17, 2.5), _line("midPole_CRV", 14, 3.5))
    camera, camera_shape = cmds.camera(name="poleCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(16, 14, 52), lookAt=(5, 7, 0))
    cmds.setAttr(camera_shape + ".verticalFilmOffset", -0.12)
    window = cmds.window("poleValidationWindow", title="PoleVectorPlacement - pole on the bend plane",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("poleValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["poleHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, (shoulder, elbow, wrist), marker, lines, owner, values, names


def evaluate_frame(frame, joints, marker, lines, owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import PoleVectorPlacement
    rx, ry, rz, elbow, stage = pose(frame)
    cmds.setAttr(joints[0] + ".rotate", rx, ry, rz)
    cmds.setAttr(joints[1] + ".rotateY", elbow)
    s, m, e = (om.MVector(cmds.xform(j, q=True, worldSpace=True, translation=True)) for j in joints)
    expected = om.MVector(*PoleVectorPlacement.polePosition(s, m, e, DISTANCE))
    dg = om.MVector(cmds.getAttr(str(owner) + ".position")[0])
    shown = om.MVector(cmds.xform(marker, q=True, worldSpace=True, translation=True))
    bend = owner.getPlug("bendDistance").get()
    offset = dg - m
    line = e - s
    if offset.length() > 1e-6:
        perpendicular = math.degrees(offset.angle(line))
        plane = abs(offset.normal() * ((m - s) ^ line).normal())
        state = "bend {:.2f} cm -> pole {:.2f} cm outside the elbow".format(bend, offset.length())
    else:
        perpendicular, plane = 90.0, 0.0
        state = "straight (bend < 0.0001 cm) -> pole = elbow"
    for curve, (a, b) in zip(lines, ((s, e), (m, dg))):
        cmds.xform(curve + ".cv[0]", worldSpace=True, translation=(a.x, a.y, a.z))
        cmds.xform(curve + ".cv[1]", worldSpace=True, translation=(b.x, b.y, b.z))
    error = (dg - expected).length()
    values[:] = [
        "BLUE = FK arm (input)   GREEN = pole (output)   YELLOW = shoulder-wrist line   GREEN LINE = elbow-pole",
        "STAGE: " + stage,
        "fixed: distance = 8 cm   upper arm 10 cm   forearm 9 cm   (world positions, cm)",
        "p = s + ((m-s).(e-s))/|e-s|^2 (e-s)    d = m - p    pole = m + distance * d/|d|    (|d| < 0.0001 -> pole = m)",
        "INPUT shoulder rotate = ({:+5.1f}, {:+5.1f}, {:+5.1f}) deg   elbow rotateY = {:6.1f} deg".format(rx, ry, rz, elbow),
        "OUTPUT pole = ({:+6.2f}, {:+6.2f}, {:+6.2f}) cm   bendDistance = {:5.2f} cm   {}".format(
            dg.x, dg.y, dg.z, bend, state),
        "CHECK |DG - formula| = {:.5f} cm   angle to shoulder-wrist line = {:6.3f} deg   off-plane = {:.5f}".format(
            error, perpendicular, plane),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (error < 1e-3 and (shown - dg).length() < 1e-3 and abs(perpendicular - 90.0) < 0.01 and plane < 1e-4)
    return {"frame": frame, "presentation_stage": stage, "input_shoulder_rotate": [rx, ry, rz],
            "input_elbow_rotate_y": elbow, "dg_pole": [dg.x, dg.y, dg.z],
            "expected_pole": [expected.x, expected.y, expected.z], "bend_distance": bend,
            "angle_to_line_degrees": perpendicular, "off_plane": plane, "ok": ok}


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
        panel, joints, marker, lines, owner, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("PoleVectorPlacement: 曲がる平面上のポールの位置", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, joints, marker, lines, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "pole-vector-placement.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-pole-vector-placement.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("pole-vector-%Y%m%d-%H%M%S")
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
