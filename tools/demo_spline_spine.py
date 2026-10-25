"""スプラインIKの背骨のサンプル(mlrig.examples.spline_spine)を、専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。``python tools/demo_spline_spine.py --launch`` で
使い捨ての隔離GUIを起動して録画する(録画済みの動画・診断は ``.maya-output/verification/`` に残る)。
``--simple`` を付けると、伸縮なしのシンプル版(``stretch=False``)を録画する。
"""

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LENGTH = 50.0
HEIGHT = 100.0
COUNT = 6
SEGMENT = 36
MAX_STRETCH = 1.5
MAX_SQUASH = 0.5
#: 一番上の骨と胸のコントローラーの距離の許容(cm)。骨は線分なので、曲がりが強いとカーブの端から少しずれる。
GAP_TOLERANCE = 0.25
# (段階名, 胸の移動, 胸の回転[度], 腰の移動, fk03 の rotateZ[度])。段階名は「この姿勢へ向かう間」に表示する。
KEYS = [
    ("1 REST", (0, 0, 0), (0, 0, 0), (0, 0, 0), 0),
    ("2 STRETCH: CHEST UP (inside maxStretch)", (0, 10, 0), (0, 0, 0), (0, 0, 0), 0),
    ("3 PAST maxStretch: STOPS AT r = 1.5", (0, 50, 0), (0, 0, 0), (0, 0, 0), 0),
    ("4 HOLD PAST LIMIT", (0, 50, 0), (0, 0, 0), (0, 0, 0), 0),
    ("5 SQUASH: CHEST DOWN (volume grows)", (0, -20, 0), (0, 0, 0), (0, 0, 0), 0),
    ("6 BACK TO SAFE RANGE", (0, 0, 0), (0, 0, 0), (0, 0, 0), 0),
    ("7 BEND FORWARD (lockOriChest = 1)", (0, -6, 18), (40, 0, 0), (0, 0, 0), 0),
    ("8 TWIST CHEST 60 deg (distributed)", (0, -6, 18), (40, 60, 0), (0, 0, 0), 0),
    ("9 S-CURVE: HIPS AND CHEST SIDEWAYS", (-10, 0, 0), (0, 0, 0), (10, 0, 0), 0),
    ("10 FK OFFSET ON fk03 (+25 deg Z)", (-10, 0, 0), (0, 0, 0), (10, 0, 0), 25),
    ("11 RETURN TO REST", (0, 0, 0), (0, 0, 0), (0, 0, 0), 0),
]
# シンプル版(伸縮なし)の動き。胸を遠ざけても骨は伸びない。
KEYS_SIMPLE = [
    ("1 REST", (0, 0, 0), (0, 0, 0), (0, 0, 0), 0),
    ("2 CHEST UP 15 cm: BONES DO NOT STRETCH", (0, 15, 0), (0, 0, 0), (0, 0, 0), 0),
    ("3 HOLD (top joint stays short of the chest)", (0, 15, 0), (0, 0, 0), (0, 0, 0), 0),
    ("4 BACK TO REST", (0, 0, 0), (0, 0, 0), (0, 0, 0), 0),
    ("5 BEND FORWARD (lockOriChest = 1)", (0, -6, 18), (40, 0, 0), (0, 0, 0), 0),
    ("6 TWIST CHEST 60 deg (distributed)", (0, -6, 18), (40, 60, 0), (0, 0, 0), 0),
    ("7 S-CURVE: HIPS AND CHEST SIDEWAYS", (-10, 0, 0), (0, 0, 0), (10, 0, 0), 0),
    ("8 FK OFFSET ON fk03 (+25 deg Z)", (-10, 0, 0), (0, 0, 0), (10, 0, 0), 25),
    ("9 RETURN TO REST", (0, 0, 0), (0, 0, 0), (0, 0, 0), 0),
]
#: True ならシンプル版を録画する(--launch から環境変数で渡す)。
SIMPLE = os.environ.get("MLRIG_SPINE_DEMO_SIMPLE") == "1"


def keys():
    """録画する動きの一覧。"""
    return KEYS_SIMPLE if SIMPLE else KEYS


