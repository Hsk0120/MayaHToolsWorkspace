"""SphereCollisionの球との柔らかい衝突を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_sphere_collision.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RADIUS = 3.0
MARKER = 0.3
CENTER = (0.0, 3.0, 0.0)
SEGMENT = 30
# (中心から見た入力の向きの角度[deg、+Xから反時計回り], 中心からの入力の距離[cm], softness[cm], 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, 7.0, 1.0, "1 REST: FAR FROM THE SPHERE"),
    (0.0, 7.0, 1.0, "2 APPROACH THE SOFT BAND (L < r + softness = 4)"),
    (0.0, 3.5, 1.0, "3 INSIDE THE SPHERE: OUTPUT STAYS ON THE SURFACE"),
    (0.0, 1.5, 1.0, "4 DEEP INSIDE (near the center): OUTPUT APPROACHES r"),
    (0.0, 0.5, 1.0, "5 MOVE AROUND INSIDE: OUTPUT SLIDES ON THE SURFACE"),
    (150.0, 1.5, 1.0, "6 softness 1 -> 0: HARD STOP"),
    (150.0, 1.5, 0.0, "7 softness 0 -> 2.5 AND PULL OUT: WIDER BAND"),
    (150.0, 4.5, 2.5, "8 RETURN TO REST"),
    (0.0, 7.0, 1.0, "8 RETURN TO REST"),
    (0.0, 7.0, 1.0, "8 RETURN TO REST"),
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
    from mlrig.setups import SphereCollision
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    collider = cmds.createNode("transform", name="head_COLLIDER")
    cmds.setAttr(collider + ".translate", *CENTER)
    target = cmds.createNode("transform", name="hand_CTRL")
    cmds.setAttr(target + ".translate", CENTER[0] + 7.0, CENTER[1], CENTER[2])
    graph = SphereCollision.create(target, collider, name="sphereCollision", radius=RADIUS, softness=1.0)
    owner = graph.container
    output = cmds.createNode("transform", name="handOutput_GRP")
    owner.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    gray = _shader("colliderGray", (0.45, 0.45, 0.5), transparency=0.55)
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.35)
    green = _shader("outputGreen", (0.15, 0.8, 0.25))
    ball = cmds.polySphere(name="collider_GEO", radius=RADIUS, subdivisionsAxis=48, subdivisionsHeight=32)[0]
    cmds.parent(ball, collider, relative=True)
    cmds.sets(ball, edit=True, forceElement=gray)
    for name, parent, group in (("input_GEO", target, red), ("output_GEO", output, green)):
        sphere = cmds.polySphere(name=name, radius=MARKER)[0]
        cmds.parent(sphere, parent, relative=True)
        cmds.sets(sphere, edit=True, forceElement=group)
    camera, camera_shape = cmds.camera(name="sphereCollisionCamera", focalLength=35)
    # 正面(+Z)から。球と、右から近づいて中を回り込む入力が枠に収まる位置に固定する。
    cmds.viewPlace(camera_shape, eye=(1.5, 3.0, 30), lookAt=(1.5, 2.2, 0))
    window = cmds.window("sphereCollisionValidationWindow", title="SphereCollision - soft sphere collision",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("sphereCollisionValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["sphereCollisionHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"owner": owner, "output": output, "target": target, "collider": collider}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた式と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import PlaneCollision
    angle, length, softness, stage = pose(frame)
    owner = scene["owner"]
    owner.getPlug("softness").set(softness)
    center = om.MPoint(*CENTER)
    direction = om.MVector(math.cos(math.radians(angle)), math.sin(math.radians(angle)), 0.0)
    point = center + direction * length
    cmds.setAttr(scene["target"] + ".translate", point.x, point.y, point.z)
    distance = length - RADIUS
    pushed = PlaneCollision.response(distance, softness)
    expected = point + direction * (pushed - distance)
    actual = om.MMatrix(cmds.getAttr(scene["output"] + ".worldMatrix[0]"))
    position = om.MPoint(actual[12], actual[13], actual[14])
    error = (position - expected).length()
    out_length = (position - center).length()
    dg_distance = cmds.getAttr(str(owner) + ".distance")
    dg_push = cmds.getAttr(str(owner) + ".push")
    dg_penetration = cmds.getAttr(str(owner) + ".penetration")
    values[:] = [
        "GREEN = output   RED = input control   GRAY (transparent) = sphere collider (radius r = {:.1f} cm, fixed)".format(
            RADIUS),
        "STAGE: " + stage,
        "L = |p - c|   d = L - r   u = (p - c) / L   penetration = max(-d, 0)   lengths in cm",
        "d' = d if d >= s, else s * exp((d - s) / s)   (s = 0: max(d, 0))   push = d' - d   out = p + u * push",
        "INPUT angle = {:6.1f} deg   input L = {:5.2f} cm   softness s = {:4.2f} cm".format(angle, length, softness),
        "OUTPUT d = {:6.3f}  push = {:6.3f}  penetration = {:5.3f}  output L = {:6.3f} cm (never below r)".format(
            dg_distance, dg_push, dg_penetration, out_length),
        "CHECK |output - formula| = {:.7f} cm".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (error < 1e-4 and abs(dg_distance - distance) < 1e-4 and out_length > RADIUS - 1e-5
          and abs(dg_penetration - max(-distance, 0.0)) < 1e-4)
    return {"frame": frame, "presentation_stage": stage,
            "input": {"angle": angle, "length": length, "softness": softness},
            "distance": dg_distance, "push": dg_push, "penetration": dg_penetration, "output_length": out_length,
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
        folder = recordVideo("SphereCollision: 球との柔らかい衝突", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "sphere_collision.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-sphere-collision.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("sphere-collision-%Y%m%d-%H%M%S")
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
