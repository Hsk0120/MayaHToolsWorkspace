"""全身骨格の肘から斜め後ろに伸ばした尻尾が、腕の動きで体に食い込みそうなとき実行時に自動で避ける。

骨格は mlrig.examples.humanoid(身長約170cm、cm 単位)。尻尾は左の肘(lowerarm_l の位置)から生え、
前腕の軸(lowerarm_l のローカル X)まわりの rotateX だけで回る。元の向きは斜め後ろ下(前腕の空間で
rotateX = REST_RX)。アニメーターは尻尾を動かさない。

ケース:
- "apose"(既定): Aポーズの骨格で、upperarm_l だけを動かす(ひねり・前後の振り・上げ下げ)。肘は一般的な
  IK を想定した1軸(lowerarm_l は rotateY だけ。rotateX・rotateZ はロック)で、今回は伸ばしたまま。
- "tpose_twist": Tポーズの骨格で、腕・肘・前腕のひねり・背骨を重ねて動かす(前腕のひねりあり)。
- "raise": Aポーズ・肘は1軸で、upperarm_l を腕を上げる姿勢(0, -109.263, -125.343 など)まで大きく動かす。
  案1に ConeReader の切り替えを足した2列(入ってきた側を保つ / 近い側へ逃げる)と比べる。

体の当たり判定は、骨盤・spine_01〜03・左右の太ももに付けた球(プロキシの円柱を包む大きさ)。

案1の実行時版:
1. 前腕の下のグループを、胴の中心(spine_02 に付けたロケーター)へ aimConstraint で向ける
   (rotateX だけ、上方向は前腕の X 軸)。狙う軸は前腕の YZ 面で角度 m の向き(m は、この動きの中で
   胴がいる方向の平均)。グループの rotateX は胴の方向が m の真反対を通るときに ±180 で切り替わるので、
   胴がいない向きに境目を置く。前腕から見た胴の方向 θ = グループの rotateX + m、外向き = θ+180。
2. rel = REST_RX - 外向き。腕が動くと θ が変わり rel が変わる。θ が連続なので押されてきた側を保つ。
3. 止める角度は左右別(L+・L-)。肘と胴の中心の距離からドリブンキーで出す(この動きの距離ごとに、
   胴の中心の方向から見た球の塞ぐ範囲の端の最大 + 余裕)。
4. 尻尾の rotateX = 外向き + clamp(rel, -L-, L+)。

ConeReader の切り替え("raise" の3・4列目):
5. 当たり判定の球ごとに ConeReader(mlrig.setups.coneReader)を置き、矢印を前腕の X 軸、コーンを肘から
   球の中心へ向ける(コーンに aimConstraint)。出力 angle = 前腕の軸と球の方向のなす角。球が尻尾の回転面を
   切るのは angle が 90度から asin(r/d) 以内のとき。m = |angle - 90| - asin((r+余裕)/d)(asin は距離からの
   ドリブンキー)の最小から w = smoothstep((SOFT - m) / SOFT) を作る。m <= 0 で w = 1、m >= SOFT で w = 0。
6. 尻尾の rotateX = rest + w * (clamp(rel, -L-, L+) - rel)。w = 0 では元の向き(避けない)、w = 1 では案1。
7. 狙う軸 m の選び方で2通り。「保つ」は胴が回転面に掛かる姿勢での胴の方向の平均(入ってきた側を保つ)、
   「近い側」は m = REST_RX + 180(rel が ±180 で折り返り、近い方の接線へ逃げる)。
L と m は、upperarm の回転を広く振った姿勢の標本から作る(録画する動きとは別)。

比べる列: 入力(避けない)と案1("raise" はさらに ConeReader の切り替えつき2列)。リグは標準ノード
(aimConstraint・distanceBetween・ドリブンキー・plusMinusAverage・clamp・condition)と ConeReader のみ。
"""

import json
import math
import os
from pathlib import Path

from maya import cmds
import maya.api.OpenMaya as om
from mlib import logger
from mlrig.examples import humanoid
from mlrig.setups.coneReader import ConeReader
from demo_top_view_moving_tangent import _line, _node, _connect
from demo_joint_twist_tangent import _sum, _multiply, _degrees, _condition
from verification_video import recordVideo
import demo_interactive

