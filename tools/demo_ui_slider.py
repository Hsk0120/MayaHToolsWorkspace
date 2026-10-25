"""UiSliderの、枠の中のスライダーと方向・角ごとの重みを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_ui_slider.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 30
SIZE = 2.0
CENTER = (0.0, 10.0)
WEIGHTS = ("right", "left", "up", "down", "upRight", "upLeft", "downRight", "downLeft")
PLACES = {"right": (1, 0), "left": (-1, 0), "up": (0, 1), "down": (0, -1),
          "upRight": (1, 1), "upLeft": (-1, 1), "downRight": (1, -1), "downLeft": (-1, -1)}
# (要求する横・縦の位置(sizeを1とする), 次の姿勢へ向かう段階名)。枠を超える入力と、枠の中への復帰を含む。
POSES = [
    (0.0, 0.0, "1 CENTER -> RIGHT"),
    (1.0, 0.0, "2 RIGHT -> UP RIGHT CORNER"),
    (1.0, 1.0, "3 PUSH PAST THE CORNER (CLAMPED)"),
    (1.7, 1.5, "4 BACK INSIDE -> UP"),
    (0.0, 0.8, "5 UP -> LEFT"),
    (-1.0, 0.3, "6 LEFT -> DOWN LEFT CORNER"),
    (-0.8, -1.0, "7 PUSH PAST THE BOTTOM (CLAMPED)"),
    (0.2, -1.8, "8 BACK -> CENTER"),
    (0.0, 0.0, "8 BACK -> CENTER"),
    (0.0, 0.0, "8 BACK -> CENTER"),
]
FRAMES = SEGMENT * (len(POSES) - 1) + 24


def pose(frame):
    """フレームの要求する位置をsmoothstepで補間して返す。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    x = POSES[index][0] + (POSES[index + 1][0] - POSES[index][0]) * weight
    y = POSES[index][1] + (POSES[index + 1][1] - POSES[index][1]) * weight
    return x, y, POSES[index][2]


def expected_outputs(x, y):
    """要求した位置から、枠で止まった位置と重みを実装とは独立に求める。"""
    x, y = max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y))
    right, left, up, down = max(x, 0.0), max(-x, 0.0), max(y, 0.0), max(-y, 0.0)
    return x, y, {"right": right, "left": left, "up": up, "down": down, "upRight": up * right,
                  "upLeft": up * left, "downRight": down * right, "downLeft": down * left}


