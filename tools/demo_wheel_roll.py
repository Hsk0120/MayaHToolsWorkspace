"""WheelRollの車体の前進距離に合わせた車輪の転がりを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_wheel_roll.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RADIUS = 3.0
WHEELBASE = 12.0
SEGMENT = 36
# (車体のtranslateZ[cm], translateX[cm、横移動], 次の姿勢へ向かう段階名)。基準は0。
POSES = [
    (0, 0, "1 REST"),
    (0, 0, "2 DRIVE FORWARD 2*pi*r = 18.85 cm: EXACTLY 1 TURN"),
    (2 * math.pi * RADIUS, 0, "3 DRIVE FORWARD MORE"),
    (32, 0, "4 REVERSE: WHEELS SPIN BACK"),
    (8, 0, "5 SIDEWAYS MOVE: NOT COUNTED AS TRAVEL"),
    (8, 6, "6 RETURN TO REST"),
    (0, 0, "6 RETURN TO REST"),
    (0, 0, "6 RETURN TO REST"),
]


def pose(frame):
    """フレームの入力(z, x, 段階名)をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:2], POSES[index + 1][:2])]
    return values + [POSES[index][2]]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _wheelGeometry(name, parent, tire, spoke, x):
    """parent下に、X軸を車軸とするタイヤと、回転がわかる十字のスポークを作る。xは車軸方向へずらす量。"""
    from maya import cmds
    wheel = cmds.polyCylinder(name=name, axis=(1, 0, 0), height=0.8, radius=RADIUS, subdivisionsX=32)[0]
    cmds.setAttr(wheel + ".translateX", x)
    cmds.parent(wheel, parent, relative=True)
    cmds.sets(wheel, edit=True, forceElement=tire)
    for index, size in enumerate(((0.3, RADIUS * 1.9, 0.5), (0.3, 0.5, RADIUS * 1.9))):
        bar = cmds.polyCube(name="{}_spoke{}".format(name, index), width=size[0], height=size[1], depth=size[2])[0]
        cmds.setAttr(bar + ".translateX", x + 0.5)
        cmds.parent(bar, parent, relative=True)
        cmds.sets(bar, edit=True, forceElement=spoke)
    # 黄色の印: タイヤの真下(生成時の接地点)。
    mark = cmds.polySphere(name=name + "_mark", radius=0.45)[0]
    cmds.setAttr(mark + ".translate", x + 0.6, -RADIUS, 0)
    cmds.parent(mark, parent, relative=True)
    return mark


