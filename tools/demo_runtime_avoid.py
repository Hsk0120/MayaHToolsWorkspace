"""前腕に固定した尻尾が、腕の動きで体に食い込みそうになったら実行時に自動で避ける(案1の実行時版)。

尻尾はアニメーターが動かさず、前腕に対する元の向き(rotateX = REST_RX = 90)のまま。shoulder・upperArm・
lowerArm(前腕のひねりを含む)が大きく動いて、前腕から見た体の方向が尻尾の向きへ回ってくると、尻尾の
rotateX を回して接線で止め、体に押されるように回す。

案1(plan1)の組み方:
1. 前腕の下のグループを、お腹(spine1)の球へ aimConstraint で +Y を向ける(rotateX だけ。上方向は
   前腕のX軸)。グループの rotateX = 前腕から見た体の方向 θ。外向き = θ + 180。
2. rel = REST_RX - 外向き。尻尾は動かないので、腕が動いて θ が変わると rel が変わる。θ は体が前腕の
   -Y 側へ回り込まない限り連続なので、体が尻尾をはさんで反対側へ回っても rel は数え直されず、
   押されてきた側を保つ。
3. 止める角度は左右で別々(L+ と L-)。体は3つの球の組み合わせで、お腹の方向から見て左右の
   広がりが違うため。どちらも肘とお腹の球の距離からドリブンキーで出す(この動きの距離ごとに、
   お腹の方向から見た塞がれる範囲の端の最大 + 5度)。
4. 尻尾の rotateX = 外向き + clamp(rel, -L-, L+)。体から十分離れていれば REST_RX のまま。

比べる列: 入力(避けない)、今の仕組み(rel・H の計算 + UE RBF。尻尾の入力を REST_RX に固定)、案1。
リグは標準ノード(aimConstraint・distanceBetween・ドリブンキー・plusMinusAverage・clamp)と UE RBF。
"""

import json
import math
import os
from pathlib import Path

from maya import cmds
import maya.api.OpenMaya as om
from mlib import logger
from demo_top_view_moving_tangent import _node, _connect
from demo_joint_twist_tangent import _sum, _multiply, _degrees
from demo_joint_sweep_compare import _tail
import demo_joint_chain_rbf as chain
import demo_joint_rbf_pose
from verification_video import recordVideo
import demo_interactive

WINDOW = "chainRbfWindow"
PANEL = "chainRbfPanel"
# 尻尾の前腕に対する向き。外向き(約180度)から -90度。前腕のひねりで体がこの向きを約40度越える。
REST_RX = 90.0
LIMIT_MARGIN = 5.0
LIMIT_KEYS = 6
SEGMENT_FRAMES = 30
# 腕の動き。前腕のひねり(lowerArm の rotateX)を大きく入れ、体が尻尾の位置を両側から通り過ぎるようにする。
MOTION = [
    ("hip", "ry", 15, 240, 0.0, 0), ("spine0", "rx", 8, 170, 0.5, 0), ("spine0", "rz", 8, 200, 0.0, 0),
    ("spine1", "ry", 10, 260, 1.0, 0), ("spine2", "rz", 6, 150, 2.0, 0),
    ("l_shoulder", "rz", 14, 220, 0.0, 0), ("l_upperArm", "rx", 40, 180, 0.0, 0),
    ("l_upperArm", "rz", 12, 260, 0.0, 20), ("l_lowerArm", "rx", 120, 300, 0.0, -30),
    ("l_lowerArm", "ry", 15, 200, 1.5, 0),
]
COUNT = 18*SEGMENT_FRAMES+1
METHODS = [
    ("input", "INPUT (no avoidance)", "tail fixed to the forearm, rx = 90", None),
    ("rbf", "CURRENT: rel/H + UE RBF", "tail input fixed at rx = 90", (1, 0.5, 0.1)),
    ("plan1", "PLAN 1: aim + driven key + clamp", "rx = outward + clamp(90 - outward, -L-, L+)",
     (0.1, 1, 0.1)),
]


def bodyRange(rig):
    """お腹の方向から見た、3つの球が塞ぐ範囲の両端(度)。リグと独立に行列から求める。

    Returns:
        tuple: (お腹の方向からの下端 a, 上端 b)。交わらなければ None。
    """
    arm = om.MMatrix(cmds.xform(rig["joints"]["l_lowerArm"], query=True, worldSpace=True, matrix=True))
    inverse = arm.inverse()
    lows, highs, belly_theta = [], [], None
    for ball, radius in rig["balls"]:
        c = om.MPoint(*cmds.xform(ball, query=True, worldSpace=True, translation=True))*inverse
        theta = math.degrees(math.atan2(c.z, c.y))
        if "belly" in ball:
            belly_theta = theta
        r2 = (radius+chain.GAP)**2-c.x**2
        if r2 <= 0:
            continue
        rho, d = math.sqrt(r2), math.hypot(c.y, c.z)
        width = math.degrees(math.asin(rho/d)) if d > rho else 90.0
        lows.append(theta-width)
        highs.append(theta+width)
    if not lows:
        return None
    return min(lows)-belly_theta, max(highs)-belly_theta


