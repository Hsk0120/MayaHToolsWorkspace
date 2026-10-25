"""OutlineBankの輪郭の縁で傾く支点を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_outline_bank.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 36
HALF = 2.0
HEIGHT = 3.0
# (rotateX[度], rotateZ[度], 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, 0.0, "1 REST"),
    (0.0, 0.0, "2 TILT TOWARD +X (rotateZ -25)"),
    (0.0, -25.0, "3 TILT DIAGONAL (+X and +Z)"),
    (20.0, -20.0, "4 TILT TOWARD -Z (rotateX -25)"),
    (-25.0, 0.0, "5 TILT TOWARD -X (rotateZ +25)"),
    (0.0, 25.0, "6 RETURN TO REST"),
    (0.0, 0.0, "6 RETURN TO REST"),
    (0.0, 0.0, "6 RETURN TO REST"),
]


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


def _box(name, group, x):
    """底の中心がtransformの原点にある箱(一辺 2*HALF、高さ HEIGHT)を作る。"""
    from maya import cmds
    root = cmds.createNode("transform", name=name)
    cmds.setAttr(root + ".translateX", x)
    box = cmds.polyCube(name=name + "_geo", width=2 * HALF, height=HEIGHT, depth=2 * HALF)[0]
    cmds.parent(box, root, relative=True)
    cmds.setAttr(box + ".translateY", HEIGHT / 2)
    cmds.sets(box, edit=True, forceElement=group)
    return root


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import OutlineBank
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    green, red = _shader("bankGreen", (0.15, 0.75, 0.25)), _shader("centerRed", (0.85, 0.15, 0.1))
    floor = cmds.polyPlane(name="floor_GEO", width=26, height=14, subdivisionsX=13, subdivisionsY=7)[0]
    cmds.setAttr(floor + ".translate", -3.5, -0.02, 0)
    cmds.sets(floor, edit=True, forceElement=_shader("floorBlue", (0.35, 0.45, 0.6)))
    # 黄 = 底の輪郭の曲線と支点。緑 = OutlineBank(傾けた側の縁が支点)。赤 = 比較用に底の中心で回すだけ(床へ潜る)。
    corners = [(HALF, 0, HALF), (HALF, 0, -HALF), (-HALF, 0, -HALF), (-HALF, 0, HALF), (HALF, 0, HALF)]
    outline = cmds.curve(degree=1, point=corners, name="base_OUTLINE")
    shape = cmds.listRelatives(outline, shapes=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideColor", 17)
    cmds.setAttr(shape + ".lineWidth", 4)
    control = cmds.createNode("transform", name="bank_CTRL")
    graph = OutlineBank.create(control, outline, name="outlineBank")
    owner = graph.container
    box = _box("box_GREEN", green, 0.0)
    cmds.connectAttr(str(owner) + ".matrix", box + ".offsetParentMatrix")
    compare = _box("box_RED", red, -7.0)
    marker = cmds.polySphere(name="pivot_MARKER", radius=0.18)[0]
    cmds.sets(marker, edit=True, forceElement=_shader("pivotYellow", (0.95, 0.85, 0.1)))
    cmds.connectAttr(str(owner) + ".pivot", marker + ".translate")
    camera, camera_shape = cmds.camera(name="outlineBankCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(6.0, 11.0, 19.0), lookAt=(-3.5, 1.2, 0.0))
    window = cmds.window("outlineBankValidationWindow", title="OutlineBank - pivot on the base outline",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("outlineBankValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("outlineBank", 7)
    scene = {"owner": owner, "control": control, "compare": compare}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、行列を式と、支点を輪郭と(傾けても動かないこと)比べた診断を返す。"""
    from maya import cmds
    import maya.api.OpenMaya as om
    from mlrig.setups import OutlineBank
    rx, rz, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(scene["control"] + ".rotate", rx, 0, rz)
    cmds.setAttr(scene["compare"] + ".rotate", rx, 0, rz)
    rotation = om.MEulerRotation(math.radians(rx), 0.0, math.radians(rz)).asMatrix()
    matrix = om.MMatrix(cmds.getAttr(owner + ".matrix"))
    pivot = om.MPoint(cmds.getAttr(owner + ".pivot")[0])
    expected = om.MMatrix(list(OutlineBank.localMatrix(rotation, pivot)))
    error = max(abs(matrix[i] - expected[i]) for i in range(16))
    on_outline = abs(max(abs(pivot.x), abs(pivot.z)) - HALF) + abs(pivot.y)
    fixed = (pivot * matrix - pivot).length()
    lowest = min((om.MPoint(x, 0, z) * matrix).y for x in (-HALF, HALF) for z in (-HALF, HALF))
    lowest_red = min((om.MPoint(x, 0, z) * rotation).y for x in (-HALF, HALF) for z in (-HALF, HALF))
    values[:] = [
        "GREEN = OutlineBank (pivot slides on the base outline, yellow)   RED = rotate about the base center only (sinks)",
        "STAGE: " + stage,
        "fixed: square outline half size = {:.1f} cm   up = Y   reach = {:.1f} cm   floor = Y 0".format(
            HALF, cmds.getAttr(owner + ".reach")),
        "d = normalize(flatten(Y * R))   pivot p = nearest outline point to reach * d   matrix = T(-p) * R * T(p)",
        "INPUT rotateX = {:7.2f} deg   rotateZ = {:7.2f} deg".format(rx, rz),
        "OUTPUT pivot = ({:6.3f}, {:6.3f}, {:6.3f}) cm   lowest corner Y: GREEN {:7.3f}  RED {:7.3f} cm".format(
            pivot.x, pivot.y, pivot.z, lowest, lowest_red),
        "CHECK max |matrix - formula| = {:.7f}   |pivot off outline| = {:.7f}   |pivot moved| = {:.7f} cm".format(
            error, on_outline, fixed),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and on_outline < 1e-4 and fixed < 1e-4
    return {"frame": frame, "presentation_stage": stage, "input": {"rotateX": rx, "rotateZ": rz},
            "pivot": [pivot.x, pivot.y, pivot.z], "error": error, "on_outline": on_outline, "fixed": fixed,
            "lowest_corner": lowest, "lowest_corner_center_pivot": lowest_red, "ok": ok}


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
        folder = recordVideo("OutlineBank: 輪郭の縁で傾く支点", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "outline_bank.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-outline-bank.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("outline-bank-%Y%m%d-%H%M%S")
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