def buildScene():
    """検証シーンを作り、(panel, 車体, 入力の車輪, 出力の車輪, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import WheelRoll
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    world = cmds.createNode("transform", name="world_GRP")
    vehicle = cmds.createNode("transform", name="vehicle_CTL", parent=world)
    grey = _shader("bodyGrey", (0.55, 0.55, 0.6))
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.55)
    green = _shader("outputGreen", (0.1, 0.75, 0.2))
    dark = _shader("spokeDark", (0.08, 0.1, 0.12))
    yellow = _shader("markYellow", (1.0, 0.85, 0.1))
    ground = cmds.polyCube(name="ground_GEO", width=4, height=0.2, depth=80)[0]
    cmds.setAttr(ground + ".translate", 0, -0.1, 18)
    cmds.parent(ground, world, relative=True)
    cmds.sets(ground, edit=True, forceElement=grey)
    body = cmds.polyCube(name="body_GEO", width=3, height=3, depth=WHEELBASE + 7)[0]
    cmds.setAttr(body + ".translate", -2.5, RADIUS + 2.5, 0)
    cmds.parent(body, vehicle, relative=True)
    cmds.sets(body, edit=True, forceElement=grey)
    inputs, outputs, owners = [], [], []
    for label, z in (("rear", -WHEELBASE / 2), ("front", WHEELBASE / 2)):
        wheel = cmds.createNode("joint", name="input_{}Wheel_JNT".format(label), parent=vehicle)
        cmds.setAttr(wheel + ".translate", 0, RADIUS, z)
        owner = WheelRoll.create(vehicle, wheel, RADIUS, name=label + "WheelRoll", forwardAxis="z", spinAxis="x",
                                 direction=1).container
        out = cmds.createNode("transform", name="output_{}Wheel_GRP".format(label), parent=vehicle)
        owner.getPlug("matrix").connectTo(out + ".offsetParentMatrix")
        # 赤(半透明)=入力の車輪(回らない)を奥、緑=出力の車輪を手前に置く。
        for node in (_wheelGeometry("input{}Wheel_GEO".format(label.title()), wheel, red, red, -1.2),):
            cmds.sets(node, edit=True, forceElement=red)
        mark = _wheelGeometry("output{}Wheel_GEO".format(label.title()), out, green, dark, 0.6)
        cmds.sets(mark, edit=True, forceElement=yellow)
        inputs.append(wheel)
        outputs.append(out)
        owners.append(owner)
    camera, camera_shape = cmds.camera(name="wheelCamera", focalLength=35)
    # 横(+X)から、前後40cmの移動範囲全体を見る位置に固定する。
    cmds.viewPlace(camera_shape, eye=(62, 8, 14), lookAt=(0, 3, 14))
    cmds.setAttr(camera_shape + ".verticalFilmOffset", -0.12)
    window = cmds.window("wheelRollValidationWindow", title="WheelRoll - wheels roll without slipping",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("wheelRollValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["wheelRollHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, vehicle, inputs, outputs, owners, values, names


def evaluate_frame(frame, vehicle, inputs, outputs, owners, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import WheelRoll
    z, x, stage = pose(frame)
    expected_spin = WheelRoll.spinAngle(z, RADIUS)
    errors, slips = [], []
    # 接地点の滑り: 車体を微小量だけ前へ動かし、その時点で真下にある点(車輪のローカルで求める)の移動量を測る。
    epsilon = 1e-3
    for out in outputs:
        cmds.setAttr(vehicle + ".translate", x, 0, z)
        world = om.MMatrix(cmds.getAttr(out + ".worldMatrix[0]"))
        center = om.MPoint(world[12], world[13], world[14])
        bottom_world = center + om.MVector(0, -RADIUS, 0)
        bottom_local = bottom_world * world.inverse()
        cmds.setAttr(vehicle + ".translate", x, 0, z + epsilon)
        moved = bottom_local * om.MMatrix(cmds.getAttr(out + ".worldMatrix[0]"))
        slips.append((moved - bottom_world).length() / epsilon)
    cmds.setAttr(vehicle + ".translate", x, 0, z)
    dg = []
    for owner, wheel, out in zip(owners, inputs, outputs):
        travel, spin = owner.getPlug("travel").get(), owner.getPlug("spin").get()
        dg.append((travel, spin, owner.getPlug("revolutions").get()))
        expected = (om.MEulerRotation(math.radians(expected_spin), 0, 0).asMatrix()
                    * om.MMatrix(cmds.getAttr(wheel + ".matrix")))
        actual = om.MMatrix(cmds.getAttr(out + ".offsetParentMatrix"))
        errors.append(max(abs(actual[i] - expected[i]) for i in range(16)))
    values[:] = [
        "GREEN = output wheels (roll)   RED (transparent) = input wheels (no roll)   YELLOW = rim mark   GREY = body",
        "STAGE: " + stage,
        "fixed: radius r = 3 cm   forward = parent +Z (left in view)   spin axis = wheel X   direction = +1   (travel from rest, cm)",
        "travel = (T - T0) . forward      spin = travel / r * 180/pi      revolutions = spin / 360",
        "INPUT vehicle translate Z = {:+7.3f} cm   X (sideways) = {:+5.2f} cm".format(z, x),
        "OUTPUT travel = {:+7.3f} cm   spin = {:+8.2f} deg   revolutions = {:+6.3f}".format(*dg[0]),
        "CHECK |spin - formula| = {:.4f} deg   matrix error = {:.1e}   contact slip ratio = {:.4f} / {:.4f}".format(
            abs(dg[0][1] - expected_spin), max(errors), *slips),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (all(abs(t - z) < 1e-3 and abs(s - expected_spin) < 0.01 for t, s, _ in dg) and max(errors) < 1e-4
          and max(slips) < 0.01)
    return {"frame": frame, "presentation_stage": stage, "input_translate_cm": [x, 0, z],
            "dg_travel_spin_revolutions": dg, "expected_spin_degrees": expected_spin,
            "matrix_errors": errors, "contact_slip_ratio": slips, "ok": ok}


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
        panel, vehicle, inputs, outputs, owners, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("WheelRoll: 車体の前進距離に合わせた車輪の転がり", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, vehicle, inputs, outputs, owners, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "wheel-roll.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-wheel-roll.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("wheel-roll-%Y%m%d-%H%M%S")
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
