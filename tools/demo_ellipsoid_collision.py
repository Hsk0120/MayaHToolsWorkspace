"""EllipsoidCollisionの楕円体との柔らかい衝突を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_ellipsoid_collision.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CENTER = (0.0, 4.0, 0.0)
TILT = 20.0
RADII = (5.0, 3.0, 2.0)
MARKER = 0.3
SEGMENT = 30
# (入力の中心からの向き[度、+Xから反時計回り], 中心からの距離[cm], softness[cm], 次の姿勢へ向かう段階名)。
# 楕円体はZ軸まわりに20度傾けてあるので、20度が長い軸(局所X、R=5)、110度が短い軸(局所Y、R=3)の向き。
POSES = [
    (20.0, 9.0, 1.0, "1 REST: FAR FROM THE ELLIPSOID"),
    (20.0, 9.0, 1.0, "2 APPROACH ALONG THE LONG AXIS (R = 5.0, band starts at 6.0)"),
    (20.0, 4.0, 1.0, "3 INSIDE THE ELLIPSOID: OUTPUT STAYS ON THE SURFACE"),
    (20.0, 1.0, 1.0, "4 DEEP INSIDE (near the center): OUTPUT APPROACHES R"),
    (110.0, 1.0, 1.0, "5 SWING INSIDE TO THE SHORT AXIS: R 5.0 -> 3.0, OUTPUT FOLLOWS THE SURFACE"),
    (110.0, 1.0, 1.0, "6 softness 1 -> 0: HARD STOP"),
    (110.0, 1.0, 0.0, "7 SWING ON THROUGH THE DIAGONAL (softness 0)"),
    (200.0, 1.5, 0.0, "8 softness 0 -> 1 AND PULL OUT TO A SAFE POSITION"),
    (200.0, 9.0, 1.0, "9 BACK IN THE SAFE RANGE: OUTPUT = INPUT"),
    (200.0, 9.0, 1.0, "9 BACK IN THE SAFE RANGE: OUTPUT = INPUT"),
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
    from mlrig.setups import EllipsoidCollision
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    chest = cmds.createNode("transform", name="chest_CENTER")
    cmds.setAttr(chest + ".translate", *CENTER)
    cmds.setAttr(chest + ".rotateZ", TILT)
    target = cmds.createNode("transform", name="hand_CTRL")
    angle = math.radians(POSES[0][0])
    cmds.setAttr(target + ".translate", CENTER[0] + POSES[0][1] * math.cos(angle),
                 CENTER[1] + POSES[0][1] * math.sin(angle), 0.0)
    graph = EllipsoidCollision.create(target, chest, name="ellipsoidCollision", radiusX=RADII[0],
                                      radiusY=RADII[1], radiusZ=RADII[2], softness=1.0)
    owner = graph.container
    output = cmds.createNode("transform", name="handOutput_GRP")
    owner.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    gray = _shader("colliderGray", (0.45, 0.45, 0.5), transparency=0.55)
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.35)
    green = _shader("outputGreen", (0.15, 0.8, 0.25))
    collider = cmds.polySphere(name="collider_GEO", radius=1.0, subdivisionsAxis=64, subdivisionsHeight=48)[0]
    cmds.parent(collider, chest, relative=True)
    cmds.setAttr(collider + ".scale", *RADII)
    cmds.sets(collider, edit=True, forceElement=gray)
    for name, parent, group in (("input_GEO", target, red), ("output_GEO", output, green)):
        sphere = cmds.polySphere(name=name, radius=MARKER)[0]
        cmds.parent(sphere, parent, relative=True)
        cmds.sets(sphere, edit=True, forceElement=group)
    camera, camera_shape = cmds.camera(name="ellipsoidCollisionCamera", focalLength=35)
    # 正面(+Z)から。楕円体と、右上から近づき中で回り込んで左下へ抜ける入力が枠に収まる位置に固定する。
    cmds.viewPlace(camera_shape, eye=(0.0, 4.0, 36), lookAt=(0.0, 4.0, 0))
    window = cmds.window("ellipsoidCollisionValidationWindow", title="EllipsoidCollision - soft ellipsoid collision",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("ellipsoidCollisionValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["ellipsoidCollisionHUD{}".format(i) for i in range(len(values))]
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


def _local(vector):
    """ワールドのベクトルを、楕円体の局所(Z軸まわりに-TILT度回す)へ戻す。"""
    angle = math.radians(-TILT)
    return (vector[0] * math.cos(angle) - vector[1] * math.sin(angle),
            vector[0] * math.sin(angle) + vector[1] * math.cos(angle), vector[2])


def _normalized(position):
    """位置を楕円体の局所で各軸の半径で割った長さ(1で表面)。"""
    local = _local([a - c for a, c in zip(position, CENTER)])
    return math.sqrt(sum((value / radius) ** 2 for value, radius in zip(local, RADII)))


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた式と比較した診断を返す。"""
    from maya import cmds
    angle, length, softness, stage = pose(frame)
    owner = scene["owner"]
    owner.getPlug("softness").set(softness)
    unit = (math.cos(math.radians(angle)), math.sin(math.radians(angle)), 0.0)
    point = [c + u * length for c, u in zip(CENTER, unit)]
    cmds.setAttr(scene["target"] + ".translate", *point)
    local = _local(unit)
    radius = 1.0 / math.sqrt(sum((value / r) ** 2 for value, r in zip(local, RADII)))
    distance = length - radius
    if softness <= 1e-4:
        pushed = max(distance, 0.0)
    elif distance >= softness:
        pushed = distance
    else:
        pushed = softness * math.exp((distance - softness) / softness)
    expected = [c + u * (radius + pushed) for c, u in zip(CENTER, unit)]
    position = cmds.getAttr(scene["output"] + ".worldMatrix[0]")[12:15]
    error = math.sqrt(sum((a - b) ** 2 for a, b in zip(position, expected)))
    out_normalized = _normalized(position)
    dg_radius = cmds.getAttr(str(owner) + ".directionRadius")
    dg_distance = cmds.getAttr(str(owner) + ".distance")
    dg_push = cmds.getAttr(str(owner) + ".push")
    dg_penetration = cmds.getAttr(str(owner) + ".penetration")
    values[:] = [
        "GREEN = output   RED = input control   GRAY = ellipsoid rx = {:.0f}  ry = {:.0f}  rz = {:.0f} cm, tilted {:.0f} deg (fixed)".format(
            RADII[0], RADII[1], RADII[2], TILT),
        "STAGE: " + stage,
        "u = (p - c) / |p - c|   l = u in ellipsoid space   R = 1 / sqrt((lx/rx)^2 + (ly/ry)^2 + (lz/rz)^2)   cm",
        "d = |p - c| - R   d' = d if d >= s, else s * exp((d - s) / s)  (s = 0: max(d, 0))   push = d' - d",
        "INPUT direction = {:6.1f} deg   |p - c| = {:5.2f} cm   softness s = {:4.2f} cm".format(angle, length, softness),
        "OUTPUT R = {:5.3f}  d = {:6.3f}  push = {:6.3f}  penetration = {:5.3f}".format(
            dg_radius, dg_distance, dg_push, dg_penetration),
        "OUTPUT normalized radius |l_out / r| = {:6.4f} (1 = surface, never below 1)".format(out_normalized),
        "CHECK |output - formula| = {:.7f} cm".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (error < 1e-4 and abs(dg_distance - distance) < 1e-4 and abs(dg_radius - radius) < 1e-4
          and out_normalized > 1.0 - 1e-5 and abs(dg_penetration - max(-distance, 0.0)) < 1e-4)
    return {"frame": frame, "presentation_stage": stage,
            "input": {"angle": angle, "length": length, "softness": softness},
            "direction_radius": dg_radius, "distance": dg_distance, "push": dg_push,
            "penetration": dg_penetration, "output_normalized_radius": out_normalized,
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
        folder = recordVideo("EllipsoidCollision: 楕円体との柔らかい衝突", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "ellipsoid_collision.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-ellipsoid-collision.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("ellipsoid-collision-%Y%m%d-%H%M%S")
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
