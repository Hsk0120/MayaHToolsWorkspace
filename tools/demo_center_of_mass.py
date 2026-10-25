"""CenterOfMassの全身の重心と床への投影を、棒人間の姿勢を変えながら専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_center_of_mass.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 36
NAME = "com"
#: サンプルの体節の並び(:meth:`mlrig.setupSamples.SetupSamples._centerOfMass` と同じ順)。
ROLES = [("pelvis", "chest"), ("chest", "head")] + [
    pair for side in "LR" for pair in (
        ("shoulder" + side, "elbow" + side), ("elbow" + side, "wrist" + side), ("wrist" + side, "hand" + side),
        ("hip" + side, "knee" + side), ("knee" + side, "ankle" + side), ("ankle" + side, "toe" + side))]
#: 手の体節の番号。
HANDS = (4, 10)
# ((背骨rx, 左肩ry, 右肩ry, 左股rx, 左膝rx, 手の質量の倍率), 次の姿勢へ向かう段階名)。
POSES = [
    ((0.0, 0.0, 0.0, 0.0, 0.0, 1.0), "1 REST (T pose)"),
    ((0.0, 0.0, 0.0, 0.0, 0.0, 1.0), "2 LEAN FORWARD (spine rx 0 -> 40)"),
    ((40.0, 0.0, 0.0, 0.0, 0.0, 1.0), "3 ARMS FORWARD (shoulders ry -80 / 80)"),
    ((40.0, -80.0, 80.0, 0.0, 0.0, 1.0), "4 LEAN BACK + LIFT LEFT LEG (spine -25, hip -70, knee 80)"),
    ((-25.0, -80.0, 80.0, -70.0, 80.0, 1.0), "5 HEAVY WEIGHTS IN THE HANDS (hand mass x 15)"),
    ((-25.0, -80.0, 80.0, -70.0, 80.0, 15.0), "6 RETURN TO REST"),
    ((0.0, 0.0, 0.0, 0.0, 0.0, 1.0), "6 RETURN TO REST"),
    ((0.0, 0.0, 0.0, 0.0, 0.0, 1.0), "6 RETURN TO REST"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    smooth = weight * weight * (3 - 2 * weight)
    start, end = POSES[index][0], POSES[index + 1][0]
    return [a + (b - a) * smooth for a, b in zip(start, end)], POSES[index][1]


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


def _position(node):
    """ノードのワールド位置を om2.MVector で返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    return om2.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))


