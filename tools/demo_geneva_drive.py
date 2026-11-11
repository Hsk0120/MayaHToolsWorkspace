"""GenevaDriveの間欠回転(ゼネバ機構)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_geneva_drive.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 60
SLOTS = 4
CENTER = 6.0
PIN = CENTER * math.sin(math.pi / SLOTS)
WHEEL = CENTER * math.cos(math.pi / SLOTS)
# (駆動輪の角度[度], 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, "1 REST (DWELL, WHEEL LOCKED)"),
    (0.0, "2 TURN THE DRIVER TO +360 deg (ONE INDEX STEP)"),
    (360.0, "3 TURN TO +720 deg (SECOND STEP)"),
    (720.0, "4 REVERSE TO +450 deg (PIN BACK IN THE SLOT)"),
    (450.0, "5 RETURN TO REST (UNWIND BOTH STEPS)"),
    (0.0, "5 RETURN TO REST (UNWIND BOTH STEPS)"),
    (0.0, "5 RETURN TO REST (UNWIND BOTH STEPS)"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    return POSES[index][0] + (POSES[index + 1][0] - POSES[index][0]) * weight, POSES[index][1]


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


def _cylinder(name, parent, radius, height, position, group):
    """Z軸向きの円柱を親の下に置く。"""
    from maya import cmds
    body = cmds.polyCylinder(name=name, radius=radius, height=height, axis=(0, 0, 1), subdivisionsX=48)[0]
    cmds.parent(body, parent, relative=True)
    cmds.setAttr(body + ".translate", *position)
    cmds.sets(body, edit=True, forceElement=group)
    return body


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import GenevaDrive
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("driverRed", (0.9, 0.15, 0.1)), "green": _shader("wheelGreen", (0.15, 0.75, 0.25)),
              "slot": _shader("slotDark", (0.05, 0.12, 0.06)), "pin": _shader("pinYellow", (1.0, 0.85, 0.1)),
              "mark": _shader("markWhite", (0.95, 0.95, 0.9))}
    # 従動輪(緑): 原点の円板と、溝の向き(ローカルの 45° + 90°·j)の暗い溝、白い目印の溝。
    wheel = cmds.createNode("transform", name="wheel_GENEVA")
    _cylinder("wheel_GEO", wheel, WHEEL, 0.4, (0, 0, 0), groups["green"])
    inner = CENTER - PIN - 0.3
    for index in range(SLOTS):
        pivot = cmds.createNode("transform", name="wheel_slotPivot{}".format(index), parent=wheel)
        cmds.setAttr(pivot + ".rotateZ", 180.0 / SLOTS + 360.0 * index / SLOTS)
        slot = cmds.polyCube(name="wheel_slot{}".format(index), width=WHEEL - inner + 0.2, height=0.55,
                             depth=0.5)[0]
        cmds.parent(slot, pivot, relative=True)
        cmds.setAttr(slot + ".translate", (WHEEL + inner) / 2.0, 0, 0.05)
        cmds.sets(slot, edit=True, forceElement=groups["mark" if index == 0 else "slot"])
    # 駆動輪(赤): 軸間距離 c の位置。ピン(黄)は生成時に従動輪と反対側(+X)。
    driver = cmds.createNode("transform", name="driver_GENEVA")
    cmds.setAttr(driver + ".translateX", CENTER)
    _cylinder("driver_GEO", driver, PIN * 0.55, 0.4, (0, 0, -0.5), groups["red"])
    arm = cmds.polyCube(name="driver_arm", width=PIN, height=0.4, depth=0.3)[0]
    cmds.parent(arm, driver, relative=True)
    cmds.setAttr(arm + ".translate", PIN / 2.0, 0, -0.4)
    cmds.sets(arm, edit=True, forceElement=groups["red"])
    pin = cmds.createNode("transform", name="driver_PIN", parent=driver)
    cmds.setAttr(pin + ".translateX", PIN)
    _cylinder("driver_pinGEO", pin, 0.22, 1.2, (0, 0, 0), groups["pin"])
    graph = GenevaDrive.create(driver, wheel, SLOTS, name="genevaDrive", axis="z")
    owner = graph.container
    camera, camera_shape = cmds.camera(name="genevaCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(3.6, -3.2, 38), lookAt=(3.6, -3.2, 0))
    window = cmds.window("genevaValidationWindow", title="GenevaDrive - intermittent indexing", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("genevaValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("geneva", 8)
    scene = {"owner": owner, "wheel": wheel, "driver": driver, "pin": pin}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、従動輪の回転を式と、ピンと溝の向きの一致で比較した診断を返す。"""
    from maya import cmds
    import maya.api.OpenMaya as om
    from mlrig.setups import GenevaDrive
    angle, stage = pose(frame)
    owner, wheel = str(scene["owner"]), scene["wheel"]
    cmds.setAttr(scene["driver"] + ".rotateZ", angle)
    expected = GenevaDrive.motion(math.radians(angle), SLOTS)
    rotate = cmds.getAttr(wheel + ".rotateZ")
    index = cmds.getAttr(owner + ".indexAngle")
    engaged = cmds.getAttr(owner + ".engaged")
    speed = cmds.getAttr(owner + ".speedRatio")
    crank = cmds.getAttr(owner + ".crankAngle")
    step = cmds.getAttr(owner + ".step")
    error = max(abs(rotate + math.degrees(expected["indexAngle"])), abs(index - math.degrees(expected["indexAngle"])),
                abs(speed - expected["speedRatio"]))
    # 試験側で独立に: 溝に入っている間、従動輪のローカルで見たピンが溝の線(45° + 90°·j)の上にあるか。
    point = om.MPoint(cmds.xform(scene["pin"], query=True, worldSpace=True, translation=True))
    local = point * om.MMatrix(cmds.getAttr(wheel + ".worldInverseMatrix[0]"))
    pitch = 360.0 / SLOTS
    offset = math.degrees(math.atan2(local.y, local.x)) - 180.0 / SLOTS
    slot_error = abs((offset + pitch / 2.0) % pitch - pitch / 2.0) if engaged > 0.5 else 0.0
    beta = math.degrees(expected["indexAngle"]) - step * pitch - 180.0 / SLOTS
    ratio = math.sin(math.pi / SLOTS)
    values[:] = [
        "RED = driver (INPUT, YELLOW pin)   GREEN = 4-slot Geneva wheel (OUTPUT, WHITE = marked slot)   angles in deg",
        "STAGE: " + stage,
        "fixed: n = {} slots   lambda = r/c = sin(180/n) = {:.4f}   alpha0 = 90 - 180/n = {:.0f} deg   c = {:.0f} cm".format(
            SLOTS, ratio, 90.0 - 180.0 / SLOTS, CENTER),
        "k = floor(theta/360)   alpha = theta - 180 - 360k   alpha' = clamp(alpha, -alpha0, alpha0)   "
        "beta = atan2(lambda sin alpha', 1 - lambda cos alpha')",
        "phi = 360k/n + 180/n + beta   wheel = -phi   speedRatio = lambda(cos alpha' - lambda) / (1 + lambda^2 - 2 lambda cos alpha')",
        "INPUT theta = {:7.2f} deg   k = {:2.0f}   alpha = {:7.2f} deg   {}".format(
            angle, step, crank, "ENGAGED (pin in slot)" if engaged > 0.5 else "DWELL (wheel locked)"),
        "OUTPUT (DG) wheel rotateZ = {:8.3f} deg   indexAngle = {:8.3f}   beta = {:7.3f}   speedRatio = {:6.3f}".format(
            rotate, index, beta, speed),
        "CHECK max |DG - formula| = {:.6f}   pin-to-slot angle error = {:.5f} deg".format(error, slot_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and slot_error < 1e-3
    return {"frame": frame, "presentation_stage": stage, "input": {"driver": angle},
            "output": {"rotate": rotate, "indexAngle": index, "engaged": engaged, "speedRatio": speed, "step": step},
            "error": error, "slot_error": slot_error, "ok": ok}


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
        folder = recordVideo("GenevaDrive: ゼネバ機構の間欠回転", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "geneva_drive.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-geneva-drive.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("geneva-drive-%Y%m%d-%H%M%S")
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
