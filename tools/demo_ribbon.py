"""Ribbon(コントロールを断面にした帯と、その上の行列)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_ribbon.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROLS = [(-9.0, 0.0, 0.0), (-3.0, 0.0, 0.0), (3.0, 0.0, 0.0), (9.0, 0.0, 0.0)]
COUNT = 10
WIDTH = 3.0
SEGMENT = 30
# (ctrl1のtranslateY, ctrl2のtranslateY, ctrl3のtranslateY, ctrl3のrotateX[度], width[cm], 次の姿勢へ向かう段階名)。
POSES = [
    (0, 0, 0, 0, WIDTH, "1 REST"),
    (0, 0, 0, 0, WIDTH, "2 ARCH: MIDDLE CONTROLS UP"),
    (4, 4, 0, 0, WIDTH, "3 S-CURVE: RIBBON PASSES THROUGH EVERY CONTROL"),
    (4, -4, 0, 0, WIDTH, "4 TWIST THE TIP CONTROL 150 DEG (NO FLIP PAST 90)"),
    (4, -4, 0, 150, WIDTH, "5 TIP UP + TWIST"),
    (2, -2, 5, 150, WIDTH, "6 WIDTH 3 -> 6 cm"),
    (2, -2, 5, 150, 6.0, "7 RETURN TO REST"),
    (0, 0, 0, 0, WIDTH, "7 RETURN TO REST"),
    (0, 0, 0, 0, WIDTH, "7 RETURN TO REST"),
]


def pose(frame):
    """フレームの入力値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:5], POSES[index + 1][:5])]
    return values + [POSES[index][5]]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _box(name, parent, group, size):
    """parentの下に、指定の大きさ(X・Y・Z)の箱を作る。"""
    from maya import cmds
    box = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    cmds.parent(box, parent, relative=True)
    cmds.sets(box, edit=True, forceElement=group)
    return box


