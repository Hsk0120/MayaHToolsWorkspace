"""SpaceBlendの複数の空間への重み付き追従を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_space_blend.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
SPACES = (("world", (-3, 4, 0)), ("chest", (1, 8, 0)), ("hand", (6, 5, 0)))
# (world, chest, handの重み, 次の姿勢へ向かう段階名)。空間は全段階を通して動き続ける。
POSES = [
    ((1, 0, 0), "1 REST: WORLD ONLY"),
    ((1, 0, 0), "2 WORLD -> CHEST"),
    ((0, 1, 0), "3 CHEST -> HAND"),
    ((0, 0, 1), "4 HAND -> EQUAL (1, 1, 1)"),
    ((1, 1, 1), "5 EQUAL -> CHEST AND HAND (0, 1, 3)"),
    ((0, 1, 3), "6 RETURN TO WORLD"),
    ((1, 0, 0), "6 RETURN TO WORLD"),
    ((1, 0, 0), "6 RETURN TO WORLD"),
]
FRAMES = SEGMENT * (len(POSES) - 1) + 24


def pose(frame):
    """フレームの重みと段階名をsmoothstepで補間し、空間の動きを返す。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    weights = [a + (b - a) * weight for a, b in zip(POSES[index][0], POSES[index + 1][0])]
    # 空間の動き: 始めと終わりで0になる包絡で、胸は左右に揺れて傾き、手は円を描いて回る。
    envelope = math.sin(math.pi * min(frame / (FRAMES - 24), 1.0)) ** 2
    angle = 2 * math.pi * frame / 72.0
    chest = ((1.5 * math.sin(angle) * envelope, 0, 0), (0, 0, 20 * math.sin(angle) * envelope))
    hand = ((1.5 * (math.cos(angle) - 1) * envelope, 1.5 * math.sin(angle) * envelope, 0),
            (0, 0, -60 * envelope))
    return weights, chest, hand, POSES[index][1]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _marker(name, parent, group, size=0.6):
    """向きの分かる、長い腕を持つ十字の形を作る(3つの直方体)。"""
    from maya import cmds
    for axis, dims in (("X", (size * 3, size * 0.4, size * 0.4)), ("Y", (size * 0.4, size * 2, size * 0.4))):
        cube = cmds.polyCube(name=name + axis, width=dims[0], height=dims[1], depth=dims[2])[0]
        cmds.parent(cube, parent, relative=True)
        cmds.setAttr(cube + ".translate", dims[0] / 2 - size * 0.2 if axis == "X" else 0,
                     dims[1] / 2 - size * 0.2 if axis == "Y" else 0, 0)
        cmds.sets(cube, edit=True, forceElement=group)


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import SpaceBlend
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    colors = {"world": (0.5, 0.5, 0.55), "chest": (0.2, 0.4, 0.95), "hand": (0.95, 0.75, 0.1)}
    spaces = {}
    for role, position in SPACES:
        node = cmds.createNode("transform", name=role + "_SPACE")
        cmds.setAttr(node + ".translate", *position)
        cube = cmds.polyCube(name=role + "_GEO", width=1.2, height=1.2, depth=1.2)[0]
        cmds.parent(cube, node, relative=True)
        cmds.sets(cube, edit=True, forceElement=_shader(role + "Color", colors[role], transparency=0.3))
        spaces[role] = node
    follower = cmds.createNode("transform", name="ctrl_REST")
    cmds.setAttr(follower + ".translate", 2.0, 6.0, 0)
    graph = SpaceBlend.create(follower, [spaces[role] for role, _ in SPACES], name="spaceBlend")
    owner = graph.container
    output = cmds.createNode("transform", name="ctrlOutput_GRP")
    owner.getPlug("matrix").connectTo(output + ".offsetParentMatrix")
    _marker("output_GEO", output, _shader("outputGreen", (0.15, 0.8, 0.25)))
    camera, camera_shape = cmds.camera(name="spaceBlendCamera", focalLength=35)
    # 正面(+Z)から。空間と出力の動きが枠に収まる位置に固定する。
    cmds.viewPlace(camera_shape, eye=(1.5, 6.5, 28), lookAt=(1.5, 5.0, 0))
    window = cmds.window("spaceBlendValidationWindow", title="SpaceBlend - weighted spaces",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("spaceBlendValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["spaceBlendHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    from maya.api import OpenMaya as om
    rest = om.MMatrix(cmds.getAttr(follower + ".worldMatrix[0]"))
    offsets = [rest * om.MMatrix(cmds.getAttr(spaces[role] + ".worldMatrix[0]")).inverse() for role, _ in SPACES]
    scene = {"owner": owner, "output": output, "spaces": spaces, "offsets": offsets}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力の位置を独立に求めた重み付き平均と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    weights, chest, hand, stage = pose(frame)
    owner = scene["owner"]
    for index, weight in enumerate(weights):
        owner.getPlug("weight" + str(index)).set(weight)
    for role, (translate, rotate) in (("chest", chest), ("hand", hand)):
        base = dict(SPACES)[role]
        cmds.setAttr(scene["spaces"][role] + ".translate", *[b + t for b, t in zip(base, translate)])
        cmds.setAttr(scene["spaces"][role] + ".rotate", *rotate)
    targets = [offset * om.MMatrix(cmds.getAttr(scene["spaces"][role] + ".worldMatrix[0]"))
               for offset, (role, _) in zip(scene["offsets"], SPACES)]
    total = sum(weights)
    expected = sum((om.MVector(t[12], t[13], t[14]) * w for t, w in zip(targets, weights)), om.MVector()) / total
    actual = om.MMatrix(cmds.getAttr(scene["output"] + ".worldMatrix[0]"))
    position = om.MVector(actual[12], actual[13], actual[14])
    error = (position - expected).length()
    from mlrig.setups import SpaceBlend
    ratios = SpaceBlend.ratios(weights)
    values[:] = [
        "GREEN = output   GRAY = world space   BLUE = chest space   YELLOW = hand space (all spaces keep moving)",
        "STAGE: " + stage,
        "fixed: offset_i = rest output * inverse(rest space_i)   target_i = offset_i * space_i",
        "position = sum(w_i * target_i) / sum(w_i)   blendMatrix ratio_i = w_i / (w_0 + ... + w_i)",
        "INPUT weight world = {:.2f}   chest = {:.2f}   hand = {:.2f}   (total {:.2f})".format(*(weights + [total])),
        "OUTPUT ratio chest = {:.3f}   hand = {:.3f}   position = ({:.2f}, {:.2f}, {:.2f}) cm".format(
            ratios[0], ratios[1], position.x, position.y, position.z),
        "CHECK |position - weighted average| = {:.7f} cm".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    return {"frame": frame, "presentation_stage": stage, "weights": weights, "ratios": ratios,
            "position": [position.x, position.y, position.z], "position_error": error, "ok": error < 1e-4}


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
        folder = recordVideo("SpaceBlend: 複数の空間への重み付き追従", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "space_blend.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-space-blend.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("space-blend-%Y%m%d-%H%M%S")
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
