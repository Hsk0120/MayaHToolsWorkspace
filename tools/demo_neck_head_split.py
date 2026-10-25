"""NeckHeadSplitの首への回転の分配を、頭だけが回る場合と並べて専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_neck_head_split.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 36
#: 首の関節(胸からの位置)と頭の位置。cm。
POINTS = [(0.0, 0.6, 0.2), (0.0, 1.9, 0.35), (0.0, 3.2, 0.45), (0.0, 4.5, 0.5)]
RED_OFFSET = -14.0
# ((コントロールの rx, ry, rz, weight0, weight1, weight2), 次の姿勢へ向かう段階名)。
POSES = [
    ((0.0, 0.0, 0.0, 0.25, 0.25, 0.25), "1 REST"),
    ((0.0, 0.0, 0.0, 0.25, 0.25, 0.25), "2 NOD DOWN (rx 0 -> 50)"),
    ((50.0, 0.0, 0.0, 0.25, 0.25, 0.25), "3 LOOK UP (rx 50 -> -40)"),
    ((-40.0, 0.0, 0.0, 0.25, 0.25, 0.25), "4 STIFF ROOT (weights 0.1 / 0.25 / 0.4)"),
    ((-40.0, 0.0, 0.0, 0.1, 0.25, 0.4), "5 NOD + TURN (rx 50, ry 45)"),
    ((50.0, 45.0, 0.0, 0.1, 0.25, 0.4), "6 WEIGHTS 0 (only the head turns)"),
    ((50.0, 45.0, 0.0, 0.0, 0.0, 0.0), "7 WEIGHTS 0.4 EACH (sum 1.2: head turns back)"),
    ((50.0, 45.0, 0.0, 0.4, 0.4, 0.4), "8 RETURN TO REST"),
    ((0.0, 0.0, 0.0, 0.25, 0.25, 0.25), "8 RETURN TO REST"),
    ((0.0, 0.0, 0.0, 0.25, 0.25, 0.25), "8 RETURN TO REST"),
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


def _matrix(node, attribute):
    """アトリビュートの行列を om2.MMatrix で返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    return om2.MMatrix(cmds.getAttr(node + "." + attribute))


def _box(name, parent, size, offset, shading):
    """parent の下に箱を置く。"""
    from maya import cmds
    box = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    box = cmds.parent(box, parent, relative=True)[0]
    cmds.setAttr(box + ".translate", *offset)
    cmds.sets(box, edit=True, forceElement=shading)
    return box


def _segments(prefix, holders, shading, head_shading):
    """首の骨(次の関節までの箱)と頭(箱と前を示す鼻)を holders の下に作る。"""
    for index, holder in enumerate(holders):
        if index < len(holders) - 1:
            here, there = POINTS[index], POINTS[index + 1]
            length = there[1] - here[1]
            _box("{}Neck{}_GEO".format(prefix, index), holder, (0.9, length * 0.92, 0.9),
                 (0, length * 0.5, (there[2] - here[2]) * 0.5), shading)
        else:
            _box(prefix + "Head_GEO", holder, (2.2, 2.6, 2.4), (0, 1.3, 0.2), head_shading)
            _box(prefix + "Nose_GEO", holder, (0.5, 0.5, 1.0), (0, 1.1, 1.8), head_shading)