def _drivenLimit(holder, attr, distance, keys):
    """距離をドライバーにしたドリブンキーで、止める角度のアトリビュートを作る。"""
    cmds.addAttr(holder, longName=attr, attributeType="double", keyable=True)
    for d, value in keys:
        cmds.setDrivenKeyframe(holder+"."+attr, currentDriver=distance+".distance", driverValue=d, value=value,
                               inTangentType="linear", outTangentType="linear")
    return holder+"."+attr


def _buildPlan1(rig, keys, color):
    """案1の実行時版を作る。

    Args:
        keys (dict): "plus"・"minus" それぞれの (距離, 止める角度) の組。

    Returns:
        dict: output, theta(度), relative(度), limitPlus・limitMinus(度)。
    """
    arm = rig["joints"]["l_lowerArm"]
    belly = [ball for ball, _ in rig["balls"] if "belly" in ball][0]
    group = cmds.createNode("transform", name="plan1BodyDirection_GRP", parent=arm)
    cmds.aimConstraint(belly, group, aimVector=(0, 1, 0), upVector=(1, 0, 0), worldUpType="objectrotation",
                       worldUpObject=arm, worldUpVector=(1, 0, 0), skip=("y", "z"))
    theta = _degrees("plan1Theta", group+".rotateX")
    outward = _sum("plan1Outward", (theta,), (180,))
    # rel = REST_RX - 外向き。
    relative = _sum("plan1Relative", (_multiply("plan1NegOutward", outward, constant=-1),), (REST_RX,))
    distance = _node("distanceBetween", "plan1BodyDistance")
    _connect(arm+".worldMatrix[0]", distance+".inMatrix1")
    _connect(belly+".worldMatrix[0]", distance+".inMatrix2")
    holder = cmds.createNode("transform", name="plan1Limit", parent=rig["group"])
    plus = _drivenLimit(holder, "limitPlus", distance, keys["plus"])
    minus = _drivenLimit(holder, "limitMinus", distance, keys["minus"])
    clamp = _node("clamp", "plan1Clamp")
    _connect(relative, clamp+".inputR")
    _connect(plus, clamp+".maxR")
    _connect(_multiply("plan1NegLimit", minus, constant=-1), clamp+".minR")
    world = _sum("plan1World", (outward, clamp+".outputR"))
    output = _tail("plan1TailOutput_JNT", color, arm)
    radians = _node("unitConversion", "plan1Radians", conversionFactor=math.pi/180)
    _connect(world, radians+".input")
    _connect(radians+".output", output+".rx")
    for attr in ("ry", "rz"):
        cmds.setAttr(output+"."+attr, lock=True)
    return {"output": output, "theta": theta, "relative": relative, "limitPlus": plus, "limitMinus": minus}


