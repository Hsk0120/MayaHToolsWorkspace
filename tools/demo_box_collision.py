"""BoxCollisionの箱との柔らかい衝突を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_box_collision.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CENTER = (0.0, 3.0, 0.0)
TILT = 15.0
SIZE = (10.0, 4.0, 4.0)
ROUNDING = 0.5
MARKER = 0.3
SEGMENT = 30
# (入力の箱の局所X[cm], 局所Y[cm], softness[cm], 次の姿勢へ向かう段階名)。入力は局所Z = 0 の面の上を動く。
# 内側の箱の半分の長さは e = (4.5, 1.5, 1.5) で、上の面は y = 2、右の面は x = 5。
POSES = [
    (0.0, 6.0, 1.0, "1 REST: FAR ABOVE THE BOX"),
    (0.0, 6.0, 1.0, "2 LOWER ONTO THE TOP FACE (top at y = 2, band starts at 3)"),
    (0.0, 1.0, 1.0, "3 INSIDE THE BOX: OUTPUT STAYS ABOVE THE TOP FACE"),
    (0.0, 0.3, 1.0, "4 DEEP INSIDE: OUTPUT APPROACHES THE TOP FACE"),
    (3.5, 1.0, 1.0, "5 SLIDE ALONG THE TOP INSIDE: PUSHED STRAIGHT UP, NO SIDEWAYS SLIDE"),
    (6.5, 3.0, 1.0, "6 OUT PAST THE ROUNDED EDGE: NORMAL TURNS AROUND THE CORNER"),
    (4.5, 0.0, 1.0, "7 INTO THE RIGHT FACE: PUSHED TO +X"),
    (4.5, 0.0, 1.0, "8 softness 1 -> 0: HARD STOP ON THE FACE"),
    (4.0, 0.0, 0.0, "9 softness 0 -> 1 AND PULL OUT TO THE RIGHT"),
    (8.0, 0.0, 1.0, "10 RETURN TO THE SAFE POSITION"),
    (0.0, 6.0, 1.0, "11 BACK IN THE SAFE RANGE: OUTPUT = INPUT"),
    (0.0, 6.0, 1.0, "11 BACK IN THE SAFE RANGE: OUTPUT = INPUT"),
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
    from mlrig.setups import BoxCollision
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    table = cmds.createNode("transform", name="table_CENTER")
    cmds.setAttr(table + ".translate", *CENTER)
    cmds.setAttr(table + ".rotateZ", TILT)
    target = cmds.createNode("transform", name="hand_CTRL")
    cmds.setAttr(target + ".translate", *_world((POSES[0][0], POSES[0][1], 0.0)))
    graph = BoxCollision.create(target, table, name="boxCollision", sizeX=SIZE[0], sizeY=SIZE[1], sizeZ=SIZE[2],
                                rounding=ROUNDING, softness=1.0)
    owner = graph.container
    output = cmds.createNode("transform", name="handOutput_GRP")
    owner.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    gray = _shader("colliderGray", (0.45, 0.45, 0.5), transparency=0.55)
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.35)
    green = _shader("outputGreen", (0.15, 0.8, 0.25))
    collider = cmds.polyCube(name="collider_GEO", width=SIZE[0], height=SIZE[1], depth=SIZE[2])[0]
    # 角の丸めは表示だけの近似(判定はDGの式で行う)。
    cmds.polyBevel3(collider, offset=ROUNDING, offsetAsFraction=False, segments=6, chamfer=True)
    cmds.parent(collider, table, relative=True)
    cmds.sets(collider, edit=True, forceElement=gray)
    for name, parent, group in (("input_GEO", target, red), ("output_GEO", output, green)):
        sphere = cmds.polySphere(name=name, radius=MARKER)[0]
        cmds.parent(sphere, parent, relative=True)
        cmds.sets(sphere, edit=True, forceElement=group)
    camera, camera_shape = cmds.camera(name="boxCollisionCamera", focalLength=35)
    # 正面(+Z)から。箱と、上から押し込み縁を回って右へ抜ける入力が枠に収まる位置に固定する。
    cmds.viewPlace(camera_shape, eye=(1.5, 4.0, 34), lookAt=(1.5, 4.0, 0))
    window = cmds.window("boxCollisionValidationWindow", title="BoxCollision - soft box collision",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("boxCollisionValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["boxCollisionHUD{}".format(i) for i in range(len(values))]
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


def _world(local):
    """箱の局所の位置をワールドへ(Z軸まわりにTILT度回して中心を足す)。"""
    angle = math.radians(TILT)
    return (CENTER[0] + local[0] * math.cos(angle) - local[1] * math.sin(angle),
            CENTER[1] + local[0] * math.sin(angle) + local[1] * math.cos(angle), CENTER[2] + local[2])


def _rotate(vector, degrees):
    """ベクトルをZ軸まわりに回す。"""
    angle = math.radians(degrees)
    return (vector[0] * math.cos(angle) - vector[1] * math.sin(angle),
            vector[0] * math.sin(angle) + vector[1] * math.cos(angle), vector[2])


def _local(position):
    """ワールドの位置を箱の局所へ戻す。"""
    return _rotate([a - c for a, c in zip(position, CENTER)], -TILT)


def _sdf(local):
    """角を丸めた箱の符号付き距離と局所の法線(BoxCollisionとは別に書いた検証用)。"""
    half = [size / 2.0 - ROUNDING for size in SIZE]
    outside = [value - min(max(value, -limit), limit) for value, limit in zip(local, half)]
    length = math.sqrt(sum(value * value for value in outside))
    if length > 1e-6:
        return length - ROUNDING, [value / length for value in outside]
    depth = [abs(value) - limit for value, limit in zip(local, half)]
    axis = max(range(3), key=lambda index: (depth[index], -index))
    normal = [0.0, 0.0, 0.0]
    normal[axis] = 1.0 if local[axis] >= 0.0 else -1.0
    return depth[axis] - ROUNDING, normal


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた式と比較した診断を返す。"""
    from maya import cmds
    x, y, softness, stage = pose(frame)
    owner = scene["owner"]
    owner.getPlug("softness").set(softness)
    cmds.setAttr(scene["target"] + ".translate", *_world((x, y, 0.0)))
    distance, normal = _sdf((x, y, 0.0))
    if softness <= 1e-4:
        pushed = max(distance, 0.0)
    elif distance >= softness:
        pushed = distance
    else:
        pushed = softness * math.exp((distance - softness) / softness)
    push = pushed - distance
    expected = _world([a + n * push for a, n in zip((x, y, 0.0), normal)])
    position = cmds.getAttr(scene["output"] + ".worldMatrix[0]")[12:15]
    error = math.sqrt(sum((a - b) ** 2 for a, b in zip(position, expected)))
    out_distance = _sdf(_local(position))[0]
    dg_distance = cmds.getAttr(str(owner) + ".distance")
    dg_push = cmds.getAttr(str(owner) + ".push")
    dg_penetration = cmds.getAttr(str(owner) + ".penetration")
    dg_normal = _rotate(cmds.getAttr(str(owner) + ".normal")[0], -TILT)
    values[:] = [
        "GREEN = output   RED = input control   GRAY = box {:.0f} x {:.0f} x {:.0f} cm, rounding r = {:.1f} cm, tilted {:.0f} deg (fixed)".format(
            SIZE[0], SIZE[1], SIZE[2], ROUNDING, TILT),
        "STAGE: " + stage,
        "l = p - c in box space   e = size/2 - r   k = clamp(l, -e, e)   outside: d = |l - k| - r,  n = (l - k) / |l - k|",
        "inside: d = max(|l| - e) - r, n = that face   d' = d if d >= s, else s*exp((d - s)/s) (s = 0: max(d, 0))   push = d' - d",
        "INPUT l = ({:5.2f}, {:5.2f}) cm   softness s = {:4.2f} cm".format(x, y, softness),
        "OUTPUT d = {:6.3f}  push = {:6.3f}  penetration = {:5.3f}  normal (box space) = ({:5.2f}, {:5.2f})".format(
            dg_distance, dg_push, dg_penetration, dg_normal[0], dg_normal[1]),
        "OUTPUT distance to the surface = {:6.4f} cm (never below 0)".format(out_distance),
        "CHECK |output - formula| = {:.7f} cm".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (error < 1e-4 and abs(dg_distance - distance) < 1e-4 and out_distance > -1e-5
          and abs(dg_penetration - max(-distance, 0.0)) < 1e-4
          and all(abs(a - b) < 1e-4 for a, b in zip(dg_normal, normal)))
    return {"frame": frame, "presentation_stage": stage,
            "input": {"local_x": x, "local_y": y, "softness": softness},
            "distance": dg_distance, "push": dg_push, "penetration": dg_penetration,
            "normal_local": list(dg_normal), "output_surface_distance": out_distance,
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
        folder = recordVideo("BoxCollision: 箱との柔らかい衝突", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "box_collision.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-box-collision.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("box-collision-%Y%m%d-%H%M%S")
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
