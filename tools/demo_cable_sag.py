"""CableSagの2本の柱の間のケーブルの垂れを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_cable_sag.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 48
COUNT = 13
START = (-6.0, 6.0, 0.0)
# (右の留め具のX, Y, length[cm], 次の姿勢へ向かう段階名)。
POSES = [
    (6.0, 6.0, 13.2, "1 REST (length = 1.1 x span)"),
    (6.0, 6.0, 13.2, "2 MOVE THE RIGHT HOOK CLOSER"),
    (1.0, 6.0, 13.2, "3 RAISE THE RIGHT HOOK"),
    (1.0, 10.0, 13.2, "4 PULL IT FARTHER THAN THE LENGTH (TAUT)"),
    (9.0, 7.0, 13.2, "5 BACK TO REST, THEN length ATTR 13.2 -> 17 cm"),
    (6.0, 6.0, 13.2, "5 BACK TO REST, THEN length ATTR 13.2 -> 17 cm"),
    (6.0, 6.0, 17.0, "6 length BACK TO 13.2 cm"),
    (6.0, 6.0, 13.2, "7 HOLD"),
    (6.0, 6.0, 13.2, "7 HOLD"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:3], POSES[index + 1][:3])]
    return values[0], values[1], values[2], POSES[index][3]


def _shader(name, color):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _hud(prefix, count):
    """上段2行・下段の残りの行のHUDを作り、(値の列, HUD名)を返す。"""
    from maya import cmds
    values = [""] * count
    names = ["{}HUD{}".format(prefix, i) for i in range(count)]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (count - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return values, names


def _box(name, size, group, parent=None, translate=(0, 0, 0)):
    """単色の箱を作る。"""
    from maya import cmds
    box = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    if parent is not None:
        box = cmds.parent(box, parent, relative=True)[0]
    cmds.setAttr(box + ".translate", *translate)
    cmds.sets(box, edit=True, forceElement=group)
    return box


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import CableSag
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    green, gray = _shader("cableGreen", (0.15, 0.75, 0.25)), _shader("postGray", (0.55, 0.56, 0.6))
    blue = _shader("hookBlue", (0.25, 0.45, 0.85))
    hooks = []
    for name, position in (("hookLeft", START), ("hookRight", POSES[0][:2] + (0.0,))):
        hook = cmds.createNode("transform", name=name)
        cmds.setAttr(hook + ".translate", *position)
        ball = cmds.polySphere(name=name + "Geo", radius=0.45)[0]
        ball = cmds.parent(ball, hook, relative=True)[0]
        cmds.sets(ball, edit=True, forceElement=blue)
        post = _box(name + "Post", (0.5, 1.0, 0.5), gray, None, (position[0], position[1] / 2.0, 0.0))
        cmds.connectAttr(hook + ".translateX", post + ".translateX")
        cmds.connectAttr(hook + ".translateY", post + ".scaleY")
        mult = cmds.createNode("multiplyDivide", name=name + "Half")
        cmds.setAttr(mult + ".input2X", 0.5)
        cmds.connectAttr(hook + ".translateY", mult + ".input1X")
        cmds.connectAttr(mult + ".outputX", post + ".translateY")
        hooks.append(hook)
    graph = CableSag.create(hooks[0], hooks[1], COUNT, name="cableSag", length=POSES[0][2])
    owner = graph.container
    # 青 = 入力の留め具。緑 = CableSagの出力(点ごとの枠に沿った短い棒、X=ケーブルに沿う向き)。灰 = 柱。
    for index in range(COUNT):
        node = cmds.createNode("transform", name="cablePoint{}_GREEN".format(index))
        _box("cablePoint{}Geo".format(index), (1.0, 0.22, 0.22), green, node)
        _box("cablePoint{}Up".format(index), (0.08, 0.5, 0.08), green, node, (0, 0.25, 0))
        cmds.connectAttr("{}.matrix{}".format(owner, index), node + ".offsetParentMatrix")
    _box("ground", (30.0, 0.1, 6.0), gray, None, (0.0, -0.05, 0.0))
    camera, camera_shape = cmds.camera(name="cableSagCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(1.5, 3.0, 36.0), lookAt=(1.5, 3.0, 0))
    window = cmds.window("cableSagValidationWindow", title="CableSag - hanging cable", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("cableSagValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("cableSag", 7)
    scene = {"owner": owner, "hooks": hooks}
    return panel, scene, values, names


def _arc(points):
    """折れ線の長さ。"""
    return sum((points[i + 1] - points[i]).length() for i in range(len(points) - 1))


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、点の位置をPython版の式と比べ、枠と弧長を確かめた診断を返す。"""
    from maya import cmds
    import maya.api.OpenMaya as om
    from mlrig.setups import CableSag
    x, y, length, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(scene["hooks"][1] + ".translate", x, y, 0.0)
    cmds.setAttr(owner + ".length", length)
    expected = CableSag.points(START, (x, y, 0.0), length, COUNT)
    error = 0.0
    frame_error = 0.0
    for index in range(COUNT):
        matrix = om.MMatrix(cmds.getAttr("{}.matrix{}".format(owner, index)))
        point = om.MVector(matrix[12], matrix[13], matrix[14])
        error = max(error, (point - om.MVector(expected[index])).length())
        axis_x = om.MVector(matrix[0], matrix[1], matrix[2])
        axis_y = om.MVector(matrix[4], matrix[5], matrix[6])
        frame_error = max(frame_error, abs(axis_x * axis_y), abs(axis_x.length() - 1.0))
        if axis_y.y <= 0.0:
            frame_error = max(frame_error, 1.0)
    span = cmds.getAttr(owner + ".span")
    sag = cmds.getAttr(owner + ".sag")
    dense = CableSag.points(START, (x, y, 0.0), length, 401)
    arc = _arc([om.MVector(p) for p in dense])
    values[:] = [
        "BLUE = hooks (input, right hook moves)   GREEN = CableSag output points (bar = X along the cable, stick = Y)",
        "STAGE: " + stage,
        "fixed: left hook = (-6, 6, 0) cm   gravity = -Y   13 points, u = i / 12",
        "sag h = sqrt(max((L - D)(2L + D) / 8, 0))   P(u) = A + C u + n h 4u(1 - u)   (n = gravity across the chord)",
        "INPUT right hook = ({:5.2f}, {:5.2f}) cm   length L = {:6.2f} cm".format(x, y, length),
        "OUTPUT span D = {:6.3f} cm   sag h = {:6.3f} cm   arc of the drawn parabola / L = {:6.4f}".format(
            span, sag, arc / length),
        "CHECK max |point - formula| = {:.7f} cm   frame error = {:.7f}".format(error, frame_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and frame_error < 1e-5 and (span >= length or arc <= length + 1e-6)
    return {"frame": frame, "presentation_stage": stage, "input": {"x": x, "y": y, "length": length},
            "position_error": error, "frame_error": frame_error, "span": span, "sag": sag, "arc_ratio": arc / length,
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
        folder = recordVideo("CableSag: ケーブルの垂れ", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "cable_sag.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-cable-sag.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("cable-sag-%Y%m%d-%H%M%S")
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
