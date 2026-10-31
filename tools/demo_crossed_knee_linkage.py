"""CrossedKneeLinkageの交差した2本の靭帯による膝の転がりと滑りを専用Maya GUIで録画する検証デモ。

新規シーンを作るため、作業中のMayaへは送らない。専用GUIで ``main()`` を実行するか、
``python tools/demo_crossed_knee_linkage.py --launch`` で使い捨ての隔離GUIを起動して録画する。
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
TIBIA_LENGTH = 5.5
# 大腿骨の空間(X が前、Y が上)での付着点(cm)。前の靭帯 A→B、後ろの靭帯 D→C。
ACL_FEMUR = (-1.0, 0.5)
ACL_TIBIA = (1.2, -2.5)
PCL_FEMUR = (0.8, 0.8)
PCL_TIBIA = (-1.5, -2.8)
TIBIA_REST = (0.2, -2.6)
ACL = math.hypot(ACL_TIBIA[0] - ACL_FEMUR[0], ACL_TIBIA[1] - ACL_FEMUR[1])
PCL = math.hypot(PCL_TIBIA[0] - PCL_FEMUR[0], PCL_TIBIA[1] - PCL_FEMUR[1])
LONG_ACL = 9.0
# (flexion[度], aclLength[cm], 次の姿勢へ向かう段階名)。
POSES = [
    (0.0, ACL, "1 REST"),
    (0.0, ACL, "2 FLEX 0 -> 120 deg"),
    (120.0, ACL, "3 EXTEND BACK TO 60 deg"),
    (60.0, ACL, "4 LENGTHEN aclLength 3.72 -> 9 cm (|a - p| > d: OUT OF REACH)"),
    (60.0, LONG_ACL, "5 RETURN aclLength TO 3.72 cm (BACK IN REACH)"),
    (60.0, ACL, "6 HYPEREXTEND TO -15 deg"),
    (-15.0, ACL, "7 BACK TO REST"),
    (0.0, ACL, "8 HOLD"),
    (0.0, ACL, "8 HOLD"),
]


def _rotate(vector, degrees):
    """曲げ角 θ(-Z 回り、脛が後ろへ)で2Dのベクトルを回す。"""
    angle = -math.radians(degrees)
    return (vector[0] * math.cos(angle) - vector[1] * math.sin(angle),
            vector[0] * math.sin(angle) + vector[1] * math.cos(angle))


def expected_pose(degrees, acl, previous):
    """B・C・届かない量・瞬間回転中心と前の靭帯の角度 φ を、φ の走査と二分法で求める(独立計算)。

    届かない場合は A から D - v への線の上で A から a の点(制限した値)を返す。
    """
    v = _rotate((PCL_TIBIA[0] - ACL_TIBIA[0], PCL_TIBIA[1] - ACL_TIBIA[1]), degrees)
    center = (PCL_FEMUR[0] - v[0], PCL_FEMUR[1] - v[1])
    d = math.hypot(center[0] - ACL_FEMUR[0], center[1] - ACL_FEMUR[1])
    excess = max(d - (acl + PCL), abs(acl - PCL) - d, 0.0)
    if excess > 0.0:
        sign = 1.0 if d * d + acl * acl - PCL * PCL >= 0.0 else -1.0
        phi = math.atan2(sign * (center[1] - ACL_FEMUR[1]), sign * (center[0] - ACL_FEMUR[0]))
    else:
        def gap(value):
            bx, by = ACL_FEMUR[0] + acl * math.cos(value), ACL_FEMUR[1] + acl * math.sin(value)
            return math.hypot(bx + v[0] - PCL_FEMUR[0], by + v[1] - PCL_FEMUR[1]) - PCL

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
    b_point = (ACL_FEMUR[0] + acl * math.cos(phi), ACL_FEMUR[1] + acl * math.sin(phi))
    c_point = (b_point[0] + v[0], b_point[1] + v[1])
    e1 = (b_point[0] - ACL_FEMUR[0], b_point[1] - ACL_FEMUR[1])
    e2 = (c_point[0] - PCL_FEMUR[0], c_point[1] - PCL_FEMUR[1])
    determinant = e1[0] * -e2[1] + e2[0] * e1[1]
    # 届かない間は2本の靭帯の線が平行になる。DGと同じく分母を 1e-9 にする(交点は遠くへ飛ぶ)。
    if abs(determinant) < 1e-9:
        determinant = 1e-9
    t = ((PCL_FEMUR[0] - ACL_FEMUR[0]) * -e2[1] + e2[0] * (PCL_FEMUR[1] - ACL_FEMUR[1])) / determinant
    crossing = (ACL_FEMUR[0] + t * e1[0], ACL_FEMUR[1] + t * e1[1])
    return b_point, c_point, excess, crossing, phi


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


def _tibiaGeo(prefix, parent, group):
    """脛骨のローカル(原点が生成時の TIBIA_REST)に脛と脛骨の上面の板を作る。"""
    _box(prefix + "Plateau", (3.4, 0.4, 0.6), group, parent, (0.0, -0.1, -0.4))
    _box(prefix + "Shaft", (1.4, TIBIA_LENGTH, 0.6), group, parent, (-0.1, -TIBIA_LENGTH / 2.0, -0.4))


def buildScene():
    """検証シーンを作り、(panel, シーンの辞書, HUD値, HUD名)を返す。"""
    from maya import cmds
    from mlrig.setups import CrossedKneeLinkage
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="deg", linear="cm", time="film")
    _, green = _shader("linkGreen", (0.15, 0.75, 0.25))
    _, gray = _shader("femurGray", (0.55, 0.56, 0.6))
    _, blue = _shader("hingeBlue", (0.25, 0.45, 0.85))
    _, white = _shader("pointWhite", (0.95, 0.95, 0.95))
    center_shader, red = _shader("centerRed", (0.95, 0.15, 0.15))
    acl_shader, acl_group = _shader("aclGreen", (0.15, 0.75, 0.25))
    femur = cmds.createNode("transform", name="femur")
    _box("femurShaft", (1.8, 8.0, 0.6), gray, femur, (0.0, 5.0, -0.8))
    _ball("femurCondyle", 1.3, gray, femur, (-0.1, 0.6, -0.8))
    points = []
    for label, value in (("aclFemur", ACL_FEMUR), ("aclTibia", ACL_TIBIA), ("pclFemur", PCL_FEMUR),
                         ("pclTibia", PCL_TIBIA)):
        node = cmds.createNode("transform", name=label + "_REST", parent=femur)
        cmds.setAttr(node + ".translate", value[0], value[1], 0)
        points.append(node)
    tibia = cmds.createNode("transform", name="tibia_REST")
    cmds.setAttr(tibia + ".translate", TIBIA_REST[0], TIBIA_REST[1], 0)
    graph = CrossedKneeLinkage.create(femur, tibia, *points, name="crossedKneeLinkage")
    owner = str(graph.container)
    _, _, _, crossing, _ = expected_pose(0.0, ACL, math.atan2(ACL_TIBIA[1] - ACL_FEMUR[1],
                                                                ACL_TIBIA[0] - ACL_FEMUR[0]))
    # 青 = 比較用の単純な蝶番(生成時の瞬間回転中心を固定軸にして同じ角度だけ回す)。
    # 緑 = CrossedKneeLinkageの出力(脛骨と2本の靭帯)。灰 = 固定の大腿骨。赤 = 瞬間回転中心。
    hinge = cmds.createNode("transform", name="hinge_BLUE")
    cmds.setAttr(hinge + ".translate", crossing[0], crossing[1], 0)
    hinge_child = cmds.createNode("transform", name="hingeTibia", parent=hinge)
    cmds.setAttr(hinge_child + ".translate", TIBIA_REST[0] - crossing[0], TIBIA_REST[1] - crossing[1], -0.8)
    _tibiaGeo("hinge", hinge_child, blue)
    tibia_out = cmds.createNode("transform", name="tibia_GREEN")
    _tibiaGeo("tibia", tibia_out, green)
    cmds.connectAttr(owner + ".tibiaMatrix", tibia_out + ".offsetParentMatrix")
    ligaments = {}
    for role, group in (("acl", acl_group), ("pcl", green)):
        node = cmds.createNode("transform", name=role + "_GREEN")
        geo = _box(role + "Geo", (1.0, 0.22, 0.22), group, node, (0.5, 0, 0.6))
        cmds.connectAttr(owner + ".{}Matrix".format(role), node + ".offsetParentMatrix")
        ligaments[role] = geo
    for label, value in (("aclFemurGeo", ACL_FEMUR), ("pclFemurGeo", PCL_FEMUR)):
        _ball(label, 0.22, white, None, (value[0], value[1], 0.8))
    center = cmds.createNode("transform", name="instantCenter_RED")
    _ball("centerGeo", 0.3, red, center, (0, 0, 1.0))
    cmds.connectAttr(owner + ".instantCenterMatrix", center + ".offsetParentMatrix")
    camera, camera_shape = cmds.camera(name="kneeCamera", focalLength=35)
    cmds.viewPlace(camera_shape, eye=(-1.5, -4.8, 48.0), lookAt=(-1.5, -4.8, 0))
    window = cmds.window("kneeValidationWindow", title="CrossedKneeLinkage - knee with crossed ligaments",
                         widthHeight=(1280, 760))
    pane = cmds.paneLayout(configuration="single")
    panel = cmds.modelPanel("kneeValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True,
                     manipulators=False, locators=False)
    cmds.showWindow(window)
    # 初回起動の隔離環境では寸法が縮むことがあるため、表示後に指定し直す。
    cmds.window(window, edit=True, widthHeight=(1280, 760), topLeftCorner=(40, 40))
    cmds.refresh(force=True)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    values, names = _hud("knee", 7)
    scene = {"owner": owner, "femur": femur, "hinge": hinge, "ligaments": ligaments, "aclShader": acl_shader,
             "phi": math.atan2(ACL_TIBIA[1] - ACL_FEMUR[1], ACL_TIBIA[0] - ACL_FEMUR[0])}
    return panel, scene, values, names


def evaluate_frame(frame, scene, values, names):
    """入力を更新し、脛骨・靭帯・瞬間回転中心を独立計算と、靭帯の長さ・届かない量と比べた診断を返す。"""
    from maya import cmds
    import maya.api.OpenMaya as om
    flexion, acl, stage = pose(frame)
    owner = scene["owner"]
    cmds.setAttr(owner + ".flexion", flexion)
    cmds.setAttr(owner + ".aclLength", acl)
    cmds.setAttr(scene["hinge"] + ".rotateZ", -flexion)
    b_expected, c_expected, expected_excess, crossing, phi = expected_pose(flexion, acl, scene["phi"])
    # 届かない間は枝の追跡を止め、届く範囲へ戻ったら直前の届いた姿勢から続ける。
    if expected_excess == 0.0:
        scene["phi"] = phi
    for role, length in (("acl", acl), ("pcl", PCL)):
        geo = scene["ligaments"][role]
        cmds.setAttr(geo + ".scaleX", length)
        cmds.setAttr(geo + ".translateX", length / 2.0)
    tibia = om.MMatrix(cmds.getAttr(owner + ".tibiaMatrix"))
    rest_b = om.MPoint(ACL_TIBIA[0] - TIBIA_REST[0], ACL_TIBIA[1] - TIBIA_REST[1], 0) * tibia
    rest_c = om.MPoint(PCL_TIBIA[0] - TIBIA_REST[0], PCL_TIBIA[1] - TIBIA_REST[1], 0) * tibia
    center_matrix = om.MMatrix(cmds.getAttr(owner + ".instantCenterMatrix"))
    center = om.MPoint(center_matrix[12], center_matrix[13], center_matrix[14])
    b_error = (rest_b - om.MPoint(b_expected[0], b_expected[1], 0)).length()
    c_error = (rest_c - om.MPoint(c_expected[0], c_expected[1], 0)).length()
    center_error = (center - om.MPoint(crossing[0], crossing[1], 0)).length()
    excess = cmds.getAttr(owner + ".excess")
    acl_distance = (rest_b - om.MPoint(ACL_FEMUR[0], ACL_FEMUR[1], 0)).length()
    pcl_distance = (rest_c - om.MPoint(PCL_FEMUR[0], PCL_FEMUR[1], 0)).length()
    aim = om.MMatrix(cmds.getAttr(owner + ".aclMatrix"))
    toward = (rest_b - om.MPoint(ACL_FEMUR[0], ACL_FEMUR[1], 0)).normal()
    aim_error = 1.0 - om.MVector(aim[0], aim[1], aim[2]).normal() * toward
    slide = math.hypot(rest_b.x - ACL_TIBIA[0], rest_b.y - ACL_TIBIA[1])
    out = expected_excess > 1e-9
    cmds.setAttr(scene["aclShader"] + ".color", *((0.95, 0.15, 0.15) if out else (0.15, 0.75, 0.25)),
                 type="double3")
    v = _rotate((PCL_TIBIA[0] - ACL_TIBIA[0], PCL_TIBIA[1] - ACL_TIBIA[1]), flexion)
    d = math.hypot(PCL_FEMUR[0] - v[0] - ACL_FEMUR[0], PCL_FEMUR[1] - v[1] - ACL_FEMUR[1])
    values[:] = [
        "GREEN = CrossedKneeLinkage (tibia, ACL, PCL)   BLUE = fixed-axis hinge (same angle)   GRAY = femur   "
        "RED = instant center",
        "STAGE: " + stage + ("   >>> OUT OF REACH: ACL RED <<<" if out else ""),
        "fixed (cm): A = (-1.0, 0.5)  D = (0.8, 0.8)  B0 = (1.2, -2.5)  C0 = (-1.5, -2.8)  pclLength p = 4.27  "
        "n = -Z",
        "v = (C0 - B0) R(theta)   B = circle(A, a) x circle(D - v, p)   C = B + v   ICR = line AB x line DC   "
        "excess = max(d-(a+p), |a-p|-d, 0)",
        "INPUT flexion theta = {:7.2f} deg   aclLength a = {:5.2f} cm   d = |D - v - A| = {:6.3f} cm".format(
            flexion, acl, d),
        "OUTPUT B = ({:6.3f}, {:6.3f})  ICR = {}  |B-A| = {:5.3f}  |C-D| = {:5.3f}  "
        "slide |B-B0| = {:5.3f}  excess = {:5.3f} cm".format(
            rest_b.x, rest_b.y, "(parallel: none)" if out else "({:6.3f}, {:6.3f})".format(center.x, center.y),
            acl_distance, pcl_distance, slide, excess),
        "CHECK |B - scan| = {:.7f}  |C - scan| = {:.7f}  |ICR - lines| = {}  |excess - formula| = {:.7f} cm"
        .format(b_error, c_error, "n/a" if out else "{:.7f}".format(center_error), abs(excess - expected_excess)),
    ]
    for hud in names:
        cmds.headsUpDisplay(hud, refresh=True)
    ok = (b_error < 1e-4 and c_error < 1e-4 and abs(excess - expected_excess) < 1e-4 and aim_error < 1e-6
          and abs(acl_distance - acl) < 1e-4 and (out or (abs(pcl_distance - PCL) < 1e-4
                                                     and center_error < 1e-3 * max(1.0, math.hypot(*crossing)))))
    return {"frame": frame, "presentation_stage": stage, "input": {"flexion": flexion, "aclLength": acl},
            "b_error": b_error, "c_error": c_error, "center_error": center_error, "excess": excess,
            "expected_excess": expected_excess, "instant_center": [center.x, center.y], "slide": slide,
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
        folder = recordVideo("CrossedKneeLinkage: 交差する靭帯の膝", frames, 24, panel,
                             lambda frame: evaluate_frame(frame, scene, values, names),
                             ffmpeg=ffmpeg, width=1280, height=720)
        record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        cmds.file(rename=str(folder / "crossed_knee_linkage.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output/verification/latest-crossed-knee-linkage.json").write_text(
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
    directory = ROOT / ".maya-output/verification-gui" / datetime.now().strftime("crossed-knee-linkage-%Y%m%d-%H%M%S")
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