WINDOW = "humanoidTailWindow"
PANEL = "humanoidTailPanel"
TAIL_LENGTH = 45.0
# 前腕の空間での尻尾の向き。lowerarm_l は X が腕の先、Y が上、Z が前なので、-135度で斜め後ろ下。
REST_RX = -135.0
MARGIN = 5.0
LIMIT_KEYS = 6
SPACING = 140.0
COUNT = 541
# 当たり判定の球。(付ける関節, ワールド中心 cm, 半径 cm)。プロキシの円柱を包む大きさ。
BODY = [
    ("pelvis", (0, 95, 0), 17), ("spine_01", (0, 111, 0), 15), ("spine_02", (0, 123.5, -0.5), 16),
    ("spine_03", (0, 139, -1), 17), ("thigh_l", (9, 75, 0.5), 10), ("thigh_r", (-9, 75, 0.5), 10),
]
TORSO_CENTER = ("spine_02", (0, 120, 0))
# 動き。(関節, 軸, 振幅deg, 周期frame, 位相rad, 中心deg)。
# Aポーズ: upperarm_l だけ(ひねり・前後の振り・上げ下げ)。
MOTION_APOSE = [
    ("upperarm_l", "rx", 60, 230, 0.0, 0), ("upperarm_l", "ry", 50, 190, 1.0, 0),
    ("upperarm_l", "rz", 25, 270, 0.5, 0),
]
# Tポーズ: 腕を下ろし、振り・肘・前腕のひねり・背骨を重ねる。
MOTION = [
    ("upperarm_l", "rz", 15, 230, 0.0, -72), ("upperarm_l", "ry", 45, 190, 0.0, 0),
    ("lowerarm_l", "ry", 35, 160, 1.0, -55), ("lowerarm_l", "rx", 95, 270, 0.0, 0),
    ("clavicle_l", "rz", 8, 210, 0.5, 0), ("spine_02", "ry", 20, 250, 1.5, 0), ("spine_01", "rz", 8, 200, 0.0, 0),
]
# 腕を上げる姿勢を含む大きな動き。(frame, rx, ry, rz) の upperarm_l のキー。ユーザーの確認姿勢を2回通る。
USER_POSE = (0.0, -109.263, -125.343)
MOTION_RAISE_KEYS = [
    (1, 0, 0, 0), (45, 50, 30, 10), (90, -60, -40, -20), (135, 0, -60, -60), (180,) + USER_POSE,
    (215,) + USER_POSE, (260, -50, -80, -60), (305, 60, 20, 15), (350, 0, -90, -60), (395, -40, 40, 20),
    (440, 40, -109, -125), (485,) + USER_POSE, (541, 0, 0, 0),
]
# ConeReader の切り替え。球の半径に足す余裕(cm)と、w が1から0へ下がる幅(度)。
GATE_PAD = 2.0
GATE_SOFT = 15.0
# 止める角度・境目を作る標本。upperarm_l の (rx, ry, rz) を振る範囲(度)。
SWEEP = (range(-90, 91, 30), range(-150, 151, 15), range(-150, 151, 15))
# ケース名 → (骨格の姿勢, 動き, 肘を1軸にするか, 録画の題名, 保存名)
CASES = {
    "apose": ("A", MOTION_APOSE, True, "全身骨格(Aポーズ): upperarmだけの動きで肘の尻尾を自動回避（案1の実行時版、肘は1軸）",
              "humanoid-tail-avoid-apose"),
    "tpose_twist": ("T", MOTION, False, "全身骨格: 肘から斜め後ろの尻尾を腕の動きで自動回避（案1の実行時版）",
                    "humanoid-tail-avoid"),
    "raise": ("A", "raise", True, "全身骨格(Aポーズ): 腕を上げる姿勢で案1とConeReaderの切り替えを比較",
              "humanoid-tail-avoid-gate"),
}
METHODS = [
    ("input", "INPUT (no avoidance)", "tail fixed to the forearm, rx = -135 (back and down)"),
    ("plan1", "PLAN 1 at runtime", "rx = outward + clamp(-135 - outward, -L-, L+)"),
]
GATE_METHODS = [
    ("input", "INPUT", "no avoidance, rx = -135"),
    ("plan1", "PLAN 1", "outward + clamp(rel, -L-, L+)"),
    ("gateKeep", "PLAN 1 + CONE (keep side)", "rest + w*(clamp(rel) - rel)"),
    ("gateNear", "PLAN 1 + CONE (near side)", "same, rel wraps at +-180"),
]


