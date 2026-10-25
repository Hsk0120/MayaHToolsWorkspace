"""EyeHighlightの目のハイライトのカメラ追従を、メニューと同じサンプルで専用Maya GUIに録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_eye_highlight.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
NAME = "ehl"
SIDES = ("left", "right")
# ((カメラ tx, ty, tz, 眼球 ry, 光 tx, ty, follow), 次の状態へ向かう段階名)。
POSES = [
    ((6.0, 15.0, 16.0, 0.0, -10.0, 24.0, 1.0), "1 REST (highlight between camera and light)"),
    ((6.0, 15.0, 16.0, 0.0, -10.0, 24.0, 1.0), "2 CAMERA moves to the left"),
    ((-12.0, 15.0, 14.0, 0.0, -10.0, 24.0, 1.0), "3 CAMERA moves up"),
    ((-12.0, 26.0, 12.0, 0.0, -10.0, 24.0, 1.0), "4 EYES turn (highlight stays toward camera/light)"),
    ((-12.0, 26.0, 12.0, 35.0, -10.0, 24.0, 1.0), "5 LIGHT moves to the right"),
    ((-12.0, 26.0, 12.0, 35.0, 14.0, 30.0, 1.0), "6 FOLLOW 1 -> 0 (highlight back to the pupil)"),
    ((-12.0, 26.0, 12.0, 35.0, 14.0, 30.0, 0.0), "7 RETURN"),
    ((6.0, 15.0, 16.0, 0.0, -10.0, 24.0, 1.0), "7 RETURN"),
    ((6.0, 15.0, 16.0, 0.0, -10.0, 24.0, 1.0), "7 RETURN"),
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
    sample = SetupSamples.build("eyeHighlight", name=NAME)
    eyes = [cmds.ls("{}_{}Eye".format(NAME, side), long=True)[0] for side in SIDES]
    highlights = [cmds.ls("{}_{}HighlightOut".format(NAME, side), long=True)[0] for side in SIDES]
    camera = cmds.ls(NAME + "_camera", long=True)[0]
    light = cmds.ls(NAME + "_light", long=True)[0]
    owners = [sample.container, NAME + "_rightHighlight"]
    # 録画で見分けられるよう、眼球(白)・瞳(紺の薄い球)・ハイライト(黄)・カメラと光の目印の球を子に置く。
    shaders = {}
    for key, color in (("eye", (0.9, 0.9, 0.88)), ("iris", (0.1, 0.15, 0.45)), ("spot", (1.0, 0.85, 0.1)),
                       ("camera", (0.2, 0.8, 0.3)), ("light", (1.0, 0.35, 0.0))):
        shader = cmds.shadingNode("lambert", asShader=True, name="ehl" + key + "Mat")
        cmds.setAttr(shader + ".color", *color, type="double3")
        if key in ("spot", "light"):
            cmds.setAttr(shader + ".incandescence", *[value * 0.5 for value in color], type="double3")
        group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=shader + "SG")
        cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
        shaders[key] = group

    def ball(name, parent, radius, scale, translate, key):
        node = cmds.polySphere(name=name, radius=radius, subdivisionsX=24, subdivisionsY=16)[0]
        node = cmds.parent(node, parent, relative=True)[0]
        cmds.setAttr(node + ".scale", *scale)
        cmds.setAttr(node + ".translate", *translate)
        cmds.sets(node, edit=True, forceElement=shaders[key])
        return node

    for eye, highlight in zip(eyes, highlights):
        ball(eye.rsplit("|", 1)[-1] + "Ball", eye, 1.0, (1, 1, 1), (0, 0, 0), "eye")
        ball(eye.rsplit("|", 1)[-1] + "Iris", eye, 0.45, (1, 1, 0.25), (0, 0, 0.93), "iris")
        ball(highlight.rsplit("|", 1)[-1] + "Spot", highlight, 0.22, (1, 1, 0.35), (0, 0, 0), "spot")
    ball("ehlCameraMark", camera, 0.8, (1, 1, 1), (0, 0, 0), "camera")
    ball("ehlLightMark", light, 0.5, (1, 1, 1), (0, 0, 0), "light")
    view = cmds.camera(name="ehlView", focalLength=55)[0]
    cmds.xform(view, translation=(12, 19, 14))
    cmds.viewLookAt(view, position=(0, 13.5, 1.5))
    window = cmds.window("ehlValidationWindow", title="EyeHighlight - catchlight follows the camera",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("ehlValidationPanel", parent=pane, camera=view, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=True,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=True, nurbsCurves=True, wireframeOnShaded=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("ehl", 7)
    scene = {"eyes": eyes, "highlights": highlights, "camera": camera, "light": light, "owners": owners}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """カメラ・眼球・光・follow を動かし、ハイライトを試験側の式(中間の向きの表面の点)と比べる。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    (cx, cy, cz, ry, lx, ly, follow), stage_name = pose(frame)
    cmds.setAttr(scene["camera"] + ".translate", cx, cy, cz)
    cmds.setAttr(scene["light"] + ".translateX", lx)
    cmds.setAttr(scene["light"] + ".translateY", ly)
    for eye in scene["eyes"]:
        cmds.setAttr(eye + ".rotateY", ry)
    for owner in scene["owners"]:
        cmds.setAttr(owner + ".follow", follow)

    def position(node):
        return om2.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))

    camera, light = position(scene["camera"]), position(scene["light"])
    errors, angles = [], []
    for eye, highlight, owner in zip(scene["eyes"], scene["highlights"], scene["owners"]):
        world = om2.MMatrix(cmds.getAttr(eye + ".worldMatrix[0]"))
        center = om2.MVector(world[12], world[13], world[14])
        view, lamp = (camera - center).normal(), (light - center).normal()
        half = (view + lamp).normal()
        forward = (om2.MVector(0, 0, 1) * world).normal()
        direction = (half * follow + forward * (1.0 - follow)).normal()
        expected = center + direction * cmds.getAttr(owner + ".radius")
        actual = om2.MMatrix(cmds.getAttr(highlight + ".worldMatrix[0]"))
        normal = om2.MVector(actual[8], actual[9], actual[10]).normal()
        errors.append(max([abs(actual[12 + i] - expected[i]) for i in range(3)] +
                          [abs(normal[i] - direction[i]) for i in range(3)]))
        angles.append((math.degrees(normal.angle(view)), math.degrees(normal.angle(lamp))))
    error = max(errors)
    spot = position(scene["highlights"][0])
    values[:] = [
        "WHITE = eyeballs   YELLOW = highlight (EyeHighlight output)   GREEN = camera   ORANGE = light",
        "STAGE: " + stage_name,
        "v = normalize(camera - E)   l = normalize(light - E)   h = normalize(v + l)   F = eye +Z (pupil)",
        "m = follow * h + (1 - follow) * F     highlight = E + radius * normalize(m)   (+Z = surface normal)",
        "INPUT camera ({:5.1f}, {:5.1f}, {:5.1f})  light x {:5.1f} y {:5.1f}  eye ry {:5.1f}  follow {:4.2f}".format(
            cx, cy, cz, lx, ly, ry, follow),
        "OUTPUT left highlight ({:6.2f}, {:6.2f}, {:6.2f})   angle to camera {:5.1f} deg / to light {:5.1f} deg".format(
            spot.x, spot.y, spot.z, angles[0][0], angles[0][1]),
        "CHECK |highlight - formula| left {:.1e}  right {:.1e}  {}".format(
            errors[0], errors[1], "OK" if error < 1e-4 else "NG"),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    return {"frame": frame, "presentation_stage": stage_name,
            "input": {"camera": [cx, cy, cz], "eyeRotateY": ry, "light": [lx, ly], "follow": follow},
            "errors": errors, "angles": angles, "ok": error < 1e-4}


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
        folder = recordVideo("EyeHighlight: 目のハイライトがカメラと光の方向に合わせて眼球の表面を移る", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "eye_highlight.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-eye-highlight.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("eye-highlight-%Y%m%d-%H%M%S")
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
