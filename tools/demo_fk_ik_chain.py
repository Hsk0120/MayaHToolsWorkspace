"""FkIkChainの尻尾のFK/IKの切り替えを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_fk_ik_chain.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
COUNT = 6
LENGTH = 2.0
# (blendの値, 次の値へ向かう段階名)。FK・IKのチェーンは全段階を通して動き続ける。
POSES = [
    (0.0, "1 FK ONLY (blend = 0)"),
    (0.0, "2 FK -> IK"),
    (1.0, "3 IK ONLY (blend = 1)"),
    (1.0, "4 IK -> HALF"),
    (0.5, "5 HALF -> FK"),
    (0.0, "5 HALF -> FK"),
]
FRAMES = SEGMENT * (len(POSES) - 1) + 24


def pose(frame):
    """フレームのblendをsmoothstepで補間し、FK・IKの各節の回転(度)と段階名を返す。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    blend = POSES[index][0] + (POSES[index + 1][0] - POSES[index][0]) * weight
    angle = 2 * math.pi * frame / 96.0
    # FKは根元から先へ進む波、IKは下へ曲がりながら先端が円を描く。
    fk = [(0, 0, 14 * math.sin(angle - 0.7 * i)) for i in range(COUNT)]
    ik = [(8 * math.sin(angle), 6 * math.cos(angle), -14 + 6 * math.cos(angle)) for _ in range(COUNT)]
    return blend, fk, ik, POSES[index][1]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _segment(name, parent, group, thickness, front=0.0):
    """parentの+Xへ節の長さの直方体を置く(節の向きが分かる形)。frontだけ+Z(カメラ側)へずらす。"""
    from maya import cmds
    cube = cmds.polyCube(name=name, width=LENGTH * 0.92, height=thickness, depth=thickness)[0]
    cmds.parent(cube, parent, relative=True)
    cmds.setAttr(cube + ".translateX", LENGTH / 2)
    cmds.setAttr(cube + ".translateZ", front)
    cmds.sets(cube, edit=True, forceElement=group)


def _chain(prefix, group, thickness):
    """原点から+Xへ並ぶtransformの節の列を作る。"""
    from maya import cmds
    nodes, parent = [], None
    for index in range(COUNT):
        node = cmds.createNode("transform", name="{}{}".format(prefix, index), parent=parent)
        cmds.setAttr(node + ".translateX", LENGTH if index else 0.0)
        if index < COUNT - 1:
            _segment(prefix + "Geo" + str(index), node, group, thickness)
        nodes.append(cmds.ls(node, long=True)[0])
        parent = node
    return nodes


