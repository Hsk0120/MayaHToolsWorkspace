"""Umbrellaの傘の骨の開閉(ランナーの位置から親骨・受け骨の角度を求める三角形の計算)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_umbrella.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNT = 8
RIB = 4.0
STRETCHER = 5.0
RIB_FULL = 7.0
TOP = 8.0
FRAMES = 372
# (フレーム, slide, その区間の段階名)。区間の間は線形に補間する。
KEYS = [
    (0, 9.0, "1 CLOSED: SLIDE = a + b = 9"),
    (24, 9.0, "2 PUSH THE RUNNER UP: THE RIBS OPEN"),
    (120, 3.0, "3 HORIZONTAL AT s = sqrt(b^2 - a^2) = 3"),
    (144, 3.0, "4 PAST HORIZONTAL: THE RIBS TURN UP"),
    (192, 1.6, "5 PAST THE OPEN LIMIT |a - b| = 1: STOPS, NEGATIVE EXCESS"),
    (228, -0.5, "6 BACK INSIDE THE RANGE"),
    (264, 5.0, "7 PAST THE CLOSED LIMIT a + b = 9: STOPS, POSITIVE EXCESS"),
    (312, 11.0, "8 BACK TO CLOSED"),
    (348, 9.0, "9 CLOSED"),
    (FRAMES, 9.0, "9 CLOSED"),
]


def parameters(frame):
    """フレームの(slide, 段階名)を返す。"""
    for start, end in zip(KEYS, KEYS[1:]):
        if frame <= end[0]:
            weight = (frame - start[0]) / float(end[0] - start[0])
            return start[1] + (end[1] - start[1]) * weight, start[2]
    return KEYS[-1][1], KEYS[-1][2]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _rod(name, parent, group, length, radius):
    """parentのローカル+X方向へ、長さlengthの円柱を作る。"""
    from maya import cmds
    rod = cmds.polyCylinder(name=name, axis=(1, 0, 0), height=length, radius=radius, subdivisionsX=12)[0]
    cmds.setAttr(rod + ".translateX", length / 2.0)
    cmds.parent(rod, parent, relative=True)
    cmds.sets(rod, edit=True, forceElement=group)


def buildScene():
    """検証シーンを作り、(panel, 部品の辞書, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import Umbrella
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    base = cmds.createNode("transform", name="umbrellaTop_GRP")
    cmds.setAttr(base + ".translateY", TOP)
    graph = Umbrella.create(base, count=COUNT, ribLength=RIB, stretcherLength=STRETCHER, name="umbrella")
    owner = graph.container
    green = _shader("ribGreen", (0.1, 0.8, 0.2))
    blue = _shader("stretcherBlue", (0.15, 0.4, 1.0))
    yellow = _shader("runnerYellow", (1.0, 0.85, 0.1))
    grey = _shader("shaftGrey", (0.45, 0.45, 0.45))
    red = _shader("inputRed", (0.9, 0.12, 0.1), transparency=0.45)
    # 灰=中棒、緑=親骨(出力)、青=受け骨(出力)、黄=ランナー(出力)、赤(半透明)=入力のslideの位置の輪。
    shaft = cmds.polyCylinder(name="shaft_GEO", axis=(0, 1, 0), height=11.5, radius=0.04)[0]
    cmds.setAttr(shaft + ".translateY", TOP + 0.5 - 11.5 / 2.0)
    cmds.sets(shaft, edit=True, forceElement=grey)
    ribs, stretchers = [], []
    for index in range(COUNT):
        rib = cmds.createNode("transform", name="output_rib{}_GRP".format(index))
        owner.getPlug("rib%dMatrix" % index).connectTo(rib + ".offsetParentMatrix")
        _rod("rib{}_GEO".format(index), rib, green, RIB_FULL, 0.09)
        stretcher = cmds.createNode("transform", name="output_stretcher{}_GRP".format(index))
        owner.getPlug("stretcher%dMatrix" % index).connectTo(stretcher + ".offsetParentMatrix")
        _rod("stretcher{}_GEO".format(index), stretcher, blue, STRETCHER, 0.07)
        ribs.append(rib)
        stretchers.append(stretcher)
    runner = cmds.createNode("transform", name="output_runner_GRP")
    owner.getPlug("runnerMatrix").connectTo(runner + ".offsetParentMatrix")
    slider = cmds.polyCylinder(name="runner_GEO", axis=(0, 1, 0), height=0.5, radius=0.35)[0]
    cmds.parent(slider, runner, relative=True)
    cmds.sets(slider, edit=True, forceElement=yellow)
    ring = cmds.polyTorus(name="inputSlide_GEO", axis=(0, 1, 0), radius=0.75, sectionRadius=0.07)[0]
    cmds.sets(ring, edit=True, forceElement=red)
    camera, camera_shape = cmds.camera(name="umbrellaCamera", focalLength=35)
    # 斜め上の横から、開閉する骨と中棒全体を見る位置に固定する。
    cmds.viewPlace(camera_shape, eye=(14, 18, 35), lookAt=(0, 6.0, 0))
    # 左のHUDの文字と重ならないように、絵を右へ寄せる。
    cmds.setAttr(camera_shape + ".horizontalFilmOffset", -0.3)
    window = cmds.window("umbrellaValidationWindow", title="Umbrella - ribs opened by the runner",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("umbrellaValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 8
    names = ["umbrellaHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"ribs": ribs, "stretchers": stretchers, "runner": runner, "ring": ring}
    return panel, scene, owner, values, names


def evaluate_frame(frame, scene, owner, values, names):
    """入力を更新し、DG出力を独立計算と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import Umbrella
    slide, stage = parameters(frame)
    owner.getPlug("slide").set(slide)
    # 赤の輪は入力のslideそのまま(止める前)の位置。
    cmds.setAttr(scene["ring"] + ".translateY", TOP - slide)
    clamped, excess, rib, stretcher, radius = Umbrella.evaluate(slide, RIB, STRETCHER)
    dg = {attr: owner.getPlug(attr).get() for attr in ("clampedSlide", "excess", "radius", "ribAngle",
                                                       "stretcherAngle")}
    # 親骨の a の点と受け骨の b の点が、同じつなぎ目に来る(全部の骨の最大のずれ、cm)。
    gaps = []
    for rib_node, stretcher_node in zip(scene["ribs"], scene["stretchers"]):
        rib_end = om.MPoint(RIB, 0, 0) * om.MMatrix(cmds.getAttr(rib_node + ".worldMatrix[0]"))
        stretcher_end = om.MPoint(STRETCHER, 0, 0) * om.MMatrix(cmds.getAttr(stretcher_node + ".worldMatrix[0]"))
        gaps.append((rib_end - stretcher_end).length())
    runner_y = cmds.xform(scene["runner"], q=True, worldSpace=True, translation=True)[1]
    value_error = max(abs(dg["clampedSlide"] - clamped), abs(dg["excess"] - excess), abs(dg["radius"] - radius),
                      abs(runner_y - (TOP - clamped)))
    angle_error = max(abs(dg["ribAngle"] - rib), abs(dg["stretcherAngle"] - stretcher))
    values[:] = [
        "GREEN = ribs  BLUE = stretchers  YELLOW = runner (outputs)   RED ring = input slide (before the limit)",
        "STAGE: " + stage,
        "fixed: 8 ribs   a = 4 cm (top to joint)   b = 5 cm (stretcher)   s = clamp(slide, |a - b|, a + b) = 1 .. 9",
        "d = (a^2 + s^2 - b^2) / (2 s)   h = sqrt(a^2 - d^2)   excess = slide - s",
        "rib angle phi = atan2(h, d) from the shaft (down)   stretcher angle psi = atan2(h, s - d) from the shaft (up)",
        "INPUT slide = {:+6.2f} cm (distance from the top to the runner)".format(slide),
        "OUTPUT s = {:5.2f} cm  excess = {:+5.2f} cm  h = {:5.2f} cm  phi = {:6.1f} deg  psi = {:6.1f} deg".format(
            dg["clampedSlide"], dg["excess"], dg["radius"], dg["ribAngle"], dg["stretcherAngle"]),
        "CHECK |DG - formula| s/excess/h {:.5f} cm  angles {:.5f} deg  |rib joint - stretcher joint| max {:.5f} cm"
        .format(value_error, angle_error, max(gaps)),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = value_error < 2e-3 and angle_error < 0.1 and max(gaps) < 5e-3
    return {"frame": frame, "presentation_stage": stage, "slide": slide, "dg": dg,
            "expected": {"clampedSlide": clamped, "excess": excess, "radius": radius, "ribAngle": rib,
                         "stretcherAngle": stretcher},
            "joint_gaps": gaps, "value_error": value_error, "angle_error_degrees": angle_error, "ok": ok}


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
        panel, scene, owner, values, names = buildScene()
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("Umbrella: 傘の骨の開閉", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "umbrella.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-umbrella.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("umbrella-%Y%m%d-%H%M%S")
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