def _bodyBalls(prefix, joints, offset):
    """当たり判定の球(表示はワイヤーのテンプレート)を関節の子に作る。

    Returns:
        list[tuple]: (球の transform, 半径)。
    """
    balls = []
    for joint, center, radius in BODY:
        sphere = cmds.polySphere(name=prefix+joint+"_collision", radius=radius, subdivisionsX=16, subdivisionsY=10,
                                 constructionHistory=False)[0]
        cmds.xform(sphere, worldSpace=True, translation=(center[0]+offset, center[1], center[2]))
        sphere = cmds.parent(sphere, joints[joint])[0]
        shape = cmds.listRelatives(sphere, shapes=True, fullPath=True)[0]
        cmds.setAttr(shape+".overrideEnabled", True)
        cmds.setAttr(shape+".overrideDisplayType", 1)
        balls.append((sphere, radius))
    return balls


def _tail(prefix, joints, color):
    """肘から生える尻尾の関節(rotateX だけで回す)と先端・表示線を作る。"""
    tail = cmds.createNode("joint", name=prefix+"tail_l", parent=joints["lowerarm_l"])
    tip = cmds.createNode("joint", name=prefix+"tail_l_tip", parent=tail)
    cmds.setAttr(tip+".ty", TAIL_LENGTH)
    _line(prefix+"tailDisplay", [(0, 0, 0), (0, TAIL_LENGTH, 0)], color, tail)
    shape = cmds.listRelatives(prefix+"tailDisplay", shapes=True, fullPath=True)[0]
    cmds.setAttr(shape+".lineWidth", 4)
    # 真上から見ると腕のプロキシの下に隠れるので、尻尾の線は常に手前に描く。
    cmds.setAttr(shape+".alwaysDrawOnTop", True)
    for node in (tail, tip):
        cmds.setAttr(node+".radius", 1.5)
    return tail


def bodyRange(joints, balls, center):
    """胴の中心の方向から見た、球が前腕の回転面を塞ぐ範囲の両端(度)。リグと独立に行列から求める。

    Returns:
        tuple | None: (下端 a, 上端 b)。交わる球がなければ None。
    """
    arm = om.MMatrix(cmds.xform(joints["lowerarm_l"], query=True, worldSpace=True, matrix=True)).inverse()
    c = om.MPoint(*cmds.xform(center, query=True, worldSpace=True, translation=True))*arm
    base = math.degrees(math.atan2(c.z, c.y))
    lows, highs = [], []
    for ball, radius in balls:
        p = om.MPoint(*cmds.xform(ball, query=True, worldSpace=True, translation=True))*arm
        r2 = radius**2-p.x**2
        if r2 <= 0:
            continue
        rho, d = math.sqrt(r2), math.hypot(p.y, p.z)
        width = math.degrees(math.asin(rho/d)) if d > rho else 90.0
        theta = math.degrees(math.atan2(p.z, p.y))
        delta = (theta-base+180) % 360-180
        lows.append(delta-width)
        highs.append(delta+width)
    if not lows:
        return None
    return min(lows), max(highs)


def torsoAngle(joints, center):
    """前腕の空間で見た胴の中心の方向(前腕の +Y から +Z へ、度)。リグと独立に行列から求める。"""
    arm = om.MMatrix(cmds.xform(joints["lowerarm_l"], query=True, worldSpace=True, matrix=True)).inverse()
    c = om.MPoint(*cmds.xform(center, query=True, worldSpace=True, translation=True))*arm
    return math.degrees(math.atan2(c.z, c.y))


def _rootInside(joints, balls):
    """尻尾の根元(肘)が、どれかの球の回転面での断面の中にあるか。あり得ない姿勢として標本から外す。"""
    arm = om.MMatrix(cmds.xform(joints["lowerarm_l"], query=True, worldSpace=True, matrix=True)).inverse()
    for ball, radius in balls:
        p = om.MPoint(*cmds.xform(ball, query=True, worldSpace=True, translation=True))*arm
        r2 = radius**2-p.x**2
        if r2 > 0 and math.hypot(p.y, p.z) <= math.sqrt(r2)+1:
            return True
    return False


