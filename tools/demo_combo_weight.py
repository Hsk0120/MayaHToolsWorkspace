"""ComboWeightの組み合わせ・途中のウェイトと、それで動かす補正シェイプを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_combo_weight.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 36
WIDTH = 8.0
LIFT = 1.2
# ((左のウェイト, 右のウェイト), 次の姿勢へ向かう段階名)。
POSES = [
    ((0.0, 0.0), "1 REST"),
    ((0.0, 0.0), "2 LEFT CORNER UP (left 0 -> 1)"),
    ((1.0, 0.0), "3 RIGHT CORNER UP TOO (right 0 -> 1)"),
    ((1.0, 1.0), "4 LEFT BACK TO HALF (left 1 -> 0.5)"),
    ((0.5, 1.0), "5 OVERSHOOT BOTH -> 1.4 (CLAMPED TO 1)"),
    ((1.4, 1.4), "6 RIGHT DOWN, LEFT HALF (0.5, 0)"),
    ((0.5, 0.0), "7 RETURN TO REST"),
    ((0.0, 0.0), "7 RETURN TO REST"),
    ((0.0, 0.0), "7 RETURN TO REST"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    (a0, b0), (a1, b1) = POSES[index][0], POSES[index + 1][0]
    return (a0 + (a1 - a0) * weight, b0 + (b1 - b0) * weight), POSES[index][1]


def _clamp(value):
    return min(max(value, 0.0), 1.0)


def shapes(x):
    """頂点のxでの (左, 右, 補正) のシェイプの上への移動量。"""
    half = WIDTH * 0.5
    return LIFT * (x + half) / WIDTH, LIFT * (half - x) / WIDTH, -LIFT * (1.0 - abs(x) / half)


def expected(left, right):
    """判定用の独立計算: 切り詰めたウェイト・積・山形。"""
    a, b = _clamp(left), _clamp(right)
    return a, b, a * b, (2.0 * a if a <= 0.5 else 2.0 * (1.0 - a))


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


def _mouth(name, y, group):
    """口の代わりの平面と、左・右・補正のシェイプを作る。"""
    from maya import cmds
    mouth = cmds.polyPlane(name=name, width=WIDTH, height=1.2, subdivisionsX=16, subdivisionsY=2,
                           axis=(0, 0, 1), constructionHistory=False)[0]
    targets = []
    count = cmds.polyEvaluate(mouth, vertex=True)
    for role in range(3):
        target = cmds.duplicate(mouth, name="{}_target{}".format(name, role))[0]
        for index in range(count):
            vertex = "{}.vtx[{}]".format(target, index)
            px, py, pz = cmds.xform(vertex, query=True, objectSpace=True, translation=True)
            cmds.xform(vertex, objectSpace=True, translation=(px, py + shapes(px)[role], pz))
        cmds.setAttr(target + ".visibility", False)
        targets.append(target)
    blend = cmds.blendShape(*(targets + [mouth]), name=name + "_blend")[0]
    cmds.setAttr(mouth + ".translateY", y)
    cmds.sets(mouth, edit=True, forceElement=group)
    rest = [cmds.xform("{}.vtx[{}]".format(mouth, i), query=True, objectSpace=True, translation=True)
            for i in range(count)]
    return mouth, blend, rest


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import ComboWeight
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("plainRed", (0.85, 0.2, 0.2)), "green": _shader("fixGreen", (0.15, 0.75, 0.25)),
              "blue": _shader("barBlue", (0.25, 0.45, 0.9)), "orange": _shader("barOrange", (0.95, 0.55, 0.1)),
              "gray": _shader("lineGray", (0.55, 0.55, 0.6))}
    graph = ComboWeight.create(["left", "right"], {"both": ["left", "right"]}, {"leftHalf": ("left", 0.5)},
                               name="mouthCombo")
    owner = str(graph.container)
    plain, plain_blend, plain_rest = _mouth("plainMouth", 4.2, groups["red"])
    fixed, fixed_blend, fixed_rest = _mouth("fixedMouth", 0.2, groups["green"])
    for blend in (plain_blend, fixed_blend):
        cmds.connectAttr(owner + ".left", blend + ".weight[0]")
        cmds.connectAttr(owner + ".right", blend + ".weight[1]")
    cmds.connectAttr(owner + ".both", fixed_blend + ".weight[2]")
    # 片側だけ上げたときの口角の高さの基準線(灰色)。
    for y in (4.2, 0.2):
        line = cmds.polyCube(name="restLine_GEO", width=WIDTH + 1.0, height=0.04, depth=0.04)[0]
        cmds.setAttr(line + ".translate", 0, y + 0.6 + LIFT, -0.1)
        cmds.sets(line, edit=True, forceElement=groups["gray"])
    # ウェイトの棒(青=both、橙=leftHalf)。高さ4がウェイト1。
    for attribute, x, group in (("both", 7.5, "blue"), ("leftHalf", 9.5, "orange")):
        bar = cmds.polyCube(name=attribute + "Bar_GEO", width=1.0, height=4.0, depth=0.5)[0]
        cmds.xform(bar, pivots=(0, -2.0, 0))
        cmds.setAttr(bar + ".translate", x, -0.3, 0)
        cmds.connectAttr(owner + "." + attribute, bar + ".scaleY")
        cmds.sets(bar, edit=True, forceElement=groups[group])
        top = cmds.polyCube(name=attribute + "Frame_GEO", width=1.3, height=0.06, depth=0.06)[0]
        cmds.setAttr(top + ".translate", x, 1.7, 0)
        cmds.sets(top, edit=True, forceElement=groups["gray"])
    camera, camera_shape = cmds.camera(name="comboCamera", orthographic=True, orthographicWidth=30)
    cmds.viewPlace(camera_shape, eye=(1.5, 0.5, 40), lookAt=(1.5, 0.5, 0), up=(0, 1, 0))
    window = cmds.window("comboValidationWindow", title="ComboWeight - smile combo corrective",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("comboValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, wireframeOnShaded=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("combo", 7)
    scene = {"owner": owner, "meshes": ((plain, plain_rest, False), (fixed, fixed_rest, True))}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """左右のウェイトを更新し、出力のウェイトと2つの口の全頂点を独立計算と比較した診断を返す。"""
    from maya import cmds
    (left, right), stage_name = pose(frame)
    owner = scene["owner"]
    cmds.setAttr(owner + ".left", left)
    cmds.setAttr(owner + ".right", right)
    a, b, both, half = expected(left, right)
    weight_error = max(abs(cmds.getAttr(owner + ".both") - both), abs(cmds.getAttr(owner + ".leftHalf") - half))
    vertex_error, centers = 0.0, []
    for mesh, rest, corrected in scene["meshes"]:
        center = 0.0
        for index, (px, py, pz) in enumerate(rest):
            shift = shapes(px)
            # 左右のシェイプはドライバーの値そのもの(1を超えた分も効く)、補正は切り詰めた値の積。
            dy = left * shift[0] + right * shift[1] + (both * shift[2] if corrected else 0.0)
            actual = cmds.xform("{}.vtx[{}]".format(mesh, index), query=True, objectSpace=True, translation=True)
            vertex_error = max(vertex_error, abs(actual[1] - (py + dy)), abs(actual[0] - px))
            if abs(px) < 1e-6 and py > 0.5:
                center = actual[1] - py
        centers.append(center)
    values[:] = [
        "RED = left + right shapes only   GREEN = + corrective (weight = both)   "
        "BLUE bar = both   ORANGE bar = leftHalf   GRAY line = one-side corner height",
        "STAGE: " + stage_name,
        "fixed: method = multiply   inbetween position p = 0.5   inputs are clamped to 0..1   corner lift = 1.2 cm",
        "both = clamp(left) * clamp(right)      leftHalf = min(x / p, (1 - x) / (1 - p)),  x = clamp(left)",
        "INPUT left = {:5.2f}   right = {:5.2f}   (clamped {:4.2f}, {:4.2f})".format(left, right, a, b),
        "OUTPUT both = {:5.3f}   leftHalf = {:5.3f}   mouth center rise: red {:5.2f} cm  green {:5.2f} cm".format(
            cmds.getAttr(owner + ".both"), cmds.getAttr(owner + ".leftHalf"), centers[0], centers[1]),
        "CHECK max |weight - formula| = {:.1e}   max |vertex - formula| = {:.1e} cm".format(
            weight_error, vertex_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = weight_error < 1e-6 and vertex_error < 1e-5
    return {"frame": frame, "presentation_stage": stage_name, "input": {"left": left, "right": right},
            "both": both, "leftHalf": half, "weight_error": weight_error, "vertex_error": vertex_error,
            "center_plain": centers[0], "center_fixed": centers[1], "ok": ok}


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
        folder = recordVideo("ComboWeight: 組み合わせの補正ウェイト", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "combo_weight.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-combo-weight.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("combo-weight-%Y%m%d-%H%M%S")
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
