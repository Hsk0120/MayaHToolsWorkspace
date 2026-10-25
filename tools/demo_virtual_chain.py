"""VirtualChainの仮想のFK階層を、本物の親子の階層と並べて専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_virtual_chain.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
LENGTH = 2.5
BEND = 12.0
COUNT = 4
# ((根元の rotateZ, 2番目の rotateZ, 3番目の rotateZ, 根元の scale, follow2), 次の姿勢へ向かう段階名)。
POSES = [
    ((0.0, 0.0, 0.0, 1.0, 1.0), "1 REST"),
    ((0.0, 0.0, 0.0, 1.0, 1.0), "2 ROTATE ROOT (rz 0 -> 35)"),
    ((35.0, 0.0, 0.0, 1.0, 1.0), "3 ROTATE CTRL1 (rz 0 -> -40)"),
    ((35.0, -40.0, 0.0, 1.0, 1.0), "4 ROTATE CTRL2 (rz 0 -> 50)"),
    ((35.0, -40.0, 50.0, 1.0, 1.0), "5 SCALE ROOT (1 -> 1.3)"),
    ((35.0, -40.0, 50.0, 1.3, 1.0), "6 follow2 = 0 (CTRL2 STOPS FOLLOWING CTRL1)"),
    ((35.0, -40.0, 50.0, 1.3, 0.0), "7 ROTATE ROOT BACK (35 -> -20), follow2 = 0"),
    ((-20.0, -40.0, 50.0, 1.3, 0.0), "8 RETURN TO REST (follow2 = 1)"),
    ((0.0, 0.0, 0.0, 1.0, 1.0), "8 RETURN TO REST (follow2 = 1)"),
    ((0.0, 0.0, 0.0, 1.0, 1.0), "8 RETURN TO REST (follow2 = 1)"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。follow2 は段階の中ほどで切り替える(0か1だけ)。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    smooth = weight * weight * (3 - 2 * weight)
    start, end = POSES[index][0], POSES[index + 1][0]
    values = [a + (b - a) * smooth for a, b in zip(start[:4], end[:4])]
    values.append(end[4] if weight >= 0.5 else start[4])
    return values, POSES[index][1]


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


def _matrix(node, attribute):
    """アトリビュートの行列を om2.MMatrix で返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    return om2.MMatrix(cmds.getAttr(node + "." + attribute))


def _world_of(group, x, y, angle):
    """group の下の (x, y) にZ回りangle度で置いたときのワールド行列(16個の数)。"""
    from maya.api import OpenMaya as om2
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    local = om2.MMatrix([c, s, 0, 0, -s, c, 0, 0, 0, 0, 1, 0, x, y, 0, 1])
    return list(local * _matrix(group, "worldMatrix[0]"))


