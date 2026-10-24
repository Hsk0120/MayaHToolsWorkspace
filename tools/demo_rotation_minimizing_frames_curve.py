"""RotationMinimizingFrames.fromCurve(曲線の接線を使う版)と、点列の差分を使うcreateを並べて録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_rotation_minimizing_frames_curve.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNT = 9
SEGMENT = 48
BASE = [(-10, 0, 0), (-6, 0, 0), (-2, 0, 0), (2, 0, 0), (6, 0, 0), (10, 0, 0)]
# (各CVのずらし量, 次の形へ向かう段階名)。
SHAPES = [
    ([(0, 0, 0)] * 6, "1 STRAIGHT CURVE (CREATION POSE)"),
    ([(0, 0, 0)] * 6, "2 BEND UP AT BOTH ENDS"),
    ([(0, 8, 0), (0, 2, 0), (0, 0, 0), (0, 0, 0), (0, 2, 0), (0, 8, 0)], "3 S-CURVE IN 3D"),
    ([(0, 6, 4), (0, 1, -5), (0, -3, 0), (0, 3, 2), (0, -2, 6), (0, 7, -3)], "4 COIL"),
    ([(4, 6, 0), (0, 0, 7), (-2, -6, 0), (2, 0, -7), (0, 6, 0), (-4, 0, 6)], "5 RETURN TO STRAIGHT"),
    ([(0, 0, 0)] * 6, "5 RETURN TO STRAIGHT"),
]


def offsets(frame):
    """フレームの各CVのずらし量と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(SHAPES) - 1)
    index = min(int(phase), len(SHAPES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [[a + (b - a) * weight for a, b in zip(p, q)] for p, q in zip(SHAPES[index][0], SHAPES[index + 1][0])]
    return values, SHAPES[index][1]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _plate(name, group, along):
    """フレームのX(接線)方向に細い棒、Y(基準ベクトル)に長い板を付ける。alongは棒の長さ。"""
    from maya import cmds
    root = cmds.createNode("transform", name=name)
    plate = cmds.polyCube(name=name + "_GEO", width=0.4, height=2.0, depth=0.12)[0]
    arrow = cmds.polyCube(name=name + "_tangent", width=along, height=0.15, depth=0.15)[0]
    cmds.setAttr(arrow + ".translateX", along / 2)
    for node in (plate, arrow):
        cmds.parent(node, root, relative=True)
        cmds.sets(node, edit=True, forceElement=group)
    return root


def buildScene():
    """検証シーンを作り、(panel, 曲線, 点のtransform, 2つのcontainer, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import RotationMinimizingFrames
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    curve = cmds.curve(name="spine_CRV", degree=3, point=BASE)
    shape = cmds.listRelatives(curve, shapes=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideColor", 17)
    cmds.setAttr(shape + ".lineWidth", 2.5)
    curve_owner = RotationMinimizingFrames.fromCurve(curve, COUNT, name="curveRmf", upVector=(0, 0, 1)).container
    # 比較: 同じ点に置いたtransformの点列から、差分の接線で作るcreate版。
    points = []
    for index in range(COUNT):
        node = cmds.createNode("transform", name="sample{}_LOC".format(index))
        p = cmds.pointOnCurve(curve, parameter=index / float(COUNT - 1), turnOnPercentage=True, position=True)
        cmds.setAttr(node + ".translate", *p)
        cmds.setAttr(node + ".rotate", 0, 0, 0)
        points.append(node)
    point_owner = RotationMinimizingFrames.create(points, name="pointRmf", upAxis="z", keepOffset=False).container
    green = _shader("curveGreen", (0.1, 0.8, 0.2))
    red = _shader("pointRed", (0.9, 0.15, 0.1), transparency=0.45)
    for index in range(COUNT):
        plate = _plate("curvePlate{}".format(index), green, 1.6)
        curve_owner.getPlug("matrix" + str(index)).connectTo(plate + ".offsetParentMatrix")
        other = _plate("pointPlate{}".format(index), red, 2.4)
        point_owner.getPlug("matrix" + str(index)).connectTo(other + ".offsetParentMatrix")
    camera, camera_shape = cmds.camera(name="curveRmfCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(10, 12, 50), lookAt=(0, 4, 0))
    cmds.setAttr(camera_shape + ".verticalFilmOffset", -0.14)
    window = cmds.window("curveRmfValidationWindow", title="Rotation minimizing frames from curve tangents",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("curveRmfValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["curveRmfHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, curve, points, curve_owner, point_owner, values, names


def _angle(a, b):
    """2つのベクトルの角度(度)。"""
    la = math.sqrt(sum(x * x for x in a))
    lb = math.sqrt(sum(x * x for x in b))
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b)) / (la * lb)))
    return math.degrees(math.acos(dot))


def evaluate_frame(frame, curve, points, curve_owner, point_owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from mlrig.setups import RotationMinimizingFrames
    shift, stage = offsets(frame)
    for index, (base, offset) in enumerate(zip(BASE, shift)):
        cmds.xform("{}.cv[{}]".format(curve, index), worldSpace=True,
                   translation=[b + o for b, o in zip(base, offset)])
    samples, tangents = [], []
    for index in range(COUNT):
        u = index / float(COUNT - 1)
        samples.append(cmds.pointOnCurve(curve, parameter=u, turnOnPercentage=True, position=True))
        tangents.append(cmds.pointOnCurve(curve, parameter=u, turnOnPercentage=True, normalizedTangent=True))
    # 比較用のcreate版の点を、曲線上の同じ位置へ動かす(表示のための操作で、fromCurveの計算には使わない)。
    for node, point in zip(points, samples):
        cmds.setAttr(node + ".translate", *point)
    expected = RotationMinimizingFrames.frames(samples, [0.0, 0.0, 1.0], tangents)
    errors, curve_tangent, point_tangent = [], [], []
    for index in range(COUNT):
        m = cmds.getAttr("{}.matrix{}".format(curve_owner, index))
        errors.append(max(_angle(m[0:3], expected[index][0]), _angle(m[4:7], expected[index][1])))
        curve_tangent.append(_angle(m[0:3], tangents[index]))
        q = cmds.getAttr("{}.matrix{}".format(point_owner, index))
        point_tangent.append(_angle(q[0:3], tangents[index]))
    values[:] = [
        "GREEN = fromCurve (curve tangents)   RED (transparent) = create on the same 9 points (difference tangents)",
        "STAGE: " + stage,
        "fromCurve: pointOnCurveInfo (turnOnPercentage, u = i/8) -> position, normalizedTangent -> double reflection",
        "same double reflection as create (Wang et al. 2008); only the tangents differ    first up = world Z",
        "INPUT 6 CVs of a cubic NURBS curve (yellow), animated",
        "OUTPUT tangent error vs curve: fromCurve max = {:.4f} deg   create ends = {:5.2f} / {:5.2f} deg".format(
            max(curve_tangent), point_tangent[0], point_tangent[-1]),
        "CHECK |DG - double reflection with curve tangents| max = {:.4f} deg".format(max(errors)),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    # 判定は単体テストと同じ考え方: Python版との差(単精度のため0.05度)と、Xが曲線の接線と一致すること。
    ok = max(errors) < 0.05 and max(curve_tangent) < 0.05
    return {"frame": frame, "presentation_stage": stage, "dg_error_degrees": errors,
            "from_curve_tangent_error_degrees": curve_tangent, "create_tangent_error_degrees": point_tangent,
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
        panel, curve, points, curve_owner, point_owner, values, names = buildScene()
        frames = SEGMENT * (len(SHAPES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("RotationMinimizingFrames.fromCurve: 曲線の接線から作る回転最小化フレーム", frames, 24,
                             panel, lambda frame: evaluate_frame(frame, curve, points, curve_owner, point_owner,
                                                                 values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "rotation-minimizing-frames-curve.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-rotation-minimizing-frames-curve.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("rmf-curve-%Y%m%d-%H%M%S")
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
