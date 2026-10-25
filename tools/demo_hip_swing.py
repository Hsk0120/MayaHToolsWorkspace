"""HipSwingの腰の振りと上体の安定化を、メニューと同じサンプルで専用Maya GUIに録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_hip_swing.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
NAME = "hsd"
# ((コントロールの rotateX, rotateY, rotateZ, swing, stabilize), 次の状態へ向かう段階名)。
POSES = [
    ((0.0, 0.0, 0.0, 1.0, 1.0), "1 REST"),
    ((0.0, 0.0, 0.0, 1.0, 1.0), "2 SWING sideways (hips tilt, chest stays upright)"),
    ((0.0, 0.0, 28.0, 1.0, 1.0), "3 SWING forward"),
    ((24.0, 0.0, -10.0, 1.0, 1.0), "4 TWIST the hips"),
    ((24.0, 35.0, -10.0, 1.0, 1.0), "5 STABILIZE 1 -> 0 (chest follows like a plain child)"),
    ((24.0, 35.0, -10.0, 1.0, 0.0), "6 STABILIZE back to 1, SWING 1 -> 0.5"),
    ((24.0, 35.0, -10.0, 0.5, 1.0), "7 RETURN"),
    ((0.0, 0.0, 0.0, 1.0, 1.0), "7 RETURN"),
    ((0.0, 0.0, 0.0, 1.0, 1.0), "7 RETURN"),
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
    sample = SetupSamples.build("hipSwing", name=NAME)

    def node(suffix):
        return cmds.ls(NAME + suffix, long=True)[0]

    scene = {"owner": str(sample.container), "control": node("_swingCtrl"), "cog": node("_cog"),
             "hips": node("_hips"), "spine": node("_spine"), "chest": node("_chest"),
             "hipsOut": node("_hipsOut"), "spineOut": node("_spineOut"), "chestOut": node("_chestOut")}
    # 録画で見分けられるよう、出力の骨盤(黄の箱)・出力の胴(緑の箱)・普通の親子なら回る胴(赤の枠)を置く。
    shaders = {}
    for key, color in (("hips", (1.0, 0.8, 0.1)), ("torso", (0.2, 0.8, 0.3))):
        shader = cmds.shadingNode("lambert", asShader=True, name="hsd" + key + "Mat")
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

    attach(cmds.polyCube(name="hsdPelvis", width=3.2, height=1.6, depth=1.6)[0], scene["hipsOut"], (0, -0.4, 0),
           "hips")
    for side, x in (("L", 1.2), ("R", -1.2)):
        attach(cmds.polyCylinder(name="hsdThigh" + side, radius=0.45, height=4.0)[0], scene["hipsOut"],
               (x, -2.8, 0), "hips")
    attach(cmds.polyCube(name="hsdTorso", width=3.0, height=3.6, depth=1.6)[0], scene["spineOut"], (0, 1.8, 0),
           "torso")
    attach(cmds.polySphere(name="hsdHead", radius=1.0)[0], scene["chestOut"], (0, 3.0, 0), "torso")
    # 普通の親子(stabilize=0)なら胴がどう回るかを、背骨の根元の入力 B に swingMatrix を掛けた赤の枠で示す。
    plain = cmds.createNode("transform", name="hsdPlainTorso")
    product = cmds.createNode("multMatrix", name="hsdPlainProduct")
    cmds.connectAttr(scene["spine"] + ".worldMatrix[0]", product + ".matrixIn[0]")
    cmds.connectAttr(scene["owner"] + ".swingMatrix", product + ".matrixIn[1]")
    cmds.connectAttr(product + ".matrixSum", plain + ".offsetParentMatrix")
    ghost = attach(cmds.polyCube(name="hsdPlainBox", width=3.0, height=3.6, depth=1.6)[0], plain, (0, 1.8, 0), None)
    cmds.setAttr(ghost + ".overrideEnabled", True)
    cmds.setAttr(ghost + ".overrideShading", False)
    cmds.setAttr(ghost + ".overrideColor", 13)
    view = cmds.camera(name="hsdView", focalLength=35)[0]
    cmds.xform(view, translation=(16, 15, 26))
    cmds.viewLookAt(view, position=(-1.5, 10.5, 0.0))
    window = cmds.window("hsdValidationWindow", title="HipSwing - swing the hips, keep the chest",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("hsdValidationPanel", parent=pane, camera=view, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=True,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=True, nurbsCurves=False, wireframeOnShaded=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("hsd", 7)
    return panel, scene, values, names


def _angle(a, b):
    """2つの行列の回転の差の角度(度)。"""
    from maya.api import OpenMaya as om2
    first = om2.MTransformationMatrix(a).rotation(asQuaternion=True)
    second = om2.MTransformationMatrix(b).rotation(asQuaternion=True)
    q = first.conjugate() * second
    return math.degrees(2.0 * math.acos(min(1.0, abs(q.w))))


def evaluate_frame(frame, scene, values, names):
    """コントロールを回し、腰は支点の周りに振れ、上体は stabilize の割合で向きを保つことを確かめる。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    (rx, ry, rz, swing, stabilize), stage_name = pose(frame)
    control, owner = scene["control"], scene["owner"]
    cmds.setAttr(control + ".rotate", rx, ry, rz)
    cmds.setAttr(owner + ".swing", swing)
    cmds.setAttr(owner + ".stabilize", stabilize)
    # 試験側の式: 支点の枠 Q = T(translate) · offsetParentMatrix · COG のワールド行列、S = Q^-1 · slerp(I, R, swing) · Q。
    move = om2.MTransformationMatrix()
    move.setTranslation(om2.MVector(*cmds.getAttr(control + ".translate")[0]), om2.MSpace.kTransform)
    frame_matrix = (move.asMatrix() * om2.MMatrix(cmds.getAttr(control + ".offsetParentMatrix"))
                    * om2.MMatrix(cmds.getAttr(scene["cog"] + ".worldMatrix[0]")))
    full = om2.MEulerRotation(math.radians(rx), math.radians(ry), math.radians(rz)).asQuaternion()
    spin = om2.MQuaternion.slerp(om2.MQuaternion(), full, swing).asMatrix()
    delta = frame_matrix.inverse() * spin * frame_matrix
    hips = om2.MMatrix(cmds.getAttr(scene["hips"] + ".worldMatrix[0]"))
    spine = om2.MMatrix(cmds.getAttr(scene["spine"] + ".worldMatrix[0]"))
    chest = om2.MMatrix(cmds.getAttr(scene["chest"] + ".worldMatrix[0]"))
    hipsOut = om2.MMatrix(cmds.getAttr(scene["hipsOut"] + ".worldMatrix[0]"))
    spineOut = om2.MMatrix(cmds.getAttr(scene["spineOut"] + ".worldMatrix[0]"))
    chestOut = om2.MMatrix(cmds.getAttr(scene["chestOut"] + ".worldMatrix[0]"))
    expected = hips * delta
    rotated = spine * delta
    swingAngle = _angle(om2.MMatrix(), delta)
    chestTilt = _angle(chest, chestOut)
    errors = [max(abs(hipsOut[i] - expected[i]) for i in range(16)),
              max(abs(spineOut[i] - rotated[i]) for i in (12, 13, 14)),
              abs(_angle(spine, spineOut) - (1.0 - stabilize) * swingAngle) * math.pi / 180.0,
              abs(chestTilt - (1.0 - stabilize) * swingAngle) * math.pi / 180.0]
    error = max(errors)
    values[:] = [
        "YELLOW = hips output   GREEN = upper body output   RED frame = upper body as a plain child   cross = swing pivot",
        "STAGE: " + stage_name,
        "pivot frame Q = T(translate) . offsetParentMatrix . parent      S = Q^-1 . slerp(I, R, swing) . Q",
        "hips out = H . S      spine out = position of B . S, rotation slerp(B . S -> B, stabilize)",
        "INPUT control rotate ({:6.1f}, {:6.1f}, {:6.1f}) deg   swing {:4.2f}   stabilize {:4.2f}".format(
            rx, ry, rz, swing, stabilize),
        "OUTPUT hips swing {:6.2f} deg   chest tilt {:6.2f} deg  (= (1 - stabilize) x swing {:6.2f})".format(
            swingAngle, chestTilt, (1.0 - stabilize) * swingAngle),
        "CHECK |output - formula| {:.1e}  {}".format(error, "OK" if error < 1e-5 else "NG"),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    return {"frame": frame, "presentation_stage": stage_name,
            "input": {"rotate": [rx, ry, rz], "swing": swing, "stabilize": stabilize},
            "swingAngle": swingAngle, "chestTilt": chestTilt, "error": error, "ok": error < 1e-5}


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
        folder = recordVideo("HipSwing: 腰だけを支点の周りに振り、上体の向きを保つ", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "hip_swing.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-hip-swing.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("hip-swing-%Y%m%d-%H%M%S")
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
