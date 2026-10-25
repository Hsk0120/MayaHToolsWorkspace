"""LipZipの閉じる割合と、閉じ合わせた上唇・下唇の位置を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_lip_zip.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNT = 7
FALLOFF = 0.3
SEGMENT = 30
# (zipLeft, zipRight, meetHeight, 下唇を下げる量[cm], 次の姿勢へ向かう段階名)。基準は0・0・0.5・0。
POSES = [
    (0.0, 0.0, 0.5, 0.0, "1 REST: OPEN MOUTH, ALL PAIRS OPEN"),
    (0.0, 0.0, 0.5, 0.0, "2 zipLeft 0 -> 0.5: CLOSES FROM THE LEFT CORNER"),
    (0.5, 0.0, 0.5, 0.0, "3 zipLeft 0.5 -> 1: WHOLE MOUTH CLOSED"),
    (1.0, 0.0, 0.5, 0.0, "4 zipLeft BACK TO 0"),
    (0.0, 0.0, 0.5, 0.0, "5 zipRight 0 -> 0.6: CLOSES FROM THE RIGHT CORNER"),
    (0.0, 0.6, 0.5, 0.0, "6 BOTH SIDES 0.45: MEET IN THE MIDDLE"),
    (0.45, 0.45, 0.5, 0.0, "7 meetHeight 0.5 -> 0.15: LIPS MEET NEAR THE LOWER LIP"),
    (0.45, 0.45, 0.15, 0.0, "8 OPEN THE JAW 1 cm: CLOSED PAIRS FOLLOW"),
    (0.45, 0.45, 0.15, 1.0, "9 RETURN TO REST"),
    (0.0, 0.0, 0.5, 0.0, "9 RETURN TO REST"),
    (0.0, 0.0, 0.5, 0.0, "9 RETURN TO REST"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:4], POSES[index + 1][:4])]
    return values, POSES[index][4]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _ball(name, parent, group, radius):
    """parentの原点に球を作る。"""
    from maya import cmds
    sphere = cmds.polySphere(name=name, radius=radius, subdivisionsAxis=16, subdivisionsHeight=10)[0]
    cmds.parent(sphere, parent, relative=True)
    cmds.sets(sphere, edit=True, forceElement=group)
    return sphere


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import LipZip
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    head = cmds.createNode("transform", name="head_GRP")
    jaw = cmds.createNode("transform", name="jaw_GRP", parent=head)
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.6)
    green = _shader("outputGreen", (0.15, 0.8, 0.25))
    upper, lower = [], []
    for index in range(COUNT):
        x = (index - (COUNT - 1) / 2.0) * 1.1
        curve = 1.0 - (x / 3.6) ** 2
        top = cmds.createNode("transform", name="upperLip{}_LOC".format(index), parent=head)
        cmds.setAttr(top + ".translate", x, 0.15 + 0.8 * curve, 0.6 * curve)
        bottom = cmds.createNode("transform", name="lowerLip{}_LOC".format(index), parent=jaw)
        cmds.setAttr(bottom + ".translate", x, -0.15 - 0.8 * curve, 0.6 * curve)
        # 赤(半透明)=入力の点。
        _ball("upperInput{}_GEO".format(index), top, red, 0.3)
        _ball("lowerInput{}_GEO".format(index), bottom, red, 0.3)
        upper.append(top)
        lower.append(bottom)
    # 右の口角(-X)から左の口角(+X)へ並べる。
    graph = LipZip.create(upper, lower, name="lipZip", falloff=FALLOFF)
    owner = graph.container
    for index in range(COUNT):
        for role in ("upper", "lower"):
            node = cmds.createNode("transform", name="{}Output{}_GRP".format(role, index))
            owner.getPlug("{}Matrix{}".format(role, index)).connectTo(node + ".offsetParentMatrix")
            # 緑=出力の点(入力より小さく、重なっても入力の赤が見えるようにする)。
            _ball("{}Output{}_GEO".format(role, index), node, green, 0.2)
    camera, camera_shape = cmds.camera(name="lipZipCamera", focalLength=35)
    # 正面(+Z)から少し上。口全体と上下の唇の隙間が見える位置に固定する。
    cmds.viewPlace(camera_shape, eye=(0, 0.2, 17), lookAt=(0, -1.4, 0))
    window = cmds.window("lipZipValidationWindow", title="LipZip - lips close from the corners",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("lipZipValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["lipZipHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"jaw": jaw, "upper": upper, "lower": lower, "owner": owner}
    return panel, scene, values, names


def _blend(first, second, weight):
    """位置は線形、回転はslerpで2つの行列を補間する(scale・shearは1・0の前提)。"""
    from maya.api import OpenMaya as om
    a, b = om.MTransformationMatrix(first), om.MTransformationMatrix(second)
    translate = a.translation(om.MSpace.kWorld) * (1.0 - weight) + b.translation(om.MSpace.kWorld) * weight
    rotation = om.MQuaternion.slerp(a.rotation(asQuaternion=True), b.rotation(asQuaternion=True), weight)
    result = om.MTransformationMatrix()
    result.setRotation(rotation)
    result.setTranslation(translate, om.MSpace.kWorld)
    return result.asMatrix()


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import LipZip
    (zip_left, zip_right, height, jaw), stage = pose(frame)
    owner = scene["owner"]
    owner.getPlug("zipLeft").set(zip_left)
    owner.getPlug("zipRight").set(zip_right)
    owner.getPlug("meetHeight").set(height)
    cmds.setAttr(scene["jaw"] + ".translateY", -jaw)
    weights, expected_weights, matrix_error = [], [], 0.0
    for index in range(COUNT):
        position = owner.getPlug("position" + str(index)).get()
        expected = LipZip.response(position, zip_left, zip_right, FALLOFF)
        weights.append(owner.getPlug("weight" + str(index)).get())
        expected_weights.append(expected)
        top = om.MMatrix(cmds.getAttr(scene["upper"][index] + ".worldMatrix[0]"))
        bottom = om.MMatrix(cmds.getAttr(scene["lower"][index] + ".worldMatrix[0]"))
        meet = _blend(bottom, top, height)
        for role, source in (("upper", top), ("lower", bottom)):
            actual = om.MMatrix(cmds.getAttr("{}.{}Matrix{}".format(owner, role, index)))
            error = max(abs(a - b) for a, b in zip(actual, _blend(source, meet, expected)))
            matrix_error = max(matrix_error, error)
    weight_error = max(abs(a - b) for a, b in zip(weights, expected_weights))
    values[:] = [
        "GREEN = output lip points   RED (transparent) = input lip points   right corner = screen left (pair 0)",
        "STAGE: " + stage,
        "fixed: falloff = 0.3   position_i = (i+1)/8   d = position (left side) or 1-position (right side)",
        "t = clamp((d - (1 - zip*(1+falloff))) / falloff, 0, 1)   w = min(s(tL) + s(tR), 1), s(t) = t*t*(3-2t)   "
        "out = blend(in, blend(lower, upper, meetHeight), w)",
        "INPUT zipLeft = {:.3f}   zipRight = {:.3f}   meetHeight = {:.3f}   jaw down = {:.3f} cm".format(
            zip_left, zip_right, height, jaw),
        "OUTPUT weight (pair 0..6, right -> left) = " + "  ".join("{:.2f}".format(value) for value in weights),
        "CHECK max |weight error| = {:.7f}   max matrix error = {:.7f}".format(weight_error, matrix_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = weight_error < 1e-5 and matrix_error < 1e-4
    return {"frame": frame, "presentation_stage": stage,
            "input": {"zipLeft": zip_left, "zipRight": zip_right, "meetHeight": height, "jaw": jaw},
            "weights": weights, "expected_weights": expected_weights,
            "weight_error": weight_error, "matrix_error": matrix_error, "ok": ok}


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
        folder = recordVideo("LipZip: 口角から順に唇を閉じ合わせる", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "lip_zip.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-lip-zip.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("lip-zip-%Y%m%d-%H%M%S")
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
