"""CapsuleCollisionの先細りのカプセルとの柔らかい衝突を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_capsule_collision.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = (0.0, 8.0, 0.0)
END = (0.0, 0.0, 0.0)
START_RADIUS = 2.5
END_RADIUS = 1.5
MARKER = 0.3
SEGMENT = 30
# (入力のX[cm], 入力のY[cm], softness[cm], 次の姿勢へ向かう段階名)。軸は始点(上、Y=8)から終点(下、Y=0)。
POSES = [
    (7.0, 4.0, 1.0, "1 REST: FAR FROM THE CAPSULE"),
    (7.0, 4.0, 1.0, "2 APPROACH THE SIDE (t = 0.5, r = 2.0, band starts at 3.0)"),
    (2.6, 4.0, 1.0, "3 INSIDE THE CAPSULE: OUTPUT STAYS ON THE SURFACE"),
    (1.0, 4.0, 1.0, "4 DEEP INSIDE (near the axis): OUTPUT APPROACHES r(t)"),
    (0.2, 4.0, 1.0, "5 SLIDE DOWN INSIDE: OUTPUT FOLLOWS THE TAPERED RADIUS"),
    (0.6, 1.0, 1.0, "6 GO PAST THE END (t clamps to 1): ROUND THE END CAP"),
    (0.3, -0.8, 1.0, "7 softness 1 -> 0: HARD STOP"),
    (0.3, -0.8, 0.0, "8 ROUND THE END CAP TO THE OTHER SIDE (softness 0)"),
    (-0.6, -0.8, 0.0, "9 MOVE UP THE OTHER SIDE (softness 0)"),
    (-0.8, 6.5, 0.0, "10 softness 0 -> 1 AND PULL OUT TO A SAFE POSITION"),
    (-7.0, 6.5, 1.0, "11 BACK IN THE SAFE RANGE: OUTPUT = INPUT"),
    (-7.0, 6.5, 1.0, "11 BACK IN THE SAFE RANGE: OUTPUT = INPUT"),
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


def _capsuleGeometry(gray):
    """両端の球と、半径が両端で違う円柱(円錐台)で先細りのカプセルの形を作る。"""
    from maya import cmds
    height = START[1] - END[1]
    side = cmds.polyCylinder(name="colliderSide_GEO", radius=1.0, height=height, subdivisionsAxis=48,
                             subdivisionsHeight=1, subdivisionsCaps=0)[0]
    for index in range(cmds.polyEvaluate(side, vertex=True)):
        vertex = "{}.vtx[{}]".format(side, index)
        x, y, z = cmds.xform(vertex, query=True, objectSpace=True, translation=True)
        radius = START_RADIUS if y > 0 else END_RADIUS
        cmds.xform(vertex, objectSpace=True, translation=(x * radius, y, z * radius))
    cmds.setAttr(side + ".translate", 0.0, (START[1] + END[1]) * 0.5, 0.0)
    parts = [side]
    for name, center, radius in (("colliderStart_GEO", START, START_RADIUS), ("colliderEnd_GEO", END, END_RADIUS)):
        ball = cmds.polySphere(name=name, radius=radius, subdivisionsAxis=48, subdivisionsHeight=32)[0]
        cmds.setAttr(ball + ".translate", *center)
        parts.append(ball)
    for part in parts:
        cmds.sets(part, edit=True, forceElement=gray)


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import CapsuleCollision
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    start = cmds.createNode("transform", name="thigh_START")
    cmds.setAttr(start + ".translate", *START)
    end = cmds.createNode("transform", name="knee_END")
    cmds.setAttr(end + ".translate", *END)
    target = cmds.createNode("transform", name="skirt_CTRL")
    cmds.setAttr(target + ".translate", POSES[0][0], POSES[0][1], 0.0)
    graph = CapsuleCollision.create(target, start, end, name="capsuleCollision", startRadius=START_RADIUS,
                                    endRadius=END_RADIUS, softness=1.0)
    owner = graph.container
    output = cmds.createNode("transform", name="skirtOutput_GRP")
    owner.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    gray = _shader("colliderGray", (0.45, 0.45, 0.5), transparency=0.55)
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.35)
    green = _shader("outputGreen", (0.15, 0.8, 0.25))
    _capsuleGeometry(gray)
    for name, parent, group in (("input_GEO", target, red), ("output_GEO", output, green)):
        sphere = cmds.polySphere(name=name, radius=MARKER)[0]
        cmds.parent(sphere, parent, relative=True)
        cmds.sets(sphere, edit=True, forceElement=group)
    camera, camera_shape = cmds.camera(name="capsuleCollisionCamera", focalLength=35)
    # 正面(+Z)から。カプセルと、右から近づき中を下って端を回り左へ抜ける入力が枠に収まる位置に固定する。
    cmds.viewPlace(camera_shape, eye=(0.0, 3.4, 34), lookAt=(0.0, 3.4, 0))
    window = cmds.window("capsuleCollisionValidationWindow", title="CapsuleCollision - soft capsule collision",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("capsuleCollisionValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["capsuleCollisionHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"owner": owner, "output": output, "target": target}
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
    a, b = om.MPoint(*START), om.MPoint(*END)
    axis = b - a

    def surface(p):
        """位置の軸上の位置 t・最近点からの向き・距離・r(t)を独立に求める。"""
        t = min(max(((p - a) * axis) / (axis * axis), 0.0), 1.0)
        offset = p - (a + axis * t)
        return t, offset, offset.length(), START_RADIUS + (END_RADIUS - START_RADIUS) * t

    t, offset, length, radius = surface(point)
    distance = length - radius
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
    _out_t, _out_offset, out_length, out_radius = surface(position)
    out_surface = out_length - out_radius
    dg_parameter = cmds.getAttr(str(owner) + ".parameter")
    dg_distance = cmds.getAttr(str(owner) + ".distance")
    dg_push = cmds.getAttr(str(owner) + ".push")
    dg_penetration = cmds.getAttr(str(owner) + ".penetration")
    values[:] = [
        "GREEN = output   RED = input control   GRAY = capsule a (top, rA = {:.1f}) - b (bottom, rB = {:.1f}) cm, fixed".format(
            START_RADIUS, END_RADIUS),
        "STAGE: " + stage,
        "t = clamp(dot(p - a, b - a) / |b - a|^2, 0, 1)   q = a + t (b - a)   r(t) = rA + (rB - rA) t   lengths in cm",
        "d = |p - q| - r(t)   d' = d if d >= s, else s * exp((d - s) / s)  (s = 0: max(d, 0))   push = d' - d",
        "INPUT p = ({:5.2f}, {:5.2f})   |p - q| = {:5.2f}   softness s = {:4.2f}".format(x, y, length, softness),
        "OUTPUT t = {:5.3f}  r(t) = {:5.3f}  d = {:6.3f}  push = {:6.3f}  penetration = {:5.3f}".format(
            dg_parameter, radius, dg_distance, dg_push, dg_penetration),
        "OUTPUT distance from the surface = {:6.3f} cm (never below 0)".format(out_surface),
        "CHECK |output - formula| = {:.7f} cm".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (error < 1e-4 and abs(dg_distance - distance) < 1e-4 and abs(dg_parameter - t) < 1e-5
          and out_surface > -1e-4 and abs(dg_penetration - max(-distance, 0.0)) < 1e-4)
    return {"frame": frame, "presentation_stage": stage,
            "input": {"x": x, "y": y, "softness": softness},
            "parameter": dg_parameter, "radius": radius, "distance": dg_distance, "push": dg_push,
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
        folder = recordVideo("CapsuleCollision: 先細りのカプセルとの柔らかい衝突", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "capsule_collision.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-capsule-collision.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("capsule-collision-%Y%m%d-%H%M%S")
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
