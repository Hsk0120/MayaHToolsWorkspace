"""Swashplate(ヘリコプターの斜板でブレードのピッチ角を変える機構)を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_swashplate.py --launch`` で使い捨ての隔離GUIを起動して録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RADIUS = 2.0
HORN = 1.5
MAX_PITCH = 30.0
REACH = HORN * math.sin(math.radians(MAX_PITCH))
PLATE_Y = 3.0
ROTOR_Y = 6.0
BLADE = 6.0
SPIN = 6.0
# (始まりのフレーム, 終わりのフレーム, 始まりの (高さの変化, 傾きZ[度]), 終わり, 補間, 段階名)。ローターは毎フレーム SPIN 度回る。
SEGMENTS = [
    (0, 24, (0.0, 0.0), (0.0, 0.0), "hold", "1 REST (LEVEL PLATE, ALL BLADES FLAT, ROTOR SPINNING)"),
    (24, 72, (0.0, 0.0), (0.5, 0.0), "smooth", "2 COLLECTIVE: RAISE THE PLATE (ALL BLADES PITCH THE SAME)"),
    (72, 144, (0.5, 0.0), (0.2, 8.0), "smooth", "3 CYCLIC: TILT THE PLATE (PITCH GOES UP AND DOWN ONCE PER TURN)"),
    (144, 216, (0.2, 8.0), (1.1, 8.0), "smooth", "4 INPUT BEYOND THE LIMIT (PITCH STOPS AT 30 deg, excess grows)"),
    (216, 288, (1.1, 8.0), (0.0, 0.0), "smooth", "5 BACK INTO THE SAFE RANGE AND TO REST"),
    (288, 312, (0.0, 0.0), (0.0, 0.0), "hold", "5 BACK INTO THE SAFE RANGE AND TO REST"),
]
FRAMES = SEGMENTS[-1][1]


def pose(frame):
    """フレームの斜板の高さの変化・傾き(度)・ローターの角度(度)と段階名を返す。"""
    for start, end, first, last, mode, stage in SEGMENTS:
        if frame <= end:
            weight = 0.0 if end == start else min(max((frame - start) / float(end - start), 0.0), 1.0)
            if mode == "smooth":
                weight = weight * weight * (3 - 2 * weight)
            values = [a + (b - a) * weight for a, b in zip(first, last)]
            return values[0], values[1], SPIN * frame, stage
    return 0.0, 0.0, SPIN * frame, SEGMENTS[-1][5]


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


def _box(name, parent, size, translate, group):
    """parent(Noneならワールド)の下へ箱を作り、色を付けて返す。"""
    from maya import cmds
    node = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    if parent:
        node = cmds.parent(node, parent, relative=True)[0]
    cmds.setAttr(node + ".translate", *translate)
    cmds.sets(node, edit=True, forceElement=group)
    return node


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import Swashplate
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    groups = {"red": _shader("plateRed", (0.9, 0.15, 0.1)), "green": _shader("bladeGreen", (0.15, 0.8, 0.25)),
              "gray": _shader("refGray", (0.55, 0.55, 0.55)), "orange": _shader("linkOrange", (1.0, 0.55, 0.1)),
              "blue": _shader("hubBlue", (0.2, 0.45, 0.95))}
    # 灰色: ローターの軸(マスト)。
    mast = cmds.polyCylinder(name="mast_GEO", radius=0.15, height=ROTOR_Y + 1.0)[0]
    cmds.setAttr(mast + ".translateY", (ROTOR_Y + 1.0) * 0.5 - 0.5)
    cmds.sets(mast, edit=True, forceElement=groups["gray"])
    # 斜板(赤): 入力。ローカルの +Y を法線とする円板。
    plate = cmds.createNode("transform", name="swashplate_INPUT")
    cmds.setAttr(plate + ".translateY", PLATE_Y)
    disc = cmds.polyCylinder(name="swashplate_GEO", radius=RADIUS + 0.3, height=0.15, subdivisionsX=48)[0]
    cmds.parent(disc, plate, relative=True)
    cmds.sets(disc, edit=True, forceElement=groups["red"])
    # ローター(青のハブ)とブレード(緑): ブレードは rotateX でピッチする。
    rotor = cmds.createNode("transform", name="rotor")
    cmds.setAttr(rotor + ".translateY", ROTOR_Y)
    hub = cmds.polyCylinder(name="hub_GEO", radius=0.4, height=0.4)[0]
    cmds.parent(hub, rotor, relative=True)
    cmds.sets(hub, edit=True, forceElement=groups["blue"])
    blades = []
    for index in range(3):
        blade = cmds.createNode("transform", name="blade{}_OUTPUT".format(index), parent=rotor)
        cmds.setAttr(blade + ".rotateY", -120.0 * index)
        _box("blade{}_GEO".format(index), blade, (BLADE, 0.06, 0.9), (BLADE * 0.5 + 0.4, 0, 0), groups["green"])
        blades.append(blade)
    # 灰色の参照: ブレード0と同じ向きでピッチしない板(ピッチ角の比較用)。
    reference = cmds.createNode("transform", name="blade0_REFERENCE", parent=rotor)
    _box("blade0_REFGEO", reference, (BLADE, 0.03, 0.9), (BLADE * 0.5 + 0.4, 0, 0), groups["gray"])
    graph = Swashplate.create(plate, rotor, blades, RADIUS, HORN, MAX_PITCH, name="swashplate")
    owner = str(graph.container)
    # 橙: ピッチリンクの下端(斜板の面の上の点)。表示用に毎フレームDGの出力から置く。
    links = []
    for index in range(3):
        link = cmds.polySphere(name="link{}_GEO".format(index), radius=0.18)[0]
        cmds.sets(link, edit=True, forceElement=groups["orange"])
        links.append(link)
    camera, camera_shape = cmds.camera(name="swCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(13.0, 11.0, 17.0), lookAt=(0.0, 4.2, 0.0))
    window = cmds.window("swValidationWindow", title="Swashplate - tilted plate pitches rotor blades",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("swValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=True,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, nurbsCurves=True)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("swashplate", 10)
    scene = {"owner": owner, "plate": plate, "rotor": rotor, "blades": blades, "links": links}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、リンクが斜板の面の上・ホーンの幾何・Python版との一致を試験側で独立に確かめた診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om2
    from mlrig.setups import Swashplate
    lift, tilt, spin, stage = pose(frame)
    owner = scene["owner"]
    cmds.setAttr(scene["plate"] + ".translateY", PLATE_Y + lift)
    cmds.setAttr(scene["plate"] + ".rotateZ", tilt)
    cmds.setAttr(scene["rotor"] + ".rotateY", spin)

    def get(attribute, index=None):
        """containerの出力の値。"""
        return cmds.getAttr(owner + "." + attribute + ("" if index is None else "[{}]".format(index)))

    inverse = om2.MMatrix(cmds.xform(scene["plate"], query=True, worldSpace=True, matrix=True)).inverse()
    matrix = cmds.getAttr(scene["plate"] + ".matrix")
    result = Swashplate.motion(math.radians(spin), matrix[4:7], matrix[12:15], (0.0, 0.0), RADIUS, HORN, 3, 0.0,
                               PLATE_Y, math.radians(MAX_PITCH))
    plane_error = horn_error = formula_error = rotate_error = 0.0
    rows = []
    for index, blade in enumerate(scene["blades"]):
        angle = math.radians(get("azimuth", index))
        height = get("linkHeight", index)
        pitch = get("bladePitch", index)
        excess = get("linkExcess", index)
        point = om2.MPoint(RADIUS * math.cos(angle), PLATE_Y + height, -RADIUS * math.sin(angle))
        # 試験側で独立に: リンクの下端が斜板の面の上(斜板のローカルで y = 0)、ホーンの先の高さ L sin θ = d - excess。
        plane_error = max(plane_error, abs((point * inverse).y))
        horn_error = max(horn_error, abs(HORN * math.sin(math.radians(pitch)) - (height - excess)))
        formula_error = max(formula_error, abs(height - result["linkHeight"][index]),
                            abs(pitch - math.degrees(result["bladePitch"][index])))
        rotate_error = max(rotate_error, abs(cmds.getAttr(blade + ".rotateX") - pitch))
        cmds.setAttr(scene["links"][index] + ".translate", point.x, point.y, point.z)
        rows.append((pitch, height, excess))
    collective = get("collective")
    values[:] = [
        "RED = swashplate (INPUT: lift translateY, tilt rotateZ)   GREEN = blades (OUTPUT pitch rotateX)   GRAY = blade 0 without pitch   ORANGE = pitch link on the plate   cm / deg",
        "STAGE: " + stage,
        "fixed: link radius Rs = {:.1f}  horn L = {:.1f}  max pitch = {:.0f} deg (link limit = +-{:.3f})   3 blades, 120 deg apart".format(
            RADIUS, HORN, MAX_PITCH, REACH),
        "a = nx/ny  b = nz/ny  G = plate height on the axis   d_i = G - Rs (a cos psi_i - b sin psi_i) - G0   pitch_i = asin(clamp(d_i, +-L sin max) / L)",
        "INPUT lift = {:6.3f} cm   tilt Z = {:5.2f} deg   rotor = {:7.1f} deg   ->  collective = {:6.3f} cm".format(
            lift, tilt, spin, collective),
    ]
    for index, (pitch, height, excess) in enumerate(rows):
        values.append("OUTPUT (DG) blade {}: link d = {:7.4f} cm   pitch = {:7.3f} deg   excess = {:6.3f} cm".format(
            index, height, pitch, excess))
    values.append("CHECK max |link point off the plate| = {:.6f} cm   max |L sin(pitch) - (d - excess)| = {:.6f} cm".format(
        plane_error, horn_error))
    values.append("CHECK max |DG - python| = {:.6f}   max |blade rotateX - pitch| = {:.6f} deg".format(
        formula_error, rotate_error))
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    pitches = [row[0] for row in rows]
    ok = (plane_error < 1e-5 and horn_error < 1e-5 and formula_error < 1e-4 and rotate_error < 1e-4
          and max(abs(value) for value in pitches) <= MAX_PITCH + 1e-6)
    return {"frame": frame, "presentation_stage": stage, "input": {"lift": lift, "tiltZ": tilt, "rotor": spin},
            "output": {"collective": collective, "pitch": pitches, "linkHeight": [row[1] for row in rows],
                       "linkExcess": [row[2] for row in rows]},
            "plane_error": plane_error, "horn_error": horn_error, "formula_error": formula_error,
            "rotate_error": rotate_error, "ok": ok}


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
        folder = recordVideo("Swashplate: 斜板の高さと傾きでブレードのピッチ角を変える", FRAMES, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "swashplate.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-swashplate.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("swashplate-%Y%m%d-%H%M%S")
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
