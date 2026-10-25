"""BodyProportionの体格のパラメーターを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_body_proportion.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 36
NAMES = ("armLength", "shoulderWidth", "legLength", "armThickness")
# (armLength, shoulderWidth, legLength, armThickness, 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, 0.0, 0.0, 0.0, "1 STANDARD BODY (all 0)"),
    (0.0, 0.0, 0.0, 0.0, "2 armLength 0 -> 1"),
    (1.0, 0.0, 0.0, 0.0, "3 armLength 1 -> 2 (clamped at 1)"),
    (2.0, 0.0, 0.0, 0.0, "4 armLength -> -1 (negative side: own amount)"),
    (-1.0, 0.0, 0.0, 0.0, "5 shoulderWidth and legLength -> 1"),
    (-1.0, 1.0, 1.0, 0.0, "6 armThickness -> 2"),
    (-1.0, 1.0, 1.0, 2.0, "7 armThickness -> -1, legLength -> -1"),
    (-1.0, 1.0, -1.0, -1.0, "8 RETURN TO STANDARD"),
    (0.0, 0.0, 0.0, 0.0, "8 RETURN TO STANDARD"),
    (0.0, 0.0, 0.0, 0.0, "8 RETURN TO STANDARD"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:4], POSES[index + 1][:4])]
    return values, POSES[index][4]


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


def _bone(name, parent, group, length, sign):
    """parentの子に、骨の向き(X)の円柱を作る(上腕の太さの目印)。"""
    from maya import cmds
    bone = cmds.polyCylinder(name=name, radius=0.45, height=length, axis=(1, 0, 0))[0]
    cmds.parent(bone, parent, relative=True)
    cmds.setAttr(bone + ".translateX", sign * length / 2.0)
    cmds.sets(bone, edit=True, forceElement=group)
    return bone


BONES = [("hips", "chest"), ("chest", "head"), ("chest", "shoulderL"), ("chest", "shoulderR"),
         ("shoulderL", "elbowL"), ("elbowL", "wristL"), ("wristL", "handL"),
         ("shoulderR", "elbowR"), ("elbowR", "wristR"), ("wristR", "handR"),
         ("hips", "hipL"), ("hipL", "kneeL"), ("kneeL", "ankleL"), ("ankleL", "toeL"),
         ("hips", "hipR"), ("hipR", "kneeR"), ("kneeR", "ankleR"), ("ankleR", "toeR")]


def _link(prefix, parent, child, group):
    """親のjointの子に、子のjointへ向かう細い円柱を作る(表示用。長さは _fitLinks で合わせる)。"""
    from maya import cmds
    link = cmds.polyCylinder(name="{}_{}_{}_LINK".format(prefix, parent, child), radius=0.18, height=1.0,
                             axis=(0, 1, 0))[0]
    cmds.parent(link, "{}_{}".format(prefix, parent), relative=True)
    cmds.sets(link, edit=True, forceElement=group)
    return link, "{}_{}".format(prefix, child)


def _fitLinks(links):
    """表示用の円柱を、親から子のjointの位置まで伸ばす(判定には使わない)。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    for link, child in links:
        vector = om.MVector(*cmds.getAttr(child + ".translate")[0])
        length = vector.length()
        if length < 1e-6:
            continue
        rotation = om.MVector(0, 1, 0).rotateTo(vector.normal()).asEulerRotation()
        cmds.setAttr(link + ".translate", *(vector * 0.5))
        cmds.setAttr(link + ".rotate", *[om.MAngle(a).asDegrees() for a in (rotation.x, rotation.y, rotation.z)])
        cmds.setAttr(link + ".scaleY", length)


