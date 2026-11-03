"""CoilSpringの両端の間のコイルばね(伸縮・密着)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_coil_spring.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNT = 41
TURNS = 5.0
RADIUS = 1.5
WIRE = 0.4
SEGMENT = 30
# (入力の先端の高さ[cm], 次の姿勢へ向かう段階名)。根元は原点、ばねの軸はY。密着長 = 5 * 0.4 = 2 cm。
POSES = [
    (8.0, "1 REST: TOP CONTROL AT 8 cm"),
    (8.0, "2 STRETCH: ONLY THE PITCH GROWS, RADIUS AND WIRE STAY"),
    (13.0, "3 COMPRESS TOWARD THE SOLID LENGTH (2 cm)"),
    (2.0, "4 PUSH PAST THE SOLID LENGTH: SPRING STOPS, coilBind GROWS"),
    (0.6, "5 HOLD BEYOND THE LIMIT"),
    (0.6, "6 RELEASE BACK INTO THE SAFE RANGE"),
    (8.0, "7 BACK AT REST: coilBind = 0"),
    (8.0, "7 BACK AT REST: coilBind = 0"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    return POSES[index][0] + (POSES[index + 1][0] - POSES[index][0]) * weight, POSES[index][1]


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
    from mlrig.setups import CoilSpring
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    base = cmds.createNode("transform", name="seat_BASE")
    tip = cmds.createNode("transform", name="top_CTRL")
    cmds.setAttr(tip + ".translate", 0.0, POSES[0][0], 0.0)
    graph = CoilSpring.create(base, tip, name="coilSpring", count=COUNT, turns=TURNS, radius=RADIUS,
                              wireDiameter=WIRE, aimAxis="y", upAxis="x")
    owner = graph.container
    gray = _shader("seatGray", (0.45, 0.45, 0.5), transparency=0.3)
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.35)
    green = _shader("outputGreen", (0.15, 0.8, 0.25))
    seat = cmds.polyCylinder(name="seat_GEO", radius=RADIUS * 1.6, height=0.2)[0]
    cmds.setAttr(seat + ".translateY", -0.1)
    cmds.sets(seat, edit=True, forceElement=gray)
    marker = cmds.polyCylinder(name="input_GEO", radius=RADIUS * 1.6, height=0.12)[0]
    cmds.parent(marker, tip, relative=True)
    cmds.sets(marker, edit=True, forceElement=red)
    outputs = []
    for index in range(COUNT):
        point = cmds.createNode("transform", name="coil{}_OUT".format(index))
        owner.getPlug("matrix" + str(index)).connectTo(point + ".offsetParentMatrix")
        sphere = cmds.polySphere(name="coil{}_GEO".format(index), radius=WIRE * 0.5)[0]
        cmds.parent(sphere, point, relative=True)
        cmds.sets(sphere, edit=True, forceElement=green)
        outputs.append(point)
    # 最後の点の軸上(局所Xの-radius)に、ばねの上端の座面(緑)を置く。
    cap = cmds.polyCylinder(name="springTop_GEO", radius=RADIUS * 1.3, height=0.1)[0]
    cmds.parent(cap, outputs[-1], relative=True)
    cmds.setAttr(cap + ".translateX", -RADIUS)
    cmds.sets(cap, edit=True, forceElement=green)
    # 各点を結ぶ線(1次のNURBS曲線)。CVを各点のワールド位置へ接続する。
    curve = cmds.curve(name="coilLine_CRV", degree=1, point=[(0, 0, 0)] * COUNT)
    shape = cmds.listRelatives(curve, shapes=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideColor", 14)
    cmds.setAttr(shape + ".lineWidth", 3)
    for index, point in enumerate(outputs):
        decompose = cmds.createNode("decomposeMatrix", name="coil{}_DM".format(index))
        cmds.connectAttr(point + ".worldMatrix[0]", decompose + ".inputMatrix")
        cmds.connectAttr(decompose + ".outputTranslate", "{}.controlPoints[{}]".format(shape, index))
    camera, camera_shape = cmds.camera(name="coilSpringCamera", focalLength=35)
    # 正面(+Z)のやや上から。根元(Y=0)から最大の伸び(Y=13)まで入り、左のHUDと重ならないよう右寄せに固定する。
    cmds.viewPlace(camera_shape, eye=(-7.0, 10.0, 34.0), lookAt=(-7.0, 6.5, 0.0))
    window = cmds.window("coilSpringValidationWindow", title="CoilSpring - coil spring between two ends",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("coilSpringValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["coilSpringHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"owner": owner, "outputs": outputs, "tip": tip}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた式と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    height, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(scene["tip"] + ".translateY", height)
    length = height
    solid = TURNS * WIRE
    effective = max(length, solid)
    bind = effective - length
    pitch = effective / TURNS
    error = 0.0
    for index, point in enumerate(scene["outputs"]):
        ratio = index / (COUNT - 1)
        angle = math.radians(360.0 * TURNS * ratio)
        # 軸Y・巻き始めX: Y軸まわりの右ねじなので、XからY×X = -Zの向きへ回る。
        expected = om.MPoint(RADIUS * math.cos(angle), effective * ratio, -RADIUS * math.sin(angle))
        matrix = om.MMatrix(cmds.getAttr(point + ".worldMatrix[0]"))
        error = max(error, (om.MPoint(matrix[12], matrix[13], matrix[14]) - expected).length())
    dg = {attr: cmds.getAttr(owner + "." + attr)
          for attr in ("length", "solidLength", "effectiveLength", "pitch", "gap", "coilBind")}
    values[:] = [
        "GREEN = output coil   RED = input top control   GRAY = seat   turns N = {:.0f}, radius R = {:.1f} cm, wire d = {:.1f} cm, fixed".format(
            TURNS, RADIUS, WIRE),
        "STAGE: " + stage,
        "solid = N d   L' = max(L, solid)   pitch = L' / N   gap = pitch - d   coilBind = L' - L   (lengths in cm)",
        "point i (t = i / {}): angle = 360 N t deg around the axis, height = L' t, distance from the axis = R".format(COUNT - 1),
        "INPUT L = {:6.3f} cm   solid = {:5.3f} cm".format(length, solid),
        "OUTPUT L' = {:6.3f}  pitch = {:5.3f}  gap = {:6.3f}  coilBind = {:5.3f}  (DG L = {:6.3f})".format(
            dg["effectiveLength"], dg["pitch"], dg["gap"], dg["coilBind"], dg["length"]),
        "LIMIT: {}".format("COIL BIND - the coil cannot get shorter" if dg["coilBind"] > 1e-4 else "free"),
        "CHECK max |output point - formula| = {:.7f} cm".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (error < 1e-4 and abs(dg["effectiveLength"] - effective) < 1e-4 and abs(dg["coilBind"] - bind) < 1e-4
          and abs(dg["pitch"] - pitch) < 1e-4 and dg["gap"] > -1e-4 and abs(dg["length"] - length) < 1e-4)
    return {"frame": frame, "presentation_stage": stage, "input": {"length": length},
            "effective_length": dg["effectiveLength"], "pitch": dg["pitch"], "gap": dg["gap"],
            "coil_bind": dg["coilBind"], "position_error": error, "ok": ok}


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
        folder = recordVideo("CoilSpring: 両端の間のコイルばね", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "coil_spring.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-coil-spring.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("coil-spring-%Y%m%d-%H%M%S")
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
