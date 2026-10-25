"""OverShoulderCameraの肩越しのカメラを、メニューと同じサンプルのカメラから覗いて専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_over_shoulder_camera.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 48
NAME = "ots"
# ((focusのX, focusのZ, partnerのX, partnerのZ, side, weight), 次の状態へ向かう段階名)。
POSES = [
    ((0.0, 0.0, 0.0, 12.0, 1.0, 1.0), "1 REST (side +1, head at screen (1/3, 1/3))"),
    ((0.0, 0.0, 0.0, 12.0, 1.0, 1.0), "2 RED WALKS (x 0 -> 8, z 0 -> -5)"),
    ((8.0, -5.0, 0.0, 12.0, 1.0, 1.0), "3 BLUE WALKS (x 0 -> -7, z 12 -> 5)"),
    ((8.0, -5.0, -7.0, 5.0, 1.0, 1.0), "4 SIDE +1 -> -1 (the other side of the line)"),
    ((8.0, -5.0, -7.0, 5.0, -1.0, 1.0), "5 WEIGHT 1 -> 0 (back to the camera at creation)"),
    ((8.0, -5.0, -7.0, 5.0, -1.0, 0.0), "6 RETURN"),
    ((0.0, 0.0, 0.0, 12.0, 1.0, 1.0), "6 RETURN"),
    ((0.0, 0.0, 0.0, 12.0, 1.0, 1.0), "6 RETURN"),
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
    """点がフィルムゲートのどこに写るか(左右・上下の端が ±1)を、カメラの軸から独立に求める。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    matrix = om2.MMatrix(cmds.getAttr(camera + ".worldMatrix[0]"))
    axes = [om2.MVector(matrix[4 * row], matrix[4 * row + 1], matrix[4 * row + 2]).normal() for row in range(3)]
    offset = om2.MVector(point) - om2.MVector(matrix[12], matrix[13], matrix[14])
    depth = -(offset * axes[2])
    focal = cmds.getAttr(shape + ".focalLength")
    width = cmds.getAttr(shape + ".horizontalFilmAperture") * 25.4 / 2.0
    height = cmds.getAttr(shape + ".verticalFilmAperture") * 25.4 / 2.0
    return (offset * axes[0]) / depth * focal / width, (offset * axes[1]) / depth * focal / height


def _person(head, color, name):
    """頭のjointの下に、頭の球・鼻・体の円柱を作る(表示用)。"""
    from maya import cmds
    group = _shader(name + "Mat", color)
    sphere = cmds.polySphere(name=name + "Head_GEO", radius=1.5)[0]
    nose = cmds.polyCone(name=name + "Nose_GEO", radius=0.4, height=1.0, axis=(0, 0, 1))[0]
    cmds.xform(nose, translation=(0, 0, 1.7))
    torso = cmds.polyCylinder(name=name + "Body_GEO", radius=1.8, height=10)[0]
    cmds.xform(torso, translation=(0, -7, 0))
    for item in (sphere, nose, torso):
        item = cmds.parent(item, head, relative=True)[0]
        cmds.sets(item, edit=True, forceElement=group)


