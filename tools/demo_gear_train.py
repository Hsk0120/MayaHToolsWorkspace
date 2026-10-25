"""GearTrainの歯車の連動を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_gear_train.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
TEETH = (24, 12, 8, 16)
LINKS = ("mesh", "shaft", "mesh")
#: (役割, 位置, 色)。半径は歯数 * 0.15cm。gear2はgear1と同じ軸(手前の小さい歯車)。
GEARS = (("driver", (0.0, 0.0, 0.0), "red"), ("gear1", (5.4, 0.0, 0.0), "green"),
         ("gear2", (5.4, 0.0, 0.6), "green"), ("gear3", (9.0, 0.0, 0.6), "green"))
# (駆動側の角度[度], gear3のphase[度], 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, 0.0, "1 REST"),
    (0.0, 0.0, "2 TURN THE DRIVER +180 deg"),
    (180.0, 0.0, "3 REVERSE TO -90 deg"),
    (-90.0, 0.0, "4 TURN TO +360 deg (ONE FULL TURN)"),
    (360.0, 0.0, "5 phase3 0 -> 30 deg (TOOTH ALIGNMENT OFFSET)"),
    (360.0, 30.0, "6 RETURN TO REST"),
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


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
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


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import GearTrain
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("driverRed", (0.9, 0.15, 0.1)), "green": _shader("gearGreen", (0.15, 0.75, 0.25)),
              "mark": _shader("markWhite", (0.95, 0.95, 0.9))}
    nodes = []
    for (role, position, color), teeth in zip(GEARS, TEETH):
        radius = teeth * 0.15
        node = cmds.createNode("transform", name=role + "_GEAR")
        cmds.setAttr(node + ".translate", *position)
        body = cmds.polyCylinder(name=role + "_GEO", radius=radius * 0.9, height=0.4, axis=(0, 0, 1),
                                 subdivisionsX=teeth * 2)[0]
        cmds.parent(body, node, relative=True)
        cmds.sets(body, edit=True, forceElement=groups[color])
        # 歯の代わりに外周へ小さな箱を歯数だけ並べ、1つ目だけ白で回転の目印にする。
        for index in range(teeth):
            tooth = cmds.polyCube(name="{}_tooth{}".format(role, index), width=radius * 0.18, height=0.5,
                                  depth=0.42)[0]
            pivot = cmds.createNode("transform", name="{}_toothPivot{}".format(role, index), parent=node)
            cmds.parent(tooth, pivot, relative=True)
            cmds.setAttr(tooth + ".translateY", radius * 0.97)
            cmds.setAttr(pivot + ".rotateZ", 360.0 * index / teeth)
            cmds.sets(tooth, edit=True, forceElement=groups["mark" if index == 0 else color])
        nodes.append(node)
    # 白い目印を互いに向かい合う側へ置き、かみ合う歯車は歯を半ピッチずらす(見た目のみ、生成時の回転)。
    cmds.setAttr(nodes[0] + ".rotateZ", 0)
    cmds.setAttr(nodes[1] + ".rotateZ", 180.0 / TEETH[1])
    cmds.setAttr(nodes[2] + ".rotateZ", 0)
    cmds.setAttr(nodes[3] + ".rotateZ", 180.0 / TEETH[3])
    graph = GearTrain.create(nodes[0], nodes[1:], TEETH, name="gearTrain", axis="z", links=LINKS)
    owner = graph.container
    camera, camera_shape = cmds.camera(name="gearTrainCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(4.6, -0.8, 30), lookAt=(4.6, -0.8, 0))
    window = cmds.window("gearTrainValidationWindow", title="GearTrain - gear ratio", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("gearTrainValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("gearTrain", 7)
    rest = [cmds.getAttr(node + ".rotateZ") for node in nodes]
    scene = {"owner": owner, "nodes": nodes, "rest": rest}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、歯車の回転を歯数の比の式と比較した診断を返す。"""
    from maya import cmds
    from mlrig.setups import GearTrain
    angle, phase, stage = pose(frame)
    owner, nodes, rest = scene["owner"], scene["nodes"], scene["rest"]
    owner.getPlug("phase3").set(math.radians(phase))
    cmds.setAttr(nodes[0] + ".rotateZ", rest[0] + angle)
    ratios = GearTrain.ratios(TEETH, LINKS)
    actual = [cmds.getAttr(node + ".rotateZ") - base for node, base in zip(nodes, rest)]
    expected = [angle] + [ratio * angle for ratio in ratios]
    expected[3] += phase
    error = max(abs(a - b) for a, b in zip(actual, expected))
    # 送った歯の数 = 歯数 * 回転角(度)。かみ合う2つは同じ大きさで逆向き(phaseの分は除く)。
    travel = [TEETH[0] * actual[0], TEETH[1] * actual[1], TEETH[2] * actual[2], TEETH[3] * (actual[3] - phase)]
    travel_error = max(abs(travel[0] + travel[1]), abs(travel[2] + travel[3]))
    values[:] = [
        "RED = driver (24 teeth)   GREEN = 12 teeth, 8 teeth (same shaft as 12, front), 16 teeth   WHITE = mark tooth",
        "STAGE: " + stage,
        "fixed: 24 -> 12 mesh, 12 = 8 shaft, 8 -> 16 mesh   ratio1 = -2   ratio2 = -2   ratio3 = +1   angles in deg",
        "mesh: ratio_i = -ratio_(i-1) * teeth_(i-1) / teeth_i   shaft: ratio_i = ratio_(i-1)   rotate_i = ratio_i * driver + phase_i",
        "INPUT driver = {:7.2f} deg   phase3 = {:5.2f} deg".format(angle, phase),
        "OUTPUT 12T = {:8.2f}   8T = {:8.2f}   16T = {:8.2f}   teeth moved: 24T {:7.1f} / 12T {:7.1f}".format(
            actual[1], actual[2], actual[3], travel[0], travel[1]),
        "CHECK max |rotation - formula| = {:.6f} deg   max |teeth moved, sum of meshing pair| = {:.5f}".format(
            error, travel_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-3 and travel_error < 1e-2
    return {"frame": frame, "presentation_stage": stage, "input": {"driver": angle, "phase3": phase},
            "rotations": actual, "expected": expected, "error": error, "travel_error": travel_error, "ok": ok}


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
        folder = recordVideo("GearTrain: 歯車の連動", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "gear_train.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-gear-train.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("gear-train-%Y%m%d-%H%M%S")
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
