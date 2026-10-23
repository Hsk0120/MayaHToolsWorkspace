"""AsymmetricSwingLimit(象限ごとに限界角が違う楕円コーン)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_asymmetric_swing_limit.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# (+Y側, -Y側, +Z側, -Z側)の限界角(度)。
LIMITS = (80.0, 30.0, 55.0, 20.0)
SOFTNESS = 0.25
LENGTH = 10.0
SEGMENT = 36
# (曲げる向きφ[度、0=+Y側・90=+Z側], 入力の曲げ角θ[度], 入力のTwist[度], 段階名)
POSES = [
    (0, 0, 0, "1 REST"),
    (0, 0, 0, "2 BEND TO +Y (l1+ = 80)"),
    (0, 60, 0, "3 +Y PAST LIMIT"),
    (0, 120, 0, "4 RETURN TO SAFE RANGE"),
    (0, 0, 0, "5 BEND TO -Y (l1- = 30)"),
    (180, 20, 0, "6 -Y PAST LIMIT"),
    (180, 90, 0, "7 RETURN TO SAFE RANGE"),
    (180, 0, 0, "8 BEND TO +Z (l2+ = 55)"),
    (90, 40, 0, "9 +Z PAST LIMIT"),
    (90, 110, 0, "10 RETURN TO SAFE RANGE"),
    (90, 0, 0, "11 BEND TO -Z (l2- = 20)"),
    (270, 15, 0, "12 -Z PAST LIMIT"),
    (270, 100, 0, "13 SWEEP AROUND ALL QUADRANTS"),
    (360, 100, 0, "13 SWEEP AROUND ALL QUADRANTS"),
    (450, 100, 0, "13 SWEEP AROUND ALL QUADRANTS"),
    (540, 100, 0, "13 SWEEP AROUND ALL QUADRANTS"),
    (630, 100, 0, "14 TWIST IS NOT LIMITED"),
    (630, 100, 70, "14 TWIST IS NOT LIMITED"),
    (630, 100, -70, "15 RETURN TO REST"),
    (630, 0, 0, "15 RETURN TO REST"),
    (630, 0, 0, "15 RETURN TO REST"),
]


def ellipseLimit(phi):
    """曲げる向きφ(度)の象限ごとの楕円の限界角(度)。"""
    from mlrig.setups import AsymmetricSwingLimit
    return AsymmetricSwingLimit.asymmetricLimitAngle(*LIMITS, math.cos(math.radians(phi)), math.sin(math.radians(phi)))


def pose(frame):
    """フレームの入力(φ, θ, twist, 段階名)をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:3], POSES[index + 1][:3])]
    return values + [POSES[index][3]]


def inputQuaternion(phi, theta, twist):
    """Twistを先に、Swingを後に適用する入力回転。"""
    from maya.api import OpenMaya as om
    swing_axis = om.MVector(0, -math.sin(math.radians(phi)), math.cos(math.radians(phi)))
    return om.MQuaternion(math.radians(twist), om.MVector(1, 0, 0)) * om.MQuaternion(math.radians(theta), swing_axis)


def _shader(name, color):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _bone(name, parent, group, radius):
    """+X方向へ長さLENGTHの棒と先端の球をparent下に作る。"""
    from maya import cmds
    rod = cmds.polyCylinder(name=name + "_rod", axis=(1, 0, 0), height=LENGTH, radius=radius, subdivisionsX=16)[0]
    tip = cmds.polySphere(name=name + "_tip", radius=radius * 2.2)[0]
    cmds.setAttr(rod + ".tx", LENGTH / 2)
    cmds.setAttr(tip + ".tx", LENGTH)
    # Twistが見えるよう、+Y側に小さな板を付ける。
    fin = cmds.polyCube(name=name + "_fin", width=LENGTH * 0.6, height=radius * 5, depth=radius * 0.6)[0]
    cmds.setAttr(fin + ".translate", LENGTH * 0.55, radius * 3, 0)
    for node in (rod, tip, fin):
        cmds.parent(node, parent, relative=True)
        cmds.sets(node, edit=True, forceElement=group)