def buildScene():
    """検証シーンを作り、(panel, コントロール, 出力, container, サーフェス, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import Ribbon
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    yellow = _shader("controlYellow", (1.0, 0.85, 0.1))
    green = _shader("outputGreen", (0.1, 0.85, 0.2))
    blue = _shader("ribbonBlue", (0.25, 0.45, 0.95), transparency=0.55)
    controls = []
    for index, position in enumerate(CONTROLS):
        control = cmds.createNode("transform", name="ribbon{}_CTL".format(index))
        cmds.setAttr(control + ".translate", *position)
        # 黄色の板 = コントロールの幅の向き(ローカルZ)。帯の断面はこの向きになる。
        _box("ribbon{}Control_GEO".format(index), control, yellow, (0.3, 0.3, WIDTH + 1.2))
        controls.append(control)
    graph = Ribbon.create(controls, count=COUNT, name="ribbon", width=WIDTH, sideAxis="z")
    owner = graph.container
    surface = "ribbon_surface"
    # 録画では帯を半透明の青で見せる(既定はテンプレート表示)。
    cmds.setAttr(surface + ".overrideEnabled", False)
    cmds.sets(surface, edit=True, forceElement=blue)
    outputs = []
    for index in range(COUNT):
        out = cmds.createNode("transform", name="output{}_GRP".format(index))
        owner.getPlug("matrix{}".format(index)).connectTo(out + ".offsetParentMatrix")
        # 緑の箱 = 出力の向き(長い辺がZ=幅、短い突起がY=法線)。
        _box("output{}_GEO".format(index), out, green, (0.35, 0.2, 2.0))
        fin = _box("output{}Fin_GEO".format(index), out, green, (0.15, 0.8, 0.15))
        cmds.setAttr(fin + ".translateY", 0.4)
        outputs.append(out)
    camera, camera_shape = cmds.camera(name="ribbonCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(10, 16, 34), lookAt=(0, 0, 0))
    window = cmds.window("ribbonValidationWindow", title="Ribbon - surface through the controls",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("ribbonValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 7
    names = ["ribbonHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, controls, outputs, owner, surface + "Shape", values, names


def evaluate_frame(frame, controls, outputs, owner, shape, values, names):
    """入力を更新し、DG出力をOpenMayaで求めたサーフェスの点・接線・法線と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    c1, c2, c3, twist, width, stage = pose(frame)
    cmds.setAttr(controls[1] + ".translateY", c1)
    cmds.setAttr(controls[2] + ".translateY", c2)
    cmds.setAttr(controls[3] + ".translateY", c3)
    cmds.setAttr(controls[3] + ".rotateX", twist)
    owner.getPlug("width").set(width)
    fn = om.MFnNurbsSurface(om.MSelectionList().add(shape).getDagPath(0))
    u0, u1, v0, v1 = fn.knotDomainInU + fn.knotDomainInV
    position_error, axis_error = 0.0, 0.0
    matrices = []
    for index in range(COUNT):
        u = u0 + owner.getPlug("position{}".format(index)).get() * (u1 - u0)
        v = v0 + 0.5 * (v1 - v0)
        point = om.MVector(fn.getPointAtParam(u, v, om.MSpace.kWorld))
        tangent = fn.tangents(u, v, om.MSpace.kWorld)[0].normal()
        normal = fn.normal(u, v, om.MSpace.kWorld).normal()
        matrix = om.MMatrix(cmds.getAttr("{}.matrix{}".format(owner, index)))
        matrices.append(matrix)
        x = om.MVector(matrix[0], matrix[1], matrix[2]).normal()
        y = om.MVector(matrix[4], matrix[5], matrix[6]).normal()
        position_error = max(position_error, (om.MVector(matrix[12], matrix[13], matrix[14]) - point).length())
        axis_error = max(axis_error, math.degrees(x.angle(tangent)), math.degrees(min(y.angle(normal),
                                                                                       y.angle(-normal))))
    # 全てのコントロールを通る: COUNT=10 の出力 0・3・6・9 はコントロール 0〜3 の位置。
    through = max((om.MVector(matrices[3 * k][12], matrices[3 * k][13], matrices[3 * k][14])
                   - om.MVector(cmds.xform(c, q=True, worldSpace=True, translation=True))).length()
                  for k, c in enumerate(controls))
    tip = matrices[-1]
    tip_twist = math.degrees(math.atan2(-tip[9], tip[10]))
    edge = om.MPoint(fn.getPointAtParam(u0, v0, om.MSpace.kWorld)).distanceTo(
        om.MPoint(fn.getPointAtParam(u0, v1, om.MSpace.kWorld)))
    # 先端の出力のZは、先端のコントロールのローカルZを出力のXに直交化した向きと一致する。
    side_world = om.MMatrix(cmds.getAttr(controls[-1] + ".worldMatrix[0]"))
    side = om.MVector(side_world[8], side_world[9], side_world[10]).normal()
    x_tip = om.MVector(tip[0], tip[1], tip[2]).normal()
    expected = (side - x_tip * (side * x_tip)).normal()
    twist_error = math.degrees(om.MVector(tip[8], tip[9], tip[10]).normal().angle(expected))
    values[:] = [
        "YELLOW = controls (plate = local Z = width axis)   BLUE = ribbon surface   GREEN = outputs (long side = Z, fin = Y)",
        "STAGE: " + stage,
        "fixed: 4 controls at x = -9, -3, 3, 9 cm   count = 10   sideAxis = z   position_i = i / 9",
        "section_i = ctrl_i world * (0, 0, +-width/2)   surface = loft(sections, cubic, uniform)   "
        "out_i = uvPin(U = position_i, V = 0.5): X = dP/dU, Y = normal",
        "INPUT ctrl1 ty = {:+5.2f}  ctrl2 ty = {:+5.2f}  ctrl3 ty = {:+5.2f}  ctrl3 rx = {:6.1f} deg  "
        "width = {:4.2f} cm".format(c1, c2, c3, twist, width),
        "OUTPUT tip Z angle about world X = {:6.1f} deg   surface width = {:5.3f} cm   max |out - control| = {:.5f} cm".format(
            tip_twist, edge, through),
        "CHECK vs OpenMaya surface: position error {:.5f} cm   axis error {:.4f} deg   "
        "tip Z vs ctrl3 local Z: {:.4f} deg".format(position_error, axis_error, twist_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (position_error < 1e-3 and axis_error < 0.05 and through < 1e-3 and abs(edge - width) < 1e-3
          and twist_error < 0.01)
    return {"frame": frame, "presentation_stage": stage, "input": [c1, c2, c3, twist, width],
            "position_error_cm": position_error, "axis_error_degrees": axis_error,
            "through_controls_error_cm": through, "tip_side_error_degrees": twist_error, "surface_width_cm": edge, "tip_twist_degrees": tip_twist,
            "ok": ok}


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
        panel, controls, outputs, owner, shape, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("Ribbon: コントロールを通る帯と、その上の行列", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, controls, outputs, owner, shape, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "ribbon.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-ribbon.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("ribbon-%Y%m%d-%H%M%S")
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
