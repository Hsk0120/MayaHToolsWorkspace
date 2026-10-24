"""JawHingeの閉じ側の柔らかい制限と前方スライドを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_jaw_hinge.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOFTNESS = 4.0
SLIDE = (0.0, 0.0, 0.03)
SEGMENT = 30
# (顎のrotateX[開き、+で開く], rotateY[左右], 次の姿勢へ向かう段階名)。基準は閉じた姿勢。
POSES = [
    (0, 0, "1 REST: CLOSED (CREATION POSE)"),
    (0, 0, "2 OPEN: ROTATION PASSES, JAW SLIDES FORWARD"),
    (30, 0, "2 OPEN: ROTATION PASSES, JAW SLIDES FORWARD"),
    (30, 0, "3 CLOSE TO REST"),
    (0, 0, "4 OVER-CLOSE INPUT: STOPS NEAR -4 DEG"),
    (-25, 0, "5 HOLD BEYOND LIMIT"),
    (-25, 0, "6 RETURN TO REST"),
    (0, 0, "7 OPEN WITH SIDE SWING: YAW KEPT"),
    (20, 15, "7 OPEN WITH SIDE SWING: YAW KEPT"),
    (20, -15, "8 OVER-CLOSE WITH SIDE SWING"),
    (-20, 10, "9 RETURN TO REST"),
    (0, 0, "9 RETURN TO REST"),
    (0, 0, "9 RETURN TO REST"),
]


def pose(frame):
    """フレームの入力(rx, ry, 段階名)をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:2], POSES[index + 1][:2])]
    return values + [POSES[index][2]]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _curve(name, points, color, parent=None, width=3.0):
    """表示色付きのNURBS曲線を作る。"""
    from maya import cmds
    curve = cmds.curve(name=name, degree=1, point=points)
    shape = cmds.listRelatives(curve, shapes=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideColor", color)
    cmds.setAttr(shape + ".lineWidth", width)
    if parent:
        cmds.parent(curve, parent, relative=True)
    return curve


def _box(name, parent, group, size, center):
    """parent下に、指定の大きさと中心の箱を作る。"""
    from maya import cmds
    box = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    cmds.setAttr(box + ".translate", *center)
    cmds.parent(box, parent, relative=True)
    cmds.sets(box, edit=True, forceElement=group)
    return box


def buildScene():
    """検証シーンを作り、(panel, 入力の顎, 出力の顎, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import JawHinge
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    head = cmds.createNode("transform", name="head_GRP")
    jaw = cmds.createNode("joint", name="input_jaw_JNT", parent=head)
    graph = JawHinge.create(jaw, name="jawHinge", pitchAxis="x", yawAxis="y", openDirection=1,
                            softness=SOFTNESS, slide=SLIDE)
    owner = graph.container
    out = cmds.createNode("transform", name="output_jaw_GRP", parent=head)
    owner.getPlug("matrix").connectTo(out + ".offsetParentMatrix")
    grey = _shader("skullGrey", (0.55, 0.55, 0.58))
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.55)
    green = _shader("outputGreen", (0.1, 0.8, 0.2))
    # 灰=上顎(固定)、赤=入力の顎(半透明)、緑=出力の顎。顎の回転中心(顎関節)は原点。
    _box("upperJaw_GEO", head, grey, (2.0, 1.2, 5.0), (0, 0.6, 2.2))
    _box("inputJaw_GEO", jaw, red, (2.1, 0.7, 5.0), (0, -0.35, 2.2))
    _box("outputJaw_GEO", out, green, (1.9, 0.6, 4.9), (0, -0.35, 2.2))
    _curve("restLine_CRV", [(0, 0, 0), (0, 0, 6.0)], 2, parent=head, width=2)
    _curve("inputJawLine_CRV", [(0, 0, 0), (0, 0, 5.5)], 13, parent=jaw, width=2)
    _curve("outputJawLine_CRV", [(0, 0, 0), (0, 0, 5.5)], 14, parent=out, width=4)
    camera, camera_shape = cmds.camera(name="jawCamera", focalLength=36)
    # 横(+X)から少し前寄りに見る。開閉・閉じすぎ・前方スライドが同時にわかる位置に固定する。
    cmds.viewPlace(camera_shape, eye=(16, 2.0, 5.0), lookAt=(0, -0.6, 2.2))
    cmds.setAttr(camera_shape + ".verticalFilmOffset", -0.06)
    window = cmds.window("jawHingeValidationWindow", title="JawHinge - soft close limit and forward slide",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("jawHingeValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["jawHingeHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, jaw, out, owner, values, names


def _quaternion(matrix):
    """行列の回転をQuaternionで返す。"""
    from maya.api import OpenMaya as om
    return om.MTransformationMatrix(om.MMatrix(matrix)).rotation(asQuaternion=True)


def evaluate_frame(frame, jaw, out, owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import JawHinge
    rx, ry, stage = pose(frame)
    cmds.setAttr(jaw + ".rotate", rx, ry, 0)
    # 顎は基準回転なし・rotateOrder xyzなので、開き角=rotateX、Yaw=rotateYとなる。
    expected = JawHinge.limitedOpen(rx, SOFTNESS)
    dg_open = owner.getPlug("openAngle").get()
    dg_limited = owner.getPlug("limitedOpen").get()
    dg_slide = list(cmds.getAttr(str(owner) + ".slideOffset")[0])
    target = om.MTransformationMatrix(om.MEulerRotation(math.radians(expected), math.radians(ry), 0).asMatrix())
    target.setTranslation(om.MVector(*SLIDE) * expected, om.MSpace.kTransform)
    # 出力のparentMatrixはoffsetParentMatrixを含むため、同じ親を持つ入力の顎(OPMは単位行列)の親行列を使う。
    target_world = target.asMatrix() * om.MMatrix(cmds.getAttr(jaw + ".parentMatrix[0]"))
    actual = om.MMatrix(cmds.getAttr(out + ".worldMatrix[0]"))
    a, b = _quaternion(actual), _quaternion(target_world)
    dot = abs(a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w)
    rotation_error = math.degrees(2 * math.acos(min(1.0, dot)))
    position_error = (om.MVector(actual[12], actual[13], actual[14])
                      - om.MVector(target_world[12], target_world[13], target_world[14])).length()
    out_yaw = math.degrees(om.MTransformationMatrix(om.MMatrix(cmds.getAttr(out + ".offsetParentMatrix")))
                           .rotation().y)
    if rx >= 0:
        state = "a >= 0 -> o = a (passes)"
    else:
        state = "a < 0 -> o = -4*(1-exp(a/4)), never below -4"
    values[:] = [
        "GREEN = output jaw   RED (transparent) = input jaw   GREY = upper jaw (fixed)   (side view, forward = left)",
        "STAGE: " + stage,
        "fixed: softness w = 4 deg   slide = (0, 0, 0.03) cm/deg   (a = open angle from closed rest, deg)",
        "o = a if a >= 0 else -w*(1-exp(a/w))      rotation pitch = o (yaw/roll kept)      position += slide*o",
        "INPUT jaw rotate = ({:+6.1f}, {:+6.1f}, 0) deg   DG openAngle a = {:+7.2f} deg".format(rx, ry, dg_open),
        "OUTPUT limitedOpen o = {:+7.2f} deg   output yaw = {:+6.2f} deg   slide Z = {:+6.3f} cm   {}".format(
            dg_limited, out_yaw, dg_slide[2], state),
        "CHECK |DG o - formula| = {:.4f} deg   output rotation error = {:.4f} deg   position error = {:.5f} cm".format(
            abs(dg_limited - expected), rotation_error, position_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (abs(dg_open - rx) < 0.01 and abs(dg_limited - expected) < 0.01 and dg_limited >= -SOFTNESS - 1e-9
          and rotation_error < 0.01 and position_error < 1e-4 and abs(out_yaw - ry) < 0.05)
    return {"frame": frame, "presentation_stage": stage, "input_jaw_rotate_degrees": [rx, ry, 0],
            "dg_open_angle": dg_open, "dg_limited_open": dg_limited, "expected_limited_open": expected,
            "dg_slide_offset_cm": dg_slide, "output_yaw_degrees": out_yaw,
            "output_rotation_error_degrees": rotation_error, "output_position_error_cm": position_error, "ok": ok}


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
        panel, jaw, out, owner, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("JawHinge: 顎の閉じすぎ防止と前方スライド", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, jaw, out, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "jaw-hinge.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-jaw-hinge.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("jaw-hinge-%Y%m%d-%H%M%S")
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
