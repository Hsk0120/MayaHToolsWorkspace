"""FourBarLinkageのクランク・カプラー・ロッカーの連動を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_four_bar_linkage.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
CRANK = 2.0
GROUND = 6.0
COUPLER = 5.0
ROCKER = 4.0
START = 60.0
# (クランクの角度[度], couplerLength[cm], 次の姿勢へ向かう段階名)。
POSES = [
    (START, COUPLER, "1 REST"),
    (START, COUPLER, "2 TURN THE CRANK ONE REVOLUTION"),
    (START + 360.0, COUPLER, "3 TURN THE CRANK TO 180 deg"),
    (540.0, COUPLER, "4 SHORTEN couplerLength 5 -> 2.5 cm (b + c < d: OUT OF REACH)"),
    (540.0, 2.5, "5 RETURN couplerLength TO 5 cm (BACK IN REACH)"),
    (540.0, COUPLER, "6 TURN BACK TO THE REST ANGLE"),
    (START + 360.0, COUPLER, "7 HOLD"),
    (START + 360.0, COUPLER, "7 HOLD"),
]


def expected_joint(degrees, coupler):
    """関節 C の位置と届かない量を、ロッカーの角度 ψ の閉じた式(K1 cosψ + K2 sinψ = K3)で求める。

    届かない場合は B から D への線の上で B から b の点(制限した値)を返す。
    """
    angle = math.radians(degrees)
    bx, by = CRANK * math.cos(angle), CRANK * math.sin(angle)
    d = math.hypot(GROUND - bx, by)
    excess = max(d - (coupler + ROCKER), abs(coupler - ROCKER) - d, 0.0)
    if excess > 0.0:
        sign = 1.0 if d * d + coupler * coupler - ROCKER * ROCKER >= 0.0 else -1.0
        return (bx + sign * coupler * (GROUND - bx) / d, by + sign * coupler * (0.0 - by) / d), excess
    k1 = 2.0 * ROCKER * (GROUND - bx)
    k2 = 2.0 * ROCKER * (0.0 - by)
    k3 = coupler * coupler - ROCKER * ROCKER - (GROUND - bx) ** 2 - by ** 2
    base = math.atan2(k2, k1)
    spread = math.acos(max(-1.0, min(1.0, k3 / math.hypot(k1, k2))))
    for psi in (base + spread, base - spread):
        cx, cy = GROUND + ROCKER * math.cos(psi), ROCKER * math.sin(psi)
        if (GROUND - bx) * (cy - by) - (0.0 - by) * (cx - bx) > 0.0:
            return (cx, cy), 0.0
    raise RuntimeError("no branch")


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:2], POSES[index + 1][:2])]
    return values[0], values[1], POSES[index][2]


def _shader(name, color):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return shader, group


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


def _ball(name, radius, group, parent=None, translate=(0, 0, 0)):
    """単色の球を作る。"""
    from maya import cmds
    ball = cmds.polySphere(name=name, radius=radius)[0]
    if parent is not None:
        ball = cmds.parent(ball, parent, relative=True)[0]
    cmds.setAttr(ball + ".translate", *translate)
    cmds.sets(ball, edit=True, forceElement=group)
    return ball


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import FourBarLinkage
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    _, green = _shader("linkGreen", (0.15, 0.75, 0.25))
    _, gray = _shader("groundGray", (0.55, 0.56, 0.6))
    _, blue = _shader("crankBlue", (0.25, 0.45, 0.85))
    joint_shader, joint_group = _shader("jointWhite", (0.95, 0.95, 0.95))
    (cx, cy), _ = expected_joint(START, COUPLER)
    base = cmds.createNode("transform", name="base")
    crank = cmds.createNode("transform", name="crank", parent=base)
    pin = cmds.createNode("transform", name="crankPin", parent=crank)
    cmds.setAttr(pin + ".translateX", CRANK)
    cmds.setAttr(crank + ".rotateZ", START)
    rocker = cmds.createNode("transform", name="rocker_REST", parent=base)
    cmds.setAttr(rocker + ".translateX", GROUND)
    end = cmds.createNode("transform", name="joint_REST", parent=base)
    cmds.setAttr(end + ".translate", cx, cy, 0)
    graph = FourBarLinkage.create(pin, rocker, end, name="fourBarLinkage")
    owner = str(graph.container)
    # 青 = 入力のクランク。緑 = FourBarLinkageの出力(カプラーとロッカー)。灰 = 固定の支点と地面の棒。
    _box("crankArm", (CRANK, 0.4, 0.3), blue, crank, (CRANK / 2.0, 0, 0.2))
    _ball("crankPinGeo", 0.3, blue, pin)
    _ball("pivotA", 0.35, gray, None, (0, 0, 0))
    _ball("pivotD", 0.35, gray, None, (GROUND, 0, 0))
    _box("groundBar", (GROUND, 0.2, 0.2), gray, None, (GROUND / 2.0, -0.6, -0.3))
    coupler = cmds.createNode("transform", name="coupler_GREEN")
    coupler_geo = _box("couplerGeo", (1.0, 0.35, 0.3), green, coupler, (COUPLER / 2.0, 0, 0.5))
    cmds.setAttr(coupler_geo + ".scaleX", COUPLER)
    cmds.connectAttr(owner + ".couplerMatrix", coupler + ".offsetParentMatrix")
    rocker_out = cmds.createNode("transform", name="rocker_GREEN")
    arm = cmds.createNode("transform", name="rockerArm", parent=rocker_out)
    cmds.setAttr(arm + ".rotateZ", math.degrees(math.atan2(cy, cx - GROUND)))
    _box("rockerGeo", (ROCKER, 0.4, 0.3), green, arm, (ROCKER / 2.0, 0, 0.2))
    cmds.connectAttr(owner + ".rockerMatrix", rocker_out + ".offsetParentMatrix")
    joint = cmds.createNode("transform", name="joint_OUT")
    _ball("jointGeo", 0.32, joint_group, joint, (0, 0, 0.8))
    cmds.connectAttr(owner + ".jointMatrix", joint + ".offsetParentMatrix")
    camera, camera_shape = cmds.camera(name="fourBarCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(3.6, 0.2, 30.0), lookAt=(3.6, 0.2, 0))
    window = cmds.window("fourBarValidationWindow", title="FourBarLinkage - crank, coupler and rocker",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("fourBarValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("fourBar", 7)
    scene = {"owner": owner, "crank": crank, "pin": pin, "couplerGeo": coupler_geo, "jointShader": joint_shader}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、関節の位置を閉じた式と、棒の長さ・向き・届かない量と比べた診断を返す。"""
    from maya import cmds
    import maya.api.OpenMaya as om
    angle, coupler, stage = pose(frame)
    owner = scene["owner"]
    cmds.setAttr(scene["crank"] + ".rotateZ", angle)
    cmds.setAttr(owner + ".couplerLength", coupler)
    cmds.setAttr(scene["couplerGeo"] + ".scaleX", coupler)
    cmds.setAttr(scene["couplerGeo"] + ".translateX", coupler / 2.0)
    (ex, ey), expected_excess = expected_joint(angle, coupler)
    joint_matrix = om.MMatrix(cmds.getAttr(owner + ".jointMatrix"))
    rocker = om.MMatrix(cmds.getAttr(owner + ".rockerMatrix"))
    coupler_matrix = om.MMatrix(cmds.getAttr(owner + ".couplerMatrix"))
    pin = om.MMatrix(cmds.getAttr(scene["pin"] + ".worldMatrix[0]"))
    joint = om.MPoint(joint_matrix[12], joint_matrix[13], joint_matrix[14])
    pin_point = om.MPoint(pin[12], pin[13], pin[14])
    pivot = om.MPoint(GROUND, 0, 0)
    joint_error = (joint - om.MPoint(ex, ey, 0)).length()
    coupler_distance = (joint - pin_point).length()
    rocker_distance = (joint - pivot).length()
    excess = cmds.getAttr(owner + ".excess")
    mu = cmds.getAttr(owner + ".transmissionAngle")
    psi = math.degrees(math.atan2(joint.y, joint.x - GROUND))
    toward = (joint - pin_point).normal()
    aim_error = 1.0 - om.MVector(coupler_matrix[0], coupler_matrix[1], coupler_matrix[2]).normal() * toward
    pivot_error = (om.MPoint(rocker[12], rocker[13], rocker[14]) - pivot).length()
    out = expected_excess > 1e-9
    cmds.setAttr(scene["jointShader"] + ".color", *((0.95, 0.15, 0.15) if out else (0.95, 0.95, 0.95)),
                 type="double3")
    theta = angle % 360.0
    d = (pivot - pin_point).length()
    values[:] = [
        "BLUE = crank (input, rotateZ)   GREEN = FourBarLinkage output (coupler, rocker)   GRAY = fixed pivots A, D",
        "STAGE: " + stage + ("   >>> OUT OF REACH: joint RED <<<" if out else ""),
        "fixed: crank a = 2 cm   ground A-D = 6 cm   rockerLength c = 4 cm   branch = upper (left of B->D)",
        "C = B + x u + h (n x u)   x = (d^2 + b^2 - c^2) / 2d   h = sqrt(b^2 - x^2)   excess = max(d-(b+c), |b-c|-d, 0)",
        "INPUT crank theta = {:6.1f} deg   couplerLength b = {:5.2f} cm   d = |D - B| = {:6.3f} cm".format(
            theta, coupler, d),
        "OUTPUT rocker psi = {:7.2f} deg   transmission mu = {:7.2f} deg   |C-B| = {:6.3f}   |C-D| = {:6.3f}   "
        "excess = {:6.3f} cm".format(psi, mu, coupler_distance, rocker_distance, excess),
        "CHECK |C - formula| = {:.7f} cm   |excess - formula| = {:.7f} cm   coupler aim error = {:.7f}".format(
            joint_error, abs(excess - expected_excess), aim_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (joint_error < 1e-4 and abs(excess - expected_excess) < 1e-4 and aim_error < 1e-6 and pivot_error < 1e-4
          and abs(coupler_distance - coupler) < 1e-4 and (out or abs(rocker_distance - ROCKER) < 1e-4))
    return {"frame": frame, "presentation_stage": stage, "input": {"angle": angle, "couplerLength": coupler},
            "joint_error": joint_error, "excess": excess, "expected_excess": expected_excess,
            "transmission_angle": mu, "rocker_angle": psi, "aim_error": aim_error, "ok": ok}


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
        folder = recordVideo("FourBarLinkage: 四節リンク", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "four_bar_linkage.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-four-bar-linkage.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("four-bar-linkage-%Y%m%d-%H%M%S")
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
