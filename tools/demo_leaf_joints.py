"""LeafJoints(不均一なscaleを子へ伝えない書き出し用の枝と葉のjoint)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_leaf_joints.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 30
#: 腕の節の (名前, 親からの位置(cm), 骨の箱の長さ(cm))。
BONES = [("shoulder", (0.0, 0.0, 0.0), 4.0), ("elbow", (4.0, 0.0, 0.0), 3.5),
         ("wrist", (3.5, 0.0, 0.0), 1.5), ("hand", (1.5, 0.0, 0.0), 0.0)]
#: 上の腕(リグとLeafJoints)と下の腕(比較用)の高さ(cm)。
RIG_Y, NAIVE_Y = 3.0, -1.4
# (肘のscale X・Y・Z, 肩のrotateZ, 肘のrotateZ, 手首のscaleY・Z, 次の姿勢へ向かう段階名)。
POSES = [
    (1.0, 1.0, 1.0, 0, 0, 1.0, "1 REST"),
    (1.0, 1.0, 1.0, 0, 0, 1.0, "2 SQUASH THE ELBOW (SHORTER, THICKER)"),
    (0.65, 1.8, 1.8, 0, 0, 1.0, "3 RAISE THE SHOULDER AND BEND THE ELBOW"),
    (0.65, 1.8, 1.8, 10, 30, 1.0, "4 STRETCH THE ELBOW AND THIN THE WRIST"),
    (1.4, 0.6, 0.6, 10, 30, 1.6, "5 RETURN TO REST"),
    (1.0, 1.0, 1.0, 0, 0, 1.0, "5 RETURN TO REST"),
    (1.0, 1.0, 1.0, 0, 0, 1.0, "5 RETURN TO REST"),
]


def pose(frame):
    """フレームの入力値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:6], POSES[index + 1][:6])]
    return values + [POSES[index][6]]


