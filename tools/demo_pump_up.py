"""PumpUpの補助骨の増幅を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_pump_up.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 36
GAIN = 1.5
SCALE_OFFSET = (0.0, 0.4, 0.4)
# (肘のrotateZ[度], pump, 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, 0.0, "1 REST"),
    (0.0, 0.0, "2 BEND THE ELBOW TO 130 deg (pump 0)"),
    (130.0, 0.0, "3 PUMP 0 -> 1"),
    (130.0, 1.0, "4 PUMP 1 -> 1.5"),
    (130.0, 1.5, "5 STRAIGHTEN THE ELBOW (pump 1.5: offset only)"),
    (0.0, 1.5, "6 RETURN TO REST"),
    (0.0, 0.0, "6 RETURN TO REST"),
    (0.0, 0.0, "6 RETURN TO REST"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:2], POSES[index + 1][:2])]
    return values, POSES[index][2]


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


def _sphere(name, parent, group, radius=0.7):
    """parentの子に、骨の向き(X)へ長い球を作る(筋肉の膨らみの目印)。"""
    from maya import cmds
    body = cmds.polySphere(name=name, radius=radius)[0]
    cmds.parent(body, parent, relative=True)
    cmds.setAttr(body + ".scale", 2.2, 1.0, 1.0)
    cmds.sets(body, edit=True, forceElement=group)
    return body


def _local(node):
    """ノードの親の空間での行列(matrix · offsetParentMatrix)。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    return om.MMatrix(cmds.getAttr(node + ".matrix")) * om.MMatrix(cmds.getAttr(node + ".offsetParentMatrix"))


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    from mlrig.setups import MuscleBulge, PumpUp
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("armRed", (0.9, 0.15, 0.1)), "green": _shader("pumpGreen", (0.15, 0.75, 0.25)),
              "ghost": _shader("helperGhost", (0.75, 0.75, 0.8), 0.55)}
    shoulder = cmds.createNode("transform", name="shoulder")
    cmds.setAttr(shoulder + ".translateY", 6)
    cmds.select(clear=True)
    upper = cmds.joint(name="upperArm")
    cmds.parent(upper, shoulder, relative=True)
    elbow = cmds.joint(name="elbow")
    cmds.setAttr(elbow + ".translateX", 5)
    upper, elbow = cmds.ls(upper, long=True)[0], cmds.ls(elbow, long=True)[0]
    for name, parent, length in (("upper_GEO", upper, 5.0), ("fore_GEO", elbow, 4.5)):
        bone = cmds.polyCylinder(name=name, radius=0.35, height=length, axis=(1, 0, 0))[0]
        cmds.parent(bone, parent, relative=True)
        cmds.setAttr(bone + ".translateX", length / 2.0)
        cmds.sets(bone, edit=True, forceElement=groups["red"])
    bulge = MuscleBulge.create(upper, elbow, name="bulge", axis="x", pushAxis="y", startAngle=60.0,
                               fullAngle=140.0, bulge=0.6, push=0.6)
    helper = cmds.createNode("joint", name="bulgeHelper", parent=upper)
    cmds.connectAttr(str(bulge.container) + ".matrix", helper + ".offsetParentMatrix")
    helper = cmds.ls(helper, long=True)[0]
    _sphere("helper_GEO", helper, groups["ghost"], radius=0.75)
    graph = PumpUp.create([helper], name="pumpUp", gains=(GAIN,), scaleOffsets=(SCALE_OFFSET,))
    pumped = cmds.createNode("joint", name="pumped", parent=upper)
    cmds.connectAttr(str(graph.container) + ".matrix0", pumped + ".offsetParentMatrix")
    pumped = cmds.ls(pumped, long=True)[0]
    _sphere("pumped_GEO", pumped, groups["green"])
    rest = om.MTransformationMatrix(_local(helper))
    camera, camera_shape = cmds.camera(name="pumpUpCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(4.5, 6.3, 22), lookAt=(4.5, 6.3, 0))
    window = cmds.window("pumpUpValidationWindow", title="PumpUp - helper amplify", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("pumpUpValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("pumpUp", 7)
    scene = {"owner": str(graph.container), "elbow": elbow, "helper": helper, "pumped": pumped, "rest": rest,
             "upper": upper}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、増幅した骨のワールド行列をMTransformationMatrixで独立に組んだ値と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    (bend, pump), stage = pose(frame)
    owner = scene["owner"]
    cmds.setAttr(scene["elbow"] + ".rotateZ", bend)
    cmds.setAttr(owner + ".pump", pump)
    current = om.MTransformationMatrix(_local(scene["helper"]))
    rest = scene["rest"]
    translate = current.translation(om.MSpace.kTransform)
    restTranslate = rest.translation(om.MSpace.kTransform)
    scale = current.scale(om.MSpace.kTransform)
    restScale = rest.scale(om.MSpace.kTransform)
    newTranslate = [translate[i] + (translate[i] - restTranslate[i]) * GAIN * pump for i in range(3)]
    newScale = [scale[i] + (scale[i] - restScale[i]) * GAIN * pump + SCALE_OFFSET[i] * pump for i in range(3)]
    expected = om.MTransformationMatrix()
    expected.setScale(newScale, om.MSpace.kTransform)
    expected.setRotation(current.rotation(asQuaternion=True))
    expected.setTranslation(om.MVector(*newTranslate), om.MSpace.kTransform)
    world = expected.asMatrix() * om.MMatrix(cmds.getAttr(scene["upper"] + ".worldMatrix[0]"))
    actual = om.MMatrix(cmds.getAttr(scene["pumped"] + ".worldMatrix[0]"))
    error = max(abs(a - b) for a, b in zip(actual, world))
    values[:] = [
        "RED = arm (input)   GRAY = existing bulge helper (MuscleBulge)   GREEN = amplified by PumpUp (output)",
        "STAGE: " + stage,
        "fixed: gain = {:.1f}   scaleOffset = (0, 0.4, 0.4)   bulge starts at 60 deg, full at 140 deg".format(GAIN),
        "scale = S + (S - S_rest) * gain * pump + scaleOffset * pump   translate = T + (T - T_rest) * gain * pump",
        "INPUT elbow rotZ = {:7.2f} deg   pump = {:5.2f}".format(bend, pump),
        "OUTPUT helper scaleY = {:5.3f}  liftY = {:5.3f} cm   amplified scaleY = {:5.3f}  liftY = {:5.3f} cm".format(
            scale[1], translate[1], cmds.getAttr(owner + ".scale0Y"), cmds.getAttr(owner + ".translate0Y")),
        "CHECK max |world matrix - formula| = {:.2e}".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4
    return {"frame": frame, "presentation_stage": stage, "input": {"elbow": bend, "pump": pump},
            "helper_scale": list(scale), "amplified_scale": newScale, "error": error, "ok": ok}


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
        folder = recordVideo("PumpUp: 補助骨の増幅", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "pump_up.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-pump-up.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("pump-up-%Y%m%d-%H%M%S")
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