def _translation(owner, attribute):
    """行列のアトリビュートの位置を om2.MVector で返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    matrix = om2.MMatrix(cmds.getAttr(owner + "." + attribute))
    return om2.MVector(matrix[12], matrix[13], matrix[14])


def _place(name, plug, shading, kind, offset):
    """行列のplugを offsetParentMatrix で受ける表示用の形を作る。"""
    from maya import cmds
    if kind == "sphere":
        shape = cmds.polySphere(name=name, radius=0.55)[0]
    else:
        shape = cmds.polyCylinder(name=name, radius=kind, height=0.08)[0]
    cmds.connectAttr(plug, shape + ".offsetParentMatrix")
    cmds.setAttr(shape + ".translateY", offset)
    cmds.sets(shape, edit=True, forceElement=shading)
    return shape


def buildScene():
    """メニューと同じサンプルで検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setupSamples import SetupSamples
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    sample = SetupSamples.build("centerOfMass", name=NAME)
    owner = sample.container
    for joint in cmds.listRelatives(sample.root, allDescendents=True, type="joint", fullPath=True) or []:
        cmds.setAttr(joint + ".radius", 0.35)
    _place("com_GEO", owner + ".centerMatrix", _shader("comGreen", (0.15, 0.85, 0.25)), "sphere", 0.0)
    _place("comFloor_GEO", owner + ".groundMatrix", _shader("floorOrange", (0.95, 0.55, 0.1)), 0.6, 0.06)
    _place("support_GEO", owner + ".supportMatrix", _shader("supportBlue", (0.2, 0.45, 0.95)), 0.35, 0.1)
    floor = cmds.polyPlane(name="floor_GEO", width=16, height=16, subdivisionsX=8, subdivisionsY=8)[0]
    cmds.sets(floor, edit=True, forceElement=_shader("floorGray", (0.5, 0.5, 0.5)))
    # 重心から床の点への縦線(表示用)。
    line = cmds.curve(name="comLine", degree=1, point=[(0, 0, 0), (0, 1, 0)])
    line_shape = cmds.listRelatives(line, shapes=True)[0]
    for index, attribute in enumerate(("centerMatrix", "groundMatrix")):
        decompose = cmds.createNode("decomposeMatrix", name="comLine{}_dcm".format(index))
        cmds.connectAttr(owner + "." + attribute, decompose + ".inputMatrix")
        cmds.connectAttr(decompose + ".outputTranslate", "{}.controlPoints[{}]".format(line_shape, index))
    cmds.setAttr(line + ".overrideEnabled", True)
    cmds.setAttr(line + ".overrideColor", 17)
    camera, camera_shape = cmds.camera(name="comCamera", focalLength=40)
    cmds.viewPlace(camera_shape, eye=(34, 14, 26), lookAt=(0, 8.6, 1.0), up=(0, 1, 0))
    window = cmds.window("comValidationWindow", title="CenterOfMass - stick figure balance", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("comValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=True, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=True, wireframeOnShaded=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("com", 7)
    scene = {"owner": owner,
             "base_hand": {index: cmds.getAttr("{}.mass{}".format(owner, index)) for index in HANDS}}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """姿勢と手の質量を動かし、重心・床の点・balance を各jointの位置から独立に求めた値と比べる。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    (spine, shoulder_l, shoulder_r, hip_l, knee_l, hand), stage_name = pose(frame)
    owner = scene["owner"]
    cmds.setAttr(NAME + "_spine.rotateX", spine)
    cmds.setAttr(NAME + "_shoulderL.rotateY", shoulder_l)
    cmds.setAttr(NAME + "_shoulderR.rotateY", shoulder_r)
    cmds.setAttr(NAME + "_hipL.rotateX", hip_l)
    cmds.setAttr(NAME + "_kneeL.rotateX", knee_l)
    for index, base in scene["base_hand"].items():
        cmds.setAttr("{}.mass{}".format(owner, index), base * hand)
    center, total = om2.MVector(), 0.0
    for index, (start, end) in enumerate(ROLES):
        mass = cmds.getAttr("{}.mass{}".format(owner, index))
        ratio = cmds.getAttr("{}.ratio{}".format(owner, index))
        point = _position(NAME + "_" + start) * (1.0 - ratio) + _position(NAME + "_" + end) * ratio
        center += point * mass
        total += mass
    center = center / total
    feet = (_position(NAME + "_ankleL") + _position(NAME + "_ankleR")) * 0.5
    dg_center = _translation(owner, "centerMatrix")
    dg_ground = _translation(owner, "groundMatrix")
    balance = cmds.getAttr(owner + ".balance")
    expected_balance = ((center.x - feet.x) ** 2 + (center.z - feet.z) ** 2) ** 0.5
    center_error = (dg_center - center).length()
    ground_error = (dg_ground - om2.MVector(center.x, 0.0, center.z)).length()
    balance_error = abs(balance - expected_balance)
    values[:] = [
        "GREEN BALL = center of mass   ORANGE DISC = its floor projection   BLUE DISC = mid point of the ankles",
        "STAGE: " + stage_name,
        "fixed: Dempster segment table (trunk 0.497, head 0.081, thigh 0.100, hand 0.006 ...)   floor y = 0 cm",
        "c = sum(m_i * ((1 - r_i) * start_i + r_i * end_i)) / sum(m_i)      balance = |c.xz - ankles.xz|",
        "INPUT spine rx {:6.1f}  shoulder ry L {:6.1f} R {:6.1f}  L hip rx {:6.1f}  L knee rx {:5.1f}  "
        "hand mass x{:5.2f}".format(spine, shoulder_l, shoulder_r, hip_l, knee_l, hand),
        "OUTPUT COM ({:6.2f}, {:6.2f}, {:6.2f}) cm   total mass {:.3f}   balance {:5.2f} cm".format(
            dg_center.x, dg_center.y, dg_center.z, cmds.getAttr(owner + ".totalMass"), balance),
        "CHECK |COM - independent| {:.1e} cm   |floor point| {:.1e} cm   |balance| {:.1e} cm".format(
            center_error, ground_error, balance_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = center_error < 1e-6 and ground_error < 1e-6 and balance_error < 1e-6
    return {"frame": frame, "presentation_stage": stage_name,
            "input": {"spine": spine, "shoulderL": shoulder_l, "shoulderR": shoulder_r, "hipL": hip_l,
                      "kneeL": knee_l, "handMass": hand},
            "center": [dg_center.x, dg_center.y, dg_center.z], "balance": balance,
            "center_error": center_error, "ground_error": ground_error, "balance_error": balance_error, "ok": ok}


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
        folder = recordVideo("CenterOfMass: 全身の重心と床への投影", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "center_of_mass.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-center-of-mass.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("center-of-mass-%Y%m%d-%H%M%S")
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
