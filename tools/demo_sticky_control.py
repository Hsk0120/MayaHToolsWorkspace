"""StickyControlの、スキンした表面に貼り付いて動くコントロールを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_sticky_control.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 36
# 表面に貼り付けるコントロールを置く頂点(6x8分割の平面、下から数えた行×7+列)。
VERTICES = (9, 17, 26, 38)
# (下のjointの回転X・回転Z(度), 2つ目のコントロールのローカルの移動X(cm), 次の姿勢へ向かう段階名)。
POSES = [
    (0, 0, 0.0, "1 REST -> BEND FORWARD"),
    (60, 0, 0.0, "2 BEND -> BEND AND TWIST"),
    (60, 35, 0.0, "3 MOVE ONE CONTROL ON THE SURFACE (LOCAL tx)"),
    (60, 35, 1.2, "4 BEND BACKWARD"),
    (-45, -20, 1.2, "5 CONTROL BACK -> REST"),
    (-45, -20, 0.0, "6 -> REST"),
    (0, 0, 0.0, "6 -> REST"),
    (0, 0, 0.0, "6 -> REST"),
]
FRAMES = SEGMENT * (len(POSES) - 1) + 24


def pose(frame):
    """フレームの姿勢をsmoothstepで補間して返す。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [POSES[index][i] + (POSES[index + 1][i] - POSES[index][i]) * weight for i in range(3)]
    return values[0], values[1], values[2], POSES[index][3]


def _shader(name, color):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def _marker(name, radius, shading):
    """小さな円盤(コントロールの目印)を作る。"""
    from maya import cmds
    node = cmds.createNode("transform", name=name)
    disc = cmds.polyCylinder(name=name + "_GEO", radius=radius, height=0.12, axis=(0, 0, 1))[0]
    cmds.parent(disc, node, relative=True)
    cmds.setAttr(disc + ".translateZ", 0.08)
    cmds.sets(disc, edit=True, forceElement=shading)
    return node


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import StickyControl
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    surface = cmds.polyPlane(name="skin_GEO", width=6, height=8, subdivisionsX=6, subdivisionsY=8,
                             axis=(0, 0, 1))[0]
    cmds.sets(surface, edit=True, forceElement=_shader("skinColor", (0.8, 0.68, 0.6)))
    top = cmds.createNode("joint", name="top_JNT")
    cmds.setAttr(top + ".translateY", 4)
    bottom = cmds.createNode("joint", name="bottom_JNT", parent=top)
    cmds.setAttr(bottom + ".translateY", -4)
    tip = cmds.createNode("joint", name="tip_JNT", parent=bottom)
    cmds.setAttr(tip + ".translateY", -4)
    cmds.skinCluster(top, bottom, surface, toSelectedBones=True, maximumInfluences=2)
    green = _shader("stickyGreen", (0.15, 0.8, 0.25))
    red = _shader("fixedRed", (0.9, 0.15, 0.1))
    controls = []
    for index, vertex in enumerate(VERTICES):
        point = cmds.pointPosition("{}.vtx[{}]".format(surface, vertex), world=True)
        control = _marker("sticky{}_CTRL".format(index), 0.35, green)
        cmds.xform(control, worldSpace=True, translation=point)
        StickyControl.create(surface, control, name="sticky{}".format(index))
        controls.append(control)
    # 比較用: 同じ場所に置いた、表面に貼り付けない赤い目印(動かない)。
    fixed = _marker("fixed_CTRL", 0.2, red)
    cmds.xform(fixed, worldSpace=True, translation=cmds.pointPosition("{}.vtx[{}]".format(surface, VERTICES[0]),
                                                                       world=True))
    cmds.setAttr(fixed + ".translateZ", 0.2)
    rest = cmds.getAttr(controls[1] + ".matrix")
    camera, camera_shape = cmds.camera(name="stickyCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(25, 0.5, 25), lookAt=(0, -2.2, 0))
    window = cmds.window("stickyValidationWindow", title="StickyControl - control on a skinned surface",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("stickyValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, wireframeOnShaded=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 7
    names = ["stickyHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    scene = {"surface": surface, "bottom": bottom, "controls": controls, "rest": rest,
             "restTranslate": cmds.getAttr(controls[1] + ".translate")[0]}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """jointを回し、各コントロールの位置を変形後の頂点(と相対操作の式)と比較した診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    rx, rz, tx, stage = pose(frame)
    cmds.setAttr(scene["bottom"] + ".rotateX", rx)
    cmds.setAttr(scene["bottom"] + ".rotateZ", rz)
    restTranslate = scene["restTranslate"]
    cmds.setAttr(scene["controls"][1] + ".translateX", restTranslate[0] + tx)
    errors = []
    for index, (control, vertex) in enumerate(zip(scene["controls"], VERTICES)):
        point = om.MPoint(cmds.pointPosition("{}.vtx[{}]".format(scene["surface"], vertex), world=True))
        pinned = om.MMatrix(cmds.getAttr("sticky{}.matrix".format(index)))
        errors.append((om.MPoint(pinned[12], pinned[13], pinned[14]) - point).length())
        world = om.MMatrix(cmds.getAttr(control + ".worldMatrix[0]"))
        expected = om.MMatrix(cmds.getAttr(control + ".matrix")) * om.MMatrix(scene["rest"] if index == 1 else
                                                                            cmds.getAttr(control + ".matrix")
                                                                            ).inverse() * pinned
        errors.append(max(abs(a - b) for a, b in zip(world, expected)))
    surfaceError = max(errors[0::2])
    relativeError = max(errors[1::2])
    moved = om.MPoint(cmds.pointPosition("{}.vtx[{}]".format(scene["surface"], VERTICES[0]), world=True))
    values[:] = [
        "GREEN = sticky controls (follow the skinned surface)   RED = same place, not sticky   (bottom joint bends)",
        "STAGE: " + stage,
        "fixed: proximityPin offsetTranslation = offsetOrientation = 1   controls placed on vertices {}".format(
            ", ".join(str(v) for v in VERTICES)),
        "matrix = pin.outputMatrix * D^-1 * mesh.worldMatrix   control world = L * L0^-1 * matrix",
        "INPUT bottom joint rotateX = {:+6.1f} deg  rotateZ = {:+6.1f} deg   control1 local tx offset = {:+.2f} cm".format(
            rx, rz, tx),
        "OUTPUT sticky0 at ({:+.3f}, {:+.3f}, {:+.3f}) cm   (red stays at the rest position)".format(
            moved.x, moved.y, moved.z),
        "CHECK distance to deformed vertex = {:.7f} cm   relative control error = {:.7f}".format(
            surfaceError, relativeError),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = surfaceError < 1e-4 and relativeError < 1e-5
    return {"frame": frame, "presentation_stage": stage, "rotate": [rx, rz], "local_tx": tx,
            "surface_error": surfaceError, "relative_error": relativeError, "ok": ok}


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
        folder = recordVideo("StickyControl: 変形する表面に貼り付くコントロール", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "sticky_control.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-sticky-control.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("sticky-control-%Y%m%d-%H%M%S")
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
