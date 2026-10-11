"""ConeReader の出力(0〜1)を UE RBF のドライバーにして、尻尾1軸回避を検証する。

シーンは demo_joint_chain_rbf と同じチェーン(hip〜l_lowerArm)と3つの球、複雑な動き。

- A(幾何ドライバー): 球から求めた折り返さない相対角 rel と半幅 H を RBF のドライバーにする。
- D(ConeReader ドライバー): 尻尾の入力の向き(ローカルY)を矢印にした ConeReader を3つ置き、
  その weight(0〜1)の3つだけを RBF のドライバーにする。コーンは胸(spine2)に追従させ、
  1フレーム目の姿勢で、体の中心方向(半角 H+20)、+側の接線方向(半角80)、-側の接線方向
  (半角80)へ向ける。左右のコーンは中心まで重ねないと、中心の左右で3つの weight が同じに
  なり補正が平均されて0になる(半角30では1フレーム目で最大70度ずれた)。RBFのポーズは、1フレーム目の姿勢で尻尾を5度刻みで一周させ、
  各向きの3つの weight と、接線で止めるための補正量(出力-入力)を組にして作る。

D は向きだけの 0〜1 を見るので、左右と「どちらから入ったか」を区別できない。
体の中心付近で補正の向きが入れ替わること(フリップ)と、1フレーム目以外の姿勢での
食い込み・Aとの差を録画で確かめる。リグは標準ノード・ConeReader・UERBFSolverNode。
"""

import json
import math
import os
from pathlib import Path

from maya import cmds
import maya.api.OpenMaya as om
from mlib import logger
from mlrig.setups import ConeReader
from demo_top_view_moving_tangent import _node, _connect
from demo_joint_twist_tangent import _sum, _multiply, _condition, _degrees
from demo_joint_sweep_compare import _divide, _clampRange, _tail
import demo_joint_chain_rbf as chain
import demo_joint_rbf_pose
from verification_video import recordVideo
import demo_interactive

WINDOW = "coneRbfWindow"
PANEL = "coneRbfPanel"
SAMPLE_STEP = 5
RBF_RADIUS = 0.1
SIDE_CONE = 80.0
CENTER_MARGIN = 20.0
METHODS = [
    ("input", "INPUT (red)", "chain + 3 body spheres", None),
    ("geo", "A: RBF driven by (rel, H)", "geometry angles, keeps entry side", (1, 0.5, 0.1)),
    ("cone", "D: RBF driven by 3 ConeReader weights", "(w_center, w_plus, w_minus), 0-1 each", (0.1, 1, 0.1)),
]
CONES = (("center", 0), ("plus", 1), ("minus", -1))


def _tailDirection(arm_matrix, rx):
    """前腕の行列と rotateX(度)から、尻尾(ローカルY)のワールド方向。"""
    local = om.MVector(0, math.cos(math.radians(rx)), math.sin(math.radians(rx)))
    return (local*arm_matrix).normal()