def buildScene():
    """メニューと同じサンプルで検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setupSamples import SetupSamples
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    sample = SetupSamples.build("overShoulderCamera", name=NAME)
    owner = sample.container
    focus = sample.target
    partner = cmds.ls(NAME + "_partnerHead", long=True)[0]
    camera = cmds.ls(NAME + "_camera", long=True)[0]
    shape = cmds.listRelatives(camera, shapes=True, fullPath=True)[0]
    # 画面の端(フィルムゲート)が見えるよう、表示だけ外側を広げる。解像度ゲートもフィルムと同じ縦横比にする。
    cmds.setAttr(shape + ".overscan", 1.3)
    cmds.setAttr(shape + ".displayFilmGate", True)
    cmds.setAttr("defaultResolution.width", 1416)
    cmds.setAttr("defaultResolution.height", 944)
    cmds.setAttr("defaultResolution.deviceAspectRatio", 1.5)
    for body in ("focusBody", "partnerBody"):
        cmds.setAttr("{}_{}.visibility".format(NAME, body), False)
    _person(focus, (0.9, 0.25, 0.2), "focus")
    _person(partner, (0.25, 0.45, 0.9), "partner")
    floor = cmds.polyPlane(name="floor_GEO", width=120, height=120, subdivisionsX=24, subdivisionsY=24)[0]
    cmds.xform(floor, worldSpace=True, translation=(0, 2, 0))
    cmds.sets(floor, edit=True, forceElement=_shader("floorGray", (0.55, 0.55, 0.55)))
    window = cmds.window("otsValidationWindow", title="OverShoulderCamera - conversation shot",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("otsValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=True, wireframeOnShaded=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("ots", 7)
    scene = {"owner": owner, "camera": camera, "shape": shape, "focus": focus, "partner": partner}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """2人の位置・side・weight を動かし、カメラの行列・頭の画面の位置・線の側を独立に求めた値と比べる。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    from mlrig.setups import OverShoulderCamera
    (fx, fz, px, pz, side, weight), stage_name = pose(frame)
    owner, camera, shape = scene["owner"], scene["camera"], scene["shape"]
    cmds.setAttr(scene["focus"] + ".translate", fx, 15, fz)
    cmds.setAttr(scene["partner"] + ".translate", px, 15, pz)
    cmds.setAttr(owner + ".side", side)
    cmds.setAttr(owner + ".weight", weight)

    def get(attr):
        return cmds.getAttr(owner + "." + attr)

    a = cmds.xform(scene["focus"], query=True, worldSpace=True, translation=True)
    b = cmds.xform(scene["partner"], query=True, worldSpace=True, translation=True)
    expected = OverShoulderCamera.placement(
        a, b, get("distance"), get("angle"), get("height"), side, get("screenX"), get("screenY"),
        cmds.getAttr(shape + ".focalLength"), cmds.getAttr(shape + ".horizontalFilmAperture"),
        cmds.getAttr(shape + ".verticalFilmAperture"))
    actual = om2.MMatrix(cmds.getAttr(camera + ".worldMatrix[0]"))
    full = weight > 1.0 - 1e-9
    matrix_error = max(abs(actual[i] - expected[i]) for i in range(16)) if full else 0.0
    sx, sy = _screen(camera, shape, a)
    screen_error = max(abs(sx - get("screenX")), abs(sy - get("screenY"))) if full else 0.0
    c = (actual[12], actual[13], actual[14])
    # (u × (c - a)).y の符号。side が ±1 付近で weight=1 なら side と同じ符号(線の同じ側)。
    cross = (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2])
    side_ok = abs(side) < 0.99 or not full or cross * side > 0.0
    values[:] = [
        "RED = focus (head kept at the thirds)   BLUE = partner (shoulder in front)   box = film gate",
        "STAGE: " + stage_name,
        "fixed: distance {:.1f} cm  angle {:.0f} deg  height {:.1f} cm  target ({:.3f}, {:.3f})  focal {:.0f} mm".format(
            get("distance"), get("angle"), get("height"), get("screenX"), get("screenY"),
            cmds.getAttr(shape + ".focalLength")),
        "c0 = a + distance * Ry(side * angle) u + (0, height, 0)     c = c0 - screenX*halfW*X - screenY*halfH*Y",
        "INPUT red ({:5.1f}, {:5.1f})  blue ({:5.1f}, {:5.1f})  side {:5.2f}  weight {:4.2f}".format(
            fx, fz, px, pz, side, weight),
        "OUTPUT red head on screen ({:6.3f}, {:6.3f})   camera side of the line {:+.2f}".format(sx, sy, cross),
        "CHECK |camera - formula| {:.1e} cm   |screen - target| {:.1e}   side {}".format(
            matrix_error, screen_error, "OK" if side_ok else "NG"),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = matrix_error < 1e-4 and screen_error < 1e-5 and side_ok
    return {"frame": frame, "presentation_stage": stage_name,
            "input": {"focus": [fx, fz], "partner": [px, pz], "side": side, "weight": weight},
            "screen": [sx, sy], "cross": cross, "matrix_error": matrix_error, "screen_error": screen_error,
            "side_ok": side_ok, "ok": ok}


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
        folder = recordVideo("OverShoulderCamera: 2人の頭から決まる肩越しのカメラ", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "over_shoulder_camera.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-over-shoulder-camera.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("over-shoulder-camera-%Y%m%d-%H%M%S")
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
