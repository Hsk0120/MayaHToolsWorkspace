"""BowStringの弦の向き・長さ・引き量(draw・drawWeight)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_bow_string.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = (0.0, 10.0, -2.0)
BOTTOM = (0.0, -10.0, -2.0)
NOCK = (0.0, 0.0, 1.0)
MAX_DRAW = 10.0
SEGMENT = 30
# (ノックのtranslateY, translateZ[cm], 次の姿勢へ向かう段階名)。基準は弦を張っただけの状態。
POSES = [
    (0, 1, "1 REST (BRACED)"),
    (0, 1, "2 DRAW: STRINGS FOLLOW THE NOCK"),
    (0, 7, "3 FULL DRAW: drawWeight -> 1"),
    (0, 11, "4 OVERDRAW: drawWeight STAYS 1 (VALUE ONLY)"),
    (0, 15, "5 RELEASE"),
    (0, 1, "6 NOCK MOVED UP: STRINGS STAY IN ONE PLANE"),
    (4, 6, "7 RETURN TO REST"),
    (0, 1, "7 RETURN TO REST"),
    (0, 1, "7 RETURN TO REST"),
]


def pose(frame):
    """フレームのノック位置と段階名をsmoothstepで補間する。"""
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


def _rod(name, parent, group, radius, length=1.0):
    """parentのローカル+X方向へ長さlengthの円柱を作る。"""
    from maya import cmds
    rod = cmds.polyCylinder(name=name, axis=(1, 0, 0), height=length, radius=radius, subdivisionsX=12)[0]
    cmds.setAttr(rod + ".translate", length / 2, 0, 0)
    cmds.parent(rod, parent, relative=True)
    cmds.sets(rod, edit=True, forceElement=group)
    return rod


def _aimMatrix(origin, target, normal):
    """originから+Xがtargetを向き、+Yがnormalを向くワールド行列(行ベクトル規約の16要素)。"""
    from maya.api import OpenMaya as om
    x = (om.MVector(target) - om.MVector(origin)).normal()
    y = om.MVector(normal).normal()
    z = (x ^ y).normal()
    y = (z ^ x).normal()
    return [x.x, x.y, x.z, 0, y.x, y.y, y.z, 0, z.x, z.y, z.z, 0, origin[0], origin[1], origin[2], 1]


def buildScene():
    """検証シーンを作り、(panel, ノック, 先端, 出力, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import BowString
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    bow = cmds.createNode("transform", name="bow_GRP")
    normal = (om.MVector(TOP) - om.MVector(NOCK)) ^ (om.MVector(BOTTOM) - om.MVector(NOCK))
    tips = []
    for role, position in (("top", TOP), ("bottom", BOTTOM)):
        tip = cmds.createNode("joint", name="input_{}Tip_JNT".format(role), parent=bow)
        # 生成時に弦の+Xがノックを向く姿勢にする(見やすさのため。一致は必須ではない)。
        cmds.xform(tip, worldSpace=True, matrix=_aimMatrix(position, NOCK, normal))
        tips.append(tip)
    nock = cmds.createNode("transform", name="nock_CTL", parent=bow)
    cmds.setAttr(nock + ".translate", *NOCK)
    graph = BowString.create(tips[0], tips[1], nock, name="bowString", aimAxis="x", upAxis="y", maxDraw=MAX_DRAW)
    owner = graph.container
    grey = _shader("bowGrey", (0.45, 0.35, 0.25))
    red = _shader("restRed", (0.9, 0.12, 0.1), transparency=0.6)
    green = _shader("stringGreen", (0.1, 0.85, 0.2))
    yellow = _shader("nockYellow", (1.0, 0.85, 0.1))
    outputs = []
    for role, tip in zip(("top", "bottom"), tips):
        out = cmds.createNode("transform", name="output_{}String_GRP".format(role), parent=bow)
        owner.getPlug(role + "Matrix").connectTo(out + ".offsetParentMatrix")
        stretch = cmds.createNode("transform", name="output_{}Stretch_GRP".format(role), parent=out)
        owner.getPlug(role + "Length").connectTo(stretch + ".scaleX")
        _rod("output{}String_GEO".format(role.title()), stretch, green, 0.12)
        # 赤(半透明)=生成時の弦(動かない)。
        rest = cmds.createNode("transform", name="rest_{}String_GRP".format(role), parent=bow)
        cmds.xform(rest, worldSpace=True, matrix=cmds.xform(tip, query=True, worldSpace=True, matrix=True))
        cmds.setAttr(rest + ".translateX", -0.6)
        length = (om.MVector(NOCK) - om.MVector(TOP if role == "top" else BOTTOM)).length()
        _rod("rest{}String_GEO".format(role.title()), rest, red, 0.08, length)
        outputs.append(out)
    # 弓の握りとリム(固定の形。曲がりは含まない)。
    for role, position in (("top", TOP), ("bottom", BOTTOM)):
        limb = cmds.createNode("transform", name="{}Limb_GRP".format(role), parent=bow)
        cmds.xform(limb, worldSpace=True, matrix=_aimMatrix((0, 0, -3.5), position, (-1, 0, 0)))
        length = (om.MVector(position) - om.MVector(0, 0, -3.5)).length()
        _rod("{}Limb_GEO".format(role), limb, grey, 0.45, length)
    grip = cmds.polyCube(name="grip_GEO", width=1.2, height=4, depth=1.4)[0]
    cmds.setAttr(grip + ".translate", 0, 0, -3.5)
    cmds.parent(grip, bow, relative=True)
    cmds.sets(grip, edit=True, forceElement=grey)
    ball = cmds.polySphere(name="nock_GEO", radius=0.45)[0]
    cmds.parent(ball, nock, relative=True)
    cmds.sets(ball, edit=True, forceElement=yellow)
    camera, camera_shape = cmds.camera(name="bowCamera", focalLength=35)
    # 横(+X)から見る。弓の面(YZ)と弦の動きが見える位置に固定する。
    cmds.viewPlace(camera_shape, eye=(40, 1, 5), lookAt=(0, 0, 4))
    window = cmds.window("bowStringValidationWindow", title="BowString - strings aim at the nock",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("bowStringValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 7
    names = ["bowStringHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, nock, tips, outputs, owner, values, names


def evaluate_frame(frame, nock, tips, outputs, owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import BowString
    y, z, stage = pose(frame)
    cmds.setAttr(nock + ".translate", 0, y, z)
    nock_p = om.MVector(cmds.xform(nock, q=True, worldSpace=True, translation=True))
    tip_p = [om.MVector(cmds.xform(t, q=True, worldSpace=True, translation=True)) for t in tips]
    lengths = [(nock_p - p).length() for p in tip_p]
    draw = (nock_p - (tip_p[0] + tip_p[1]) * 0.5).length() - 3.0
    weight = BowString.drawWeight(draw, MAX_DRAW)
    errors = []
    for out, p in zip(outputs, tip_p):
        matrix = om.MMatrix(cmds.getAttr(out + ".worldMatrix[0]"))
        axis = om.MVector(matrix[0], matrix[1], matrix[2]).normal()
        errors.append(math.degrees(axis.angle((nock_p - p).normal())))
    dg = {attr: owner.getPlug(attr).get() for attr in ("topLength", "bottomLength", "restDraw", "draw", "drawWeight")}
    if draw > MAX_DRAW + 1e-6:
        state = "draw > maxDraw 10 -> drawWeight clamped to 1 (nock not limited)"
    elif draw < -1e-6:
        state = "draw < 0 -> drawWeight clamped to 0"
    else:
        state = "0 <= draw <= maxDraw -> drawWeight = draw / 10"
    values[:] = [
        "GREEN = output strings   RED (transparent) = strings at creation   YELLOW = nock control   BROWN = bow",
        "STAGE: " + stage,
        "fixed: restDraw = {:.2f} cm (braced)   maxDraw = 10 cm   tips (0, +-10, -2)".format(dg["restDraw"]),
        "each half: aimMatrix +X -> nock, +Y -> bow plane normal   length = |nock - tip|   "
        "draw = |nock - (top+bottom)/2| - restDraw   drawWeight = clamp(draw/maxDraw, 0, 1)",
        "INPUT nock = (0, {:5.2f}, {:5.2f}) cm   independent: lengths {:6.3f} / {:6.3f}  draw {:+6.3f}".format(
            y, z, lengths[0], lengths[1], draw),
        "OUTPUT topLength = {:6.3f}  bottomLength = {:6.3f}  draw = {:+6.3f}  drawWeight = {:5.3f}   {}".format(
            dg["topLength"], dg["bottomLength"], dg["draw"], dg["drawWeight"], state),
        "CHECK aim error top = {:.4f} deg  bottom = {:.4f} deg".format(errors[0], errors[1]),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (abs(dg["topLength"] - lengths[0]) < 1e-3 and abs(dg["bottomLength"] - lengths[1]) < 1e-3
          and abs(dg["draw"] - draw) < 1e-3 and abs(dg["drawWeight"] - weight) < 1e-4 and max(errors) < 0.01)
    return {"frame": frame, "presentation_stage": stage, "input_nock_cm": [0.0, y, z],
            "independent_lengths_cm": lengths, "independent_draw_cm": draw, "expected_draw_weight": weight,
            "dg": dg, "aim_error_degrees": errors, "ok": ok}


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
        panel, nock, tips, outputs, owner, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("BowString: 弦の向き・長さと引き量", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, nock, tips, outputs, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "bow_string.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-bow-string.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("bow-string-%Y%m%d-%H%M%S")
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
