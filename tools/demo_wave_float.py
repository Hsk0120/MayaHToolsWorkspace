"""WaveFloat(トロコイド波の面に浮かぶ船)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_wave_float.py --launch`` で使い捨ての隔離GUIを起動して録画する。
水面のメッシュは表示のためだけにデモ側のPythonで毎フレーム同じ式で変形する(リグ本体は標準DGのみ)。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMES = 360
SIZE = 36.0
DIVISIONS = 48
# 波ごとの (wavelength, direction(度), steepness, speed) は固定。振幅だけ段階で変える。
FIXED = ((12.0, 0.0, 0.5, 0.25), (7.0, 40.0, 0.4, 0.18))
# (フレーム, amplitude0, amplitude1, boatX, boatZ, tilt, drift, 段階名)。区間の間は線形に補間する。
KEYS = [
    (0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, "1 REST: AMPLITUDE 0 (NO JUMP)"),
    (24, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, "2 WAVES RAMP UP"),
    (72, 0.8, 0.35, 0.0, 0.0, 1.0, 1.0, "3 BOAT RIDES THE WAVES (HEAVE, SURGE, TILT)"),
    (144, 0.8, 0.35, 0.0, 0.0, 1.0, 1.0, "4 CONTROL MOVES ACROSS THE WATER"),
    (204, 0.8, 0.35, 9.0, -6.0, 1.0, 1.0, "5 TILT 1 -> 0 (STAYS LEVEL)"),
    (240, 0.8, 0.35, 9.0, -6.0, 0.0, 1.0, "6 DRIFT 1 -> 0 (ONLY UP AND DOWN)"),
    (276, 0.8, 0.35, 9.0, -6.0, 0.0, 0.0, "7 BACK TO TILT 1, DRIFT 1"),
    (300, 0.8, 0.35, 9.0, -6.0, 1.0, 1.0, "8 AMPLITUDE BACK TO 0: RETURNS TO INPUT"),
    (336, 0.0, 0.0, 9.0, -6.0, 1.0, 1.0, "9 REST"),
    (FRAMES, 0.0, 0.0, 9.0, -6.0, 1.0, 1.0, "9 REST"),
]


def parameters(frame):
    """フレームの(amplitude0, amplitude1, boatX, boatZ, tilt, drift, 段階名)を返す。"""
    for start, end in zip(KEYS, KEYS[1:]):
        if frame <= end[0]:
            weight = (frame - start[0]) / float(end[0] - start[0])
            return [a + (b - a) * weight for a, b in zip(start[1:7], end[1:7])] + [start[7]]
    return list(KEYS[-1][1:7]) + [KEYS[-1][7]]


def waves(amplitudes):
    """振幅の組から、WaveFloat.surface に渡す波の値を作る。"""
    return [(amplitude,) + fixed for amplitude, fixed in zip(amplitudes, FIXED)]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _boat(name, parent, group):
    """parentの下に船の形(胴・船首・帆柱)を作る。+Xが船首。"""
    from maya import cmds
    parts = [cmds.polyCube(name=name + "_hull", width=6, height=1.0, depth=2.4)[0],
             cmds.polyCone(name=name + "_bow", radius=1.2, height=1.6, axis=(1, 0, 0))[0],
             cmds.polyCylinder(name=name + "_mast", radius=0.12, height=4)[0]]
    cmds.setAttr(parts[0] + ".translateY", 0.3)
    cmds.setAttr(parts[1] + ".translate", 3.8, 0.3, 0)
    cmds.setAttr(parts[2] + ".translateY", 2.5)
    for node in parts:
        cmds.parent(node, parent, relative=True)
        cmds.sets(node, edit=True, forceElement=group)


def buildScene():
    """検証シーンを作り、(panel, 入力, 出力, container, 水面, 元の頂点, HUD値, HUD名)を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import WaveFloat
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    control = cmds.createNode("transform", name="boat_CTRL")
    cmds.setAttr(control + ".rotateY", 20)
    graph = WaveFloat.create(control, name="boatFloat", count=2)
    owner = graph.container
    for index, (wavelength, direction, steepness, speed) in enumerate(FIXED):
        owner.getPlug("wavelength" + str(index)).set(wavelength)
        owner.getPlug("direction" + str(index)).set(direction, uiUnits=True)
        owner.getPlug("steepness" + str(index)).set(steepness)
        owner.getPlug("speed" + str(index)).set(speed)
    output = cmds.createNode("transform", name="boat_OUT")
    owner.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.6)
    green = _shader("outputGreen", (0.1, 0.8, 0.2))
    blue = _shader("waterBlue", (0.15, 0.4, 0.85), transparency=0.35)
    # 赤(半透明)=入力のコントロール(静かな水面の高さ)、緑=波に乗せた出力、青=水面。
    _boat("input", control, red)
    _boat("output", output, green)
    water = cmds.polyPlane(name="water_GEO", width=SIZE, height=SIZE, subdivisionsX=DIVISIONS,
                           subdivisionsY=DIVISIONS)[0]
    cmds.setAttr(water + ".translate", 4, 0, -3)
    cmds.sets(water, edit=True, forceElement=blue)
    selection = om.MSelectionList()
    selection.add(water)
    mesh = om.MFnMesh(selection.getDagPath(0))
    rest = mesh.getPoints(om.MSpace.kWorld)
    camera, camera_shape = cmds.camera(name="floatCamera", focalLength=35)
    # 斜め上から、水面と船の傾きが分かる位置に固定する。
    cmds.viewPlace(camera_shape, eye=(-14, 12, 22), lookAt=(4, 0, -2))
    window = cmds.window("waveFloatValidationWindow", title="WaveFloat - boat on trochoidal waves",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("waveFloatValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["waveFloatHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, control, output, owner, mesh, rest, values, names


def _expected(world, time, wave_values, tilt, drift):
    """入力のワールド行列から、出力の行列・変位・法線を独立に計算する(接線は差分近似)。"""
    from maya.api import OpenMaya as om
    from mlrig.setups import WaveFloat
    p = om.MVector(world[12], world[13], world[14])

    def point(x, z):
        offset, _, _ = WaveFloat.surface(x, z, time, wave_values, drift)
        return om.MVector(x + offset[0], offset[1], z + offset[2])

    step = 1e-4
    tangent_x = (point(p.x + step, p.z) - point(p.x - step, p.z)) / (2 * step)
    tangent_z = (point(p.x, p.z + step) - point(p.x, p.z - step)) / (2 * step)
    normal = (tangent_z ^ tangent_x).normal()
    x = tangent_x.normal()
    z = x ^ normal
    rotation = om.MMatrix([x.x, x.y, x.z, 0, normal.x, normal.y, normal.z, 0, z.x, z.y, z.z, 0, 0, 0, 0, 1])
    quaternion = om.MQuaternion.slerp(om.MQuaternion(), om.MTransformationMatrix(rotation).rotation(True), tilt)
    offset = om.MVector(WaveFloat.surface(p.x, p.z, time, wave_values, drift)[0])

    def move(vector):
        return om.MMatrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, vector.x, vector.y, vector.z, 1])

    return world * move(-p) * quaternion.asMatrix() * move(p + offset), offset, normal


