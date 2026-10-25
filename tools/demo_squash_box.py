"""SquashBoxの4辺からの潰しと伸ばしを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_squash_box.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEIGHT = 4.0
WIDTH = 3.0
DEPTH = 2.0
SEGMENT = 30
SIDES = ("top", "bottom", "outer", "inner")
# (top, bottom, outer, inner[cm], volume, 次の姿勢へ向かう段階名)。基準は全て0・volume 1。
POSES = [
    ((0, 0, 0, 0), 1.0, "1 REST"),
    ((0, 0, 0, 0), 1.0, "2 top +2: STRETCH UP FROM THE BOTTOM, THINNER"),
    ((2, 0, 0, 0), 1.0, "3 top -1.5: SQUASH DOWN, WIDER"),
    ((-1.5, 0, 0, 0), 1.0, "4 bottom +1.5: STRETCH DOWN FROM THE TOP"),
    ((0, 1.5, 0, 0), 1.0, "5 outer +1.2: STRETCH OUT FROM THE INNER SIDE"),
    ((0, 0, 1.2, 0), 1.0, "6 inner -0.8 WITH top +1: COMBINED"),
    ((1, 0, 0, -0.8), 1.0, "7 volume 1 -> 0: NO THINNING"),
    ((1, 0, 0, -0.8), 0.0, "8 RETURN TO REST"),
    ((0, 0, 0, 0), 1.0, "8 RETURN TO REST"),
    ((0, 0, 0, 0), 1.0, "8 RETURN TO REST"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    sides = [a + (b - a) * weight for a, b in zip(POSES[index][0], POSES[index + 1][0])]
    volume = POSES[index][1] + (POSES[index + 1][1] - POSES[index][1]) * weight
    return sides, volume, POSES[index][2]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _box(name, parent, group):
    """parentの原点を中心に、幅・高さ・奥行きの箱を作る。"""
    from maya import cmds
    cube = cmds.polyCube(name=name, width=WIDTH, height=HEIGHT, depth=DEPTH)[0]
    cmds.parent(cube, parent, relative=True)
    cmds.sets(cube, edit=True, forceElement=group)
    return cube


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import SquashBox
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    root = cmds.createNode("transform", name="box_ROOT")
    cmds.setAttr(root + ".rotateY", 20)
    graph = SquashBox.create(root, name="squashBox", height=HEIGHT, width=WIDTH)
    owner = graph.container
    output = cmds.createNode("transform", name="boxOutput_GRP")
    owner.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    # 判定用の参照: scalePivotを反対の辺に置いたtransformの階層(上→下→外→内)。表示しない。
    reference, parent = {}, root
    for side, pivot in (("top", (0, -HEIGHT / 2, 0)), ("bottom", (0, HEIGHT / 2, 0)),
                        ("outer", (-WIDTH / 2, 0, 0)), ("inner", (WIDTH / 2, 0, 0))):
        node = cmds.createNode("transform", name="reference_" + side, parent=parent)
        cmds.setAttr(node + ".scalePivot", *pivot)
        reference[side] = node
        parent = node
    red = _shader("restRed", (0.9, 0.12, 0.1), transparency=0.7)
    green = _shader("outputGreen", (0.15, 0.8, 0.25), transparency=0.25)
    # 赤(半透明)=生成時の箱、緑=出力の箱。
    _box("restBox_GEO", root, red)
    _box("outputBox_GEO", output, green)
    camera, camera_shape = cmds.camera(name="squashBoxCamera", focalLength=35)
    # 正面(+Z)から少し上。上下左右に伸ばしても枠に収まる位置に固定する。
    cmds.viewPlace(camera_shape, eye=(0, 1.5, 26), lookAt=(0, -1.2, 0))
    window = cmds.window("squashBoxValidationWindow", title="SquashBox - squash and stretch from four sides",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("squashBoxValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["squashBoxHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"owner": owner, "output": output, "reference": reference, "leaf": parent}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を参照の階層と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import SquashBox
    sides, volume, stage = pose(frame)
    owner = scene["owner"]
    owner.getPlug("volume").set(volume)
    factors = []
    for side, amount in zip(SIDES, sides):
        owner.getPlug(side).set(amount)
        length = HEIGHT if side in ("top", "bottom") else WIDTH
        main, perp = SquashBox.factors(amount, length, volume)
        factors.append((main, perp))
        scale = [perp, perp, perp]
        scale[1 if side in ("top", "bottom") else 0] = main
        cmds.setAttr(scene["reference"][side] + ".scale", *scale)
    actual = om.MMatrix(cmds.getAttr(scene["output"] + ".worldMatrix[0]"))
    expected = om.MMatrix(cmds.getAttr(scene["leaf"] + ".worldMatrix[0]"))
    error = max(abs(a - b) for a, b in zip(actual, expected))
    values[:] = [
        "GREEN = output box   RED (transparent) = rest box   height = 4 cm (Y)   width = 3 cm (X)",
        "STAGE: " + stage,
        "fixed: pivot of each side = centre of the opposite side at rest   order = top, bottom, outer, inner (nested)",
        "main = 1 + a/d   perpendicular = 1 - volume*a/d   P = T(-p) S T(p)   local = P_inner P_outer P_bottom P_top",
        "INPUT top = {:5.2f}  bottom = {:5.2f}  outer = {:5.2f}  inner = {:5.2f} cm   volume = {:.2f}".format(
            *(list(sides) + [volume])),
        "OUTPUT main/perp: top {:.3f}/{:.3f}  bottom {:.3f}/{:.3f}  outer {:.3f}/{:.3f}  inner {:.3f}/{:.3f}".format(
            *[value for pair in factors for value in pair]),
        "CHECK |matrix - nested scalePivot reference| = {:.7f}".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    return {"frame": frame, "presentation_stage": stage, "input": dict(zip(SIDES, sides), volume=volume),
            "factors": factors, "matrix_error": error, "ok": error < 1e-5}


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
        folder = recordVideo("SquashBox: 4辺からの潰しと伸ばし", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "squash_box.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-squash-box.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("squash-box-%Y%m%d-%H%M%S")
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
