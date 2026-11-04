"""ScapulaGlideの胸郭の楕円体の上を滑る肩甲骨を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_scapula_glide.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RADII = (4.0, 6.0, 3.0)
OFFSET = 0.3
SEGMENT = 30
# (肩甲骨のコントロールの位置[cm], 次の姿勢へ向かう段階名)。胸郭の中心は原点・回転なし、背中は-Z側。
POSES = [
    ((1.5, 1.5, -5.0), "1 REST: CONTROL BEHIND THE BACK"),
    ((1.5, 1.5, -5.0), "2 PULL THE CONTROL FAR AWAY: OUTPUT STAYS ON THE SURFACE"),
    ((2.5, 3.0, -10.0), "3 PUSH THE CONTROL INTO THE RIBCAGE: OUTPUT STAYS ON THE SURFACE"),
    ((1.5, 1.0, -1.0), "4 SLIDE AROUND THE SIDE (LONG X AXIS)"),
    ((6.0, 0.5, -1.0), "5 NEAR THE CENTER: DIRECTION STILL DEFINED"),
    ((0.3, 0.2, -0.3), "6 OVER THE TOP (LONG Y AXIS)"),
    ((1.0, 8.0, -1.5), "7 BACK TO REST"),
    ((1.5, 1.5, -5.0), "8 BACK AT REST"),
    ((1.5, 1.5, -5.0), "8 BACK AT REST"),
]


def pose(frame):
    """フレームの位置と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    start, end = POSES[index][0], POSES[index + 1][0]
    return tuple(a + (b - a) * weight for a, b in zip(start, end)), POSES[index][1]