def main(record=True):
    """専用GUIで3列を同じ入力で動かし、正面から録画して検査する。

    Args:
        record (bool): False なら録画せず、タイムラインで確認できるシーンを作る。
    """
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    plugin = str(demo_joint_rbf_pose.PLUGIN).format(cmds.about(majorVersion=True))
    if not cmds.pluginInfo("MayaUERBFPlugin", query=True, loaded=True):
        cmds.loadPlugin(plugin)
    if PANEL in cmds.getPanel(allPanels=True):
        cmds.deleteUI(PANEL, panel=True)
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW, window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")

    material = cmds.shadingNode("lambert", asShader=True, name="bodyProxyMaterial")
    cmds.setAttr(material+".color", 0.18, 0.22, 0.28, type="double3")
    cmds.setAttr(material+".transparency", 0.55, 0.55, 0.55, type="double3")
    material_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    _connect(material+".outColor", material_group+".surfaceShader")
    rigs = {key: chain._buildRig(key, i, material_group, chain.BODY, len(METHODS))
            for i, (key, _, _, _) in enumerate(METHODS)}
    input_geometry = chain._buildGeometry("input", rigs["input"])
    geometry = chain._buildGeometry("geo", rigs["geo"], soft=True)
    geo_plug, geo_solver, geo_grid = chain._buildRbf("geo", geometry)
    outputs = {"geo": chain._finish("geo", rigs["geo"], geometry, geo_plug, METHODS[1][3])}

    # 体と腕の動き、尻尾の入力(チェーンのデモと同じ)。
    count = (len(chain.INPUT)-1)*chain.SEGMENT_FRAMES+1
    for rig in rigs.values():
        for joint, attr, amplitude, period, phase, offset in chain.MOTION:
            for frame in range(0, count, 3):
                value = offset+amplitude*math.sin(2*math.pi*frame/period+phase)
                cmds.setKeyframe(rig["joints"][joint], attribute=attr, time=frame+1, value=value)
    stages = []
    for frame in range(count):
        phase = frame/chain.SEGMENT_FRAMES
        index = min(int(phase), len(chain.INPUT)-2)
        w = phase-index
        w = w*w*(3-2*w)
        rel = chain.INPUT[index][0]+(chain.INPUT[index+1][0]-chain.INPUT[index][0])*w
        stages.append(chain.INPUT[index][1] if frame else chain.INPUT[0][1])
        outward = cmds.getAttr(input_geometry["outward"], time=frame+1)
        for rig in rigs.values():
            cmds.setKeyframe(rig["source"], attribute="rx", time=frame+1, value=outward+rel)
    cmds.playbackOptions(minTime=1, maxTime=count)

    # D: 1フレーム目の姿勢で、3つの ConeReader のコーンを体の中心と左右の接線へ向ける。
    cmds.currentTime(1)
    rig = rigs["cone"]
    outward, half, _ = chain.referenceGeometry(rig)
    limit = 180-half
    arm_matrix = om.MMatrix(cmds.xform(rig["joints"]["l_lowerArm"], query=True, worldSpace=True, matrix=True))
    readers, cone_dirs, cone_angles = {}, {}, {}
    for label, side in CONES:
        rx = outward+180 if side == 0 else outward+side*limit
        direction = _tailDirection(arm_matrix, rx)
        angle = half+CENTER_MARGIN if side == 0 else SIDE_CONE
        reader = ConeReader.create(driverJoint=rig["source"], coneJoint=rig["joints"]["spine2"],
                                   name="d"+label.capitalize(), coneAngle=angle, driverAxis="y", size=3)
        euler = om.MVector(1, 0, 0).rotateTo(direction).asEulerRotation()
        cmds.xform(reader.cone, worldSpace=True, rotation=[math.degrees(v) for v in (euler.x, euler.y, euler.z)])
        readers[label], cone_dirs[label], cone_angles[label] = reader, direction, angle

    # D のポーズ: 尻尾を一周させ、3つの weight と接線で止める補正量を組にする。
    samples = []
    for step in range(-180, 180, SAMPLE_STEP):
        direction = _tailDirection(arm_matrix, outward+step)
        weights = tuple(ConeReader.weight(math.degrees(direction.angle(cone_dirs[label])), cone_angles[label])
                        for label, _ in CONES)
        target = step if abs(step) <= limit else math.copysign(limit, step)
        samples.append((weights, target-step))
    driver = _node("composeMatrix", "coneDriver")
    for (label, _), axis in zip(CONES, "XYZ"):
        _connect(readers[label].container.getFullName()+".weight", driver+".inputTranslate"+axis)
    solver = _node("UERBFSolverNode", "conePoseSolver", mode=0, inputMode=0, distanceMethod=0, functionType=0,
                   normalizeMethod=1, automaticRadius=False, radius=RBF_RADIUS)
    _connect(driver+".outputMatrix", solver+".inputs[0]")
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    cmds.setAttr(solver+".inputsRest[0]", identity, type="matrix")
    blend = _node("plusMinusAverage", "conePoseBlendSum")
    total = _node("plusMinusAverage", "coneWeightSum")
    for i, (weights, offset) in enumerate(samples):
        cmds.setAttr(solver+".targets[{}].targetValues[0]".format(i), identity[:12]+list(weights)+[1],
                     type="matrix")
        weighted = _node("multDoubleLinear", "conePose{}".format(i), input2=offset)
        _connect(solver+".outputs[{}]".format(i), weighted+".input1")
        _connect(weighted+".output", blend+".input1D[{}]".format(i))
        _connect(solver+".outputs[{}]".format(i), total+".input1D[{}]".format(i))
    offset_plug = _divide("conePoseBlend", blend+".output1D",
                          _clampRange("coneWeightSumSafe", total+".output1D", 1e-6, 1e9))
    # どのポーズからも遠く重みの合計がほぼ0なら、割り算が不安定になるので補正しない。
    offset_plug = _condition("coneWeightGuard", total+".output1D", 0.01, offset_plug, 0)
    output = _tail("coneTailOutput_JNT", METHODS[2][3], rig["joints"]["l_lowerArm"])
    corrected = _sum("coneWorld", (_degrees("coneRequested", rig["source"]+".rx"), offset_plug))
    radians = _node("unitConversion", "coneRadians", conversionFactor=math.pi/180)
    _connect(corrected, radians+".input")
    _connect(radians+".output", output+".rx")
    for attr in ("ry", "rz"):
        cmds.setAttr(output+"."+attr, lock=True)
    outputs["cone"] = output

    camera, camera_shape = cmds.camera(name="coneRbfCamera", orthographic=True)
    cmds.setAttr(camera+".translate", 0, 12.5, 60)
    cmds.setAttr(camera_shape+".orthographicWidth", chain.SPACING*len(METHODS))
    if cmds.windowPref(WINDOW, exists=True):
        cmds.windowPref(WINDOW, remove=True)
    window = cmds.window(WINDOW, widthHeight=(1800, 760))
    pane = cmds.paneLayout(parent=window)
    panel = cmds.modelPanel(PANEL, parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", grid=False, cameras=False,
                     joints=True, headsUpDisplay=True, manipulators=False, selectionHiliteDisplay=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1800, 760))
    cmds.setFocus(panel)
    cmds.select(clear=True)
    demo_interactive.clearHuds(window)
    texts = {}
    for column, section in enumerate((0, 2, 4)):
        for row in range(3):
            for prefix, base, block in (("coneRbfTop", section, row), ("coneRbfBottom", section+5, 2-row)):
                name = "{}{}_{}".format(prefix, column, row)
                texts[name] = ""
                cmds.headsUpDisplay(name, section=base, block=block, blockSize="large", dataFontSize="large",
                                    command=lambda n=name: texts[n])

    last = {"geo": None, "cone": None}
    flash = {"geo": -1, "cone": -1}

    def penetration(rig, joint):
        """リグに接続しない線分と球の交差検査。最も深い食い込み(cm)。交差しなければ0。"""
        m = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
        deepest = 0.0
        for ball, radius in rig["balls"]:
            c = cmds.xform(ball, query=True, worldSpace=True, translation=True)
            o = [a-b for a, b in zip(m[12:15], c)]
            t = max(0, min(chain.LENGTH, -sum(a*b for a, b in zip(o, m[4:7]))))
            deepest = max(deepest, radius-math.sqrt(sum((a+t*b)**2 for a, b in zip(o, m[4:7]))))
        return deepest

    def evaluate(frame):
        """両列の出力・食い込み・変化量と、D の weight・補正量を記録する。"""
        demo_interactive.setTime(frame)
        requested = cmds.getAttr(rigs["input"]["source"]+".rx")
        ref_outward, ref_half, active = chain.referenceGeometry(rigs["input"])
        rel = requested-ref_outward if ref_outward is not None else None
        result = {"frame": frame, "stage": stages[frame], "requested_degrees": requested,
                  "relative_degrees": rel, "half_width_degrees": ref_half,
                  "input_penetration_cm": penetration(rigs["input"], rigs["input"]["source"])}
        lines = {}
        for key in ("geo", "cone"):
            actual = cmds.getAttr(outputs[key]+".rx")
            depth = penetration(rigs[key], outputs[key])
            step = abs((actual-last[key]+180) % 360-180) if last[key] is not None else 0.0
            last[key] = actual
            if step > 15:
                flash[key] = frame+24
            result[key] = {"output_degrees": actual, "penetration_cm": depth, "step_degrees": step}
            lines[key] = ("BODY HIT {:.2f}cm".format(depth) if depth > 0 else "clear") \
                + "  step {:.1f}".format(step) + ("  JUMP!" if frame <= flash[key] else "")
        weights = [cmds.getAttr(readers[label].container.getFullName()+".weight") for label, _ in CONES]
        offset = cmds.getAttr(outputs["cone"]+".rx")-requested
        result["cone"].update({"cone_weights": weights, "offset_degrees": offset})
        geo_weights = [cmds.getAttr(geo_solver+".outputs[{}]".format(i)) for i in range(len(geo_grid))]
        cone_weights = [cmds.getAttr(solver+".outputs[{}]".format(i)) for i in range(len(samples))]
        result["geo"]["weight_sum"] = sum(geo_weights)
        result["cone"]["weight_sum"] = sum(cone_weights)
        result["output_difference_degrees"] = abs(((result["cone"]["output_degrees"]
                                                    - result["geo"]["output_degrees"])+180) % 360-180)
        # A は保証として非交差、D は記録のみ。両方とも RBF の重みが出ていることを確かめる。
        result["cone"]["unseen_pose"] = sum(cone_weights) <= 0.01
        # A は保証として非交差と重みの合計を検査する。D は食い込み・跳び・未学習の姿勢を記録のみ。
        result["ok"] = result["geo"]["penetration_cm"] <= 0 and abs(sum(geo_weights)-1) < 0.05
        texts["coneRbfTop0_0"], texts["coneRbfTop0_1"] = METHODS[0][1], METHODS[0][2]
        texts["coneRbfTop0_2"] = "rel={}  H={:.1f}  L={:.1f}".format(
            "{:+.1f}".format(rel) if rel is not None else "-", ref_half, 180-ref_half)
        texts["coneRbfBottom0_0"] = "BODY HIT" if result["input_penetration_cm"] > 0 else "clear"
        texts["coneRbfBottom0_1"] = "D cones follow spine2, aimed at frame 1"
        texts["coneRbfBottom0_2"] = stages[frame]
        texts["coneRbfTop1_0"], texts["coneRbfTop1_1"] = METHODS[1][1], METHODS[1][2]
        texts["coneRbfTop1_2"] = "output - input = {:+.1f}".format(
            ((result["geo"]["output_degrees"]-requested+180) % 360)-180)
        texts["coneRbfBottom1_0"] = lines["geo"]
        texts["coneRbfBottom1_1"] = ""
        texts["coneRbfBottom1_2"] = ""
        texts["coneRbfTop2_0"], texts["coneRbfTop2_1"] = METHODS[2][1], METHODS[2][2]
        texts["coneRbfTop2_2"] = "w = {:.2f} / {:.2f} / {:.2f}".format(*weights)
        texts["coneRbfBottom2_0"] = lines["cone"]
        texts["coneRbfBottom2_1"] = "output - input = {:+.1f}".format(offset)
        texts["coneRbfBottom2_2"] = "diff from A = {:.1f}{}".format(
            result["output_difference_degrees"],
            "  UNSEEN POSE (no correction)" if result["cone"]["unseen_pose"] else "")
        for name in texts:
            cmds.headsUpDisplay(name, refresh=True)
        return result

    if not record:
        demo_interactive.attachInteractive(window, count, evaluate, [(last, None), (flash, -1)])
        logger.info("ConeReaderドライバーのRBFシーンを作成しました。タイムラインで確認できます。")
        return
    folder = recordVideo("尻尾1軸回避: ConeReaderの0〜1をRBFのドライバーにする（幾何ドライバーとの比較）",
                         count, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1800, height=760)
    cmds.file(rename=str(folder/"cone-rbf.ma"))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-cone-rbf.json").write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("ConeReaderドライバーの検証に失敗: {}".format(folder))
    logger.info("ConeReaderドライバーの検証を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
