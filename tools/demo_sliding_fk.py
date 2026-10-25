"""SlidingFkの位置をずらせるFKを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_sliding_fk.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 36
COUNT = 8
LENGTH = 1.5
# (ctrl Aのrotate Z, position0, falloff0, ctrl Bのrotate Z, position1, falloff1, 次の姿勢へ向かう段階名)
POSES = [
    (0, 0.2, 0.25, 0, 0.8, 0.25, "1 REST"),
    (0, 0.2, 0.25, 0, 0.8, 0.25, "2 ROTATE CONTROL A (rotateZ 0 -> 60)"),
    (60, 0.2, 0.25, 0, 0.8, 0.25, "3 SLIDE A ALONG THE CHAIN (position0 0.2 -> 0.75)"),
    (60, 0.75, 0.25, 0, 0.8, 0.25, "4 WIDEN A (falloff0 0.25 -> 0.7)"),
    (60, 0.75, 0.7, 0, 0.8, 0.25, "5 ROTATE CONTROL B (rotateZ 0 -> -45, position1 0.8 -> 0.3)"),
    (60, 0.75, 0.7, -45, 0.3, 0.25, "6 RETURN TO REST"),
    (0, 0.2, 0.25, 0, 0.8, 0.25, "6 RETURN TO REST"),
]
FRAMES = SEGMENT * (len(POSES) - 1) + 24


def pose(frame):
    """フレームの値をsmoothstepで補間し、(値の列, 段階名)を返す。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:6], POSES[index + 1][:6])]
    return values, POSES[index][6]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _segment(name, parent, group, thickness, front=0.0):
    """parentの+Xへ節の長さの直方体を置く。frontだけ+Z(カメラ側)へずらす。"""
    from maya import cmds
    cube = cmds.polyCube(name=name, width=LENGTH * 0.92, height=thickness, depth=thickness)[0]
    cmds.parent(cube, parent, relative=True)
    cmds.setAttr(cube + ".translateX", LENGTH / 2)
    cmds.setAttr(cube + ".translateZ", front)
    cmds.sets(cube, edit=True, forceElement=group)


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import SlidingFk
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    gray = _shader("inputGray", (0.6, 0.6, 0.65), 0.6)
    joints, parent = [], None
    for index in range(COUNT):
        node = cmds.createNode("transform", name="tail{}".format(index), parent=parent)
        cmds.setAttr(node + ".translateX", LENGTH if index else 0.0)
        if index < COUNT - 1:
            _segment("tailGeo" + str(index), node, gray, 0.3, -0.4)
        joints.append(cmds.ls(node, long=True)[0])
        parent = node
    controls = [cmds.createNode("transform", name="ctrl" + role) for role in "AB"]
    graph = SlidingFk.create(joints, controls, name="slidingFk", positions=(0.2, 0.8), falloff=0.25)
    owner = graph.container
    green = _shader("outputGreen", (0.15, 0.8, 0.25))
    outputs = []
    for index in range(COUNT):
        node = cmds.createNode("transform", name="out{}".format(index))
        owner.getPlug("matrix" + str(index)).connectTo(node + ".offsetParentMatrix")
        if index < COUNT - 1:
            _segment("outGeo" + str(index), node, green, 0.5)
        outputs.append(node)
    markers = []
    for role, color in (("A", (0.95, 0.8, 0.1)), ("B", (0.95, 0.45, 0.1))):
        marker = cmds.polyCone(name="marker" + role, radius=0.35, height=0.8)[0]
        cmds.setAttr(marker + ".rotateZ", 180)
        cmds.sets(marker, edit=True, forceElement=_shader("marker" + role + "Color", color))
        markers.append(marker)
    camera, camera_shape = cmds.camera(name="slidingFkCamera", focalLength=35)
    # 横(+Z)から。尻尾の根元を左に置き、上下に曲がる範囲が枠に収まる位置に固定する。
    cmds.viewPlace(camera_shape, eye=(5.5, 0.0, 28), lookAt=(5.5, 0.0, 0))
    window = cmds.window("slidingFkValidationWindow", title="SlidingFk - sliding FK controls",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("slidingFkValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["slidingFkHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    params = SlidingFk.parameters([(LENGTH * i, 0, 0) for i in range(COUNT)])
    scene = {"owner": owner, "controls": controls, "outputs": outputs, "markers": markers, "params": params}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた三角形の重み・回転の積と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    (rot0, pos0, fall0, rot1, pos1, fall1), stage = pose(frame)
    owner, params = scene["owner"], scene["params"]
    for index, (rotate, position, falloff) in enumerate(((rot0, pos0, fall0), (rot1, pos1, fall1))):
        cmds.setAttr(scene["controls"][index] + ".rotateZ", rotate)
        owner.getPlug("position" + str(index)).set(position)
        owner.getPlug("falloff" + str(index)).set(falloff)
        # 目印は、入力のチェーン上の位置の少し上に置く(コントロールの位置を示すだけで、計算には使わない)。
        cmds.setAttr(scene["markers"][index] + ".translate", position * LENGTH * (COUNT - 1), 1.2, 0)
    weights = []
    for center, falloff in ((pos0, fall0), (pos1, fall1)):
        triangles = [min(max(1 - abs(t - center) / falloff, 0.0), 1.0) for t in params[:-1]]
        total = sum(triangles)
        weights.append([value / total if total > 1e-6 else 0.0 for value in triangles])
    # 同じZ軸の回転なので、節ごとの回転角は rotA*wA + rotB*wB(独立計算)。
    expected, previous = [], om.MMatrix()
    for j in range(COUNT):
        angle = math.radians(rot0 * weights[0][j] + rot1 * weights[1][j]) if j < COUNT - 1 else 0.0
        local = om.MTransformationMatrix()
        local.setTranslation(om.MVector(LENGTH if j else 0.0, 0, 0), om.MSpace.kTransform)
        previous = om.MEulerRotation(0, 0, angle).asMatrix() * local.asMatrix() * previous
        expected.append(previous)
    actual = [om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]")) for node in scene["outputs"]]
    error = max(abs(a - b) for x, y in zip(actual, expected) for a, b in zip(x, y))
    bend = math.degrees(math.atan2(actual[-1][13] - actual[-2][13], actual[-1][12] - actual[-2][12]))
    expectedBend = rot0 * sum(weights[0]) + rot1 * sum(weights[1])
    values[:] = [
        "GREEN = output   GRAY = input chain   YELLOW = control A position   ORANGE = control B position",
        "STAGE: " + stage,
        "t_j = arc length ratio of joint j (fixed)   tri = clamp(1 - |t_j - position| / falloff, 0, 1)",
        "w_j = tri_j / sum(tri)   R_j = slerp(I, Q_A, wA_j) * slerp(I, Q_B, wB_j)   out_j = R_j * rest_j * out_(j-1)",
        "INPUT A: rotZ {:6.1f} deg  position {:.3f}  falloff {:.3f}   B: rotZ {:6.1f} deg  position {:.3f}  falloff {:.3f}".format(
            rot0, pos0, fall0, rot1, pos1, fall1),
        "OUTPUT weight A per joint = [" + " ".join("{:.2f}".format(w) for w in weights[0])
        + "]   tip bend = {:.2f} deg".format(bend),
        "CHECK |output - independent| = {:.7f}   |tip bend - (rotA + rotB)| = {:.5f} deg".format(
            error, abs(bend - expectedBend)),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    return {"frame": frame, "presentation_stage": stage, "values": [rot0, pos0, fall0, rot1, pos1, fall1],
            "weights": weights, "matrix_error": error, "bend": bend, "expected_bend": expectedBend,
            "ok": error < 1e-4 and abs(bend - expectedBend) < 1e-3}


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
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("SlidingFk: 位置をずらせるFK", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "sliding_fk.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-sliding-fk.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("sliding-fk-%Y%m%d-%H%M%S")
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