def _curve(name, points, color, closed=True):
    """表示色付きのNURBS曲線を作る。"""
    from maya import cmds
    if closed:
        points = points + points[:1]
    curve = cmds.curve(name=name, degree=1, point=points)
    shape = cmds.listRelatives(curve, shapes=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideColor", color)
    cmds.setAttr(shape + ".lineWidth", 2.5)
    return curve


def _boundary(angle_of):
    """長さLENGTHの球面上で、向きφごとの角度angle_of(φ)の点列。"""
    points = []
    for step in range(0, 360, 4):
        a = math.radians(angle_of(step))
        phi = math.radians(step)
        points.append((LENGTH * math.cos(a), LENGTH * math.sin(a) * math.cos(phi), LENGTH * math.sin(a) * math.sin(phi)))
    return points


def buildScene():
    """検証シーンを作り、(panel, 入力joint, 出力joint, container, HUD値リスト)を返す。"""
    from maya import cmds
    from mlrig.setups import AsymmetricSwingLimit
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    root = cmds.createNode("transform", name="shoulder_GRP")
    source = cmds.createNode("joint", name="input_JNT", parent=root)
    output = cmds.createNode("joint", name="limited_JNT", parent=root)
    graph = AsymmetricSwingLimit.create(source, name="shoulderSwingLimit", axis="x", limit1Positive=LIMITS[0],
                                        limit1Negative=LIMITS[1], limit2Positive=LIMITS[2],
                                        limit2Negative=LIMITS[3], softness=SOFTNESS)
    owner = graph.container
    owner.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    _bone("input", source, _shader("inputRed", (0.9, 0.12, 0.1)), 0.12)
    _bone("limited", output, _shader("limitedGreen", (0.1, 0.85, 0.2)), 0.22)
    _curve("limitEllipse_CRV", _boundary(ellipseLimit), 17)
    _curve("softStart_CRV", _boundary(lambda p: ellipseLimit(p) * (1 - SOFTNESS)), 2)
    for step in range(0, 360, 45):
        a, phi = math.radians(ellipseLimit(step)), math.radians(step)
        tip = (LENGTH * math.cos(a), LENGTH * math.sin(a) * math.cos(phi), LENGTH * math.sin(a) * math.sin(phi))
        _curve("limitRay{}_CRV".format(step), [(0, 0, 0), tip], 17, closed=False)
    _curve("restAxis_CRV", [(0, 0, 0), (LENGTH * 1.15, 0, 0)], 3, closed=False)
    labels = (("+Y  l1+ = 80", 0), ("-Y  l1- = 30", 180), ("+Z  l2+ = 55", 90), ("-Z  l2- = 20", 270))
    for label, step in labels:
        a, phi = math.radians(ellipseLimit(step)), math.radians(step)
        position = (LENGTH * 1.05 * math.cos(a), LENGTH * 1.05 * math.sin(a) * math.cos(phi),
                    LENGTH * 1.05 * math.sin(a) * math.sin(phi))
        text = cmds.annotate(root, text=label, point=position)
        cmds.setAttr(cmds.listRelatives(text, parent=True)[0] + ".displayArrow", False)
    camera, camera_shape = cmds.camera(name="swingLimitCamera", focalLength=30)
    cmds.viewPlace(camera_shape, eye=(-15, 12, 29), lookAt=(3.5, 1.5, 1.5))
    # 左側のHUD文字と重ならないよう、画面上で円錐を右へ寄せる。
    cmds.setAttr(camera_shape + ".horizontalFilmOffset", -0.32)
    cmds.setAttr(camera_shape + ".verticalFilmOffset", -0.04)
    window = cmds.window("asymSwingLimitValidationWindow", title="AsymmetricSwingLimit - quadrant ellipse", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("asymSwingLimitValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=True,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 8
    names = ["asymSwingLimitHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, source, output, owner, values, names


def evaluate_frame(frame, source, output, owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import SwingLimit
    phi, theta, twist, stage = pose(frame)
    euler = inputQuaternion(phi, theta, twist).asEulerRotation()
    cmds.setAttr(source + ".rotate", *[math.degrees(v) for v in euler])
    angle = owner.getPlug("swingAngle").get()
    limit = owner.getPlug("limitAngle").get()
    limited = owner.getPlug("limitedAngle").get()
    ratio = owner.getPlug("ratio").get()
    expected_limit = ellipseLimit(phi)
    expected_limited = SwingLimit.softAngle(theta, expected_limit, SOFTNESS)
    width = max(SOFTNESS * limit, SwingLimit.MINIMUM_SOFT_WIDTH)
    # 期待する出力: twist * slerp(I, swing, θ'/θ)。
    swing = inputQuaternion(phi, theta, 0)
    fraction = expected_limited / theta if theta > 1e-4 else 1.0
    expected = (om.MQuaternion(math.radians(twist), om.MVector(1, 0, 0))
                * om.MQuaternion.slerp(om.MQuaternion(), swing, fraction)).asMatrix()
    actual = om.MMatrix(cmds.getAttr(output + ".worldMatrix[0]"))
    matrix_error = max(abs(actual.getElement(r, c) - expected.getElement(r, c)) for r in range(3) for c in range(3))
    axis = om.MVector(actual.getElement(0, 0), actual.getElement(0, 1), actual.getElement(0, 2))
    output_bend = math.degrees(om.MVector(1, 0, 0).angle(axis))
    c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    a = LIMITS[0] if c > 0 else LIMITS[1]
    b = LIMITS[2] if s > 0 else LIMITS[3]
    quadrant = "{}Y/{}Z  a = {:.0f}  b = {:.0f}".format("+" if c > 0 else "-", "+" if s > 0 else "-", a, b)
    state = "INSIDE (output = input)" if theta <= limit - width + 1e-6 else "SOFT ZONE -> approaches L, never exceeds"
    values[:] = [
        "RED = input  GREEN = limited output  YELLOW = limit L  GREY = soft start L - w",
        "STAGE: " + stage,
        "fixed: l1+ = 80  l1- = 30 (Y)  l2+ = 55  l2- = 20 (Z) deg  softness = 0.25  w = 0.25 * L",
        "a = c>0 ? l1+ : l1-   b = s>0 ? l2+ : l2-   phi = {:5.1f} deg  c = {:+.2f}  s = {:+.2f}  ({})".format(
            phi % 360, c, s, quadrant),
        "L = a*b*r / sqrt((b*c)^2 + (a*s)^2) = {:6.2f} deg   excess = theta - theta' = {:6.2f} deg".format(
            limit, owner.getPlug("excessAngle").get()),
        "INPUT bend theta = {:6.2f} deg   input twist = {:+6.1f} deg (not limited)".format(angle, twist),
        "theta' = theta  if theta <= L - w ({:6.2f})  else (L-w) + w*(1 - exp(-(theta-(L-w))/w))".format(limit - width),
        "OUTPUT theta' = {:6.2f} deg   ratio = theta'/theta = {:5.3f}   {}".format(limited, ratio, state),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (abs(angle - theta) < 0.02 and (theta < 0.5 or abs(limit - expected_limit) < 0.02)
          and abs(limited - expected_limited) < 0.02 and abs(output_bend - expected_limited) < 0.05
          and matrix_error < 1e-3 and limited <= limit + 1e-4)
    return {"frame": frame, "presentation_stage": stage, "phi_degrees": phi, "input_bend_degrees": theta,
            "input_twist_degrees": twist, "dg_swing_angle": angle, "dg_limit_angle": limit,
            "dg_limited_angle": limited, "dg_ratio": ratio, "dg_excess_angle": owner.getPlug("excessAngle").get(), "expected_limit_angle": expected_limit,
            "expected_limited_angle": expected_limited, "output_bend_degrees": output_bend,
            "matrix_error": matrix_error, "ok": ok}


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
        panel, source, output, owner, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("AsymmetricSwingLimit: 象限ごとの楕円コーンのソフトなスイング制限", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, source, output, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "asymmetric-swing-limit.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-asymmetric-swing-limit.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("asymmetric-swing-limit-%Y%m%d-%H%M%S")
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