def main(record=True):
    """専用GUIで3列を同じ腕の動きで動かし、正面から録画して検査する。

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
            for i, (key, *_) in enumerate(METHODS)}
    geometry = chain._buildGeometry("rbf", rigs["rbf"], soft=True)
    rbf_plug, rbf_solver, rbf_grid = chain._buildRbf("rbf", geometry, rigs["rbf"])
    outputs = {"rbf": chain._finish("rbf", rigs["rbf"], geometry, rbf_plug, METHODS[1][3])}
    for rig in rigs.values():
        cmds.setAttr(rig["source"]+".rx", REST_RX)
        for joint, attr, amplitude, period, phase, offset in MOTION:
            for frame in range(0, COUNT, 3):
                value = offset+amplitude*math.sin(2*math.pi*frame/period+phase)
                cmds.setKeyframe(rig["joints"][joint], attribute=attr, time=frame+1, value=value)
    cmds.playbackOptions(minTime=1, maxTime=COUNT)

    # 止める角度のドリブンキー(左右別)。この動きの、肘とお腹の距離ごとに、お腹の方向から見た塞がれる
    # 範囲の端(+側から近づくと下端 a、-側から近づくと上端 b で止まる)の最大から作る。
    # rel = 外向きからの角度なので、+側は L+ = 180 - |a|、-側は L- = 180 - b。
    rig = rigs["plan1"]
    belly = [ball for ball, _ in rig["balls"] if "belly" in ball][0]
    samples = []
    for frame in range(0, COUNT, 3):
        cmds.currentTime(frame+1)
        elbow = om.MVector(*cmds.xform(rig["joints"]["l_lowerArm"], query=True, worldSpace=True, translation=True))
        center = om.MVector(*cmds.xform(belly, query=True, worldSpace=True, translation=True))
        bounds = bodyRange(rig)
        if bounds:
            samples.append(((elbow-center).length(), bounds))
    lo, hi = min(d for d, _ in samples), max(d for d, _ in samples)
    width = (hi-lo)/(LIMIT_KEYS-1)
    keys = {"plus": [], "minus": []}
    for k in range(LIMIT_KEYS):
        d = lo+width*k
        near = [b for dd, b in samples if abs(dd-d) <= width]
        keys["plus"].append((d, 180-(max(-a for a, _ in near)+LIMIT_MARGIN)))
        keys["minus"].append((d, 180-(max(b for _, b in near)+LIMIT_MARGIN)))
    plan1 = _buildPlan1(rig, keys, METHODS[2][3])
    outputs["plan1"] = plan1["output"]

    camera, camera_shape = cmds.camera(name="runtimeAvoidCamera", orthographic=True)
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

    last = {"rbf": None, "plan1": None}
    flash = {"rbf": -1, "plan1": -1}

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
        """各列の食い込み・変化量と、案1の rel・L を記録する。"""
        demo_interactive.setTime(frame)
        outward, half, _ = chain.referenceGeometry(rigs["input"])
        rel = REST_RX-outward if outward is not None else None
        result = {"frame": frame, "relative_degrees": rel, "half_width_degrees": half,
                  "input_penetration_cm": penetration(rigs["input"], rigs["input"]["source"]),
                  "plan1_relative_degrees": cmds.getAttr(plan1["relative"]),
                  "plan1_limit_plus_degrees": cmds.getAttr(plan1["limitPlus"]),
                  "plan1_limit_minus_degrees": cmds.getAttr(plan1["limitMinus"]),
                  "plan1_theta_degrees": cmds.getAttr(plan1["theta"])}
        lines = {}
        for key in ("rbf", "plan1"):
            actual = cmds.getAttr(outputs[key]+".rx")
            depth = penetration(rigs[key], outputs[key])
            step = abs((actual-last[key]+180) % 360-180) if last[key] is not None else 0.0
            last[key] = actual
            if step > 15:
                flash[key] = frame+24
            result[key] = {"output_degrees": actual, "penetration_cm": depth, "step_degrees": step}
            lines[key] = ("BODY HIT {:.2f}cm".format(depth) if depth > 0 else "clear") \
                + "  step {:.1f}".format(step) + ("  JUMP!" if frame <= flash[key] else "")
        rbf_weights = sum(cmds.getAttr(rbf_solver+".outputs[{}]".format(i)) for i in range(len(rbf_grid)))
        result["ok"] = result["rbf"]["penetration_cm"] <= 0 and abs(rbf_weights-1) < 0.05
        info = {
            "input": ("rel={}  H={:.1f}".format("{:+.1f}".format(rel) if rel is not None else "-", half),
                      "BODY HIT {:.2f}cm".format(result["input_penetration_cm"])
                      if result["input_penetration_cm"] > 0 else "clear", "arm moves, tail never animated"),
            "rbf": ("tail rx {:.1f}".format(result["rbf"]["output_degrees"]), lines["rbf"], ""),
            "plan1": ("rel {:+.1f}  L+ {:.1f}  L- {:.1f}".format(
                result["plan1_relative_degrees"], result["plan1_limit_plus_degrees"],
                result["plan1_limit_minus_degrees"]),
                lines["plan1"], "L from elbow-belly distance (driven key)"),
        }
        for column, (key, title, formula, _) in enumerate(METHODS):
            texts["chainTop{}_0".format(column)] = title
            texts["chainTop{}_1".format(column)] = formula
            texts["chainTop{}_2".format(column)] = info[key][0]
            texts["chainBottom{}_0".format(column)] = info[key][1]
            texts["chainBottom{}_1".format(column)] = info[key][2] if key != "input" else ""
            texts["chainBottom{}_2".format(column)] = info[key][2] if key == "input" else ""
        for name in texts:
            cmds.headsUpDisplay(name, refresh=True)
        return result

    if not record:
        demo_interactive.attachInteractive(window, COUNT, evaluate, [(last, None), (flash, -1)])
        logger.info("実行時に自動で避けるシーンを作成しました。タイムラインで確認できます。")
        return
    folder = recordVideo("尻尾1軸回避: 腕の動きで食い込みそうなとき実行時に自動で避ける（案1の実行時版）", COUNT, 24, panel,
                         evaluate, ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1800, height=760)
    cmds.file(rename=str(folder/"runtime-avoid.ma"))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-runtime-avoid.json").write_text(
        json.dumps({"folder": str(folder), "limit_keys": keys}, ensure_ascii=False), encoding="utf-8")
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("実行時の回避の検証に失敗: {}".format(folder))
    logger.info("実行時の回避の検証を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
