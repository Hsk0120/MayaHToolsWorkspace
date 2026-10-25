"""ChainNet(2本の親チェーンのFKの動きを、間の子チェーンへ割合で受け渡す)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_chain_net.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 30
#: チェーンの役割と根元のZ(cm)。両端が親(黄)、間が子(緑・青)。
ROLES = [("masterA", -4.0), ("slave0", -2.0), ("slave1", 0.0), ("slave2", 2.0), ("masterB", 4.0)]
COUNT = 4
LENGTH = 2.5
# (親Aの各節のrotateZ, 親Bの各節のrotateZ, 親Bの各節のrotateY, 子1の節1のrotateY, bias1, 次の姿勢へ向かう段階名)。
POSES = [
    (0, 0, 0, 0, 0.5, "1 REST"),
    (0, 0, 0, 0, 0.5, "2 BEND MASTER A ONLY (B STAYS)"),
    (-20, 0, 0, 0, 0.5, "3 BEND MASTER B THE OTHER WAY AND SIDEWAYS"),
    (-20, 20, -30, 0, 0.5, "4 ANIMATE SLAVE 1 ON TOP (OWN ROTATE Y)"),
    (-20, 20, -30, 25, 0.5, "5 CHANGE bias1 FROM 0.5 TO 1.0 (FOLLOW B)"),
    (-20, 20, -30, 25, 1.0, "6 RETURN TO REST"),
    (0, 0, 0, 0, 0.5, "6 RETURN TO REST"),
    (0, 0, 0, 0, 0.5, "6 RETURN TO REST"),
]


def pose(frame):
    """フレームの入力値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:5], POSES[index + 1][:5])]
    return values + [POSES[index][5]]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _box(name, parent, group, size):
    """parentの下に、指定の大きさ(X・Y・Z)の箱を作る。"""
    from maya import cmds
    box = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    cmds.parent(box, parent, relative=True)
    cmds.sets(box, edit=True, forceElement=group)
    return box


def buildScene():
    """検証シーンを作り、(panel, チェーンの辞書, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import ChainNet
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    yellow = _shader("masterYellow", (1.0, 0.85, 0.1))
    green = _shader("slaveGreen", (0.1, 0.85, 0.2))
    blue = _shader("slaveBlue", (0.2, 0.5, 1.0))
    body = cmds.createNode("transform", name="fin_GRP")
    chains = {}
    for role, z in ROLES:
        joints, parent = [], body
        for index in range(COUNT):
            joint = cmds.createNode("joint", name="{}{}_JNT".format(role, index), parent=parent)
            cmds.setAttr(joint + ".translate", LENGTH if index else 0.0, 0, 0 if index else z)
            group = yellow if role.startswith("master") else (blue if role == "slave1" else green)
            bone = _box("{}{}_GEO".format(role, index), joint, group, (LENGTH * 0.92, 0.35, 0.6))
            cmds.setAttr(bone + ".translateX", LENGTH / 2)
            joints.append(joint)
            parent = joint
        chains[role] = joints
    slaves = [chains["slave{}".format(i)] for i in range(3)]
    graph = ChainNet.create(chains["masterA"], chains["masterB"], slaves, name="chainNet", connect=True)
    owner = graph.container
    camera, camera_shape = cmds.camera(name="netCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(-8, 10, 27), lookAt=(5.5, -2.0, 0))
    window = cmds.window("chainNetValidationWindow", title="ChainNet - master chains drive the chains between",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("chainNetValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 7
    names = ["chainNetHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, chains, owner, values, names


def _matrix(plug):
    """plugの行列。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    return om.MMatrix(cmds.getAttr(plug))


def _translation(x, y, z):
    """平行移動だけの行列。"""
    from maya.api import OpenMaya as om
    matrix = om.MTransformationMatrix()
    matrix.setTranslation(om.MVector(x, y, z), om.MSpace.kTransform)
    return matrix.asMatrix()