def _shader(name, color, transparency=0.0):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    cmds.setAttr(shader + ".transparency", transparency, transparency, transparency, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _bone(name, parent, group, length, size):
    """parentの下に、+Xへ length 伸びる太さ size の箱を作る。"""
    from maya import cmds
    box = cmds.polyCube(name=name, width=length, height=size, depth=size)[0]
    cmds.parent(box, parent, relative=True)
    cmds.setAttr(box + ".translateX", length / 2)
    cmds.sets(box, edit=True, forceElement=group)
    return box


def _chain(prefix, parent, compensate):
    """腕のjointの列を作る。compensate なら jointツールと同じく親のscaleを inverseScale へ繋ぐ。"""
    from maya import cmds
    joints = []
    for name, position, _ in BONES:
        joint = cmds.createNode("joint", name="{}_{}_JNT".format(prefix, name), parent=parent)
        cmds.setAttr(joint + ".translate", *position)
        if joints:
            if compensate:
                cmds.connectAttr(joints[-1] + ".scale", joint + ".inverseScale")
            else:
                cmds.setAttr(joint + ".segmentScaleCompensate", False)
        joints.append(joint)
        parent = joint
    return joints


def buildScene():
    """検証シーンを作り、(panel, リグの腕, 比較の腕, LeafJoints, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import LeafJoints
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    yellow = _shader("rigYellow", (1.0, 0.85, 0.1), 0.65)
    green = _shader("leafGreen", (0.1, 0.85, 0.2))
    red = _shader("naiveRed", (0.9, 0.2, 0.15))
    rig_group = cmds.createNode("transform", name="rig_GRP")
    cmds.setAttr(rig_group + ".translateY", RIG_Y)
    arm = _chain("rig", rig_group, True)
    naive_group = cmds.createNode("transform", name="naive_GRP")
    cmds.setAttr(naive_group + ".translateY", NAIVE_Y)
    naive = _chain("naive", naive_group, False)
    export = cmds.createNode("transform", name="export_GRP")
    setup = LeafJoints.create(arm, name="leafJoints", parent=export)
    _, leaves = setup.getJoints()
    for (name, _, length), joint, leaf, copy in zip(BONES, arm, leaves, naive):
        if length:
            _bone("rig_{}_GEO".format(name), joint, yellow, length, 1.0)
            _bone("leaf_{}_GEO".format(name), str(leaf), green, length * 0.96, 0.8)
            _bone("naive_{}_GEO".format(name), copy, red, length * 0.96, 0.8)
        # 比較の腕は、リグの腕の値をそのまま segmentScaleCompensate 無しで掛けたもの(書き出し先へ直接出した場合)。
        for attribute in ("translate", "rotate", "scale"):
            cmds.connectAttr(joint + "." + attribute, copy + "." + attribute)
    camera, camera_shape = cmds.camera(name="leafCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(5.0, 2.2, 35), lookAt=(4.5, 0.9, 0))
    window = cmds.window("leafJointsValidationWindow", title="LeafJoints - scale stays in the leaf joints",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("leafJointsValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 7
    names = ["leafJointsHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, arm, naive, setup, values, names


def _matrix(plug):
    """plugの行列。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    return om.MMatrix(cmds.getAttr(plug))


def _scale(matrix):
    """行列のワールドのscale。"""
    from maya.api import OpenMaya as om
    return list(om.MTransformationMatrix(matrix).scale(om.MSpace.kWorld))


def _engineWorld(joint):
    """jointOrient・inverseScaleを使わず、translate・rotate・scaleの親子の積だけで求めたワールド行列。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    transform = om.MTransformationMatrix()
    transform.setScale(cmds.getAttr(joint + ".scale")[0], om.MSpace.kTransform)
    rotate = [om.MAngle.uiToInternal(value) for value in cmds.getAttr(joint + ".rotate")[0]]
    transform.setRotation(om.MEulerRotation(rotate))
    transform.setTranslation(om.MVector(cmds.getAttr(joint + ".translate")[0]), om.MSpace.kTransform)
    local = transform.asMatrix()
    parent = (cmds.listRelatives(joint, parent=True, fullPath=True) or [None])[0]
    if parent is None:
        return local
    if cmds.nodeType(parent) != "joint":
        return local * _matrix(parent + ".worldMatrix[0]")
    return local * _engineWorld(parent)


def evaluate_frame(frame, arm, naive, setup, values, names):
    """入力を更新し、葉のjointが腕と一致し、枝がscale 1で、scaleが葉にしか現れないことを確かめる。"""
    from maya import cmds
    sx, sy, sz, shoulder, elbow, wrist, stage = pose(frame)
    cmds.setAttr(arm[1] + ".scale", sx, sy, sz)
    cmds.setAttr(arm[0] + ".rotateZ", shoulder)
    cmds.setAttr(arm[1] + ".rotateZ", elbow)
    cmds.setAttr(arm[2] + ".scale", 1.0, 1.0 / wrist, 1.0 / wrist)
    cmds.setAttr(arm[2] + ".scaleX", wrist)
    branches, leaves = setup.getJoints()
    error, branch_scale = 0.0, 0.0
    for source, branch, leaf in zip(arm, branches, leaves):
        world = _matrix(source + ".worldMatrix[0]")
        for actual in (_matrix(str(leaf) + ".worldMatrix[0]"), _engineWorld(str(leaf))):
            error = max(error, max(abs(a - b) for a, b in zip(actual, world)))
        branch_scale = max(branch_scale, max(abs(value - 1.0) for value in _scale(_matrix(str(branch) + ".worldMatrix[0]"))))
    elbow_leaf = _scale(_matrix(str(leaves[1]) + ".worldMatrix[0]"))
    hand_leaf = _scale(_matrix(str(leaves[3]) + ".worldMatrix[0]"))
    hand_naive = _scale(_matrix(naive[3] + ".worldMatrix[0]"))
    values[:] = [
        "BOTTOM: RED = same channel values with no scale compensation (plain parent multiplication)   STAGE: " + stage,
        "TOP: YELLOW = rig arm (segment scale compensate on)   GREEN = LeafJoints leaf joints (export)",
        "branch B_i = N_i * N_parent^-1 (N = world matrix without scale and shear)   leaf F_i = W_i * N_i^-1 (scale only)",
        "INPUT elbow scale = ({:4.2f}, {:4.2f}, {:4.2f})   shoulder rotateZ = {:+5.1f} deg   elbow rotateZ = {:+5.1f} deg"
        "   wrist scaleX = {:4.2f}".format(sx, sy, sz, shoulder, elbow, wrist),
        "OUTPUT elbow leaf world scale = ({:4.2f}, {:4.2f}, {:4.2f})   hand leaf = ({:4.2f}, {:4.2f}, {:4.2f})".format(
            *(elbow_leaf + hand_leaf)),
        "RED hand world scale = ({:4.2f}, {:4.2f}, {:4.2f})  (inherits the elbow and wrist scale)".format(*hand_naive),
        "CHECK leaf = rig world and plain TRS product: max error {:.2e}   branch scale - 1: max {:.2e}".format(
            error, branch_scale),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and branch_scale < 1e-5 and max(abs(value - 1.0) for value in hand_leaf) < 1e-5
    return {"frame": frame, "presentation_stage": stage, "input": [sx, sy, sz, shoulder, elbow, wrist],
            "elbow_leaf_scale": elbow_leaf, "hand_leaf_scale": hand_leaf, "naive_hand_scale": hand_naive,
            "max_error": error, "max_branch_scale_error": branch_scale, "ok": ok}


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
        panel, arm, naive, setup, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("LeafJoints: 不均一なscaleを葉のjointだけに持たせる書き出し用の骨格", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, arm, naive, setup, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "leaf_joints.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-leaf-joints.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("leaf-joints-%Y%m%d-%H%M%S")
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