def expected(point):
    """胸郭が原点・回転なしの場合の、期待する位置・法線・向きの半径・距離を返す。"""
    length = math.sqrt(sum(value * value for value in point))
    local = [value / length for value in point] if length > 1e-6 else [1.0, 0.0, 0.0]
    radius = 1.0 / math.sqrt(sum((value / r) ** 2 for value, r in zip(local, RADII)))
    surface = [value * radius for value in local]
    gradient = [value / (r * r) for value, r in zip(surface, RADII)]
    size = math.sqrt(sum(value * value for value in gradient))
    normal = [value / size for value in gradient]
    position = [s + n * OFFSET for s, n in zip(surface, normal)]
    return position, normal, radius, length - radius


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import ScapulaGlide
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    ribcage = cmds.createNode("transform", name="ribcage_JNT")
    control = cmds.createNode("transform", name="scapula_CTRL")
    cmds.setAttr(control + ".translate", *POSES[0][0])
    graph = ScapulaGlide.create(control, ribcage, name="scapulaGlide", radiusX=RADII[0], radiusY=RADII[1],
                                radiusZ=RADII[2], offset=OFFSET, normalAxis="z", upAxis="y")
    owner = graph.container
    gray = _shader("ribcageGray", (0.5, 0.5, 0.55), transparency=0.55)
    red = _shader("inputRed", (0.95, 0.12, 0.1), transparency=0.2)
    green = _shader("outputGreen", (0.15, 0.85, 0.25))
    yellow = _shader("normalYellow", (0.95, 0.85, 0.1))
    body = cmds.polySphere(name="ribcage_GEO", radius=1.0, subdivisionsAxis=48, subdivisionsHeight=32)[0]
    cmds.setAttr(body + ".scale", *RADII)
    cmds.parent(body, ribcage, relative=True)
    cmds.sets(body, edit=True, forceElement=gray)
    marker = cmds.polySphere(name="input_GEO", radius=0.35)[0]
    cmds.parent(marker, control, relative=True)
    cmds.sets(marker, edit=True, forceElement=red)
    output = cmds.createNode("transform", name="scapula_OUT")
    owner.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    blade = cmds.polyCube(name="scapula_GEO", width=2.2, height=3.0, depth=0.2)[0]
    cmds.parent(blade, output, relative=True)
    cmds.sets(blade, edit=True, forceElement=green)
    # 出力のZ軸(外向きの法線)を示す黄色の棒。
    arrow = cmds.polyCylinder(name="normal_GEO", radius=0.08, height=2.0, axis=(0, 0, 1))[0]
    cmds.parent(arrow, output, relative=True)
    cmds.setAttr(arrow + ".translateZ", 1.0)
    cmds.sets(arrow, edit=True, forceElement=yellow)
    camera, camera_shape = cmds.camera(name="scapulaGlideCamera", focalLength=35)
    # 背中側(-Z)の斜め上から。左のHUDと重ならないよう右寄せに固定する。
    cmds.viewPlace(camera_shape, eye=(-17.0, 9.0, -27.0), lookAt=(-4.5, 1.0, 0.0))
    window = cmds.window("scapulaGlideValidationWindow", title="ScapulaGlide - shoulder blade on the ribcage",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("scapulaGlideValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["scapulaGlideHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"owner": owner, "output": output, "control": control}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた式と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    point, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(scene["control"] + ".translate", *point)
    position, normal, radius, distance = expected(point)
    matrix = om.MMatrix(cmds.getAttr(scene["output"] + ".worldMatrix[0]"))
    actual = om.MPoint(matrix[12], matrix[13], matrix[14])
    error = (actual - om.MPoint(*position)).length()
    axis = om.MVector(matrix[8], matrix[9], matrix[10]).normal()
    normal_error = (axis - om.MVector(*normal)).length()
    dg_normal = cmds.getAttr(owner + ".normal")[0]
    dg_radius = cmds.getAttr(owner + ".directionRadius")
    dg_distance = cmds.getAttr(owner + ".distance")
    # offsetを戻した点の陰関数の値(表面なら1)
    back = [a - n * OFFSET for a, n in zip((actual.x, actual.y, actual.z), dg_normal)]
    implicit = sum((value / r) ** 2 for value, r in zip(back, RADII))
    side = "OUTSIDE" if dg_distance > 1e-4 else ("INSIDE" if dg_distance < -1e-4 else "ON")
    values[:] = [
        "GREEN = output shoulder blade   YELLOW = output Z (outward normal)   RED = input control   GRAY = ribcage",
        "STAGE: " + stage,
        "ellipsoid radii rx, ry, rz = {:.0f}, {:.0f}, {:.0f} cm   offset = {:.1f} cm   (fixed)".format(
            RADII[0], RADII[1], RADII[2], OFFSET),
        "l = p / |p|   R = 1 / |(lx/rx, ly/ry, lz/rz)|   s = l R   n = normalize(sx/rx^2, sy/ry^2, sz/rz^2)   out = s + n offset",
        "INPUT p = ({:6.2f}, {:6.2f}, {:6.2f}) cm   |p| = {:6.2f}   distance = |p| - R = {:6.2f} cm ({})".format(
            point[0], point[1], point[2], math.sqrt(sum(v * v for v in point)), dg_distance, side),
        "OUTPUT out = ({:6.2f}, {:6.2f}, {:6.2f}) cm   R = {:5.2f} cm   n = ({:5.2f}, {:5.2f}, {:5.2f})".format(
            actual.x, actual.y, actual.z, dg_radius, dg_normal[0], dg_normal[1], dg_normal[2]),
        "SURFACE (x/rx)^2 + (y/ry)^2 + (z/rz)^2 at out - n offset = {:.6f}  (1 = on the surface)".format(implicit),
        "CHECK |out - formula| = {:.7f} cm   |Z axis - n| = {:.7f}".format(error, normal_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (error < 1e-4 and normal_error < 1e-4 and abs(implicit - 1.0) < 1e-4 and abs(dg_radius - radius) < 1e-4
          and abs(dg_distance - distance) < 1e-4)
    return {"frame": frame, "presentation_stage": stage, "input": {"point": list(point)},
            "output": [actual.x, actual.y, actual.z], "normal": list(dg_normal), "direction_radius": dg_radius,
            "distance": dg_distance, "implicit": implicit, "position_error": error, "normal_error": normal_error,
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
        panel, scene, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("ScapulaGlide: 胸郭の上を滑る肩甲骨", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "scapula_glide.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-scapula-glide.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("scapula-glide-%Y%m%d-%H%M%S")
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