def evaluate_frame(frame, control, output, owner, mesh, rest, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import WaveFloat
    amplitude0, amplitude1, boat_x, boat_z, tilt, drift, stage = parameters(frame)
    time = float(frame)
    for attr, value in (("amplitude0", amplitude0), ("amplitude1", amplitude1), ("tilt", tilt),
                        ("drift", drift), ("time", time)):
        owner.getPlug(attr).set(value)
    cmds.setAttr(control + ".translate", boat_x, 0, boat_z)
    wave_values = waves((amplitude0, amplitude1))
    # 表示用の水面: 静かな水面の各点を同じ式で動かす(drift=1の面。船のdriftとは独立)。
    points = om.MPointArray()
    for vertex in rest:
        offset, _, _ = WaveFloat.surface(vertex.x, vertex.z, time, wave_values, 1.0)
        points.append(om.MPoint(vertex.x + offset[0], offset[1], vertex.z + offset[2]))
    mesh.setPoints(points, om.MSpace.kWorld)
    world = om.MMatrix(cmds.getAttr(control + ".worldMatrix[0]"))
    expected, offset, normal = _expected(world, time, wave_values, tilt, drift)
    actual = om.MMatrix(owner.getPlug("matrix").get())
    shown = om.MMatrix(cmds.getAttr(output + ".worldMatrix[0]"))
    error = max(max(abs(actual[i] - expected[i]), abs(shown[i] - expected[i])) for i in range(16))
    heave = owner.getPlug("heave").get()
    dg_normal = om.MVector(cmds.getAttr(str(owner) + ".normal")[0])
    angle = math.degrees(om.MVector(0, 1, 0).angle(dg_normal))
    surge = math.hypot(actual[12] - world[12], actual[14] - world[14])
    values[:] = [
        "GREEN = output boat on the waves   RED (transparent) = input control (calm water level)   BLUE = water",
        "STAGE: " + stage,
        "fixed: wave0 L=12 cm dir=0 deg Q=0.5 speed=0.25 cm/frame   wave1 L=7 cm dir=40 deg Q=0.4 speed=0.18",
        "theta_i = 2pi/L_i * (D_i . p - speed_i * time)   offset = sum(Q_i*drift*A_i*D_i*cos, A_i*sin)"
        "   N = normalize(Tz x Tx)   matrix = W * T(-p) * slerp(I, R(N), tilt) * T(p + offset)",
        "INPUT time = {:5.1f} frame   A0 = {:4.2f} cm   A1 = {:4.2f} cm   boat x,z = {:+5.2f}, {:+5.2f} cm"
        "   tilt = {:4.2f}   drift = {:4.2f}".format(time, amplitude0, amplitude1, boat_x, boat_z, tilt, drift),
        "OUTPUT heave = {:+6.3f} cm   horizontal shift = {:5.3f} cm   normal tilt = {:5.2f} deg".format(
            heave, surge, angle),
        "CHECK |DG matrix - independent (finite-difference normal)| max = {:.6f}   |heave - formula| = {:.6f}".format(
            error, abs(heave - offset.y)),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-3 and abs(heave - offset.y) < 1e-4
    return {"frame": frame, "presentation_stage": stage, "amplitudes": [amplitude0, amplitude1],
            "boat": [boat_x, boat_z], "tilt": tilt, "drift": drift, "heave": heave, "expected_heave": offset.y,
            "normal_tilt_degrees": angle, "horizontal_shift": surge, "matrix_error": error, "ok": ok}


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
        panel, control, output, owner, mesh, rest, values, names = buildScene()
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("WaveFloat: 波の面に浮かぶ船(トロコイド波の和)", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, control, output, owner, mesh, rest, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "wave-float.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-wave-float.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("wave-float-%Y%m%d-%H%M%S")
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
