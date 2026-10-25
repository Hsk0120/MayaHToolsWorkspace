"""RotationMinimizingFrames(double reflection法)と、固定の上方向で向きを決める方法を並べて録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_rotation_minimizing_frames.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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


def _line():
    return [[2.0 * i - 8.0, 0.0, 0.0] for i in range(COUNT)]


def _arch():
    # XY平面の半円。両端と頂点付近で接線が上方向(Y)と平行または垂直になる。
    return [[-7.0 * math.cos(a), 7.0 * math.sin(a) - 3.0, 0.0] for a in (math.pi * i / (COUNT - 1) for i in range(COUNT))]


def _helix():
    return [[4.0 * math.cos(a), 1.2 * a - 5.0, 4.0 * math.sin(a)] for a in (2.4 * math.pi * i / (COUNT - 1) for i in range(COUNT))]


def _wave():
    return [[2.0 * i - 8.0, 3.0 * math.sin(i * 0.9), 3.0 * math.cos(i * 0.7) - 3.0] for i in range(COUNT)]


# (形, 次の形へ向かう段階名)。
SHAPES = [
    (_line(), "1 STRAIGHT LINE (CREATION POSE)"),
    (_line(), "2 BEND INTO AN ARCH THROUGH VERTICAL"),
    (_arch(), "3 ARCH: TANGENT PASSES VERTICAL AT BOTH ENDS"),
    (_arch(), "4 TWIST INTO A HELIX: FIXED-UP FRAMES FLIP, RMF DOES NOT"),
    (_helix(), "5 HELIX -> 3D WAVE"),
    (_wave(), "6 RETURN TO STRAIGHT LINE"),
    (_line(), "6 RETURN TO STRAIGHT LINE"),
]


def pose(frame):
    """フレームの点列と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(SHAPES) - 1)
    index = min(int(phase), len(SHAPES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    points = [[a + (b - a) * weight for a, b in zip(p, q)] for p, q in zip(SHAPES[index][0], SHAPES[index + 1][0])]
    return points, SHAPES[index][1]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _plate(name, group, offset):
    """フレームのX(接線)に薄く、Y(基準ベクトル)に長い板。Y側の先端に印の球を付ける。offsetはY方向へずらす量。"""
    from maya import cmds
    root = cmds.createNode("transform", name=name)
    plate = cmds.polyCube(name=name + "_GEO", width=0.5, height=2.2, depth=0.12)[0]
    cmds.setAttr(plate + ".translateY", offset)
    tip = cmds.polySphere(name=name + "_tip", radius=0.25)[0]
    cmds.setAttr(tip + ".translateY", offset + 1.2)
    for node in (plate, tip):
        cmds.parent(node, root, relative=True)
        cmds.sets(node, edit=True, forceElement=group)
    return root


def _fixedUpFrame(t, position):
    """比較用: 接線をX、固定の上方向(0,1,0)から作ったYのフレーム(行列の16成分)。"""
    up = [0.0, 1.0, 0.0]
    b = [t[1] * up[2] - t[2] * up[1], t[2] * up[0] - t[0] * up[2], t[0] * up[1] - t[1] * up[0]]
    length = math.sqrt(sum(v * v for v in b))
    b = [v / length for v in b] if length > 1e-9 else [0.0, 0.0, 1.0]
    r = [b[1] * t[2] - b[2] * t[1], b[2] * t[0] - b[0] * t[2], b[0] * t[1] - b[1] * t[0]]
    return [t[0], t[1], t[2], 0, r[0], r[1], r[2], 0, b[0], b[1], b[2], 0, position[0], position[1], position[2], 1]


def buildScene():
    """検証シーンを作り、(panel, 点のtransform, 緑の板, 赤の板, 曲線, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import RotationMinimizingFrames
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    nodes = []
    for index, point in enumerate(SHAPES[0][0]):
        node = cmds.createNode("transform", name="point{}_LOC".format(index))
        cmds.setAttr(node + ".translate", *point)
        nodes.append(node)
    owner = RotationMinimizingFrames.create(nodes, name="rmf", upAxis="z", keepOffset=False).container
    green = _shader("rmfGreen", (0.1, 0.8, 0.2))
    red = _shader("fixedUpRed", (0.9, 0.15, 0.1), transparency=0.35)
    greens, reds = [], []
    for index in range(COUNT):
        plate = _plate("rmfPlate{}".format(index), green, 0.0)
        owner.getPlug("matrix" + str(index)).connectTo(plate + ".offsetParentMatrix")
        greens.append(plate)
        reds.append(_plate("fixedUpPlate{}".format(index), red, 0.0))
    curve = cmds.curve(name="path_CRV", degree=1, point=SHAPES[0][0])
    shape = cmds.listRelatives(curve, shapes=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideColor", 17)
    cmds.setAttr(shape + ".lineWidth", 2.5)
    camera, camera_shape = cmds.camera(name="rmfCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(14, 12, 34), lookAt=(0, 0, 0))
    cmds.setAttr(camera_shape + ".verticalFilmOffset", -0.14)
    window = cmds.window("rmfValidationWindow", title="Rotation minimizing frames (double reflection)",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("rmfValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["rmfHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, nodes, greens, reds, curve, owner, values, names


def _angle(a, b):
    """2つの単位ベクトルの角度(度)。"""
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))
    return math.degrees(math.acos(dot))


def evaluate_frame(frame, nodes, greens, reds, curve, owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from mlrig.setups import RotationMinimizingFrames
    points, stage = pose(frame)
    for node, point in zip(nodes, points):
        cmds.setAttr(node + ".translate", *point)
    for index, point in enumerate(points):
        cmds.xform("{}.cv[{}]".format(curve, index), worldSpace=True, translation=point)
    expected = RotationMinimizingFrames.frames(points, [0.0, 0.0, 1.0])
    errors, orthogonality, rmf_steps, fixed_steps, fixed_frames = [], [], [], [], []
    for index in range(COUNT):
        m = cmds.getAttr("{}.matrix{}".format(owner, index))
        t, r = m[0:3], m[4:7]
        errors.append(max(_angle(t, expected[index][0]), _angle(r, expected[index][1])))
        orthogonality.append(abs(sum(a * b for a, b in zip(t, r))))
        fixed = _fixedUpFrame(expected[index][0], points[index])
        fixed_frames.append(fixed)
        cmds.xform(reds[index], worldSpace=True, matrix=fixed)
    for index in range(COUNT - 1):
        turn = _angle(expected[index][0], expected[index + 1][0])
        rmf_steps.append(_angle(expected[index][1], expected[index + 1][1]) - turn)
        fixed_steps.append(_angle(fixed_frames[index][4:7], fixed_frames[index + 1][4:7]))
    values[:] = [
        "GREEN = rotation minimizing frames (DG)   RED (transparent) = fixed world-up frames (comparison only)",
        "STAGE: " + stage,
        "Wang et al. 2008 double reflection: v1 = x[i+1]-x[i], r_L = r - 2(v1.r)/(v1.v1) v1, t_L likewise",
        "v2 = t[i+1] - t_L,  r[i+1] = r_L - 2(v2.r_L)/(v2.v2) v2     (plate long axis = r, tip ball = +r)",
        "INPUT 9 points (yellow path), first up = world Z     tangents: central differences, ends one-sided",
        "OUTPUT max (r step - tangent turn) = {:+.3f} deg (info)   fixed-up max r step = {:6.1f} deg".format(
            max(rmf_steps), max(fixed_steps)),
        "CHECK |DG - double reflection| max = {:.4f} deg   |t.r| max = {:.1e}".format(max(errors), max(orthogonality)),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    # vectorProduct・plusMinusAverageは単精度(float3)なので、9点ぶんの鏡映の連鎖で倍精度のPython版と
    # 0.03度程度の差が出る(初回の録画で最大0.028度)。判定は0.05度とする。
    # 隣り合うrの角度と接線の曲がりの差は表示だけにする(離散のdouble reflectionでは0以下になるとは限らない)。
    ok = max(errors) < 0.05 and max(orthogonality) < 1e-4
    return {"frame": frame, "presentation_stage": stage, "points": points, "dg_error_degrees": errors,
            "orthogonality": orthogonality, "rmf_step_excess_degrees": rmf_steps,
            "fixed_up_step_degrees": fixed_steps, "ok": ok}


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
        panel, nodes, greens, reds, curve, owner, values, names = buildScene()
        frames = SEGMENT * (len(SHAPES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("RotationMinimizingFrames: double reflection法の回転最小化フレーム", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, nodes, greens, reds, curve, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "rotation-minimizing-frames.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-rotation-minimizing-frames.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("rmf-%Y%m%d-%H%M%S")
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