def _blend(first, second, weight):
    """blendMatrixと同じ補間(位置は線形、回転はクォータニオンの球面線形補間)の独立計算。"""
    from maya.api import OpenMaya as om
    a, b = om.MTransformationMatrix(first), om.MTransformationMatrix(second)
    result = om.MTransformationMatrix()
    ta, tb = a.translation(om.MSpace.kTransform), b.translation(om.MSpace.kTransform)
    result.setTranslation(ta + (tb - ta) * weight, om.MSpace.kTransform)
    result.setRotation(om.MQuaternion.slerp(a.rotation(asQuaternion=True), b.rotation(asQuaternion=True), weight))
    return result.asMatrix()


def _bend(matrix):
    """行列の回転角(度、0〜180)。"""
    from maya.api import OpenMaya as om
    angle = math.degrees(abs(om.MTransformationMatrix(matrix).rotation(asQuaternion=True).asAxisAngle()[1]))
    angle %= 360.0
    return min(angle, 360.0 - angle)


def evaluate_frame(frame, chains, owner, values, names):
    """入力を更新し、子チェーンの各節のワールド行列を、OpenMayaで独立に求めた差の補間と節の積と比較する。"""
    from maya import cmds
    az, bz, by, own, bias1, stage = pose(frame)
    for index, node in enumerate(chains["masterA"]):
        cmds.setAttr(node + ".rotate", 0, 0, az * (0.6 + 0.4 * index / (COUNT - 1)))
    for node in chains["masterB"]:
        cmds.setAttr(node + ".rotate", 0, by * 0.5, bz)
    cmds.setAttr(chains["slave1"][1] + ".rotateY", own)
    owner.getPlug("bias1").set(bias1)
    # 生成時は全ての節の rotate・jointOrient が0なので、生成時のローカル行列は平行移動だけ。
    error, bends = 0.0, []
    for slave in range(3):
        bias = owner.getPlug("bias{}".format(slave)).get()
        chain = chains["slave{}".format(slave)]
        parent = _matrix("fin_GRP.worldMatrix[0]")
        for index, node in enumerate(chain):
            deltas = []
            for role, z in (ROLES[0], ROLES[4]):
                rest = _translation(LENGTH if index else 0.0, 0, 0 if index else z)
                deltas.append(_matrix(chains[role][index] + ".matrix") * rest.inverse())
            delta = _blend(deltas[0], deltas[1], bias)
            rest = _translation(LENGTH if index else 0.0, 0, 0 if index else ROLES[slave + 1][1])
            local = _matrix(node + ".matrix") * rest.inverse() * delta * rest
            parent = local * parent
            actual = _matrix(node + ".worldMatrix[0]")
            error = max(error, max(abs(a - b) for a, b in zip(actual, parent)))
            if index == 1:
                bends.append(_bend(_matrix("{}.delta{}_1".format(owner, slave))))
    biases = [owner.getPlug("bias{}".format(i)).get() for i in range(3)]
    values[:] = [
        "YELLOW = master chains A (back) and B (front), driven   GREEN = slave chains 0, 2   BLUE = slave chain 1",
        "STAGE: " + stage,
        "fixed: bias0 = 0.25  bias2 = 0.75   bias = share of master B   D = M * M0^-1 per joint (own rest space)",
        "slave joint offsetParentMatrix = S0^-1 * blend(D_A, D_B, bias) * S0 * O0   (slave keys layer on top)",
        "INPUT master A rotateZ = {:+6.1f} deg (x0.6 to x1.0 root to tip)   master B rotate = (0, {:+6.1f}, {:+6.1f}) deg   "
        "slave1 own rotateY = {:+5.1f} deg   bias1 = {:4.2f}".format(az, by * 0.5, bz, own, biases[1]),
        "OUTPUT bend received at joint 1: slave0 {:5.1f}  slave1 {:5.1f}  slave2 {:5.1f} deg".format(*bends),
        "CHECK slave world matrices vs OpenMaya: max error {:.2e}".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4
    return {"frame": frame, "presentation_stage": stage, "input": [az, bz, by, own, bias1], "biases": biases,
            "bend_degrees": bends, "max_error": error, "ok": ok}


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
        panel, chains, owner, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("ChainNet: 両端の親チェーンの動きを間の子チェーンへ受け渡す", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, chains, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "chain_net.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-chain-net.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("chain-net-%Y%m%d-%H%M%S")
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