def measure(rig):
    """今の姿勢の標本。肘と胴の中心の距離・前腕の軸と胴の方向のなす角の90度からのずれ・塞ぐ範囲・胴の方向。

    Returns:
        dict | None: distance, dev, bounds, torso。根元が球の中なら None。
    """
    joints = rig["joints"]
    if _rootInside(joints, rig["balls"]):
        return None
    m = cmds.xform(joints["lowerarm_l"], query=True, worldSpace=True, matrix=True)
    axis = om.MVector(*m[0:3]).normal()
    to_center = om.MVector(*cmds.xform(rig["center"], query=True, worldSpace=True, translation=True)) \
        - om.MVector(*m[12:15])
    return {"distance": to_center.length(), "dev": abs(math.degrees(axis.angle(to_center))-90),
            "bounds": bodyRange(joints, rig["balls"], rig["center"]), "torso": torsoAngle(joints, rig["center"])}


def sweepSamples(rig):
    """upperarm_l の回転を SWEEP の範囲で振った姿勢の標本(リグと独立)。終わったら回転0に戻す。"""
    upper = rig["joints"]["upperarm_l"]
    samples = []
    for rx in SWEEP[0]:
        for ry in SWEEP[1]:
            for rz in SWEEP[2]:
                cmds.setAttr(upper+".rotate", rx, ry, rz)
                sample = measure(rig)
                if sample:
                    samples.append(sample)
    cmds.setAttr(upper+".rotate", 0, 0, 0)
    return samples


def limitKeys(samples):
    """標本から、距離ごとの止める角度 L+・L- のドリブンキーを作る。"""
    blocked = [s for s in samples if s["bounds"]]
    lo, hi = min(s["distance"] for s in blocked), max(s["distance"] for s in blocked)
    width = max((hi-lo)/(LIMIT_KEYS-1), 1e-3)
    keys = {"plus": [], "minus": []}
    for k in range(LIMIT_KEYS):
        d = lo+width*k
        near = [s for s in blocked if abs(s["distance"]-d) <= width] or blocked
        keys["plus"].append((d, max(0.0, 180-(max(-s["bounds"][0] for s in near)+MARGIN))))
        keys["minus"].append((d, max(0.0, 180-(max(s["bounds"][1] for s in near)+MARGIN))))
    return keys


def _drivenAttr(holder, attr, driver, values):
    """holder に attr を作り、driver からの直線のドリブンキーをつける。"""
    cmds.addAttr(holder, longName=attr, attributeType="double", keyable=True)
    for d, value in values:
        cmds.setDrivenKeyframe(holder+"."+attr, currentDriver=driver, driverValue=d, value=value,
                               inTangentType="linear", outTangentType="linear")
    return holder+"."+attr


def _buildGate(prefix, arm, balls):
    """ConeReader で、体が尻尾の回転面に掛かっている度合い w(0〜1)を作る。

    球ごとに ConeReader を置き、矢印を前腕の X 軸、コーンを肘から球の中心へ向ける。球(中心までの距離 d、
    半径 r)が回転面を切るのは、なす角 angle が 90度から asin(r/d) 以内のとき。ずれ dev = |angle - 90| と
    境目 T = asin((r + GATE_PAD)/d)(距離からのドリブンキー)の差 m = dev - T を球ごとに求め、最も小さい m から
    w = smoothstep((GATE_SOFT - m)/GATE_SOFT) を作る。m <= 0(どれかの球が面を切る)で w = 1。

    Returns:
        dict: weight(w)、margin(最も小さい m)のプラグ。
    """
    margins = []
    for i, (ball, radius) in enumerate(balls):
        name = "{}ballCone{}".format(prefix, i)
        reader = ConeReader.create(driverJoint=arm, coneJoint=arm, name=name, coneAngle=90.0, driverAxis="x",
                                   size=8.0)
        # コーンの軸を肘から球の中心へ向ける。比べるのは向きだけなので、上方向は使わない。
        cmds.aimConstraint(ball, reader.cone, aimVector=(1, 0, 0), upVector=(0, 1, 0), worldUpType="none")
        for group in (name+"_driver_GRP", name+"_cone_GRP"):
            cmds.setAttr(group+".visibility", False)
        offset = _sum(name+"Offset", (name+".angle",), (-90,))
        dev = _condition(name+"Dev", offset, 0, offset, _multiply(name+"NegOffset", offset, constant=-1),
                         operation=3)
        distance = _node("distanceBetween", name+"Distance")
        _connect(arm+".worldMatrix[0]", distance+".inMatrix1")
        _connect(ball+".worldMatrix[0]", distance+".inMatrix2")
        holder = cmds.createNode("transform", name=name+"_gate", parent=ball)
        limit = radius+GATE_PAD
        values = [(limit*k, math.degrees(math.asin(1/k))) for k in (1, 1.05, 1.15, 1.3, 1.5, 1.8, 2.2, 2.8, 3.6,
                                                                    4.6, 6, 8, 11)]
        gate = _drivenAttr(holder, "gateAngle", distance+".distance", values)
        margins.append(_sum(name+"Margin", (dev, gate), subtract=True))
    margin = margins[0]
    for i, other in enumerate(margins[1:]):
        margin = _condition("{}GateMin{}".format(prefix, i), margin, 0, margin, other, operation=4)
        # condition は secondTerm にプラグをつなぐ。
        _connect(other, margin.rsplit(".", 1)[0]+".secondTerm")
    ratio = _sum(prefix+"GateRatioBase", (_multiply(prefix+"GateNegMargin", margin, constant=-1),), (GATE_SOFT,))
    clamp = _node("clamp", prefix+"GateClamp", maxR=1)
    _connect(_multiply(prefix+"GateRatio", ratio, constant=1.0/GATE_SOFT), clamp+".inputR")
    t = clamp+".outputR"
    # smoothstep: t*t*(3-2t)。
    weight = _multiply(prefix+"GateWeight", _multiply(prefix+"GateSquare", t, t),
                       _sum(prefix+"GateThreeMinus", (_multiply(prefix+"GateTwice", t, constant=-2),), (3,)))
    return {"weight": weight, "margin": margin}