def _independent(rest_in_chest, control_rest, control_now, weights):
    """胸を単位行列としたときの各関節の行列を、クォータニオンの軸と角度から独立に求める。"""
    from maya.api import OpenMaya as om2

    def power(q, ratio):
        q = om2.MQuaternion(q)
        if q.w < 0:
            q = q.negateIt()
        axis, angle = q.asAxisAngle()
        return om2.MQuaternion(angle * ratio, axis).asMatrix()

    delta = om2.MTransformationMatrix(control_rest.inverse() * control_now).rotation(asQuaternion=True)
    result, total, position, previous = [], 0.0, om2.MVector(), om2.MVector()
    for index, rest in enumerate(rest_in_chest):
        point = om2.MVector(rest[12], rest[13], rest[14])
        position = position + (point - previous) * power(delta, total)
        previous = point
        if index < len(rest_in_chest) - 1:
            total += weights[index]
            rotation = power(delta, total)
        else:
            rotation = power(delta, 1.0)
        orient = om2.MMatrix(rest)
        for column in range(3):
            orient.setElement(3, column, 0.0)
        translate = om2.MTransformationMatrix()
        translate.setTranslation(position, om2.MSpace.kTransform)
        result.append(orient * rotation * translate.asMatrix())
    return result


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import NeckHeadSplit
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    green = _shader("splitGreen", (0.15, 0.75, 0.25))
    green_head = _shader("splitGreenHead", (0.35, 0.9, 0.45))
    red = _shader("headOnlyRed", (0.85, 0.2, 0.2))
    red_head = _shader("headOnlyRedHead", (0.95, 0.4, 0.35))
    gray = _shader("chestGray", (0.45, 0.45, 0.45))
    chest = cmds.createNode("transform", name="chest")
    cmds.setAttr(chest + ".translateY", 4.0)
    _box("chest_GEO", chest, (3.5, 3.0, 2.4), (0, -1.6, 0), gray)
    joints, parent = [], chest
    for index, point in enumerate(POINTS):
        previous = POINTS[index - 1] if index else (0.0, 0.0, 0.0)
        node = cmds.createNode("transform", name="joint{}".format(index), parent=parent)
        cmds.setAttr(node + ".translate", *[a - b for a, b in zip(point, previous)])
        joints.append(cmds.ls(node, long=True)[0])
        parent = node
    control = cmds.createNode("transform", name="head_ctrl")
    cmds.setAttr(control + ".translate", 0, 4.0 + POINTS[-1][1] + 1.3, 1.5)
    graph = NeckHeadSplit.create(chest, joints, control, name="neckSplit")
    owner = str(graph.container)
    holders = []
    for index in range(len(POINTS)):
        holder = cmds.createNode("transform", name="green{}".format(index))
        cmds.connectAttr("{}.matrix{}".format(owner, index), holder + ".offsetParentMatrix")
        holders.append(holder)
    _segments("green", holders, green, green_head)
    # 比較用(赤): 首は動かさず、頭だけをコントロールの回転の変化どおりに回す。
    red_chest = cmds.createNode("transform", name="redChest")
    cmds.setAttr(red_chest + ".translate", 0, 4.0, RED_OFFSET)
    _box("redChest_GEO", red_chest, (3.5, 3.0, 2.4), (0, -1.6, 0), gray)
    red_holders = []
    for index, point in enumerate(POINTS):
        holder = cmds.createNode("transform", name="red{}".format(index), parent=red_chest)
        cmds.setAttr(holder + ".translate", *point)
        red_holders.append(holder)
    _segments("red", red_holders, red, red_head)
    camera, camera_shape = cmds.camera(name="neckCamera", orthographic=True, orthographicWidth=40)
    cmds.viewPlace(camera_shape, eye=(60, 3.5, RED_OFFSET * 0.5), lookAt=(0, 3.5, RED_OFFSET * 0.5), up=(0, 1, 0))
    window = cmds.window("neckValidationWindow", title="NeckHeadSplit - head control shared by the neck",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("neckValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, wireframeOnShaded=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("neck", 7)
    chest_world = _matrix(chest, "worldMatrix[0]")
    scene = {"owner": owner, "control": control, "chest": chest, "red": red_holders,
             "rest_in_chest": [_matrix(j, "worldMatrix[0]") * chest_world.inverse() for j in joints],
             "control_rest": _matrix(control, "worldMatrix[0]") * chest_world.inverse()}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """コントロールと割合を動かし、緑(分配)を独立計算と比べ、赤(頭だけ)を置いた診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    (rx, ry, rz, w0, w1, w2), stage_name = pose(frame)
    owner, control = scene["owner"], scene["control"]
    cmds.setAttr(control + ".rotate", rx, ry, rz)
    weights = (w0, w1, w2)
    for index, value in enumerate(weights):
        cmds.setAttr("{}.weight{}".format(owner, index), value)
    chest = _matrix(scene["chest"], "worldMatrix[0]")
    control_now = _matrix(control, "worldMatrix[0]") * chest.inverse()
    expected = _independent(scene["rest_in_chest"], scene["control_rest"], control_now, weights)
    outputs = [_matrix(owner, "matrix{}".format(i)) * chest.inverse() for i in range(len(POINTS))]
    formula_error = max(max(abs(a - b) for a, b in zip(o, e)) for o, e in zip(outputs, expected))
    # 頭の向きの変化 = コントロールの向きの変化(胸の空間)。
    def rotation(matrix):
        return om2.MTransformationMatrix(matrix).rotation(asQuaternion=True).asMatrix()
    head_expected = rotation(scene["rest_in_chest"][-1]) * rotation(scene["control_rest"]).inverse() \
        * rotation(control_now)
    head_error = max(abs(a - b) for a, b in zip(rotation(outputs[-1]), head_expected))
    points = [om2.MPoint(m[12], m[13], m[14]) for m in outputs]
    rest = [om2.MPoint(m[12], m[13], m[14]) for m in scene["rest_in_chest"]]
    rest_lengths = [rest[i].distanceTo(rest[i - 1]) for i in range(1, len(points))]
    length_error = max(abs(points[i].distanceTo(points[i - 1]) - rest_lengths[i - 1]) for i in range(1, len(points)))
    # 赤: 頭だけを回す(首は作成時のまま)。
    red_head = rotation(scene["rest_in_chest"][-1]) * rotation(scene["control_rest"]).inverse() * rotation(control_now)
    angles = om2.MTransformationMatrix(red_head).rotation()
    cmds.setAttr(scene["red"][-1] + ".rotate", *[a * 57.29577951308232 for a in angles])
    tilt = [om2.MTransformationMatrix(outputs[i] * (outputs[i - 1].inverse() if i else om2.MMatrix())).rotation(
        asQuaternion=True).asAxisAngle()[1] * 57.29577951308232 for i in range(len(points))]
    values[:] = [
        "LEFT GREEN = NeckHeadSplit (rotation shared by 3 neck joints)   RIGHT RED = head only (stiff neck)",
        "STAGE: " + stage_name,
        "fixed: 3 neck joints + head, bones 1.3 cm, chest still   D = rotation of (ctrl rest in chest)^-1 * ctrl in chest",
        "neck i: V_i = slerp(I, D, w_i) * T(b_i) * V_(i-1)    head: orientation = D, position from the neck tip",
        "INPUT ctrl rotate ({:6.1f}, {:6.1f}, {:6.1f}) deg   weights {:.2f} / {:.2f} / {:.2f}  (sum {:.2f})".format(
            rx, ry, rz, w0, w1, w2, w0 + w1 + w2),
        "OUTPUT bend per joint (deg): neck0 {:5.1f}  neck1 {:5.1f}  neck2 {:5.1f}  head {:5.1f}".format(*tilt),
        "CHECK |green - formula| {:.1e}   |head - ctrl orientation| {:.1e}   bone length change {:.1e} cm".format(
            formula_error, head_error, length_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = formula_error < 1e-6 and head_error < 1e-6 and length_error < 1e-6
    return {"frame": frame, "presentation_stage": stage_name,
            "input": {"rotate": [rx, ry, rz], "weights": list(weights)},
            "bend": tilt, "formula_error": formula_error, "head_error": head_error,
            "length_error": length_error, "ok": ok}


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
        folder = recordVideo("NeckHeadSplit: 首と頭への回転の分配", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "neck_head_split.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-neck-head-split.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("neck-head-split-%Y%m%d-%H%M%S")
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