def _expected(owner, index, role, values):
    """containerの生成時の値・量と、パラメーターの値から、骨indexの値を独立に求める。"""
    from maya import cmds
    upper = role[0].upper() + role[1:]
    result = list(cmds.getAttr("{}.rest{}{}".format(owner, upper, index))[0])
    for name in NAMES:
        attribute = "{}.{}{}{}".format(owner, name, upper, index)
        if not cmds.objExists(attribute):
            continue
        low, high = cmds.getAttr(owner + "." + name + "Minimum"), cmds.getAttr(owner + "." + name + "Maximum")
        value = min(max(values[name], low), high)
        amount = cmds.getAttr(attribute)[0] if value >= 0 else cmds.getAttr(
            "{}.{}{}Negative{}".format(owner, name, upper, index))[0]
        for axis in range(3):
            result[axis] += abs(value) * amount[axis]
    return result


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setupSamples import SetupSamples
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"green": _shader("bodyGreen", (0.15, 0.75, 0.25)), "ghost": _shader("standardGhost", (0.85, 0.2, 0.15), 0.6)}
    ghost = SetupSamples.build("bodyProportion", name="refBody")
    sample = SetupSamples.build("bodyProportion", name="figure")
    links = {}
    for prefix, group in (("refBody", groups["ghost"]), ("figure", groups["green"])):
        links[prefix] = [_link(prefix, parent, child, group) for parent, child in BONES]
        _fitLinks(links[prefix])
    for prefix, group in (("refBody", groups["ghost"]), ("figure", groups["green"])):
        for side, sign in (("L", 1), ("R", -1)):
            _bone("{}_upper{}_GEO".format(prefix, side), "{}_shoulder{}".format(prefix, side), group, 3.0, sign)
    camera, camera_shape = cmds.camera(name="bodyProportionCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(-10.5, 7.6, 44), lookAt=(-10.5, 7.6, 0))
    window = cmds.window("bodyProportionValidationWindow", title="BodyProportion - body shape", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("bodyProportionValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("bodyProportion", 8)
    joints = [joint.getFullName() for joint in sample.setup.getJoints()]
    scene = {"owner": sample.container, "joints": joints, "links": links["figure"]}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """パラメーターを更新し、全ての骨の translate・scale を独立に求めた値と比較した診断を返す。"""
    from maya import cmds
    numbers, stage = pose(frame)
    owner = scene["owner"]
    current = dict(zip(NAMES, numbers))
    for name, value in current.items():
        cmds.setAttr(owner + "." + name, value)
    error = 0.0
    for index, joint in enumerate(scene["joints"]):
        for role in ("translate", "scale"):
            actual = cmds.getAttr(joint + "." + role)[0]
            error = max(error, max(abs(a - b) for a, b in zip(actual, _expected(owner, index, role, current))))
    _fitLinks(scene["links"])
    wrist = cmds.xform("figure_wristL", query=True, worldSpace=True, translation=True)
    ankle = cmds.xform("figure_ankleL", query=True, worldSpace=True, translation=True)
    values[:] = [
        "TRANSPARENT RED = standard body (all 0)   GREEN = changed by the parameters (output)",
        "STAGE: " + stage,
        "fixed: range -1..1 (armThickness -1..2)   at -1: arm -0.6 cm/joint, thickness -0.3",
        "fixed at +1: arm +0.9 cm/joint, shoulder +0.8 cm, leg -0.8 cm/joint, thickness scaleYZ +0.4",
        "value = rest + clamp(v, 0, max) * amount + clamp(-v, 0, -min) * negativeAmount",
        "INPUT armLength = {:5.2f}  shoulderWidth = {:5.2f}  legLength = {:5.2f}  armThickness = {:5.2f}".format(*numbers),
        "OUTPUT wristL x = {:6.3f} cm   ankleL y = {:6.3f} cm   shoulderL scaleY = {:5.3f}".format(
            wrist[0], ankle[1], cmds.getAttr("figure_shoulderL.scaleY")),
        "CHECK max |joint translate/scale - formula| = {:.2e}  (all joints)".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-5
    return {"frame": frame, "presentation_stage": stage, "input": current, "wrist": wrist, "ankle": ankle,
            "error": error, "ok": ok}


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
        folder = recordVideo("BodyProportion: 体格のパラメーター", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "body_proportion.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-body-proportion.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("body-proportion-%Y%m%d-%H%M%S")
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