def pose(frame):
    """フレームの入力(胸の移動・回転、腰の移動、fk03 の回転、段階名)を smoothstep で補間する。"""
    poses = keys()
    phase = min(frame / SEGMENT, len(poses) - 1)
    index = min(int(phase), len(poses) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    a, b = poses[index], poses[index + 1]
    mix = [tuple(x + (y - x) * weight for x, y in zip(a[i], b[i])) for i in (1, 2, 3)]
    return mix[0], mix[1], mix[2], a[4] + (b[4] - a[4]) * weight, b[0]


def _shader(name, color):
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return group


def buildScene():
    """検証シーンを作り、(panel, 背骨, HUD値リスト, HUD名) を返す。"""
    from maya import cmds
    from mlrig.examples import spline_spine
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    spine = spline_spine.build(name="spine", joint_count=COUNT, length=LENGTH, height=HEIGHT, stretch=not SIMPLE)
    green = _shader("deformGreen", (0.12, 0.8, 0.25))
    # 変形用の骨に、断面(体積)と向きが見える円盤を付ける(骨の子なので scaleY/Z が効く)。
    for joint in spine.deform:
        disc = cmds.polyCylinder(radius=8, height=2.0, axis=(1, 0, 0), subdivisionsAxis=24,
                                 name=str(joint).split("|")[-1] + "_disc")[0]
        cmds.parent(disc, str(joint), relative=True)
        cmds.sets(disc, edit=True, forceElement=green)
        # 正面(+Z)が分かる小さな突起。
        nose = cmds.polyCube(width=2, height=2, depth=5, name=str(joint).split("|")[-1] + "_nose")[0]
        cmds.parent(nose, str(joint), relative=True)
        cmds.setAttr(nose + ".translateZ", 9)
        cmds.sets(nose, edit=True, forceElement=green)
    # スプラインのカーブを白で見せる(IKの骨とハンドルは隠したまま。黄色はFKのコントローラー)。
    setup = "spine_setup_grp"
    cmds.setAttr(setup + ".visibility", True)
    for joint in spine.ik:
        cmds.setAttr(str(joint) + ".drawStyle", 2)
    curve = spine.graph.member("curve").getFullName()
    cmds.setAttr(curve + ".visibility", True)
    for shape in cmds.listRelatives(curve, shapes=True, fullPath=True):
        cmds.setAttr(shape + ".overrideEnabled", True)
        cmds.setAttr(shape + ".overrideColor", 16)
        cmds.setAttr(shape + ".lineWidth", 3)
    rest = cmds.curve(degree=1, point=[(0, HEIGHT, 0), (0, HEIGHT + LENGTH, 0)], name="restLength_CRV")
    shape = cmds.listRelatives(rest, shapes=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideColor", 2)
    camera, camera_shape = cmds.camera(name="splineSpineCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(120, 172, 165), lookAt=(0, 146, 4))
    # 左側のHUD文字と重ならないよう、画面上で背骨を右へ寄せる。
    cmds.setAttr(camera_shape + ".horizontalFilmOffset", -0.3)
    window = cmds.window("splineSpineValidationWindow", title="Spline IK spine (mGear-like){}".format(
        " - simple" if SIMPLE else ""), widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("splineSpineValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=True,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False, ikHandles=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values = [""] * 9
    names = ["splineSpineHUD{}".format(i) for i in range(len(values))]
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=0 if i < 2 else 5, block=(1 - i) if i < 2 else (len(values) - 1 - i),
                            blockSize="large", dataFontSize="large", command=lambda row=i: values[row])
    return panel, spine, values, names


def _position(node):
    from maya import cmds
    from maya.api import OpenMaya as om
    return om.MVector(*cmds.xform(str(node), query=True, worldSpace=True, translation=True))


def _axis(node, index):
    from maya import cmds
    from maya.api import OpenMaya as om
    m = cmds.xform(str(node), query=True, worldSpace=True, matrix=True)
    return om.MVector(*m[index * 4:index * 4 + 3]).normal()


def evaluate_frame(frame, spine, values, names):
    """入力を更新し、DGの値を独立計算と比べた診断を返す。"""
    from maya import cmds
    from maya.api import OpenMaya as om
    chest_t, chest_r, hips_t, fk_rz, stage = pose(frame)
    cmds.setAttr(str(spine.chest) + ".translate", *chest_t, type="double3")
    cmds.setAttr(str(spine.chest) + ".rotate", *chest_r, type="double3")
    cmds.setAttr(str(spine.hips) + ".translate", *hips_t, type="double3")
    cmds.setAttr(str(spine.fk[2]) + ".rotateZ", fk_rz)
    curve = spine.graph.member("curve").getFullName()
    shape = cmds.listRelatives(curve, shapes=True, fullPath=True)[0]
    selection = om.MSelectionList()
    selection.add(shape)
    arc = om.MFnNurbsCurve(selection.getDagPath(0)).length()
    ratio = arc / LENGTH
    r = 1.0 if SIMPLE else min(max(ratio, MAX_SQUASH), MAX_STRETCH)
    segment_dg = cmds.getAttr(str(spine.ik[1]) + ".translateX")
    lengths = [(_position(b) - _position(a)).length() for a, b in zip(spine.deform, spine.deform[1:])]
    middle_index = COUNT // 2
    weight = math.sin(math.pi * middle_index / (COUNT - 1))
    expected_scale = 1 + weight * (r ** -0.5 - 1)
    scale_dg = cmds.getAttr(str(spine.deform[middle_index]) + ".scaleY")
    top = spine.deform[-1]
    gap = (_position(top) - _position(spine.chest)).length()
    chest_y = _axis(spine.chest, 1)
    lock_error = math.degrees(_axis(top, 0).angle(chest_y))
    z0, z_top = _axis(spine.deform[0], 2), _axis(top, 2)
    twist_top = math.degrees(math.atan2(z_top.x, z_top.z)) if abs(chest_r[0]) < 1e-6 else float("nan")
    clamped = abs(r - ratio) > 1e-6
    if SIMPLE:
        return _simpleFrame(frame, stage, arc, segment_dg, lengths, scale_dg, gap, lock_error, chest_t, chest_r,
                            hips_t, fk_rz, values, names)
    values[:] = [
        "CYAN = hips/chest IK ctrl  MAGENTA = tangent ctrl  YELLOW = FK ctrl  WHITE = spline curve  GREEN = deform joints  GREY = rest",
        "STAGE: " + stage,
        "fixed: rest length L0 = 50 cm, {} joints   maxStretch = 1.5   maxSquash = 0.5   volume = 1   lockOri hips/chest = 1".format(COUNT),
        "ratio = arcLength / L0 = {:6.2f} / 50 = {:5.3f}    r = clamp(ratio, 0.5, 1.5) = {:5.3f}{}".format(
            arc, ratio, r, "   (CLAMPED)" if clamped else ""),
        "joint length = 10 cm * r = {:6.3f} cm   DG ik02.translateX = {:6.3f} cm   deform segments = {:6.3f}..{:6.3f} cm".format(
            10 * r, segment_dg, min(lengths), max(lengths)),
        "volume: s = 1 + volume * w * (r^-0.5 - 1),  w = sin(pi*3/5) = {:4.2f}  ->  {:5.3f}   DG spine_04.scaleY = {:5.3f}".format(
            weight, expected_scale, scale_dg),
        "top joint to chest ctrl = {:6.2f} cm   ({})".format(
            gap, "chain stops short because r is clamped" if clamped
            else "FK offset moves the chain" if fk_rz > 1e-6 else "reaches the chest (tolerance 0.25 cm)"),
        "lockOriChest: angle(top joint X, chest ctrl Y) = {:5.2f} deg{}   chest rotate = ({:5.1f}, {:5.1f}, {:5.1f}) deg".format(
            lock_error, " (FK offset added)" if fk_rz > 1e-6 else "", *chest_r),
        "fk03 rotateZ = {:5.1f} deg (FK layered on the spline: joints above fk03 follow)".format(fk_rz),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (abs(segment_dg - 10 * r) < 1e-3
          and max(abs(length - 10 * r) for length in lengths) < 2e-3
          and abs(scale_dg - expected_scale) < 1e-4
          and (fk_rz > 1e-6 or lock_error < 0.05)
          and (clamped or fk_rz > 1e-6 or gap < GAP_TOLERANCE))
    return {"frame": frame, "presentation_stage": stage, "arc_length": arc, "ratio": ratio, "clamped_ratio": r,
            "dg_segment": segment_dg, "deform_segments": lengths, "expected_mid_scale": expected_scale,
            "dg_mid_scale": scale_dg, "top_to_chest": gap, "lock_error_degrees": lock_error,
            "fk03_rotate_z": fk_rz, "chest_translate": chest_t, "chest_rotate": chest_r, "hips_translate": hips_t,
            "top_twist_degrees": twist_top, "ok": ok}


def _simpleFrame(frame, stage, arc, segment_dg, lengths, scale_dg, gap, lock_error, chest_t, chest_r, hips_t,
                 fk_rz, values, names):
    """シンプル版(伸縮なし)のHUDと判定。骨の長さは常に 10 cm、断面は 1 のまま。"""
    from maya import cmds
    values[:] = [
        "CYAN = hips/chest IK ctrl  MAGENTA = tangent ctrl  YELLOW = FK ctrl  WHITE = spline curve  GREEN = deform joints  GREY = rest",
        "STAGE: " + stage,
        "fixed: SIMPLE version (stretch=False)   rest length L0 = 50 cm, {} joints, 10 cm each   lockOri hips/chest = 1".format(COUNT),
        "curve arcLength = {:6.2f} cm   (not used: no stretch, no volume)".format(arc),
        "joint length = 10 cm (fixed)   DG ik02.translateX = {:6.3f} cm   deform segments = {:6.3f}..{:6.3f} cm".format(
            segment_dg, min(lengths), max(lengths)),
        "cross section scale = 1 (no volume)   DG spine_04.scaleY = {:5.3f}".format(scale_dg),
        "top joint to chest ctrl = {:6.2f} cm   (bones keep their length; the chain does not reach a far chest)".format(gap),
        "lockOriChest: angle(top joint X, chest ctrl Y) = {:5.2f} deg{}   chest rotate = ({:5.1f}, {:5.1f}, {:5.1f}) deg".format(
            lock_error, " (FK offset added)" if fk_rz > 1e-6 else "", *chest_r),
        "fk03 rotateZ = {:5.1f} deg (FK layered on the spline: joints above fk03 follow)".format(fk_rz),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (abs(segment_dg - 10) < 1e-6
          and max(abs(length - 10) for length in lengths) < 2e-3
          and abs(scale_dg - 1) < 1e-9
          and (fk_rz > 1e-6 or lock_error < 0.05))
    return {"frame": frame, "presentation_stage": stage, "arc_length": arc, "dg_segment": segment_dg,
            "deform_segments": lengths, "dg_mid_scale": scale_dg, "top_to_chest": gap,
            "lock_error_degrees": lock_error, "fk03_rotate_z": fk_rz, "chest_translate": chest_t,
            "chest_rotate": chest_r, "hips_translate": hips_t, "ok": ok}


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
        panel, spine, values, names = buildScene()
        frames = SEGMENT * (len(keys()) - 1) + 24
        ffmpeg = os.environ.get("MAYA_VERIFICATION_FFMPEG") or shutil.which("ffmpeg")
        title = "スプラインIKの背骨のサンプル(mGear風{})".format("・伸縮なし" if SIMPLE else "")
        folder = recordVideo(title, frames, 24, panel,
                             lambda frame: evaluate_frame(frame, spine, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "spline-spine.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-spline-spine{}.json".format("-simple" if SIMPLE else "")).write_text(
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


def launch(simple=False):
    """使い捨ての隔離Maya 2027 GUIを起動して録画する。作業中のMayaには触れない。

    Args:
        simple (bool): True ならシンプル版(伸縮なし)を録画する。
    """
    from datetime import datetime
    sys.path.insert(0, str(ROOT / "tools"))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maya/inhouse/mlib/__tests__"))
    from runGui import run_version
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("spline-spine-%Y%m%d-%H%M%S")
    environment = {"PYTHONPATH": os.pathsep.join([str(ROOT / "maya/inhouse"), str(ROOT / "tools")]),
                   "MLRIG_SPINE_DEMO_SIMPLE": "1" if simple else "0"}
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
    parser.add_argument("--simple", action="store_true", help="伸縮なしのシンプル版を録画する")
    arguments = parser.parse_args()
    if arguments.launch:
        sys.exit(launch(simple=arguments.simple))
    main()