def _blend(first, second, weight):
    """blendMatrixと同じ考え方(scale・移動は線形、回転は球面補間)で2つの行列を混ぜる(独立計算)。"""
    from maya.api import OpenMaya as om
    a, b = om.MTransformationMatrix(first), om.MTransformationMatrix(second)
    rotation = om.MQuaternion.slerp(a.rotation(asQuaternion=True), b.rotation(asQuaternion=True), weight)
    translate = a.translation(om.MSpace.kTransform) * (1 - weight) + b.translation(om.MSpace.kTransform) * weight
    result = om.MTransformationMatrix()
    result.setRotation(rotation)
    result.setTranslation(translate, om.MSpace.kTransform)
    return result.asMatrix()


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import FkIkChain
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    fk = _chain("fk", _shader("fkBlue", (0.2, 0.4, 0.95), 0.55), 0.35)
    ik = _chain("ik", _shader("ikYellow", (0.95, 0.75, 0.1), 0.55), 0.35)
    local = FkIkChain.create(fk, ik, name="tailLocal").container
    world = FkIkChain.create(fk, ik, name="tailWorld", space="world").container
    outputs = {}
    for role, owner, color, thickness in (("local", local, (0.15, 0.8, 0.25), 0.6),
                                         ("world", world, (0.9, 0.2, 0.15), 0.25)):
        group = _shader(role + "Output", color)
        nodes = []
        for index in range(COUNT):
            node = cmds.createNode("transform", name="{}Out{}".format(role, index))
            owner.getPlug("matrix" + str(index)).connectTo(node + ".offsetParentMatrix")
            if index < COUNT - 1:
                # ワールドで混ぜた比較用(赤)は、緑に隠れないようカメラ側へずらして描く。
                _segment("{}OutGeo{}".format(role, index), node, group, thickness, 0.6 if role == "world" else 0.0)
            nodes.append(node)
        outputs[role] = nodes
    camera, camera_shape = cmds.camera(name="fkIkChainCamera", focalLength=35)
    # 横(+Z)から。尻尾の根元を左、先を右に置き、曲がる範囲が枠に収まる位置に固定する。
    cmds.viewPlace(camera_shape, eye=(5.0, -3.0, 24), lookAt=(5.0, -3.0, 0))
    window = cmds.window("fkIkChainValidationWindow", title="FkIkChain - tail FK/IK blend",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("fkIkChainValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
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
    names = ["fkIkChainHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"fk": fk, "ik": ik, "local": local, "world": world, "outputs": outputs}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、DG出力を独立に求めた相対行列の補間・積と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    blend, fk, ik, stage = pose(frame)
    for role, rotations in (("fk", fk), ("ik", ik)):
        for node, rotate in zip(scene[role], rotations):
            cmds.setAttr(node + ".rotate", *rotate)
    for owner in (scene["local"], scene["world"]):
        owner.getPlug("blend").set(blend)
    fkW = [om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]")) for node in scene["fk"]]
    ikW = [om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]")) for node in scene["ik"]]
    expected = [_blend(fkW[0], ikW[0], blend)]
    for index in range(1, COUNT):
        expected.append(_blend(fkW[index] * fkW[index - 1].inverse(), ikW[index] * ikW[index - 1].inverse(), blend)
                        * expected[-1])
    actual = {role: [om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]")) for node in nodes]
              for role, nodes in scene["outputs"].items()}
    error = max(abs(a - b) for x, y in zip(actual["local"], expected) for a, b in zip(x, y))

    def lengths(matrices):
        return [(om.MVector(b[12], b[13], b[14]) - om.MVector(a[12], a[13], a[14])).length()
                for a, b in zip(matrices, matrices[1:])]

    localLengths, worldLengths = lengths(actual["local"]), lengths(actual["world"])
    lengthError = max(abs(value - LENGTH) for value in localLengths)
    tip = actual["local"][-1]
    values[:] = [
        "GREEN = FkIkChain output (local)   RED = world blend   BLUE = FK chain   YELLOW = IK chain",
        "STAGE: " + stage,
        "fixed: segment length = {:.1f} cm   L_i = W_i * inverse(W_(i-1)) for FK and IK".format(LENGTH),
        "out_0 = blend(W_fk0, W_ik0, w)   out_i = blend(L_fk_i, L_ik_i, w) * out_(i-1)   (rotation slerp)",
        "INPUT blend w = {:.3f}   fkVisibility = {}   ikVisibility = {}".format(
            blend, int(scene["local"].getPlug("fkVisibility").get()), int(scene["local"].getPlug("ikVisibility").get())),
        "OUTPUT segment length local min/max = {:.4f} / {:.4f} cm   world min = {:.4f} cm   tip = ({:.2f}, {:.2f}) cm".format(
            min(localLengths), max(localLengths), min(worldLengths), tip[12], tip[13]),
        "CHECK |output - independent| = {:.7f}   |local length - {:.1f}| = {:.7f} cm".format(error, LENGTH, lengthError),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    return {"frame": frame, "presentation_stage": stage, "blend": blend, "matrix_error": error,
            "local_lengths": localLengths, "world_lengths": worldLengths, "length_error": lengthError,
            "ok": error < 1e-4 and lengthError < 1e-4}


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
        folder = recordVideo("FkIkChain: 尻尾のFK/IKの切り替え", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "fk_ik_chain.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-fk-ik-chain.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("fk-ik-chain-%Y%m%d-%H%M%S")
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
