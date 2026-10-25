"""LiveMirrorの左右の鏡像を、メニューと同じサンプルで専用Maya GUIに録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_live_mirror.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 48
NAME = "lmr"
JOINTS = ("shoulder", "elbow", "hand")
# ((肩rz, 肩ry, 肘ry, 手首rx, ルートtx, ルートry, 右手首の上乗せrz, weight), 次の状態へ向かう段階名)。
POSES = [
    ((-30.0, 0.0, 20.0, 0.0, 0.0, 0.0, 0.0, 1.0), "1 REST (right = mirror of left)"),
    ((-30.0, 0.0, 20.0, 0.0, 0.0, 0.0, 0.0, 1.0), "2 LEFT SHOULDER rotates"),
    ((25.0, -40.0, 20.0, 0.0, 0.0, 0.0, 0.0, 1.0), "3 LEFT ELBOW and WRIST rotate"),
    ((25.0, -40.0, 85.0, 60.0, 0.0, 0.0, 0.0, 1.0), "4 ROOT moves and turns (mirror plane follows)"),
    ((25.0, -40.0, 85.0, 60.0, 6.0, 35.0, 0.0, 1.0), "5 RIGHT WRIST own rotateZ (layered on the mirror)"),
    ((25.0, -40.0, 85.0, 60.0, 6.0, 35.0, 45.0, 1.0), "6 WEIGHT 1 -> 0 (back to the right pose at creation)"),
    ((25.0, -40.0, 85.0, 60.0, 6.0, 35.0, 45.0, 0.0), "7 RETURN"),
    ((-30.0, 0.0, 20.0, 0.0, 0.0, 0.0, 0.0, 1.0), "7 RETURN"),
    ((-30.0, 0.0, 20.0, 0.0, 0.0, 0.0, 0.0, 1.0), "7 RETURN"),
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
    from maya.api import OpenMaya as om2
    from mlrig.setupSamples import SetupSamples
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    sample = SetupSamples.build("liveMirror", name=NAME)
    root = cmds.ls(NAME + "_root", long=True)[0]
    left = [cmds.ls("{}_{}L".format(NAME, j), long=True)[0] for j in JOINTS]
    right = [cmds.ls("{}_{}R".format(NAME, j), long=True)[0] for j in JOINTS]
    owners = [sample.container, NAME + "_elbowMirror", NAME + "_handMirror"]
    # jointの表示色は録画で見分けにくいので、骨の向きに沿った箱(左=赤、右=緑)を子に置く。
    # 右は Behavior の鏡像なので、子の方向は局所の -X。
    shaders = {}
    for side, color in (("L", (0.85, 0.25, 0.2)), ("R", (0.2, 0.8, 0.3))):
        shader = cmds.shadingNode("lambert", asShader=True, name="lmr" + side + "Mat")
        cmds.setAttr(shader + ".color", *color, type="double3")
        group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=shader + "SG")
        cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
        shaders[side] = group
    for joints, side, sign in ((left, "L", 1.0), (right, "R", -1.0)):
        for joint, length in zip(joints, (4.0, 4.0, 1.5)):
            box = cmds.polyCube(name="{}_{}Box".format(joint.rsplit("|", 1)[-1], side), width=length,
                                height=0.6, depth=1.2 if joint == joints[-1] else 0.6)[0]
            box = cmds.parent(box, joint, relative=True)[0]
            cmds.setAttr(box + ".translateX", sign * length / 2.0)
            cmds.sets(box, edit=True, forceElement=shaders[side])
    rest_local = om2.MMatrix(cmds.getAttr(right[2] + ".matrix"))
    camera = cmds.camera(name="lmrView", focalLength=35)[0]
    cmds.xform(camera, translation=(0, 14, 48))
    window = cmds.window("lmrValidationWindow", title="LiveMirror - mirror left arm pose to the right",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("lmrValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=True,
                     selectionHiliteDisplay=False, cameras=False, joints=True, headsUpDisplay=True,
                     manipulators=False, locators=True, nurbsCurves=True, wireframeOnShaded=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("lmr", 7)
    scene = {"root": root, "left": left, "right": right, "owners": owners, "rest_local": rest_local}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """左の腕・ルート・右の上乗せ・weight を動かし、右のjointを反射の式で独立に求めた値と比べる。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    (srz, sry, ery, hrx, rtx, rry, layer, weight), stage_name = pose(frame)
    root, left, right = scene["root"], scene["left"], scene["right"]
    cmds.setAttr(left[0] + ".rotate", 0, sry, srz)
    cmds.setAttr(left[1] + ".rotateY", ery)
    cmds.setAttr(left[2] + ".rotateX", hrx)
    cmds.setAttr(root + ".translateX", rtx)
    cmds.setAttr(root + ".rotateY", rry)
    cmds.setAttr(right[2] + ".rotateZ", layer)
    for owner in scene["owners"]:
        cmds.setAttr(owner + ".weight", weight)

    def world(node):
        return om2.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))

    # 試験側の式: 対称面(ルートのYZ面)の原点 o・法線 n で点を p - 2((p-o)・n)n、軸を反射して3軸とも反転。
    plane = world(root)
    normal = om2.MVector(plane[0], plane[1], plane[2]).normal()
    origin = om2.MPoint(plane[12], plane[13], plane[14])
    errors = []
    for index, (source, target) in enumerate(zip(left, right)):
        matrix = world(source)
        expected = om2.MMatrix()
        for row in range(3):
            axis = om2.MVector(matrix[4 * row], matrix[4 * row + 1], matrix[4 * row + 2])
            axis = -(axis - normal * (2.0 * (axis * normal)))
            for column in range(3):
                expected.setElement(row, column, axis[column])
        point = om2.MPoint(matrix[12], matrix[13], matrix[14])
        point = point - normal * (2.0 * ((point - origin) * normal))
        for column in range(3):
            expected.setElement(3, column, point[column])
        if index == 2:
            delta = om2.MMatrix(cmds.getAttr(target + ".matrix")) * scene["rest_local"].inverse()
            expected = delta * expected
        actual = world(target)
        errors.append(max(abs(actual[i] - expected[i]) for i in range(16)))
    full = weight > 1.0 - 1e-9
    error = max(errors) if full else 0.0
    hand = world(right[2])
    values[:] = [
        "RED = left arm (animated)   GREEN = right arm (LiveMirror output)   vertical line = mirror plane (root YZ)",
        "STAGE: " + stage_name,
        "M = F * Wleft * P^-1 * S * P     F = diag(-1,-1,-1) (behavior)   S = diag(-1,1,1)   P = root world",
        "right OPM = L0^-1 * M * parentWorld^-1  ->  right world = (L * L0^-1) * M     blend by weight",
        "INPUT shoulder rz {:6.1f} ry {:6.1f}  elbow ry {:5.1f}  wrist rx {:5.1f}  root tx {:4.1f} ry {:5.1f}".format(
            srz, sry, ery, hrx, rtx, rry),
        "INPUT right wrist own rz {:5.1f}  weight {:4.2f}   OUTPUT right wrist ({:6.2f}, {:6.2f}, {:6.2f})".format(
            layer, weight, hand[12], hand[13], hand[14]),
        "CHECK |right - reflection formula| shoulder {:.1e}  elbow {:.1e}  wrist {:.1e}  {}".format(
            errors[0], errors[1], errors[2], "SKIP (weight < 1)" if not full else ("OK" if error < 1e-5 else "NG")),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-5
    return {"frame": frame, "presentation_stage": stage_name,
            "input": {"shoulder": [srz, sry], "elbow": ery, "wrist": hrx, "root": [rtx, rry], "layer": layer,
                      "weight": weight},
            "errors": errors, "checked": full, "ok": ok}


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
        folder = recordVideo("LiveMirror: 左の腕の姿勢を対称面で右へ写す", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "live_mirror.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-live-mirror.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("live-mirror-%Y%m%d-%H%M%S")
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
