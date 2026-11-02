"""TorusCollisionの輪(トーラス)との柔らかい衝突を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_torus_collision.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAJOR_RADIUS = 4.0
MINOR_RADIUS = 1.2
MARKER = 0.25
SEGMENT = 30
# (入力のX[cm], 入力のY[cm], softness[cm], 次の姿勢へ向かう段階名)。輪は原点、軸はY。入力はZ=0の面を動き、
# X=+4・-4にある管の断面を外から・穴の側から通る。
POSES = [
    (8.0, 2.0, 1.0, "1 REST: FAR FROM THE RING"),
    (8.0, 2.0, 1.0, "2 APPROACH THE OUTER SIDE OF THE TUBE (band starts 2.2 cm from the core)"),
    (5.0, 0.0, 1.0, "3 INSIDE THE TUBE: OUTPUT STAYS ON THE SURFACE"),
    (4.3, 0.1, 1.0, "4 DEEP INSIDE: ROUND THE CROSS-SECTION OVER THE CORE"),
    (3.9, 0.4, 1.0, "5 TO THE HOLE SIDE OF THE TUBE"),
    (3.3, 0.0, 1.0, "6 INTO THE HOLE: FREE, FAR FROM THE TUBE"),
    (0.0, 0.0, 1.0, "7 CROSS THE AXIS (d is continuous) TO THE OTHER TUBE"),
    (-3.3, 0.0, 1.0, "8 softness 1 -> 0: HARD STOP"),
    (-3.3, 0.0, 0.0, "9 ROUND UNDER THE TUBE (softness 0)"),
    (-4.0, -0.5, 0.0, "10 TO THE OUTER SIDE (softness 0)"),
    (-4.9, 0.0, 0.0, "11 softness 0 -> 1 AND PULL OUT TO A SAFE POSITION"),
    (-8.0, 2.0, 1.0, "12 BACK IN THE SAFE RANGE: OUTPUT = INPUT"),
    (-8.0, 2.0, 1.0, "12 BACK IN THE SAFE RANGE: OUTPUT = INPUT"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:3], POSES[index + 1][:3])]
    return values[0], values[1], values[2], POSES[index][3]


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
    from mlrig.setups import TorusCollision
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    torus = cmds.createNode("transform", name="hoop_TORUS")
    target = cmds.createNode("transform", name="hand_CTRL")
    cmds.setAttr(target + ".translate", POSES[0][0], POSES[0][1], 0.0)
    graph = TorusCollision.create(target, torus, name="torusCollision", majorRadius=MAJOR_RADIUS,
                                  minorRadius=MINOR_RADIUS, softness=1.0)
    owner = graph.container
    output = cmds.createNode("transform", name="handOutput_GRP")
    owner.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    gray = _shader("colliderGray", (0.45, 0.45, 0.5), transparency=0.55)
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.35)
    green = _shader("outputGreen", (0.15, 0.8, 0.25))
    ring = cmds.polyTorus(name="collider_GEO", radius=MAJOR_RADIUS, sectionRadius=MINOR_RADIUS,
                          subdivisionsAxis=64, subdivisionsHeight=32)[0]
    cmds.parent(ring, torus, relative=True)
    cmds.sets(ring, edit=True, forceElement=gray)
    for name, parent, group in (("input_GEO", target, red), ("output_GEO", output, green)):
        sphere = cmds.polySphere(name=name, radius=MARKER)[0]
        cmds.parent(sphere, parent, relative=True)
        cmds.sets(sphere, edit=True, forceElement=group)
    camera, camera_shape = cmds.camera(name="torusCollisionCamera", focalLength=35)
    # 正面(+Z)のやや上から。輪が楕円に見え、左右の端(X=±4)で管の断面を入力が通る位置に固定する。
    cmds.viewPlace(camera_shape, eye=(0.0, 6.0, 30.0), lookAt=(0.0, 0.3, 0.0))
    window = cmds.window("torusCollisionValidationWindow", title="TorusCollision - soft torus collision",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("torusCollisionValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["torusCollisionHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"owner": owner, "output": output, "target": target, "torus": torus}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた式と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    x, y, softness, stage = pose(frame)
    owner = scene["owner"]
    owner.getPlug("softness").set(softness)
    point = om.MPoint(x, y, 0.0)
    cmds.setAttr(scene["target"] + ".translate", point.x, point.y, point.z)
    frameMatrix = om.MMatrix(cmds.getAttr(scene["torus"] + ".worldMatrix[0]"))
    c = om.MPoint(frameMatrix[12], frameMatrix[13], frameMatrix[14])
    localX = om.MVector(frameMatrix[0], frameMatrix[1], frameMatrix[2]).normal()
    n = om.MVector(frameMatrix[4], frameMatrix[5], frameMatrix[6]).normal()

    def ring(p):
        """位置の高さ・軸からの距離・芯の円上の最近点からの向きと距離を独立に求める。"""
        v = p - c
        height = v * n
        planar = v - n * height
        axisDistance = planar.length()
        closest = c + (planar.normal() if axisDistance > 1e-6 else localX) * MAJOR_RADIUS
        offset = p - closest
        return height, axisDistance, offset, offset.length()

    height, axisDistance, offset, length = ring(point)
    distance = length - MINOR_RADIUS
    if softness <= 1e-4:
        pushed = max(distance, 0.0)
    elif distance >= softness:
        pushed = distance
    else:
        pushed = softness * math.exp((distance - softness) / softness)
    expected = point + offset.normal() * (pushed - distance)
    actual = om.MMatrix(cmds.getAttr(scene["output"] + ".worldMatrix[0]"))
    position = om.MPoint(actual[12], actual[13], actual[14])
    error = (position - expected).length()
    out_height, out_axis, _offset, _length = ring(position)
    out_surface = math.hypot(out_axis - MAJOR_RADIUS, out_height) - MINOR_RADIUS
    dg_distance = cmds.getAttr(str(owner) + ".distance")
    dg_push = cmds.getAttr(str(owner) + ".push")
    dg_penetration = cmds.getAttr(str(owner) + ".penetration")
    dg_height = cmds.getAttr(str(owner) + ".height")
    dg_axis = cmds.getAttr(str(owner) + ".axisDistance")
    values[:] = [
        "GREEN = output   RED = input control   GRAY = ring: core R = {:.1f} cm, tube r = {:.1f} cm, axis n = local Y, fixed".format(
            MAJOR_RADIUS, MINOR_RADIUS),
        "STAGE: " + stage,
        "h = dot(p - c, n)   w = (p - c) - h n   q = c + R w / |w|  (|w| = 0: w = local X)   lengths in cm",
        "d = |p - q| - r   d' = d if d >= s, else s * exp((d - s) / s)  (s = 0: max(d, 0))   push = d' - d",
        "INPUT p = ({:5.2f}, {:5.2f})   |p - q| = {:5.3f}   softness s = {:4.2f}".format(x, y, length, softness),
        "OUTPUT height = {:6.3f}  axisDistance = {:5.3f}  d = {:6.3f}  push = {:6.3f}  penetration = {:5.3f}".format(
            dg_height, dg_axis, dg_distance, dg_push, dg_penetration),
        "OUTPUT distance from the torus surface = {:6.3f} cm (never below 0)".format(out_surface),
        "CHECK |output - formula| = {:.7f} cm".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (error < 1e-4 and abs(dg_distance - distance) < 1e-4 and abs(dg_height - height) < 1e-4
          and abs(dg_axis - axisDistance) < 1e-4 and out_surface > -1e-4
          and abs(dg_penetration - max(-distance, 0.0)) < 1e-4)
    return {"frame": frame, "presentation_stage": stage,
            "input": {"x": x, "y": y, "softness": softness},
            "height": dg_height, "axis_distance": dg_axis, "distance": dg_distance, "push": dg_push,
            "penetration": dg_penetration, "output_surface_distance": out_surface,
            "position_error": error, "ok": ok}


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
        folder = recordVideo("TorusCollision: 輪(トーラス)との柔らかい衝突", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "torus_collision.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-torus-collision.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("torus-collision-%Y%m%d-%H%M%S")
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