def _buildPlan1(prefix, joints, center, keys, color, aim_angle, balls=None):
    """案1の実行時版。balls(当たり判定の球)を渡すと ConeReader の切り替えをつける。

    Returns:
        dict: output, relative, limitPlus, limitMinus, theta(いずれも度のプラグ)。切り替えつきなら weight・margin も。
    """
    arm = joints["lowerarm_l"]
    group = cmds.createNode("transform", name=prefix+"torsoDirection_GRP", parent=arm)
    aim = (0, math.cos(math.radians(aim_angle)), math.sin(math.radians(aim_angle)))
    cmds.aimConstraint(center, group, aimVector=aim, upVector=(1, 0, 0), worldUpType="objectrotation",
                       worldUpObject=arm, worldUpVector=(1, 0, 0), skip=("y", "z"))
    theta = _sum(prefix+"Theta", (_degrees(prefix+"AimRotate", group+".rotateX"),), (aim_angle,))
    outward = _sum(prefix+"Outward", (theta,), (180,))
    # 尻尾の元の向きを、胴がいる平均の向き(aim_angle)と同じ周に合わせる。そうしないと rel が1周ずれる。
    rest = REST_RX+360*round(((aim_angle+180)-REST_RX)/360.0)
    relative = _sum(prefix+"Relative", (_multiply(prefix+"NegOutward", outward, constant=-1),), (rest,))
    distance = _node("distanceBetween", prefix+"TorsoDistance")
    _connect(arm+".worldMatrix[0]", distance+".inMatrix1")
    _connect(center+".worldMatrix[0]", distance+".inMatrix2")
    holder = cmds.createNode("transform", name=prefix+"tailLimit", parent=joints["root"])
    plugs = {}
    for attr, values in (("limitPlus", keys["plus"]), ("limitMinus", keys["minus"])):
        plugs[attr] = _drivenAttr(holder, attr, distance+".distance", values)
    clamp = _node("clamp", prefix+"Clamp")
    _connect(relative, clamp+".inputR")
    _connect(plugs["limitPlus"], clamp+".maxR")
    _connect(_multiply(prefix+"NegLimit", plugs["limitMinus"], constant=-1), clamp+".minR")
    if balls:
        plugs.update(_buildGate(prefix, arm, balls))
        # rest + w*(clamp(rel) - rel)。w=0 は元の向き、w=1 は outward + clamp(rel) と同じ。
        correction = _sum(prefix+"Correction", (clamp+".outputR", relative), subtract=True)
        world = _sum(prefix+"World", (_multiply(prefix+"WeightedCorrection", correction, plugs["weight"]),), (rest,))
    else:
        world = _sum(prefix+"World", (outward, clamp+".outputR"))
    output = _tail(prefix, joints, color)
    radians = _node("unitConversion", prefix+"Radians", conversionFactor=math.pi/180)
    _connect(world, radians+".input")
    _connect(radians+".output", output+".rx")
    for attr in ("ry", "rz"):
        cmds.setAttr(output+"."+attr, lock=True)
    return {"output": output, "relative": relative, "theta": theta, **plugs}


