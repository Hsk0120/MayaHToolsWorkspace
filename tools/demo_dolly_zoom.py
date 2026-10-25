"""DollyZoomの焦点距離の連動を、メニューと同じサンプルのカメラから覗いて専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_dolly_zoom.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 48
NAME = "dolly"
# ((カメラのtranslateZ, weight), 次の状態へ向かう段階名)。
POSES = [
    ((30.0, 1.0), "1 REST (camera z 30, focal 35 mm)"),
    ((30.0, 1.0), "2 DOLLY IN (camera z 30 -> 9)"),
    ((9.0, 1.0), "3 DOLLY OUT (camera z 9 -> 75)"),
    ((75.0, 1.0), "4 WEIGHT 1 -> 0 (back to the rest focal length)"),
    ((75.0, 0.0), "5 RETURN (weight 1, camera z 30)"),
    ((30.0, 1.0), "5 RETURN (weight 1, camera z 30)"),
    ((30.0, 1.0), "5 RETURN (weight 1, camera z 30)"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    smooth = weight * weight * (3 - 2 * weight)
    start, end = POSES[index][0], POSES[index + 1][0]
    return [a + (b - a) * smooth for a, b in zip(start, end)], POSES[index][1]


def _shader(name, color):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
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


def _screen(camera, shape, point):
    """点が画面の横・縦のどこに写るか(横は -1〜1 が画面の左右の端)を、カメラの軸から独立に求める。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    matrix = om2.MMatrix(cmds.getAttr(camera + ".worldMatrix[0]"))
    axes = [om2.MVector(matrix[4 * row], matrix[4 * row + 1], matrix[4 * row + 2]).normal() for row in range(3)]
    offset = om2.MVector(point) - om2.MVector(matrix[12], matrix[13], matrix[14])
    depth = -(offset * axes[2])
    half = cmds.getAttr(shape + ".horizontalFilmAperture") * 25.4 / 2.0
    focal = cmds.getAttr(shape + ".focalLength")
    return (offset * axes[0]) / depth * focal / half, depth


def buildScene():
    """メニューと同じサンプルで検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setupSamples import SetupSamples
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    sample = SetupSamples.build("dollyZoom", name=NAME)
    owner = sample.container
    camera = sample.target
    shape = cmds.listRelatives(camera, shapes=True, fullPath=True)[0]
    # 画面の端(フィルムゲート)が見えるよう、表示だけ外側を広げる(画角・焦点距離には影響しない)。
    cmds.setAttr(shape + ".overscan", 1.25)
    cmds.setAttr(shape + ".displayFilmGate", True)
    head = cmds.polySphere(name="subject_GEO", radius=2.2)[0]
    cmds.xform(head, worldSpace=True, translation=(0, 10, 0))
    cmds.sets(head, edit=True, forceElement=_shader("subjectRed", (0.9, 0.25, 0.2)))
    posts = _shader("postBlue", (0.25, 0.45, 0.9))
    for index in range(6):
        locator = "{}_post{}".format(NAME, index)
        position = cmds.xform(locator, query=True, worldSpace=True, translation=True)
        post = cmds.polyCube(name="post{}_GEO".format(index), width=1.6, height=16, depth=1.6)[0]
        cmds.xform(post, worldSpace=True, translation=position)
        cmds.sets(post, edit=True, forceElement=posts)
    floor = cmds.polyPlane(name="floor_GEO", width=40, height=160, subdivisionsX=10, subdivisionsY=40)[0]
    cmds.xform(floor, worldSpace=True, translation=(0, 2, -40))
    cmds.sets(floor, edit=True, forceElement=_shader("floorGray", (0.55, 0.55, 0.55)))
    window = cmds.window("dollyValidationWindow", title="DollyZoom - camera keeps the subject size",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("dollyValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=True, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=True, wireframeOnShaded=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("dolly", 7)
    scene = {"owner": owner, "camera": camera, "shape": shape,
             "width": cmds.getAttr(owner + ".frameWidth"), "rest": cmds.getAttr(owner + ".restFocalLength")}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """カメラの距離と weight を動かし、焦点距離・画面の端に写る幅を独立に求めた値と比べる。"""
    from maya import cmds
    (distance, weight), stage_name = pose(frame)
    owner, camera, shape = scene["owner"], scene["camera"], scene["shape"]
    cmds.setAttr(camera + ".translateZ", distance)
    cmds.setAttr(owner + ".weight", weight)
    aperture = cmds.getAttr(shape + ".horizontalFilmAperture")
    width, rest = scene["width"], scene["rest"]
    edge, depth = _screen(camera, shape, (width / 2.0, 10, 0))
    zoom = depth * aperture * 25.4 / width
    expected = rest + weight * (zoom - rest)
    focal = cmds.getAttr(shape + ".focalLength")
    fov = cmds.getAttr(owner + ".fieldOfView")
    maya_fov = cmds.camera(camera, query=True, horizontalFieldOfView=True)
    focal_error = abs(focal - expected) / expected
    fov_error = abs(fov - maya_fov)
    # weight=1 なら被写体の面の幅の端は画面の端(1)に写る。weight<1 では写る幅が変わる(確認は焦点距離の式)。
    edge_error = abs(edge - 1.0) if weight > 1.0 - 1e-9 else 0.0
    values[:] = [
        "RED = subject (its size stays)   BLUE = posts behind   GREEN = frameWidth at the subject   box = film gate",
        "STAGE: " + stage_name,
        "fixed: rest focal {:.1f} mm   film aperture {:.3f} in   frameWidth {:.2f} cm".format(rest, aperture, width),
        "f = rest + weight * (depth * aperture * 25.4 / frameWidth - rest)      fov = 2 atan(aperture*25.4 / 2f)",
        "INPUT camera z {:6.2f} cm   depth {:6.2f} cm   weight {:4.2f}".format(distance, depth, weight),
        "OUTPUT focal length {:7.2f} mm   horizontal fov {:6.2f} deg   green edge on screen x {:6.3f}".format(
            focal, fov, edge),
        "CHECK focal rel. error {:.1e}   |fov - Maya camera fov| {:.1e} deg   |edge - 1| {:.1e}".format(
            focal_error, fov_error, edge_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = focal_error < 1e-6 and fov_error < 1e-3 and edge_error < 1e-5
    return {"frame": frame, "presentation_stage": stage_name,
            "input": {"cameraZ": distance, "weight": weight}, "depth": depth, "focalLength": focal,
            "fieldOfView": fov, "edge": edge, "focal_error": focal_error, "fov_error": fov_error,
            "edge_error": edge_error, "ok": ok}


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
        folder = recordVideo("DollyZoom: カメラの距離と焦点距離の連動", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "dolly_zoom.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-dolly-zoom.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("dolly-zoom-%Y%m%d-%H%M%S")
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
