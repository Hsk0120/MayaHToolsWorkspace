"""PatellaFollowの膝蓋腱に引かれて溝に沿って滑る膝蓋骨を専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_patella_follow.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
TIBIA_LENGTH = 4.8
# 大腿骨の空間(X が前、Y が上、膝が原点)での溝の中心・膝蓋骨・脛骨粗面(cm)。
GROOVE = (0.0, 0.3)
PATELLA = (1.6, 0.6)
TUBEROSITY = (0.9, -3.0)
RADIUS = math.hypot(PATELLA[0] - GROOVE[0], PATELLA[1] - GROOVE[1])
TENDON = math.hypot(TUBEROSITY[0] - PATELLA[0], TUBEROSITY[1] - PATELLA[1])
LONG_TENDON = 6.5
# (膝の曲げ[度、脛が後ろへ], tendonLength[cm], 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, TENDON, "1 REST"),
    (0.0, TENDON, "2 FLEX 0 -> 120 deg"),
    (120.0, TENDON, "3 EXTEND BACK TO 60 deg"),
    (60.0, TENDON, "4 LENGTHEN tendonLength 3.67 -> 6.5 cm (L - r > d: OUT OF REACH)"),
    (60.0, LONG_TENDON, "5 RETURN tendonLength TO 3.67 cm (BACK IN REACH)"),
    (60.0, TENDON, "6 HYPEREXTEND TO -10 deg"),
    (-10.0, TENDON, "7 BACK TO REST"),
    (0.0, TENDON, "8 HOLD"),
    (0.0, TENDON, "8 HOLD"),
]


def _tuberosity(flexion):
    """膝の曲げ flexion(-Z 回り、脛が後ろへ)での脛骨粗面。"""
    angle = -math.radians(flexion)
    x, y = TUBEROSITY
    return x * math.cos(angle) - y * math.sin(angle), x * math.sin(angle) + y * math.cos(angle)


def expected_pose(flexion, tendon, previous):
    """膝蓋骨の位置・届かない量・溝の角度 φ を、φ の走査と二分法で求める(独立計算)。

    届かない場合は G から T への線の上で G から r の点(制限した値)を返す。
    """
    t_point = _tuberosity(flexion)
    d = math.hypot(t_point[0] - GROOVE[0], t_point[1] - GROOVE[1])
    excess = max(d - (RADIUS + tendon), abs(RADIUS - tendon) - d, 0.0)
    if excess > 0.0:
        sign = 1.0 if d * d + RADIUS * RADIUS - tendon * tendon >= 0.0 else -1.0
        phi = math.atan2(sign * (t_point[1] - GROOVE[1]), sign * (t_point[0] - GROOVE[0]))
    else:
        def gap(value):
            px, py = GROOVE[0] + RADIUS * math.cos(value), GROOVE[1] + RADIUS * math.sin(value)
            return math.hypot(px - t_point[0], py - t_point[1]) - tendon

        roots = []
        steps = 720
        for index in range(steps):
            low, high = 2 * math.pi * index / steps, 2 * math.pi * (index + 1) / steps
            if gap(low) * gap(high) > 0.0:
                continue
            for _ in range(60):
                middle = 0.5 * (low + high)
                if gap(low) * gap(middle) <= 0.0:
                    high = middle
                else:
                    low = middle
            roots.append(0.5 * (low + high))
        phi = min(roots, key=lambda value: abs((value - previous + math.pi) % (2 * math.pi) - math.pi))
    point = (GROOVE[0] + RADIUS * math.cos(phi), GROOVE[1] + RADIUS * math.sin(phi))
    return point, t_point, excess, phi, d


def pose(frame):
    """フレームの値と段階名をsmoothstepで補間する。"""
    phase = min(frame / SEGMENT, len(POSES) - 1)
    index = min(int(phase), len(POSES) - 2)
    weight = phase - index
    weight = weight * weight * (3 - 2 * weight)
    values = [a + (b - a) * weight for a, b in zip(POSES[index][:2], POSES[index + 1][:2])]
    return values[0], values[1], POSES[index][2]


def _shader(name, color):
    """単色のlambertを作る。"""
    from maya import cmds
    shader = cmds.shadingNode("lambert", asShader=True, name=name)
    cmds.setAttr(shader + ".color", *color, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    return shader, group


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


def _box(name, size, group, parent=None, translate=(0, 0, 0)):
    """単色の箱を作る。"""
    from maya import cmds
    box = cmds.polyCube(name=name, width=size[0], height=size[1], depth=size[2])[0]
    if parent is not None:
        box = cmds.parent(box, parent, relative=True)[0]
    cmds.setAttr(box + ".translate", *translate)
    cmds.sets(box, edit=True, forceElement=group)
    return box


def _ball(name, radius, group, parent=None, translate=(0, 0, 0)):
    """単色の球を作る。"""
    from maya import cmds
    ball = cmds.polySphere(name=name, radius=radius)[0]
    if parent is not None:
        ball = cmds.parent(ball, parent, relative=True)[0]
    cmds.setAttr(ball + ".translate", *translate)
    cmds.sets(ball, edit=True, forceElement=group)
    return ball


def _patellaGeo(prefix, parent, group, depth):
    """膝蓋骨の形(縦長の箱)を、膝蓋骨のローカルの原点に作る。"""
    _box(prefix + "Geo", (0.5, 1.6, 0.5), group, parent, (0.15, 0.0, depth))


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import PatellaFollow
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    _, green = _shader("patellaGreen", (0.15, 0.75, 0.25))
    _, gray = _shader("boneGray", (0.55, 0.56, 0.6))
    _, blue = _shader("rigidBlue", (0.25, 0.45, 0.85))
    _, white = _shader("pointWhite", (0.95, 0.95, 0.95))
    tendon_shader, tendon_group = _shader("tendonGreen", (0.15, 0.75, 0.25))
    femur = cmds.createNode("transform", name="femur")
    _box("femurShaft", (1.8, 4.5, 0.6), gray, femur, (-0.2, 3.0, -1.0))
    _ball("femurCondyle", 1.2, gray, femur, (GROOVE[0], GROOVE[1], -1.0))
    groove = cmds.createNode("transform", name="groove_REST", parent=femur)
    cmds.setAttr(groove + ".translate", GROOVE[0], GROOVE[1], 0)
    ring = cmds.polyTorus(name="grooveRing", radius=RADIUS, sectionRadius=0.03, subdivisionsAxis=72)[0]
    cmds.setAttr(ring + ".rotateX", 90)
    cmds.setAttr(ring + ".translate", GROOVE[0], GROOVE[1], 0.0)
    cmds.sets(ring, edit=True, forceElement=white)
    patella = cmds.createNode("transform", name="patella_REST", parent=femur)
    cmds.setAttr(patella + ".translate", PATELLA[0], PATELLA[1], 0)
    tibia = cmds.createNode("transform", name="tibia_INPUT")
    _box("tibiaPlateau", (3.0, 0.4, 0.6), gray, tibia, (-0.3, -0.9, -1.0))
    _box("tibiaShaft", (1.4, TIBIA_LENGTH, 0.6), gray, tibia, (-0.3, -0.9 - TIBIA_LENGTH / 2.0, -1.0))
    tuberosity = cmds.createNode("transform", name="tuberosity_REST", parent=tibia)
    cmds.setAttr(tuberosity + ".translate", TUBEROSITY[0], TUBEROSITY[1], 0)
    _ball("tuberosityGeo", 0.22, white, tuberosity, (0, 0, 0.6))
    # 青 = 比較用の、脛骨に固定しただけの膝蓋骨(脛と一緒に回る)。
    rigid = cmds.createNode("transform", name="patella_BLUE", parent=tibia)
    cmds.setAttr(rigid + ".translate", PATELLA[0], PATELLA[1], 0)
    _patellaGeo("rigid", rigid, blue, -0.4)
    graph = PatellaFollow.create(femur, tibia, groove, patella, tuberosity, name="patellaFollow")
    owner = str(graph.container)
    # 緑 = PatellaFollowの出力(膝蓋骨と膝蓋腱)。灰 = 大腿骨・脛骨(入力)。白 = 溝の円と脛骨粗面。
    patella_out = cmds.createNode("transform", name="patella_GREEN")
    _patellaGeo("patella", patella_out, green, 0.4)
    cmds.connectAttr(owner + ".patellaMatrix", patella_out + ".offsetParentMatrix")
    tendon_out = cmds.createNode("transform", name="tendon_GREEN")
    tendon_geo = _box("tendonGeo", (1.0, 0.18, 0.18), tendon_group, tendon_out, (0.5, 0, 0.6))
    cmds.connectAttr(owner + ".tendonMatrix", tendon_out + ".offsetParentMatrix")
    camera, camera_shape = cmds.camera(name="patellaCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(-0.5, -1.5, 40.0), lookAt=(-0.5, -1.5, 0))
    window = cmds.window("patellaValidationWindow", title="PatellaFollow - kneecap pulled by the patellar tendon",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("patellaValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("patella", 7)
    scene = {"owner": owner, "tibia": tibia, "tendon": tendon_geo, "tendonShader": tendon_shader,
             "phi": math.atan2(PATELLA[1] - GROOVE[1], PATELLA[0] - GROOVE[0])}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、膝蓋骨・膝蓋腱・溝の角度を独立計算と、溝の半径・腱の長さ・届かない量と比べた診断を返す。"""
    from maya import cmds
    import maya.api.OpenMaya as om
    flexion, tendon, stage = pose(frame)
    owner = scene["owner"]
    cmds.setAttr(scene["tibia"] + ".rotateZ", -flexion)
    cmds.setAttr(owner + ".tendonLength", tendon)
    expected, t_point, expected_excess, phi, d = expected_pose(flexion, tendon, scene["phi"])
    # 届かない間は枝の追跡を止め、届く範囲へ戻ったら直前の届いた姿勢から続ける。
    if expected_excess == 0.0:
        scene["phi"] = phi
    rest_phi = math.atan2(PATELLA[1] - GROOVE[1], PATELLA[0] - GROOVE[0])
    expected_angle = -math.degrees((phi - rest_phi + math.pi) % (2 * math.pi) - math.pi)
    patella = om.MMatrix(cmds.getAttr(owner + ".patellaMatrix"))
    point = om.MPoint(patella[12], patella[13], patella[14])
    tendon_matrix = om.MMatrix(cmds.getAttr(owner + ".tendonMatrix"))
    toward = (om.MPoint(t_point[0], t_point[1], 0) - point)
    span = toward.length()
    cmds.setAttr(scene["tendon"] + ".scaleX", span)
    cmds.setAttr(scene["tendon"] + ".translateX", span / 2.0)
    aim_error = 1.0 - om.MVector(tendon_matrix[0], tendon_matrix[1], tendon_matrix[2]).normal() * toward.normal()
    p_error = (point - om.MPoint(expected[0], expected[1], 0)).length()
    radius = math.hypot(point.x - GROOVE[0], point.y - GROOVE[1])
    angle = cmds.getAttr(owner + ".grooveAngle")
    excess = cmds.getAttr(owner + ".excess")
    out = expected_excess > 1e-9
    cmds.setAttr(scene["tendonShader"] + ".color", *((0.95, 0.15, 0.15) if out else (0.15, 0.75, 0.25)),
                 type="double3")
    values[:] = [
        "GREEN = PatellaFollow (patella, tendon)   BLUE = patella fixed to the tibia   GRAY = femur / tibia (input)   "
        "WHITE = groove circle, tuberosity",
        "STAGE: " + stage + ("   >>> OUT OF REACH: TENDON RED <<<" if out else ""),
        "fixed (cm): G = (0.0, 0.3)  P0 = (1.6, 0.6)  T0 = (0.9, -3.0)  grooveRadius r = 1.63  n = -Z",
        "T = T0 rotated with the tibia   P = circle(G, r) x circle(T, L)   R = angleBetween(P0 - G, P - G)   "
        "excess = max(d-(r+L), |r-L|-d, 0)",
        "INPUT knee flexion = {:7.2f} deg   tendonLength L = {:5.2f} cm   d = |T - G| = {:6.3f} cm".format(
            flexion, tendon, d),
        "OUTPUT P = ({:6.3f}, {:6.3f})  grooveAngle = {:7.2f} deg  |P-G| = {:5.3f}  |P-T| = {:5.3f}  "
        "excess = {:5.3f} cm".format(point.x, point.y, angle, radius, span, excess),
        "CHECK |P - scan| = {:.7f} cm  |angle - scan| = {:.5f} deg  |excess - formula| = {:.7f} cm  "
        "tendon aim 1-cos = {:.1e}".format(p_error, abs(angle - expected_angle), abs(excess - expected_excess),
                                           aim_error),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (p_error < 1e-4 and abs(excess - expected_excess) < 1e-4 and aim_error < 1e-6
          and abs(radius - RADIUS) < 1e-4 and abs(angle - expected_angle) < 1e-3
          and (out or abs(span - tendon) < 1e-4))
    return {"frame": frame, "presentation_stage": stage, "input": {"flexion": flexion, "tendonLength": tendon},
            "patella": [point.x, point.y], "p_error": p_error, "groove_angle": angle,
            "expected_groove_angle": expected_angle, "excess": excess, "expected_excess": expected_excess,
            "aim_error": aim_error, "ok": ok}


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
        folder = recordVideo("PatellaFollow: 膝蓋腱に引かれる膝蓋骨", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "patella_follow.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-patella-follow.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("patella-follow-%Y%m%d-%H%M%S")
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