def main(record=True, case="apose", view="top"):
    """専用GUIで2体を同じ腕の動きで動かし、斜め後ろから録画して検査する。

    Args:
        record (bool): False なら録画せず、タイムラインで確認できるシーンを作る。
        case (str): "apose"(Aポーズ・upperarm だけ・肘は1軸)、"tpose_twist"、"raise"(腕を上げる姿勢と
            ConeReader の切り替えの比較)。
        view (str): "top" は真上からの平行投影、"back" は斜め後ろからの透視投影。
    """
    pose, motion, hinge, title, save_name = CASES[case]
    methods = GATE_METHODS if motion == "raise" else METHODS
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    if PANEL in cmds.getPanel(allPanels=True):
        cmds.deleteUI(PANEL, panel=True)
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW, window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")

    rigs = {}
    for i, (key, _, _) in enumerate(methods):
        prefix = key+"_"
        result = humanoid.build(prefix=prefix, pose=pose)
        # 尻尾と当たり判定の球が見えるよう、プロキシを薄くする。
        cmds.setAttr(prefix+"humanProxy_mat.transparency", 0.72, 0.72, 0.72, type="double3")
        # 1列目(入力)が画面の左に来るように置く。真上からは +X が画面の右、斜め後ろからは左右が反転する。
        offset = (i-(len(methods)-1)/2.0)*SPACING*(1 if view == "top" else -1)
        cmds.setAttr(result["root"]+".tx", offset)
        joints = result["joints"]
        center = cmds.spaceLocator(name=prefix+"torsoCenter_LOC")[0]
        cmds.xform(center, worldSpace=True, translation=[v+offset*(k == 0) for k, v in enumerate(TORSO_CENTER[1])])
        center = cmds.parent(center, joints[TORSO_CENTER[0]])[0]
        cmds.setAttr(center+".visibility", False)
        rigs[key] = {"joints": joints, "balls": _bodyBalls(prefix, joints, offset),
                     "center": center}
        if hinge:
            # 肘は一般的な IK を想定した1軸(曲げる軸 rotateY だけ)。
            for attr in ("rx", "rz"):
                cmds.setAttr(joints["lowerarm_l"]+"."+attr, lock=True)
    # 止める角度などの標本。"raise" は upperarm の回転を広く振った姿勢から(キーを打つ前に作る)。
    sweep = sweepSamples(rigs["plan1"]) if motion == "raise" else None
    for key, _, _ in methods:
        joints = rigs[key]["joints"]
        if motion == "raise":
            for frame, rx, ry, rz in MOTION_RAISE_KEYS:
                for attr, value in (("rx", rx), ("ry", ry), ("rz", rz)):
                    cmds.setKeyframe(joints["upperarm_l"], attribute=attr, time=frame, value=value)
            continue
        for joint, attr, amplitude, period, phase, middle in motion:
            for frame in range(0, COUNT, 3):
                value = middle+amplitude*math.sin(2*math.pi*frame/period+phase)
                cmds.setKeyframe(joints[joint], attribute=attr, time=frame+1, value=value)
    cmds.playbackOptions(minTime=1, maxTime=COUNT)

    # 入力(避けない)の尻尾。
    rigs["input"]["tail"] = _tail("input_", rigs["input"]["joints"], (1, 0.15, 0.15))
    cmds.setAttr(rigs["input"]["tail"]+".rx", REST_RX)

    # 止める角度のドリブンキー(左右別)。この動きの、肘と胴の中心の距離ごとの塞がれる範囲の端から作る。
    # rel = 外向きからの角度。+側から押されると下端 a、-側から押されると上端 b で止まる。
    rig = rigs["plan1"]
    if sweep is None:
        samples = []
        for frame in range(0, COUNT, 3):
            cmds.currentTime(frame+1)
            samples.append(measure(rig))
        samples = [s for s in samples if s]
        # 胴がいる方向の平均(円周上の平均)を、グループが狙う軸にする。
        angles = [math.radians(s["torso"]) for s in samples]
    else:
        samples = sweep
        # 胴が回転面に掛かる姿勢だけで、胴がいる方向の平均を取る(掛からない姿勢では向きを問わない)。
        angles = [math.radians(s["torso"]) for s in samples if s["bounds"]]
    aim_angle = math.degrees(math.atan2(sum(math.sin(a) for a in angles), sum(math.cos(a) for a in angles)))
    spread = max(abs((math.degrees(a)-aim_angle+180) % 360-180) for a in angles)
    keys = limitKeys(samples)
    plans = {"plan1": _buildPlan1("plan1_", rig["joints"], rig["center"], keys, (0.1, 1, 0.1), aim_angle)}
    if motion == "raise":
        for key, color, aim in (("gateKeep", (0.2, 0.6, 1), aim_angle), ("gateNear", (1, 0.8, 0.1), REST_RX+180)):
            plans[key] = _buildPlan1(key+"_", rigs[key]["joints"], rigs[key]["center"], keys, color, aim,
                                     balls=rigs[key]["balls"])
    for key, plan in plans.items():
        rigs[key]["tail"] = plan["output"]

    if view == "top":
        # 真上から見下ろす。画面の右が +X、画面の上が -Z(体の後ろ)。
        camera, camera_shape = cmds.camera(name="humanoidTailCamera", orthographic=True)
        cmds.setAttr(camera+".translate", 0, 400, -10)
        cmds.setAttr(camera+".rotate", -90, 0, 0)
        cmds.setAttr(camera_shape+".orthographicWidth", SPACING*len(methods)+80)
    else:
        camera, camera_shape = cmds.camera(name="humanoidTailCamera")
        cmds.setAttr(camera+".translate", 260, 210, -330)
        cmds.setAttr(camera+".rotate", -12, 141, 0)
        cmds.setAttr(camera_shape+".focalLength", 30)
    if cmds.windowPref(WINDOW, exists=True):
        cmds.windowPref(WINDOW, remove=True)
    window = cmds.window(WINDOW, widthHeight=(1600, 860))
    pane = cmds.paneLayout(parent=window)
    panel = cmds.modelPanel(PANEL, parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", grid=view != "top", cameras=False, joints=True,
                     headsUpDisplay=True, manipulators=False, selectionHiliteDisplay=False, locators=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1600, 860))
    cmds.setFocus(panel)
    cmds.select(clear=True)
    demo_interactive.clearHuds(window)
    texts = {}
    for column, section in enumerate((0, 4) if len(methods) == 2 else (0, 1, 3, 4)):
        for row in range(3):
            for prefix, base, block in (("humanTop", section, row), ("humanBottom", section+5, 2-row)):
                name = "{}{}_{}".format(prefix, column, row)
                texts[name] = ""
                cmds.headsUpDisplay(name, section=base, block=block, blockSize="large", dataFontSize="large",
                                    command=lambda n=name: texts[n])

    last = {key: None for key, _, _ in methods}
    flash = {key: -1 for key, _, _ in methods}

    def penetration(key):
        """尻尾の線分と当たり判定の球の交差検査(リグに接続しない)。最も深い食い込み(cm)。"""
        m = cmds.xform(rigs[key]["tail"], query=True, worldSpace=True, matrix=True)
        origin, direction = m[12:15], om.MVector(*m[4:7]).normal()
        deepest = 0.0
        for ball, radius in rigs[key]["balls"]:
            c = cmds.xform(ball, query=True, worldSpace=True, translation=True)
            o = [a-b for a, b in zip(origin, c)]
            t = max(0, min(TAIL_LENGTH, -sum(a*b for a, b in zip(o, direction))))
            deepest = max(deepest, radius-math.sqrt(sum((a+t*b)**2 for a, b in zip(o, direction))))
        return deepest

    def evaluate(frame):
        """2体の尻尾の食い込み・変化量と、案1の rel・L を記録する。"""
        demo_interactive.setTime(frame)
        plan1 = plans["plan1"]
        result = {"frame": frame, "plan1_relative_degrees": cmds.getAttr(plan1["relative"]),
                  "plan1_theta_degrees": cmds.getAttr(plan1["theta"]),
                  "plan1_limit_plus_degrees": cmds.getAttr(plan1["limitPlus"]),
                  "plan1_limit_minus_degrees": cmds.getAttr(plan1["limitMinus"]),
                  "upperarm_rotate": list(cmds.getAttr(rigs["plan1"]["joints"]["upperarm_l"]+".rotate")[0])}
        lines = {}
        for key, _, _ in methods:
            m = cmds.xform(rigs[key]["tail"], query=True, worldSpace=True, matrix=True)
            arm = om.MMatrix(cmds.xform(rigs[key]["joints"]["lowerarm_l"], query=True, worldSpace=True, matrix=True))
            local = om.MVector(*m[4:7])*arm.inverse()
            angle = math.degrees(math.atan2(local.z, local.y))
            step = abs((angle-last[key]+180) % 360-180) if last[key] is not None else 0.0
            last[key] = angle
            if step > 15:
                flash[key] = frame+24
            depth = penetration(key)
            result[key] = {"tail_angle_degrees": angle, "penetration_cm": depth, "step_degrees": step}
            lines[key] = ("BODY HIT {:.1f}cm".format(depth) if depth > 0 else "clear") \
                + "  step {:.1f}".format(step) + ("  JUMP!" if frame <= flash[key] else "")
        for key, plan in plans.items():
            if "weight" in plan:
                result[key].update({"weight": cmds.getAttr(plan["weight"]),
                                    "margin_degrees": cmds.getAttr(plan["margin"]),
                                    "relative_degrees": cmds.getAttr(plan["relative"])})
        result["ok"] = all(result[key]["penetration_cm"] <= 0 for key in plans)
        if motion == "raise":
            rotate = result["upperarm_rotate"]
            info = {"input": (lines["input"], "upperarm {:.0f} {:.0f} {:.0f}".format(*rotate),
                              "user pose" if max(abs(a-b) for a, b in zip(rotate, USER_POSE)) < 0.5 else ""),
                    "plan1": (lines["plan1"], "rel {:+.0f}".format(result["plan1_relative_degrees"]),
                              "L+ {:.0f}  L- {:.0f}".format(result["plan1_limit_plus_degrees"],
                                                            result["plan1_limit_minus_degrees"]))}
            for key in ("gateKeep", "gateNear"):
                r = result[key]
                info[key] = (lines[key], "w {:.2f}  rel {:+.0f}".format(r["weight"], r["relative_degrees"]),
                             "min(|angle-90| - T) {:+.0f}".format(r["margin_degrees"]))
        else:
            info = {
            "input": (lines["input"], "torso dir from forearm {:+.1f}".format(result["plan1_theta_degrees"]),
                      "rel {:+.1f}".format(result["plan1_relative_degrees"])),
            "plan1": (lines["plan1"], "L+ {:.1f}  L- {:.1f}".format(result["plan1_limit_plus_degrees"],
                                                                     result["plan1_limit_minus_degrees"]),
                      "L from elbow-torso distance (driven keys)"),
            }
        for column, (key, title, formula) in enumerate(methods):
            texts["humanTop{}_0".format(column)] = title
            texts["humanTop{}_1".format(column)] = formula
            texts["humanTop{}_2".format(column)] = info[key][0]
            texts["humanBottom{}_0".format(column)] = info[key][1]
            texts["humanBottom{}_1".format(column)] = info[key][2]
            moving = "upperarm_l" if motion == "raise" else ", ".join(sorted({j for j, *_ in motion}))
            texts["humanBottom{}_2".format(column)] = (
                "{}-pose, moving: {}{}".format(pose, moving, "  (elbow: 1 axis)" if hinge else "")
                if column == 0 else "")
        for name in texts:
            cmds.headsUpDisplay(name, refresh=True)
        return result

    if not record:
        demo_interactive.attachInteractive(window, COUNT, evaluate, [(last, None), (flash, -1)])
        logger.info("全身骨格の尻尾の自動回避シーンを作成しました。タイムラインで確認できます。")
        return
    folder = recordVideo(title, COUNT, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1600, height=860)
    cmds.file(rename=str(folder/(save_name+".ma")))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-{}.json".format(save_name)).write_text(
        json.dumps({"folder": str(folder), "limit_keys": keys, "aim_angle": aim_angle, "torso_spread": spread,
                    "samples": len(samples)},
                   ensure_ascii=False), encoding="utf-8")
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("全身骨格の尻尾の自動回避の検証に失敗: {}".format(folder))
    logger.info("全身骨格の尻尾の自動回避の検証を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
