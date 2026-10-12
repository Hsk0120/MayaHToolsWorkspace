"""ConeReader 2つと UE RBF だけで尻尾1軸回避を組む簡易版を、今の仕組みと比べる。

シーン・動き・尻尾の入力は demo_joint_chain_rbf の case="mixed" と同じ。

- 今の仕組み(rbf): 球から rel・H を計算し、385ポーズの UE RBF でなだらかに避ける。
- 簡易版(simple):
  1. 肘に置いたグループを、お腹(spine1)の球の中心へ aimConstraint で向ける(上方向は前腕のX軸)。
  2. そのグループに ConeReader を2つ付ける。矢印は尻尾の入力の向き(ローカルY)、コーンは体の
     方向から前腕の軸まわりに ±35度ずらし、半角は65度。
  3. 2つの weight(0〜1)をドライバージョイントの translateX/Y に入れて UE RBF に渡す。
  4. ポーズは23個。1フレーム目の姿勢で尻尾をいくつかの向きに向け、2つの weight と、近い方の
     接線の少し手前まで押し戻す角度(出力-入力)を組にする。RBF の半径は0.2。
  5. 出力は Pose Editor で編集できる形(ドリブンジョイント+UEPoseBlenderNode)。尻尾の出力は
     入力 + ドリブンの rotateX。

簡易版は「今どちらに近いか」しか分からないので、体の中心を越えるとフリップし、コーンの角度と
ポーズは1フレーム目の姿勢で決めたままなので、肘と体の距離が変わると止まる位置がずれる。
それを録画で確かめる。リグは標準ノード・ConeReader・UERBFSolverNode。
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
from demo_joint_twist_tangent import _degrees
from demo_joint_sweep_compare import _tail
import demo_joint_chain_rbf as chain
import demo_joint_rbf_pose
from verification_video import recordVideo
import demo_interactive

WINDOW = "chainRbfWindow"
PANEL = "chainRbfPanel"
CONE_OFFSET = 35.0
CONE_ANGLE = 65.0
RBF_RADIUS = 0.2
# ポーズを置く尻尾の向き。外向きからの角度(度)。体の中心寄り(90〜180)は10度刻み。
SAMPLE_RELS = (0, 60, -60) + tuple(s*r for r in range(90, 181, 10) for s in (1, -1) if not (r == 180 and s < 0))
# 中心を越えない入力。接線(約130度)の先の体の手前までは入れるが、±180度は越えない。
INPUT_NO_CROSS = [
    (-40, "1 INITIAL"), (-40, "2 TOWARD BODY FROM +"), (100, "2 TOWARD BODY FROM +"), (160, "2 TOWARD BODY FROM +"),
    (160, "3 HOLD (BODY MOVES)"), (165, "3 HOLD (BODY MOVES)"), (150, "3 HOLD (BODY MOVES)"), (165, "3 HOLD (BODY MOVES)"),
    (100, "4 BACK"), (-40, "4 BACK"), (-40, "5 TOWARD BODY FROM -"), (-100, "5 TOWARD BODY FROM -"),
    (-160, "5 TOWARD BODY FROM -"), (-160, "6 HOLD (BODY MOVES)"), (-150, "6 HOLD (BODY MOVES)"),
    (-165, "6 HOLD (BODY MOVES)"), (-150, "6 HOLD (BODY MOVES)"), (-40, "7 RETURN"),
]
# 入力の種類 → (尻尾の入力, 録画の題名, 保存名)
INPUTS = {
    "mixed": (None, "尻尾1軸回避: ConeReader×2＋UE RBFの簡易版（今の仕組みとの比較）", "simple-cone-rbf"),
    "no_cross": (INPUT_NO_CROSS, "尻尾1軸回避: 簡易版（中心を越えない入力）", "simple-cone-rbf-no-cross"),
}
METHODS = [
    ("input", "INPUT (red)", "hip/spine0-2/shoulder/upperArm/lowerArm", None, "input"),
    ("rbf", "CURRENT: rel/H + 385 poses", "keeps entry side, tangent from spheres", (1, 0.5, 0.1), "rbf"),
    ("simple", "SIMPLE: 2 ConeReaders + RBF", "{} poses, cones +/-35 deg, 65 deg wide".format(len(SAMPLE_RELS)+1),
     (0.1, 1, 0.1), "simple"),
]


def _tailDirection(arm_matrix, rx):
    """前腕の行列と rotateX(度)から、尻尾(ローカルY)のワールド方向。"""
    return (om.MVector(0, math.cos(math.radians(rx)), math.sin(math.radians(rx)))*arm_matrix).normal()


def _buildSimple(rig, color):
    """簡易版のコーン・RBF・ドリブン・出力を作る。1フレーム目で呼ぶ。

    Returns:
        dict: readers, solver, poses, output, driver。
    """
    arm = rig["joints"]["l_lowerArm"]
    belly = [ball for ball, _ in rig["balls"] if "belly" in ball][0]
    aim = cmds.createNode("transform", name="simpleBodyAim_GRP", parent=rig["group"])
    cmds.pointConstraint(arm, aim)
    cmds.aimConstraint(belly, aim, aimVector=(1, 0, 0), upVector=(0, 0, 1), worldUpType="objectrotation",
                       worldUpObject=arm, worldUpVector=(1, 0, 0))
    readers = []
    for label, sign in (("A", 1), ("B", -1)):
        reader = ConeReader.create(driverJoint=rig["source"], coneJoint=aim, name="simpleCone"+label,
                                   coneAngle=CONE_ANGLE, driverAxis="y", size=3)
        cmds.setAttr(reader.cone+".rotate", 0, 0, sign*CONE_OFFSET)
        readers.append(reader)

    # ドライバージョイント: translate = (weightA, weightB)。
    driver = cmds.createNode("joint", name="simpleRbfDriver_JNT", parent=rig["group"])
    cmds.setAttr(driver+".translate", 0, 0, 0)
    for reader, axis in zip(readers, "XY"):
        _connect(reader.container.getFullName()+".weight", driver+".translate"+axis)
    cmds.setAttr(driver+".visibility", False)
    solver = _node("UERBFSolverNode", "simplePoseSolver", mode=0, inputMode=0, distanceMethod=0, functionType=0,
                   normalizeMethod=1, automaticRadius=False, radius=RBF_RADIUS)
    _connect(driver+".matrix", solver+".inputs[0]")
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    cmds.setAttr(solver+".inputsRest[0]", identity, type="matrix")

    # ポーズ: 1フレーム目の姿勢で、尻尾を外向きから rel 回したときの2つの weight と、近い方の接線までの補正量。
    outward, half, _ = chain.referenceGeometry(rig)
    limit = 180-half
    arm_matrix = om.MMatrix(cmds.xform(arm, query=True, worldSpace=True, matrix=True))
    axes = [om.MVector(*cmds.xform(r.cone, query=True, worldSpace=True, matrix=True)[0:3]).normal() for r in readers]
    poses = [((0.0, 0.0), 0.0, "outside")]
    for rel in SAMPLE_RELS:
        direction = _tailDirection(arm_matrix, outward+rel)
        weights = tuple(ConeReader.weight(math.degrees(direction.angle(axis)), CONE_ANGLE) for axis in axes)
        # 今の仕組みと同じく、接線の少し手前でなだらかに止める値にする(接線ちょうどだと補間で行き過ぎる)。
        target = chain.poseValue(rel if rel != 180 else 180, half)
        poses.append((weights, target-rel, "rel{:+04d}".format(rel)))
    for i, (weights, offset, name) in enumerate(poses):
        cmds.setAttr(solver+".targets[{}].targetValues[0]".format(i), identity[:12]+[weights[0], weights[1], 0, 1],
                     type="matrix")
        cmds.setAttr(solver+".targets[{}].targetName".format(i), name, type="string")

    # 出力: 入力の角度で回るグループの中のドリブンジョイントを、ポーズの補正量で回す(Pose Editor 互換)。
    requested = _degrees("simpleRequested", rig["source"]+".rx")
    driven = chain._buildPoseBlender("simple", rig, None, solver, [offset for _, offset, _ in poses], angle=requested)
    output = _tail("simpleTailOutput_JNT", color, arm)
    total = _node("plusMinusAverage", "simpleWorld")
    _connect(requested, total+".input1D[0]")
    _connect(_degrees("simpleDrivenDegrees", driven+".rotateX"), total+".input1D[1]")
    radians = _node("unitConversion", "simpleRadians", conversionFactor=math.pi/180)
    _connect(total+".output1D", radians+".input")
    _connect(radians+".output", output+".rx")
    for attr in ("ry", "rz"):
        cmds.setAttr(output+"."+attr, lock=True)
    return {"readers": readers, "solver": solver, "poses": poses, "output": output, "driver": driver}


def main(record=True, inputs="mixed"):
    """専用GUIで3列を同じ入力で動かし、正面から録画して検査する。

    Args:
        record (bool): False なら録画せず、タイムラインで確認できるシーンを作る。
        inputs (str): "mixed" は中心を何度も越える入力、"no_cross" は中心を越えない入力。
    """
    profile, title, save_name = INPUTS[inputs]
    profile = profile or chain.INPUT
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
            for i, (key, *_) in enumerate(METHODS)}
    input_geometry = chain._buildGeometry("input", rigs["input"])
    geometry = chain._buildGeometry("rbf", rigs["rbf"], soft=True)
    rbf_plug, rbf_solver, rbf_grid = chain._buildRbf("rbf", geometry, rigs["rbf"])
    outputs = {"rbf": chain._finish("rbf", rigs["rbf"], geometry, rbf_plug, METHODS[1][3])}

    count = (len(profile)-1)*chain.SEGMENT_FRAMES+1
    for rig in rigs.values():
        for joint, attr, amplitude, period, phase, offset in chain.MOTION:
            for frame in range(0, count, 3):
                value = offset+amplitude*math.sin(2*math.pi*frame/period+phase)
                cmds.setKeyframe(rig["joints"][joint], attribute=attr, time=frame+1, value=value)
    stages = []
    for frame in range(count):
        phase = frame/chain.SEGMENT_FRAMES
        index = min(int(phase), len(profile)-2)
        w = phase-index
        w = w*w*(3-2*w)
        rel = profile[index][0]+(profile[index+1][0]-profile[index][0])*w
        stages.append(profile[index][1] if frame else profile[0][1])
        outward = cmds.getAttr(input_geometry["outward"], time=frame+1)
        for rig in rigs.values():
            cmds.setKeyframe(rig["source"], attribute="rx", time=frame+1, value=outward+rel)
    cmds.playbackOptions(minTime=1, maxTime=count)
    cmds.currentTime(1)
    simple = _buildSimple(rigs["simple"], METHODS[2][3])
    outputs["simple"] = simple["output"]

    camera, camera_shape = cmds.camera(name="simpleConeCamera", orthographic=True)
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
            for prefix, base, block in (("chainTop", section, row), ("chainBottom", section+5, 2-row)):
                name = "{}{}_{}".format(prefix, column, row)
                texts[name] = ""
                cmds.headsUpDisplay(name, section=base, block=block, blockSize="large", dataFontSize="large",
                                    command=lambda n=name: texts[n])

    last = {"rbf": None, "simple": None}
    flash = {"rbf": -1, "simple": -1}

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
        """両列の出力・食い込み・変化量と、簡易版のコーンの値を記録する。"""
        demo_interactive.setTime(frame)
        requested = cmds.getAttr(rigs["input"]["source"]+".rx")
        outward, half, _ = chain.referenceGeometry(rigs["input"])
        rel = requested-outward if outward is not None else None
        result = {"frame": frame, "stage": stages[frame], "requested_degrees": requested, "relative_degrees": rel,
                  "half_width_degrees": half,
                  "input_penetration_cm": penetration(rigs["input"], rigs["input"]["source"])}
        lines = {}
        for key in ("rbf", "simple"):
            actual = cmds.getAttr(outputs[key]+".rx")
            depth = penetration(rigs[key], outputs[key])
            step = abs((actual-last[key]+180) % 360-180) if last[key] is not None else 0.0
            last[key] = actual
            if step > 15:
                flash[key] = frame+24
            result[key] = {"output_degrees": actual, "penetration_cm": depth, "step_degrees": step,
                           "relative_output_degrees": actual-outward if outward is not None else None}
            lines[key] = ("BODY HIT {:.2f}cm".format(depth) if depth > 0 else "clear") \
                + "  step {:.1f}".format(step) + ("  JUMP!" if frame <= flash[key] else "")
        weights = [cmds.getAttr(r.container.getFullName()+".weight") for r in simple["readers"]]
        result["simple"]["cone_weights"] = weights
        result["simple"]["offset_degrees"] = cmds.getAttr(outputs["simple"]+".rx")-requested
        rbf_weights = sum(cmds.getAttr(rbf_solver+".outputs[{}]".format(i)) for i in range(len(rbf_grid)))
        simple_weights = sum(cmds.getAttr(simple["solver"]+".outputs[{}]".format(i))
                             for i in range(len(simple["poses"])))
        result["rbf"]["weight_sum"], result["simple"]["weight_sum"] = rbf_weights, simple_weights
        # 今の仕組みは非交差と重みを保証として検査する。簡易版は食い込み・跳びを記録のみ。
        result["ok"] = result["rbf"]["penetration_cm"] <= 0 and abs(rbf_weights-1) < 0.05
        texts["chainTop0_0"], texts["chainTop0_1"] = METHODS[0][1], METHODS[0][2]
        texts["chainTop0_2"] = "rel={}  H={:.1f}".format("{:+.1f}".format(rel) if rel is not None else "-", half)
        texts["chainBottom0_0"] = "BODY HIT" if result["input_penetration_cm"] > 0 else "clear"
        texts["chainBottom0_1"] = "simple: cones follow the belly direction"
        texts["chainBottom0_2"] = stages[frame]
        for column, key in ((1, "rbf"), (2, "simple")):
            texts["chainTop{}_0".format(column)] = METHODS[column][1]
            texts["chainTop{}_1".format(column)] = METHODS[column][2]
            texts["chainTop{}_2".format(column)] = "out rel {}".format(
                "{:+.1f}".format(result[key]["relative_output_degrees"])
                if result[key]["relative_output_degrees"] is not None else "-")
            texts["chainBottom{}_0".format(column)] = lines[key]
            texts["chainBottom{}_1".format(column)] = (
                "cone A {:.2f}  cone B {:.2f}".format(*weights) if key == "simple" else "")
            texts["chainBottom{}_2".format(column)] = (
                "correction {:+.1f}".format(result["simple"]["offset_degrees"]) if key == "simple" else "")
        for name in texts:
            cmds.headsUpDisplay(name, refresh=True)
        return result

    if not record:
        demo_interactive.attachInteractive(window, count, evaluate, [(last, None), (flash, -1)])
        logger.info("簡易版のシーンを作成しました。タイムラインで確認できます。")
        return
    folder = recordVideo(title, count, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1800, height=760)
    cmds.file(rename=str(folder/(save_name+".ma")))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-{}.json".format(save_name)).write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("簡易版の検証に失敗: {}".format(folder))
    logger.info("簡易版の検証を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
