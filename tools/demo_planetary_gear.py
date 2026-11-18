"""PlanetaryGear(太陽歯車・内歯車・キャリアと遊星歯車の遊星歯車機構)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_planetary_gear.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUN, PLANET = 24.0, 12.0
RING = SUN + 2.0 * PLANET
MODULE = 0.125  # ピッチ円の半径 = MODULE * 歯数(cm)
RS, RP, RR = MODULE * SUN, MODULE * PLANET, MODULE * RING
# (始まりのフレーム, 終わりのフレーム, 太陽の始まり, 終わり, 内歯車の始まり, 終わり[度], 補間, 段階名)
SEGMENTS = [
    (0, 24, 0.0, 0.0, 0.0, 0.0, "hold", "1 REST"),
    (24, 168, 0.0, 360.0, 0.0, 0.0, "linear", "2 RING FIXED: SUN 1 TURN -> CARRIER 1/3 TURN THE SAME WAY"),
    (168, 264, 360.0, 360.0, 0.0, -90.0, "smooth", "3 SUN HELD: RING -90 deg -> CARRIER -60 deg"),
    (264, 336, 360.0, 180.0, -90.0, 0.0, "smooth", "4 BOTH INPUTS MOVE BACK"),
    (336, 384, 180.0, 0.0, 0.0, 0.0, "smooth", "5 BACK TO REST"),
    (384, 408, 0.0, 0.0, 0.0, 0.0, "hold", "5 BACK TO REST"),
]
FRAMES = SEGMENTS[-1][1]


def pose(frame):
    """フレームの (太陽の角度, 内歯車の角度, 段階名) を返す(linear 以外はsmoothstep)。"""
    for start, end, sun0, sun1, ring0, ring1, mode, stage in SEGMENTS:
        if frame <= end:
            weight = 0.0 if end == start else min(max((frame - start) / float(end - start), 0.0), 1.0)
            if mode == "smooth":
                weight = weight * weight * (3 - 2 * weight)
            return sun0 + (sun1 - sun0) * weight, ring0 + (ring1 - ring0) * weight, stage
    return 0.0, 0.0, SEGMENTS[-1][7]


def expected(sun, ring):
    """試験側の独立な式。ピッチ円の2つの接点で弧長が一致する連立式
    rs (s - c) + rp (p - c) = 0、rr (r - c) - rp (p - c) = 0 を解いた (キャリア, 遊星の固定した空間での自転) [度]。"""
    carrier = (RS * sun + RR * ring) / (RS + RR)
    planet = carrier - RS / RP * (sun - carrier)
    return carrier, planet


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


def _gear(name, parent, radius, group, mark_group, mark_length):
    """parent の下に Z 軸の円板(歯車のピッチ円)と、向きが分かる目印の箱を作る。"""
    from maya import cmds
    disc = cmds.polyCylinder(name=name + "_GEO", radius=radius, height=0.2, axis=(0, 0, 1), subdivisionsAxis=48)[0]
    disc = cmds.parent(disc, parent, relative=True)[0]
    cmds.sets(disc, edit=True, forceElement=group)
    mark = cmds.polyCube(name=name + "_MARK", width=mark_length, height=0.18, depth=0.2)[0]
    mark = cmds.parent(mark, parent, relative=True)[0]
    cmds.setAttr(mark + ".translate", mark_length * 0.5, 0, 0.2)
    cmds.sets(mark, edit=True, forceElement=mark_group)


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import PlanetaryGear
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("sunRed", (0.9, 0.15, 0.1)), "green": _shader("carrierGreen", (0.15, 0.75, 0.25)),
              "gray": _shader("ringGray", (0.5, 0.5, 0.5)), "blue": _shader("planetBlue", (0.2, 0.45, 0.95)),
              "white": _shader("markWhite", (0.95, 0.95, 0.95)), "dark": _shader("markDark", (0.1, 0.1, 0.1))}
    sun = cmds.createNode("transform", name="sun_GEAR")
    _gear("sun", sun, RS, groups["red"], groups["white"], RS)
    # 内歯車(灰色の輪、内側の縁がピッチ円)と、回転が分かる黒い目印。
    ring = cmds.createNode("transform", name="ring_GEAR")
    pipe = cmds.polyPipe(name="ring_GEO", radius=RR + 0.6, thickness=0.6, height=0.2, axis=(0, 0, 1),
                         subdivisionsAxis=64)[0]
    pipe = cmds.parent(pipe, ring, relative=True)[0]
    cmds.sets(pipe, edit=True, forceElement=groups["gray"])
    ring_mark = cmds.polyCube(name="ring_MARK", width=1.0, height=0.5, depth=0.2)[0]
    ring_mark = cmds.parent(ring_mark, ring, relative=True)[0]
    cmds.setAttr(ring_mark + ".translate", RR + 0.8, 0, 0.2)
    cmds.sets(ring_mark, edit=True, forceElement=groups["dark"])
    # キャリア(緑の3本の腕)と、腕の先の遊星歯車(青、キャリアの子)。
    carrier = cmds.createNode("transform", name="carrier_ARM")
    planets = []
    distance = RS + RP
    for index in range(3):
        angle = math.radians(120.0 * index)
        arm = cmds.polyCube(name="carrier_ARM{}".format(index), width=distance, height=0.35, depth=0.15)[0]
        arm = cmds.parent(arm, carrier, relative=True)[0]
        cmds.setAttr(arm + ".translate", 0.5 * distance * math.cos(angle), 0.5 * distance * math.sin(angle), 0.45)
        cmds.setAttr(arm + ".rotateZ", 120.0 * index)
        cmds.sets(arm, edit=True, forceElement=groups["green"])
        planet = cmds.createNode("transform", name="planet{}_GEAR".format(index), parent=carrier)
        cmds.setAttr(planet + ".translate", distance * math.cos(angle), distance * math.sin(angle), 0.0)
        _gear("planet{}".format(index), planet, RP, groups["blue"], groups["white"], RP)
        planets.append(cmds.ls(planet, long=True)[0])
    graph = PlanetaryGear.create(sun, ring, carrier, planets, SUN, PLANET, driven="carrier", name="planetaryGear",
                                 axis="z")
    owner = graph.container
    camera, camera_shape = cmds.camera(name="pgCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(-12.0, -0.5, 38), lookAt=(-12.0, -0.5, 0))
    window = cmds.window("pgValidationWindow", title="PlanetaryGear - sun, planets and carrier",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("pgValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("planetaryGear", 8)
    scene = {"owner": owner, "sun": sun, "ring": ring, "carrier": carrier, "planets": planets}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、キャリアと遊星歯車の回転を試験側の式と、ピッチ円の接点の弧長の一致で比較した診断を返す。"""
    from maya import cmds
    sun, ring, stage = pose(frame)
    owner = str(scene["owner"])
    cmds.setAttr(scene["sun"] + ".rotateZ", sun)
    cmds.setAttr(scene["ring"] + ".rotateZ", ring)
    carrier_expected, planet_expected = expected(sun, ring)
    carrier = cmds.getAttr(scene["carrier"] + ".rotateZ")
    spins = [cmds.getAttr(planet + ".rotateZ") for planet in scene["planets"]]
    planet = carrier + spins[0]  # キャリアの子なので、固定した空間での自転はキャリア + 自転
    spin_output = cmds.getAttr(owner + ".planetSpin")
    angle_output = cmds.getAttr(owner + ".planetAngle")
    error = max(abs(carrier - carrier_expected), abs(planet - planet_expected), abs(angle_output - planet_expected),
                max(abs(value - spins[0]) for value in spins))
    # 試験側で独立に: シーンの回転から2つの接点の弧長の差(cm)を求める
    sun_arc_error = abs(math.radians(RS * (sun - carrier) + RP * (planet - carrier)))
    ring_arc_error = abs(math.radians(RR * (ring - carrier) - RP * (planet - carrier)))
    values[:] = [
        "RED = sun (INPUT)   GRAY = ring (INPUT)   GREEN = carrier (OUTPUT)   BLUE = planets (OUTPUT)   white/black marks = gear angle   deg",
        "STAGE: " + stage,
        "fixed: Zs = {:.0f}   Zp = {:.0f}   Zr = Zs + 2 Zp = {:.0f}   pitch radius = {:.3f} x teeth cm".format(
            SUN, PLANET, RING, MODULE),
        "carrier = (Zs sun + Zr ring) / (Zs + Zr)   planet spin (on carrier) = -(Zs / Zp)(sun - carrier)",
        "INPUT sun = {:8.2f} deg   ring = {:8.2f} deg".format(sun, ring),
        "OUTPUT (DG) carrier = {:8.2f} deg   planet spin = {:8.2f} deg   planet (fixed space) = {:8.2f} deg".format(
            carrier, spin_output, angle_output),
        "CHECK arc at sun contact {:.6f} cm   arc at ring contact {:.6f} cm   (0 = rolling, no slip)".format(
            sun_arc_error, ring_arc_error),
        "CHECK |DG - formula| = {:.6f} deg".format(error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = error < 1e-4 and sun_arc_error < 1e-5 and ring_arc_error < 1e-5
    return {"frame": frame, "presentation_stage": stage, "input": {"sun": sun, "ring": ring},
            "output": {"carrier": carrier, "planetSpin": spin_output, "planetAngle": angle_output, "planets": spins},
            "error": error, "sun_arc_error": sun_arc_error, "ring_arc_error": ring_arc_error, "ok": ok}


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
        folder = recordVideo("PlanetaryGear: 太陽歯車・内歯車・キャリアと遊星歯車", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "planetary_gear.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-planetary-gear.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("planetary-gear-%Y%m%d-%H%M%S")
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
