"""UnevenGroundの凹凸のある地面への足と腰の接地を、メニューと同じサンプルで専用Maya GUIに録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_uneven_ground.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 48
NAME = "ugd"
SIDES = ("left", "right")
# ((左の地面 ty, rx, rz, 右の地面 ty, 左足 tz, 左足 ty, align), 次の状態へ向かう段階名)。
POSES = [
    ((1.5, 12.0, 8.0, 0.0, 0.5, 0.0, 1.0), "1 REST (feet on the ground, hips on the lower foot)"),
    ((1.5, 12.0, 8.0, 0.0, 0.5, 0.0, 1.0), "2 LEFT GROUND steps up"),
    ((3.5, 12.0, 8.0, 0.0, 0.5, 0.0, 1.0), "3 LEFT GROUND tilts"),
    ((3.5, 22.0, -18.0, 0.0, 0.5, 0.0, 1.0), "4 RIGHT GROUND goes down (hips follow the lower foot)"),
    ((3.5, 22.0, -18.0, -2.0, 0.5, 0.0, 1.0), "5 LEFT FOOT steps forward and lifts (flat-floor animation)"),
    ((3.5, 22.0, -18.0, -2.0, 2.5, 1.2, 1.0), "6 ALIGN 1 -> 0 (sole no longer follows the slope)"),
    ((3.5, 22.0, -18.0, -2.0, 2.5, 1.2, 0.0), "7 RETURN"),
    ((1.5, 12.0, 8.0, 0.0, 0.5, 0.0, 1.0), "7 RETURN"),
    ((1.5, 12.0, 8.0, 0.0, 0.5, 0.0, 1.0), "7 RETURN"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    smooth = weight * weight * (3 - 2 * weight)
    start, end = POSES[index][0], POSES[index + 1][0]
    return [a + (b - a) * smooth for a, b in zip(start, end)], POSES[index][1]


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
    """メニューと同じサンプルで検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setupSamples import SetupSamples
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    sample = SetupSamples.build("unevenGround", name=NAME)

    def node(suffix):
        return cmds.ls(NAME + suffix, long=True)[0]

    scene = {"owner": str(sample.container), "hips": node("_hipsCtrl"), "hipsOut": node("_hipsOut"),
             "feet": [node("_leftFootCtrl"), node("_rightFootCtrl")],
             "outs": [node("_leftFootOut"), node("_rightFootOut")],
             "grounds": [node("_leftGround"), node("_rightGround")]}
    # 録画で見分けられるよう、地面(灰の板)・入力の足(赤の枠)・出力の足(黄の箱)・腰(緑の球)を子に置く。
    shaders = {}
    for key, color in (("ground", (0.55, 0.55, 0.6)), ("foot", (1.0, 0.8, 0.1)), ("hips", (0.2, 0.8, 0.3))):
        shader = cmds.shadingNode("lambert", asShader=True, name="ugd" + key + "Mat")
        cmds.setAttr(shader + ".color", *color, type="double3")
        group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=shader + "SG")
        cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
        shaders[key] = group

    def attach(mesh, parent, translate, key):
        mesh = cmds.parent(mesh, parent, relative=True)[0]
        cmds.setAttr(mesh + ".translate", *translate)
        if key:
            cmds.sets(mesh, edit=True, forceElement=shaders[key])
        return mesh

    for ground in scene["grounds"]:
        # locator の scale (2, 0.3, 2) の下なので、板は 1.4 x 1.4 (表示 2.8 x 2.8)。
        attach(cmds.polyPlane(name=ground.rsplit("|", 1)[-1] + "Plane", width=1.4, height=1.4,
                              subdivisionsX=4, subdivisionsY=4)[0], ground, (0, 0, 0), "ground")
    for foot, out in zip(scene["feet"], scene["outs"]):
        attach(cmds.polyCube(name=out.rsplit("|", 1)[-1] + "Box", width=1.0, height=0.4, depth=2.0)[0],
               out, (0, 0.2, 0.3), "foot")
        ghost = attach(cmds.polyCube(name=foot.rsplit("|", 1)[-1] + "Ghost", width=1.0, height=0.4, depth=2.0)[0],
                       foot, (0, 0.2, 0.3), None)
        cmds.setAttr(ghost + ".overrideEnabled", True)
        cmds.setAttr(ghost + ".overrideShading", False)
        cmds.setAttr(ghost + ".overrideColor", 13)
    attach(cmds.polySphere(name="ugdHipsBall", radius=0.8)[0], scene["hipsOut"], (0, 0, 0), "hips")
    # 腰から足への脚の線(表示用。出力の位置を結ぶ1次の曲線)。
    for side, out in zip(SIDES, scene["outs"]):
        curve = cmds.curve(name="ugd" + side + "Leg", degree=1, point=[(0, 0, 0), (0, 0, 0)])
        shape = cmds.listRelatives(curve, shapes=True, fullPath=True)[0]
        for index, source in enumerate((scene["hipsOut"], out)):
            point = cmds.createNode("decomposeMatrix", name="ugd{}Leg{}".format(side, index))
            cmds.connectAttr(source + ".worldMatrix[0]", point + ".inputMatrix")
            cmds.connectAttr(point + ".outputTranslate", shape + ".controlPoints[{}]".format(index))
        cmds.setAttr(curve + ".overrideEnabled", True)
        cmds.setAttr(curve + ".overrideColor", 14)
    view = cmds.camera(name="ugdView", focalLength=35)[0]
    cmds.xform(view, translation=(13, 15, 17))
    cmds.viewLookAt(view, position=(-3.0, 4.5, 0.5))
    window = cmds.window("ugdValidationWindow", title="UnevenGround - feet and hips on uneven ground",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("ugdValidationPanel", parent=pane, camera=view, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=True,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=True, wireframeOnShaded=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("ugd", 7)
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """地面・足・align を動かし、足が地面の平面の上に載ること・腰が低い方の足に合わせることを確かめる。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    (gy, grx, grz, ry, fz, fy, align), stage_name = pose(frame)
    left, right = scene["grounds"]
    cmds.setAttr(left + ".translateY", gy)
    cmds.setAttr(left + ".rotateX", grx)
    cmds.setAttr(left + ".rotateZ", grz)
    cmds.setAttr(right + ".translateY", ry)
    cmds.setAttr(scene["feet"][0] + ".translateZ", fz)
    cmds.setAttr(scene["feet"][0] + ".translateY", fy)
    cmds.setAttr(scene["owner"] + ".align", align)
    floor = cmds.getAttr(scene["owner"] + ".floorHeight")
    errors, lifts, tilts = [], [], []
    for foot, out, ground in zip(scene["feet"], scene["outs"], scene["grounds"]):
        before = om2.MMatrix(cmds.getAttr(foot + ".worldMatrix[0]"))
        after = om2.MMatrix(cmds.getAttr(out + ".worldMatrix[0]"))
        plane = om2.MMatrix(cmds.getAttr(ground + ".worldMatrix[0]"))
        point = om2.MVector(before[12], before[13], before[14])
        moved = om2.MVector(after[12], after[13], after[14])
        normal = om2.MVector(plane[4], plane[5], plane[6]).normal()
        origin = om2.MVector(plane[12], plane[13], plane[14])
        # 試験側の式: 足の真下の地面の高さ = 足を通る鉛直な線と平面の交点。
        lift = point.y + ((origin - point) * normal) / normal.y - floor
        lifts.append(lift)
        up = om2.MVector(after[4], after[5], after[6]).normal()
        errors.append(max(abs(moved.x - point.x), abs(moved.z - point.z), abs(moved.y - (point.y + lift))))
        if align == 1.0:
            errors.append(max(abs(up[i] - normal[i]) for i in range(3)))
        elif align == 0.0:
            rest = om2.MVector(before[4], before[5], before[6]).normal()
            errors.append(max(abs(up[i] - rest[i]) for i in range(3)))
        tilts.append(math.degrees(om2.MVector(0, 1, 0).angle(up)))
    hips = om2.MMatrix(cmds.getAttr(scene["hips"] + ".worldMatrix[0]"))
    hipsOut = om2.MMatrix(cmds.getAttr(scene["hipsOut"] + ".worldMatrix[0]"))
    drop = hipsOut[13] - hips[13]
    errors.append(abs(drop - min(lifts)))
    error = max(errors)
    values[:] = [
        "GRAY = ground per foot   RED box = input foot (flat floor)   YELLOW = output foot   GREEN = hips output",
        "STAGE: " + stage_name,
        "ground height under the foot  y_g = p.y + ((g - p) . n) / n.y      lift h = y_g - floorHeight (floor = 0)",
        "foot out = tilt by D (world up -> n, x align) then move up by h      hips out = hips + min(h_left, h_right)",
        "INPUT left ground y {:5.2f} rx {:6.1f} rz {:6.1f}  right ground y {:5.2f}  left foot z {:4.2f} y {:4.2f}  align {:4.2f}".format(
            gy, grx, grz, ry, fz, fy, align),
        "OUTPUT lift L {:6.3f}  R {:6.3f} cm   hips {:6.3f} cm   sole tilt L {:5.1f}  R {:5.1f} deg".format(
            lifts[0], lifts[1], drop, tilts[0], tilts[1]),
        "CHECK |output - formula| {:.1e}  {}".format(error, "OK" if error < 1e-4 else "NG"),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    return {"frame": frame, "presentation_stage": stage_name,
            "input": {"leftGround": [gy, grx, grz], "rightGroundY": ry, "leftFoot": [fz, fy], "align": align},
            "lifts": lifts, "hipsDrop": drop, "tilts": tilts, "error": error, "ok": error < 1e-4}


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
        folder = recordVideo("UnevenGround: 平らな床で付けた足と腰を、凹凸のある地面へ接地させる", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "uneven_ground.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-uneven-ground.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("uneven-ground-%Y%m%d-%H%M%S")
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