def _shader(name, color):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import UiSlider
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    # 枠(灰色の4本の棒)。パネルごと少し傾けて、親の空間で読むことを示す。
    panelGroup = cmds.createNode("transform", name="facePanel_GRP")
    cmds.setAttr(panelGroup + ".translate", CENTER[0], CENTER[1], 0)
    cmds.setAttr(panelGroup + ".rotateZ", 8)
    gray = _shader("frameGray", (0.55, 0.55, 0.6))
    for index, (width, height, x, y) in enumerate((
            (2 * SIZE + 0.2, 0.1, 0, SIZE), (2 * SIZE + 0.2, 0.1, 0, -SIZE),
            (0.1, 2 * SIZE + 0.2, SIZE, 0), (0.1, 2 * SIZE + 0.2, -SIZE, 0))):
        bar = cmds.polyCube(name="frame{}_GEO".format(index), width=width, height=height, depth=0.1)[0]
        cmds.parent(bar, panelGroup, relative=True)
        cmds.setAttr(bar + ".translate", x, y, 0)
        cmds.sets(bar, edit=True, forceElement=gray)
    control = cmds.createNode("transform", name="slider_CTRL", parent=panelGroup)
    knob = cmds.polyCylinder(name="slider_GEO", radius=0.35, height=0.3, axis=(0, 0, 1))[0]
    cmds.parent(knob, control, relative=True)
    cmds.sets(knob, edit=True, forceElement=_shader("knobYellow", (0.95, 0.8, 0.1)))
    # 要求した位置(枠の外へ出ることがある)を示す赤い小球。
    request = cmds.createNode("transform", name="request_POS", parent=panelGroup)
    ball = cmds.polySphere(name="request_GEO", radius=0.18)[0]
    cmds.parent(ball, request, relative=True)
    cmds.sets(ball, edit=True, forceElement=_shader("requestRed", (0.9, 0.15, 0.1)))
    graph = UiSlider.create(control, name="uiSlider", size=SIZE)
    owner = graph.container
    green = _shader("weightGreen", (0.15, 0.8, 0.25))
    for attr in WEIGHTS:
        holder = cmds.createNode("transform", name=attr + "_GRP", parent=panelGroup)
        x, y = PLACES[attr]
        cmds.setAttr(holder + ".translate", x * (SIZE + 1.0), y * (SIZE + 1.0), 0)
        sphere = cmds.polySphere(name=attr + "_GEO", radius=0.55)[0]
        cmds.parent(sphere, holder, relative=True)
        cmds.sets(sphere, edit=True, forceElement=green)
        for axis in "XYZ":
            owner.getPlug(attr).connectTo(holder + ".scale" + axis)
    camera, camera_shape = cmds.camera(name="uiSliderCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(0, 9.2, 26), lookAt=(0, 9.2, 0))
    window = cmds.window("uiSliderValidationWindow", title="UiSlider - face panel slider",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("uiSliderValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["uiSliderHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"owner": owner, "control": control, "request": request}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """要求した位置へコントロールを動かし、枠で止まった位置とDGの重みを独立に求めた値と比較した診断を返す。"""
    from maya import cmds
    x, y, stage = pose(frame)
    owner, control, request = scene["owner"], scene["control"], scene["request"]
    cmds.setAttr(request + ".translate", x * SIZE, y * SIZE, 0.3)
    cmds.setAttr(control + ".translate", x * SIZE, y * SIZE, 0)
    expectedX, expectedY, expected = expected_outputs(x, y)
    translate = cmds.getAttr(control + ".translate")[0]
    actualX, actualY = owner.getPlug("x").get(), owner.getPlug("y").get()
    actual = {name: owner.getPlug(name).get() for name in WEIGHTS}
    limitError = max(abs(translate[0] - expectedX * SIZE), abs(translate[1] - expectedY * SIZE), abs(translate[2]))
    weightError = max([abs(actual[name] - expected[name]) for name in WEIGHTS]
                      + [abs(actualX - expectedX), abs(actualY - expectedY)])
    outside = abs(x) > 1.0 or abs(y) > 1.0
    values[:] = [
        "YELLOW = slider control (stops at the frame)   RED = requested position   GREEN ball size = weight",
        "STAGE: " + stage + ("   << REQUEST OUTSIDE THE FRAME >>" if outside else ""),
        "fixed: size = {:.1f} cm   rangeX = rangeY = (-1, 1)   (translate in the panel space, rest = 0)".format(SIZE),
        "x = clamp(tx/size, -1, 1)  y = clamp(ty/size, -1, 1)  right = max(x,0)  left = max(-x,0)"
        "  upRight = up*right ...",
        "INPUT requested x = {:+.3f}  y = {:+.3f}   control tx = {:+.3f} cm  ty = {:+.3f} cm (transformLimits)".format(
            x, y, translate[0], translate[1]),
        "OUTPUT x {:+.3f} y {:+.3f}  ".format(actualX, actualY)
        + "  ".join("{} {:.3f}".format(name, actual[name]) for name in WEIGHTS),
        "CHECK limit error = {:.7f} cm   weight error = {:.7f}".format(limitError, weightError),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = limitError < 1e-4 and weightError < 1e-5
    return {"frame": frame, "presentation_stage": stage, "requested": [x, y], "translate": list(translate),
            "outputs": dict(actual, x=actualX, y=actualY), "limit_error": limitError, "weight_error": weightError,
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
        panel, scene, values, names = buildScene()
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("UiSlider: 枠の中のスライダーと方向ごとの重み", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "ui_slider.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-ui-slider.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("ui-slider-%Y%m%d-%H%M%S")
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