def _chain(prefix, group, parented, shading):
    """尻尾の4つのコントロールと、中の骨(箱)を作る。parented なら本物の親子、そうでなければ兄弟。"""
    from maya import cmds
    nodes, x, y, angle = [], 0.0, 0.0, 0.0
    for index in range(COUNT):
        parent = nodes[-1] if (parented and nodes) else group
        node = cmds.createNode("transform", name="{}{}".format(prefix, index), parent=parent)
        node = cmds.ls(node, long=True)[0]
        cmds.xform(node, worldSpace=True, matrix=_world_of(group, x, y, angle))
        size = LENGTH if index < COUNT - 1 else 0.6
        box = cmds.polyCube(name="{}{}_GEO".format(prefix, index), width=size, height=0.45, depth=0.45)[0]
        box = cmds.parent(box, node, relative=True)[0]
        cmds.setAttr(box + ".translateX", size * 0.5 - 0.15)
        cmds.sets(box, edit=True, forceElement=shading)
        nodes.append(node)
        x += LENGTH * math.cos(math.radians(angle))
        y += LENGTH * math.sin(math.radians(angle))
        angle -= BEND
    return nodes


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import VirtualChain
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    green = _shader("flatGreen", (0.15, 0.75, 0.25))
    red = _shader("realRed", (0.85, 0.2, 0.2))
    flat_group = cmds.createNode("transform", name="flat_ctrls")
    cmds.setAttr(flat_group + ".translate", -15, 3.5, 0)
    real_group = cmds.createNode("transform", name="real_ctrls")
    cmds.setAttr(real_group + ".translate", 1, 3.5, 0)
    flat = _chain("flatCtrl", flat_group, False, green)
    real = _chain("realCtrl", real_group, True, red)
    rest = {"flat_world": [_matrix(n, "worldMatrix[0]") for n in flat],
            "flat_local": [_matrix(n, "matrix") for n in flat],
            "flat_rotate": [cmds.getAttr(n + ".rotateZ") for n in flat],
            "real_local": [_matrix(n, "matrix") for n in real]}
    graph = VirtualChain.create(flat, name="tailChain")
    camera, camera_shape = cmds.camera(name="chainCamera", orthographic=True, orthographicWidth=34)
    cmds.viewPlace(camera_shape, eye=(-2.0, 0.0, 40), lookAt=(-2.0, 0.0, 0), up=(0, 1, 0))
    window = cmds.window("chainValidationWindow", title="VirtualChain - flat tail controls as FK",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("chainValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, wireframeOnShaded=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("chain", 7)
    scene = {"owner": str(graph.container), "flat": flat, "real": real, "rest": rest,
             "flat_group": flat_group, "real_group": real_group}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """コントロールを動かし、緑(仮想)を独立に書いた式・本物の階層(赤)と比較した診断を返す。"""
    from maya import cmds
    (root, middle, third, scale, follow), stage_name = pose(frame)
    flat, real, rest = scene["flat"], scene["real"], scene["rest"]
    cmds.setAttr(scene["owner"] + ".follow2", follow)
    for index, rz in enumerate((root, middle, third, 0.0)):
        cmds.setAttr(flat[index] + ".rotateZ", rest["flat_rotate"][index] + rz)
    for axis in "XYZ":
        cmds.setAttr(flat[0] + ".scale" + axis, scale)
    # 本物の階層へ、作成時からの同じ局所の変化を入れる(follow2 = 0 の間も赤は常に追う)。
    for index, node in enumerate(real):
        delta = _matrix(flat[index], "matrix") * rest["flat_local"][index].inverse()
        cmds.xform(node, objectSpace=True, matrix=list(delta * rest["real_local"][index]))
    group_flat = _matrix(scene["flat_group"], "worldMatrix[0]")
    group_real = _matrix(scene["real_group"], "worldMatrix[0]")
    # 判定用の独立計算: W_i = D_i * W_i(作成時) * W_(i-1)(作成時)^-1 * W_(i-1)、追わないつなぎは D_i * W_i(作成時)。
    expected = [_matrix(flat[0], "worldMatrix[0]")]
    for index in range(1, COUNT):
        free = _matrix(flat[index], "matrix") * rest["flat_local"][index].inverse() * rest["flat_world"][index]
        chained = free * rest["flat_world"][index - 1].inverse() * expected[-1]
        expected.append(chained if (index != 2 or follow == 1.0) else free)
    formula_error = max(max(abs(a - b) for a, b in zip(_matrix(n, "worldMatrix[0]"), e))
                        for n, e in zip(flat, expected))
    real_error = max(max(abs(a - b) for a, b in zip(_matrix(f, "worldMatrix[0]") * group_flat.inverse(),
                                                    _matrix(r, "worldMatrix[0]") * group_real.inverse()))
                     for f, r in zip(flat, real))
    tip = cmds.xform(flat[-1], query=True, worldSpace=True, translation=True)
    values[:] = [
        "LEFT GREEN = flat sibling controls joined by VirtualChain   RIGHT RED = real parented hierarchy (same local values)",
        "STAGE: " + stage_name,
        "fixed: 4 controls, bone 2.5 cm, rest bend -12 deg each, K_i = O_i * P_i * W_(i-1)^-1 at creation",
        "O_i = K_i * W_(i-1) * P_i^-1  ->  W_i = M_i * K_i * W_(i-1)   (follow_i = 0 keeps the rest O_i)",
        "INPUT rz root {:6.1f}  ctrl1 {:6.1f}  ctrl2 {:6.1f} deg   root scale {:4.2f}   follow2 = {:.0f}".format(
            root, middle, third, scale, follow),
        "OUTPUT green tip = ({:6.2f}, {:6.2f}) cm   outliner: all 4 controls are siblings under flat_ctrls".format(
            tip[0], tip[1]),
        "CHECK max |green - formula| = {:.1e}   max |green - red| = {:.1e} {}".format(
            formula_error, real_error, "(follows)" if follow == 1.0 else "(red differs: follow2 = 0)"),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = formula_error < 1e-6 and (real_error < 1e-6 if follow == 1.0 else True)
    return {"frame": frame, "presentation_stage": stage_name,
            "input": {"root": root, "ctrl1": middle, "ctrl2": third, "scale": scale, "follow2": follow},
            "formula_error": formula_error, "real_error": real_error, "ok": ok}


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
        folder = recordVideo("VirtualChain: 仮想のFK階層", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "virtual_chain.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-virtual-chain.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("virtual-chain-%Y%m%d-%H%M%S")
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
