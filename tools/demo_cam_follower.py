"""CamFollower(カムの休止・上昇・休止・下降)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_cam_follower.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 60
BASE = 3.0
RISE = 2.0
UP, HOLD, DOWN = 120.0, 60.0, 120.0
SAMPLES = 720
# (カムの角度[度], 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, "1 REST (END OF LOW DWELL)"),
    (0.0, "2 TURN THE CAM ONE FULL TURN (RISE, HIGH DWELL, RETURN, LOW DWELL)"),
    (360.0, "3 TURN ON TO +510 deg (SECOND RISE INTO THE HIGH DWELL)"),
    (510.0, "4 REVERSE TO +300 deg (BACK DOWN THE SAME PATH)"),
    (300.0, "5 RETURN TO REST"),
    (0.0, "5 RETURN TO REST"),
    (0.0, "5 RETURN TO REST"),
]


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    return POSES[index][0] + (POSES[index + 1][0] - POSES[index][0]) * weight, POSES[index][1]


def expected(degrees):
    """試験側の独立な式。区間ごとにサイクロイド曲線で変位(cm)と区間名を返す。"""
    wrapped = degrees % 360.0
    if wrapped < UP:
        u = wrapped / UP
        return RISE * (u - math.sin(2.0 * math.pi * u) / (2.0 * math.pi)), "RISE"
    if wrapped < UP + HOLD:
        return RISE, "HIGH DWELL"
    if wrapped < UP + HOLD + DOWN:
        u = (wrapped - UP - HOLD) / DOWN
        return RISE * (1.0 - (u - math.sin(2.0 * math.pi * u) / (2.0 * math.pi))), "RETURN"
    return 0.0, "LOW DWELL"


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


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import CamFollower
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("camRed", (0.9, 0.15, 0.1)), "green": _shader("followerGreen", (0.15, 0.75, 0.25)),
              "gray": _shader("restGray", (0.45, 0.45, 0.45)), "mark": _shader("markWhite", (0.95, 0.95, 0.9))}
    # カム(赤): 原点。輪郭は試験側の式で、ローカルの角度 90° - θ の向きへ BASE + lift(θ) の点を並べた面。
    cam = cmds.createNode("transform", name="cam_CAM")
    points = []
    for index in range(SAMPLES):
        theta = 360.0 * index / SAMPLES
        radius = BASE + expected(theta)[0]
        points.append((radius * math.sin(math.radians(theta)), radius * math.cos(math.radians(theta)), 0.0))
    profile = cmds.polyCreateFacet(point=points, name="cam_PROFILE")[0]
    cmds.parent(profile, cam, relative=True)
    cmds.sets(profile, edit=True, forceElement=groups["red"])
    hub = cmds.polyCylinder(name="cam_HUB", radius=0.4, height=0.3, axis=(0, 0, 1))[0]
    cmds.parent(hub, cam, relative=True)
    cmds.setAttr(hub + ".translateZ", 0.2)
    cmds.sets(hub, edit=True, forceElement=groups["mark"])
    marker = cmds.polyCube(name="cam_MARK", width=0.25, height=BASE - 0.6, depth=0.1)[0]
    cmds.parent(marker, cam, relative=True)
    cmds.setAttr(marker + ".translate", 0, (BASE - 0.6) / 2.0 + 0.3, 0.2)
    cmds.sets(marker, edit=True, forceElement=groups["mark"])
    # 従動節(緑の棒): 先端がカムの真上の輪郭に乗る。灰色の棒は動かない下の位置の目印。
    rest = cmds.polyCube(name="follower_REST", width=0.5, height=4.0, depth=0.1)[0]
    cmds.setAttr(rest + ".translate", -0.7, BASE + 2.0, -0.2)
    cmds.sets(rest, edit=True, forceElement=groups["gray"])
    follower = cmds.createNode("transform", name="follower_ROD")
    cmds.setAttr(follower + ".translateY", BASE)
    rod = cmds.polyCube(name="follower_GEO", width=0.5, height=4.0, depth=0.3)[0]
    cmds.parent(rod, follower, relative=True)
    cmds.setAttr(rod + ".translate", 0, 2.0, 0.2)
    cmds.sets(rod, edit=True, forceElement=groups["green"])
    graph = CamFollower.create(cam, follower, RISE, UP, HOLD, DOWN, name="camFollower", axis="z", followerAxis="y")
    owner = graph.container
    camera, camera_shape = cmds.camera(name="camCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(-9.5, 0.5, 34), lookAt=(-9.5, 0.5, 0))
    window = cmds.window("camValidationWindow", title="CamFollower - dwell, rise, dwell, return", widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("camValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("camFollower", 8)
    scene = {"owner": owner, "cam": cam, "follower": follower, "profile": profile}
    return panel, scene, values, names


def _contact(profile):
    """カムの輪郭の頂点をワールドへ変換し、x = 0 を上側で横切る2点の補間で、真上の輪郭の高さを求める。"""
    from maya import cmds
    points = cmds.xform(profile + ".vtx[*]", query=True, worldSpace=True, translation=True)
    points = [points[i:i + 3] for i in range(0, len(points), 3)]
    best = None
    for index, a in enumerate(points):
        b = points[(index + 1) % len(points)]
        if (a[0] <= 0.0 <= b[0] or b[0] <= 0.0 <= a[0]) and a[0] != b[0]:
            t = -a[0] / (b[0] - a[0])
            height = a[1] + (b[1] - a[1]) * t
            best = height if best is None else max(best, height)
    return best


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、従動節の変位を試験側の式と、カムの輪郭との接触で比較した診断を返す。"""
    from maya import cmds
    angle, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(scene["cam"] + ".rotateZ", angle)
    lift_expected, segment = expected(angle)
    translate = cmds.getAttr(scene["follower"] + ".translateY")
    lift = cmds.getAttr(owner + ".lift")
    velocity = cmds.getAttr(owner + ".velocity")
    rise_progress = cmds.getAttr(owner + ".riseProgress")
    return_progress = cmds.getAttr(owner + ".returnProgress")
    cam_angle = cmds.getAttr(owner + ".camAngle")
    error = max(abs(lift - lift_expected), abs(translate - BASE - lift_expected))
    # 試験側で独立に: 回したカムの輪郭(形状の頂点)の真上の高さと、従動節の先の高さの差。
    contact = _contact(scene["profile"])
    contact_error = abs(contact - translate)
    values[:] = [
        "RED = cam (INPUT, rotateZ)   GREEN = follower rod (OUTPUT, translateY)   GRAY = low position   cm / deg",
        "STAGE: " + stage,
        "fixed: h = rise = {:.1f} cm   beta1 = {:.0f}   betaD = {:.0f}   beta2 = {:.0f}   low dwell = {:.0f} deg   law = cycloidal".format(
            RISE, UP, HOLD, DOWN, 360.0 - UP - HOLD - DOWN),
        "w = theta mod 360   u1 = clamp(w/beta1, 0, 1)   u2 = clamp((w - beta1 - betaD)/beta2, 0, 1)   f(u) = u - sin(2 pi u)/(2 pi)",
        "lift = h (f(u1) - f(u2))   velocity = h (f'(u1)/beta1 - f'(u2)/beta2)  [cm/rad]   f'(u) = 1 - cos(2 pi u)",
        "INPUT theta = {:7.2f} deg   w = {:6.2f} deg   {:<10}   u1 = {:5.3f}   u2 = {:5.3f}".format(
            angle, cam_angle, segment, rise_progress, return_progress),
        "OUTPUT (DG) lift = {:6.3f} cm   translateY = {:6.3f} cm   velocity = {:6.3f} cm/rad".format(
            lift, translate, velocity),
        "CHECK |DG - formula| = {:.6f} cm   |rod tip - cam profile| = {:.5f} cm".format(error, contact_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and contact_error < 2e-3
    return {"frame": frame, "presentation_stage": stage, "input": {"cam": angle},
            "output": {"lift": lift, "translate": translate, "velocity": velocity, "riseProgress": rise_progress,
                       "returnProgress": return_progress},
            "error": error, "contact_error": contact_error, "ok": ok}


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
        folder = recordVideo("CamFollower: カムの休止・上昇・休止・下降", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "cam_follower.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-cam-follower.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("cam-follower-%Y%m%d-%H%M%S")
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
