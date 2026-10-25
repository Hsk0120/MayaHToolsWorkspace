"""MetaSpread(両端の中手骨の回転を間へ割合で分配)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_meta_spread.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
#: 中手骨の付け根の位置(cm、手の空間)とjointOrientのY(度)。4本、人差し指側から小指側。
METAS = [((0.0, 0.0, 3.0), -12.0), ((0.0, 0.3, 1.0), -4.0), ((0.0, 0.3, -1.0), 4.0), ((0.0, 0.0, -3.0), 12.0)]
LENGTH = 7.0
# (人差し指側の回転X・Y, 小指側の回転X・Y[度], 次の姿勢へ向かう段階名)。
POSES = [
    (0, 0, 0, 0, "1 REST"),
    (0, 0, 0, 0, "2 PINKY SIDE ONLY: CUP (X) AND SPREAD (Y)"),
    (0, 0, -40, -25, "3 INDEX SIDE ONLY"),
    (25, 15, -40, -25, "4 BOTH ENDS TOWARD OTHER DIRECTIONS"),
    (-10, -20, -30, 25, "5 RETURN TO REST"),
    (0, 0, 0, 0, "5 RETURN TO REST"),
    (0, 0, 0, 0, "5 RETURN TO REST"),
]


def pose(frame):
    """フレームの入力値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:4], POSES[index + 1][:4])]
    return values + [POSES[index][4]]


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
    """検証シーンを作り、(panel, 中手骨, 出力, container, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import MetaSpread
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    yellow = _shader("endYellow", (1.0, 0.85, 0.1))
    grey = _shader("restGrey", (0.6, 0.6, 0.6), transparency=0.7)
    green = _shader("outputGreen", (0.1, 0.85, 0.2))
    hand = cmds.createNode("transform", name="hand_GRP")
    cmds.setAttr(hand + ".rotate", 0, 0, -10)
    metas = []
    for index, (position, orient) in enumerate(METAS):
        meta = cmds.createNode("joint", name="meta{}_JNT".format(index), parent=hand)
        cmds.setAttr(meta + ".translate", *position)
        cmds.setAttr(meta + ".jointOrient", 0, orient, 0)
        bone = _box("meta{}_GEO".format(index), meta, yellow if index in (0, 3) else grey, (LENGTH, 0.6, 0.6))
        cmds.setAttr(bone + ".translateX", LENGTH / 2)
        metas.append(meta)
    graph = MetaSpread.create(metas[0], metas[3], metas[1:3], name="metaSpread")
    owner = graph.container
    outputs = []
    for index in range(2):
        out = cmds.createNode("transform", name="output{}_GRP".format(index), parent=hand)
        owner.getPlug("matrix{}".format(index)).connectTo(out + ".offsetParentMatrix")
        bone = _box("output{}_GEO".format(index), out, green, (LENGTH, 0.45, 0.45))
        cmds.setAttr(bone + ".translateX", LENGTH / 2)
        outputs.append(out)
    camera, camera_shape = cmds.camera(name="metaCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(4, 16, 14), lookAt=(4, -4, 0))
    window = cmds.window("metaSpreadValidationWindow", title="MetaSpread - rotation shared by the middles",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("metaSpreadValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 7
    names = ["metaSpreadHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, metas, outputs, owner, values, names


def _quat(matrix):
    """行列の回転のクォータニオン。"""
    from maya.api import OpenMaya as om
    return om.MTransformationMatrix(om.MMatrix(matrix)).rotation(asQuaternion=True)


def _angle(quaternion):
    """クォータニオンの回転角(度、0〜180)。"""
    angle = math.degrees(abs(quaternion.asAxisAngle()[1])) % 360.0
    return min(angle, 360.0 - angle)


def evaluate_frame(frame, metas, outputs, owner, values, names):
    """入力を更新し、DG出力をOpenMayaのクォータニオンの球面線形補間と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    ax, ay, bx, by, stage = pose(frame)
    cmds.setAttr(metas[0] + ".rotate", ax, ay, 0)
    cmds.setAttr(metas[3] + ".rotate", bx, by, 0)
    rests = [om.MEulerRotation(0, math.radians(orient), 0).asQuaternion() for _, orient in METAS]
    p0 = rests[0].inverse() * _quat(cmds.getAttr(metas[0] + ".matrix"))
    p1 = rests[3].inverse() * _quat(cmds.getAttr(metas[3] + ".matrix"))
    errors, angles = [], []
    for index, out in enumerate(outputs):
        weight = owner.getPlug("weight{}".format(index)).get()
        dot = p0.x * p1.x + p0.y * p1.y + p0.z * p1.z + p0.w * p1.w
        target = om.MQuaternion(-p1.x, -p1.y, -p1.z, -p1.w) if dot < 0 else p1
        expected = rests[index + 1] * om.MQuaternion.slerp(p0, target, weight)
        actual = _quat(cmds.getAttr(out + ".offsetParentMatrix"))
        errors.append(_angle(expected.inverse() * actual))
        angles.append(_angle(rests[index + 1].inverse() * actual))
    end_angles = [_angle(p0), _angle(p1)]
    values[:] = [
        "YELLOW = end metacarpals (driven)   GREEN = middle outputs   GREY (transparent) = original middle joints",
        "STAGE: " + stage,
        "fixed: weight0 = 1/3  weight1 = 2/3   jointOrient Y = -12, -4, 4, 12 deg (different per joint)",
        "P_end = R_rest^-1 * R_now (parent space)   out_i = R_i * slerp(P_first, P_last, weight_i) * T_i",
        "INPUT first rotate = ({:+6.1f}, {:+6.1f}) deg   last rotate = ({:+6.1f}, {:+6.1f}) deg   "
        "|P_first| = {:5.1f}  |P_last| = {:5.1f} deg".format(ax, ay, bx, by, end_angles[0], end_angles[1]),
        "OUTPUT middle rotation from rest: {:5.1f} deg / {:5.1f} deg".format(angles[0], angles[1]),
        "CHECK vs OpenMaya slerp: error {:.5f} deg / {:.5f} deg".format(errors[0], errors[1]),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = max(errors) < 0.01
    return {"frame": frame, "presentation_stage": stage, "input_degrees": [ax, ay, bx, by],
            "end_delta_degrees": end_angles, "middle_rotation_degrees": angles, "error_degrees": errors, "ok": ok}


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
        panel, metas, outputs, owner, values, names = buildScene()
        frames = SEGMENT * (len(POSES) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        folder = recordVideo("MetaSpread: 両端の回転を間へ分配", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, metas, outputs, owner, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "meta_spread.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-meta-spread.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("meta-spread-%Y%m%d-%H%M%S")
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
