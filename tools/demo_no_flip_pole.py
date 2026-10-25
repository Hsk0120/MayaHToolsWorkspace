"""NoFlipPoleの反転しない膝のポールを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_no_flip_pole.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
REACH = 9.0
HIP_HEIGHT = 10.0
#: 左(赤、Z=+13)はワールドに固定したポール、右(緑、Z=-13)はNoFlipPoleのポール。同じ足の動きを与える。
LEGS = (("fixed", 13.0, 13), ("noFlip", -13.0, 14))
# (足の振り角[度、真下0・前が正], 足のY回りの向き[度], kneeTwist[度], 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, 0.0, 0.0, "1 REST"),
    (0.0, 0.0, 0.0, "2 SWING THE FOOT BACK"),
    (-50.0, 0.0, 0.0, "3 SWING FORWARD AND UP (PAST THE FIXED POLE)"),
    (70.0, 0.0, 0.0, "4 BACK TO REST"),
    (0.0, 0.0, 0.0, "5 TURN THE FOOT 60 deg: KNEE FOLLOWS THE FOOT"),
    (0.0, 60.0, 0.0, "6 kneeTwist 0 -> -45 deg"),
    (0.0, 60.0, -45.0, "7 SWING FORWARD WITH TURNED FOOT AND TWIST"),
    (60.0, 60.0, -45.0, "8 RETURN TO REST"),
    (0.0, 0.0, 0.0, "8 RETURN TO REST"),
    (0.0, 0.0, 0.0, "8 RETURN TO REST"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:3], POSES[index + 1][:3])]
    return values[0], values[1], values[2], POSES[index][3]


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


def _bone(name, parent, child, group):
    """jointの間に骨の形の円柱を置く(表示用)。"""
    from maya import cmds
    length = cmds.getAttr(child + ".translate")[0]
    length = math.sqrt(sum(v * v for v in length))
    bone = cmds.polyCylinder(name=name, radius=0.35, height=length, axis=(1, 0, 0))[0]
    cmds.parent(bone, parent, relative=True)
    cmds.setAttr(bone + ".translateX", length / 2)
    cmds.sets(bone, edit=True, forceElement=group)


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import NoFlipPole
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {13: _shader("fixedRed", (0.9, 0.15, 0.1)), 14: _shader("noFlipGreen", (0.15, 0.75, 0.25)),
              "foot": _shader("footGray", (0.6, 0.6, 0.65))}
    legs = {}
    for role, z, color in LEGS:
        cmds.select(clear=True)
        hip = cmds.joint(name=role + "_hip", position=(0, HIP_HEIGHT, z))
        knee = cmds.joint(name=role + "_knee", position=(0, 5.5, z + 1.2))
        ankle = cmds.joint(name=role + "_ankle", position=(0, HIP_HEIGHT - REACH, z))
        cmds.joint(hip, edit=True, orientJoint="xyz", secondaryAxisOrient="zup", children=True)
        cmds.select(clear=True)
        handle = cmds.ikHandle(startJoint=hip, endEffector=ankle, solver="ikRPsolver", name=role + "_ik")[0]
        foot = cmds.createNode("transform", name=role + "_footCtrl")
        cmds.setAttr(foot + ".translate", 0, HIP_HEIGHT - REACH, z)
        handle = cmds.parent(handle, foot)[0]
        cmds.setAttr(handle + ".visibility", False)
        arrow = cmds.polyCone(name=role + "_footArrow", radius=0.6, height=2.4, axis=(0, 0, 1))[0]
        cmds.parent(arrow, foot, relative=True)
        cmds.setAttr(arrow + ".translateZ", 1.2)
        cmds.sets(arrow, edit=True, forceElement=groups["foot"])
        _bone(role + "_thigh_GEO", hip, knee, groups[color])
        _bone(role + "_shin_GEO", knee, ankle, groups[color])
        ball = cmds.polySphere(name=role + "_pole_GEO", radius=0.5)[0]
        cmds.sets(ball, edit=True, forceElement=groups[color])
        legs[role] = {"hip": hip, "knee": knee, "ankle": ankle, "handle": handle, "foot": foot, "pole": ball,
                      "z": z}
    graph = NoFlipPole.create(legs["noFlip"]["hip"], legs["noFlip"]["foot"], mid=legs["noFlip"]["knee"],
                              name="noFlipPole", distance=6.0)
    owner = graph.container
    cmds.connectAttr(str(owner) + ".matrix", legs["noFlip"]["pole"] + ".offsetParentMatrix")
    rest = cmds.xform(legs["noFlip"]["pole"], query=True, worldSpace=True, translation=True)
    cmds.xform(legs["fixed"]["pole"], worldSpace=True,
               translation=(rest[0], rest[1], rest[2] - legs["noFlip"]["z"] + legs["fixed"]["z"]))
    for leg in legs.values():
        cmds.poleVectorConstraint(leg["pole"], leg["handle"])
    camera, camera_shape = cmds.camera(name="noFlipPoleCamera", focalLength=35)
    # 真横(+X)から。2本の脚を前後(Z)に離して並べ、足の振りと膝の向きが重ならずに見える位置に固定する。
    cmds.viewPlace(camera_shape, eye=(60, 3, 0), lookAt=(0, 3, 0))
    window = cmds.window("noFlipPoleValidationWindow", title="NoFlipPole - knee pole without flipping",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("noFlipPoleValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, ikHandles=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("noFlipPole", 8)
    scene = {"owner": owner, "legs": legs, "offset": math.radians(cmds.getAttr(str(owner) + ".offset"))}
    return panel, scene, values, names


def _vector(node):
    from maya.api import OpenMaya as om
    return om.MVector(*cmds_xform(node))


def cmds_xform(node):
    """ノードのワールド位置。"""
    from maya import cmds
    return cmds.xform(node, query=True, worldSpace=True, translation=True)


def _kneeAngle(leg, twist):
    """足の前の向き(脚の軸に垂直な面へ射影)を twist だけ回した向きと、膝の向きの角度(度)。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    a, k, b = _vector(leg["hip"]), _vector(leg["knee"]), _vector(leg["foot"])
    axis = (b - a).normal()
    knee = k - a
    knee = (knee - axis * (knee * axis)).normal()
    forward = om.MVector(0, 0, 1) * om.MMatrix(cmds.getAttr(leg["foot"] + ".worldMatrix[0]"))
    side = (forward - axis * (forward * axis)).normal()
    target = side.rotateBy(om.MQuaternion(twist, axis))
    return math.degrees(math.acos(max(-1.0, min(1.0, knee * target))))


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、ポールの位置を式と、膝の向きを足の前の向きと比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import NoFlipPole
    swing, yaw, twist, stage = pose(frame)
    owner, legs, offset = scene["owner"], scene["legs"], scene["offset"]
    owner.getPlug("kneeTwist").set(math.radians(twist))
    for leg in legs.values():
        angle = math.radians(swing)
        cmds.setAttr(leg["foot"] + ".translate", 0, HIP_HEIGHT - REACH * math.cos(angle),
                     leg["z"] + REACH * math.sin(angle))
        cmds.setAttr(leg["foot"] + ".rotateY", yaw)
    green, red = legs["noFlip"], legs["fixed"]
    forward = om.MVector(0, 0, 1) * om.MMatrix(cmds.getAttr(green["foot"] + ".worldMatrix[0]"))
    expected = om.MVector(*NoFlipPole.polePosition(cmds_xform(green["hip"]), cmds_xform(green["foot"]), forward,
                                                    6.0, 0.5, offset + math.radians(twist)))
    error = (_vector(green["pole"]) - expected).length()
    green_angle = _kneeAngle(green, offset + math.radians(twist))
    red_angle = _kneeAngle(red, offset + math.radians(twist))
    values[:] = [
        "GREEN (right) = NoFlipPole (pole follows the foot)   RED (left) = pole fixed in world   GRAY cone = foot forward",
        "STAGE: " + stage,
        "fixed: distance = 6 cm   position = 0.5   offset = {:.2f} deg (rest knee from foot forward)   leg reach 9 cm".format(
            math.degrees(offset)),
        "frame A: Y = hip -> foot, X = foot forward projected   pole = hip + Y * L * 0.5 + (X cos t - Z sin t) * distance",
        "t = offset + kneeTwist   knee angle = angle between the knee direction and (foot forward turned by t)",
        "INPUT swing = {:6.1f} deg (0 = down, + = forward)   foot yaw = {:5.1f} deg   kneeTwist = {:6.1f} deg".format(
            swing, yaw, twist),
        "OUTPUT knee angle: GREEN = {:6.2f} deg   RED = {:6.1f} deg (RED flips when > 90)".format(green_angle, red_angle),
        "CHECK |pole - formula| = {:.7f} cm   GREEN knee angle < 0.5 deg".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and green_angle < 0.5
    return {"frame": frame, "presentation_stage": stage, "input": {"swing": swing, "yaw": yaw, "kneeTwist": twist},
            "pole_error": error, "green_knee_angle": green_angle, "red_knee_angle": red_angle, "ok": ok}


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
        folder = recordVideo("NoFlipPole: 反転しない膝のポール", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "no_flip_pole.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-no-flip-pole.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("no-flip-pole-%Y%m%d-%H%M%S")
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
