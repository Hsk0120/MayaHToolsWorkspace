"""全身骨格(Aポーズ)の左右6本の尻尾で、腕のツイストを打ち消す処理を確かめる。

骨格は mlrig.examples.humanoid の Aポーズ(身長約170cm、cm 単位)。尻尾は左右3本ずつで、
付け根と親は次のとおり。いずれも親の骨の X 軸(腕の軸)まわりの rotateX だけで回る。

- upperarm の根元: upperarm の子
- 肘(lowerarm の根元): lowerarm の子
- 手首(hand の根元): lowerarm の子

初期ポーズ: Aポーズで、腕と直角のまま真後ろから下へ30度ひねった向き(rotateX = REST_RX = -120)。
右は jointOrientX = 180 にして、左右とも同じ値で鏡像の向き・回り方にする。

ツイストの打ち消し:
1. 骨(upperarm / lowerarm)の、鎖骨(clavicle)から見た今の回転を、初期ポーズからの差 R にする。
   R = 骨の worldMatrix x 鎖骨の worldInverseMatrix x (初期ポーズでの同じ積)^-1。
   lowerarm の R には upperarm のツイストも含まれる。
2. R を decomposeMatrix のクォータニオン (x, y, z, w) にし、骨の X 軸まわりの成分 (x, 0, 0, w) を
   正規化して quatToEuler でツイスト角 t を取り出す(スイング・ツイスト分解)。
3. 尻尾の rotateX = REST_RX - t。upperarm の尻尾は upperarm の t、lowerarm の尻尾は lowerarm の t。

リグは標準ノード(multMatrix・decomposeMatrix・quatNormalize・quatToEuler・plusMinusAverage・
unitConversion)のみ。matrixNodes・quatNodes は Maya 同梱のプラグイン。

検査はリグと独立に行う。骨の X 軸を初期の向きから今の向きへ最短で回す回転(ツイストなし)を
初期ポーズの尻尾の向きにかけ、実際の尻尾の向きとの角度差を測る。打ち消しありは0度になるはず。
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
from verification_video import recordVideo
import demo_interactive
import tail_shared_avoid

WINDOW = "tailTwistCancelWindow"
PANEL = "tailTwistCancelPanel"
REST_RX = -120.0
TAIL_LENGTH = 45.0
SPACING = 170.0
COUNT = 361
# (種類, 親の骨, 付け根の位置にする関節, 色)。左右それぞれに作る。
TAILS = [("upperarm", "upperarm", "upperarm", (0.2, 0.6, 1)), ("elbow", "lowerarm", "lowerarm", (1, 0.2, 0.2)),
         ("hand", "lowerarm", "hand", (1, 0.8, 0.1))]
SIDES = ("_l", "_r")
# 動き。(関節, 軸, 振幅deg, 周期frame, 位相rad, 中心deg)。左右に同じ値(鏡像)。
# upperarm のツイスト(rx)・前後の振り(ry)・上げ下げ(rz)と、肘の曲げ(lowerarm の ry だけ。肘は1軸)。
MOTION = [
    ("upperarm", "rx", 70, 120, 0.0, 0), ("upperarm", "ry", 35, 170, 0.7, 0), ("upperarm", "rz", 20, 210, 1.3, 0),
    ("lowerarm", "ry", 35, 150, 0.4, -40),
]
# 調査で食い込みが多かった姿勢を通る動き。(frame, upperarm rx, ry, rz, lowerarm ry)。左右に同じ値。
# 腕を後ろへ引く・後ろで内側へ回す・前に出して肘を深く曲げる・体に沿って下ろす。保持中にひねりを加える。
PROBLEM_KEYS = [
    (1, 0, 0, 0, 0), (40, 0, 45, 0, 0), (55, 40, 45, 0, 0), (70, -40, 45, 0, 0), (85, 0, 45, 0, 0),
    (120, 0, 60, -60, 0), (140, 0, 60, -60, 0), (175, 0, 0, 0, -20), (215, 0, -75, -15, -120),
    (235, 40, -75, -15, -120), (255, -40, -75, -15, -120), (275, 0, -60, 30, -90), (310, 0, 0, -45, 0),
    (330, 0, 0, -45, 0), (361, 0, 0, 0, 0),
]
# 肘を90度以上曲げたまま upperarm をひねる動き(尻尾どうしの交差の再現)。形式は PROBLEM_KEYS と同じ。
CROSS_KEYS = [
    (1, 0, 0, 0, 0), (30, 0, 0, 0, -110), (60, 0, 0, 0, -110), (180, 170, 0, 0, -110), (210, 170, 0, 0, -110),
    (270, 0, 0, 0, -110), (300, 0, 0, 0, -95), (330, 120, 0, 0, -95), (361, 0, 0, 0, 0),
]
# 付け根からこの長さ(cm)以内の当たりは「付け根の近く」として分けて数える。肩の付け根は胸のプロキシの
# 表面から約2cmなので、付け根の近くでは体の角をかすりやすい。
ROOT_ZONE = 8.0
# 尻尾どうしが交差したとみなす線分の最短距離(cm)。表示の線の太さ程度。
CROSS_DISTANCE = 1.0
# 体のプロキシ(左右の腕・鎖骨・手・指以外)。尻尾の線分がこれらの面を横切れば食い込みとする。
BODY_PROXIES = ("pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head", "thigh_l", "thigh_r", "calf_l",
                "calf_r")
METHODS = [("raw", "NO TWIST CANCEL", "tail rx = -120 (fixed)"),
           ("cancel", "TWIST CANCEL", "tail rx = -120 - twist(bone vs clavicle)")]
# 尻尾どうしの交差を防ぐ案(motion="cross_fix"・"problem_fix" で使う)。肘・手首の尻尾にスイング(骨に沿う傾き)を足す。
FIX_METHODS = [("local", "LOCAL VALUE CANCEL", "rx = -120 - sum rx"),
               ("parallel", "A: PARALLEL", "elbow/hand tails aim along the upperarm tail"),
               ("swing", "B: SWING ONLY (+-60)", "rx = local, swing = along-bone part of A"),
               ("elbow", "D: CANCEL ELBOW BEND", "rx = local, ry = -elbow bend")]
# 案D に前腕のコーンを足した比較(motion="*_cone" で使う)。
CONE_METHODS = [("local", "LOCAL VALUE CANCEL", "rx = -120 - sum rx"),
                ("elbow", "D: CANCEL ELBOW BEND", "rx = local, ry = -elbow bend"),
                ("elbowcone", "D + FOREARM CONE", "push off the forearm axis by w")]
# 案D＋前腕のコーンに、3本共通の体の回避を足した比較(motion="*_avoid" で使う)。
AVOID_METHODS = [("local", "LOCAL VALUE CANCEL", "rx = -120 - sum rx"),
                 ("elbowcone", "D + FOREARM CONE", "no body avoidance"),
                 ("avoid", "D + CONE + BODY AVOID", "rx += shared delta (3 tails)")]
# 体の回避に使う当たり判定の球。(付ける関節, ワールド中心 cm, 半径 cm)。プロキシ(胸の円柱は半径15cm など)に
# 合わせた大きさ。demo_humanoid_tail_avoid.BODY より小さく、初期ポーズの尻尾は塞がれない。
AVOID_BODY = [
    ("pelvis", (0, 95, 0), 17), ("spine_01", (0, 111, 0), 13), ("spine_02", (0, 123.5, -0.5), 14),
    ("spine_03", (0, 139, -1), 15), ("thigh_l", (9, 75, 0.5), 9), ("thigh_r", (-9, 75, 0.5), 9),
    ("neck_01", (0, 152, -1.5), 6), ("head", (0, 165, 0), 11),
]
# 胴の中心(ワールド、オフセット前)。spine_02 に付ける。
TORSO_CENTER = (0, 120, 0)
# 前腕のコーンの半角(度)。D の向きが前腕の軸からこの角度以内に入ると、肘の曲げの打ち消しを弱める。
FOREARM_CONE = 25.0
# 肘を90度に曲げ、upperarm のひねりで D の手首の尻尾が前腕に沿う姿勢(rotateX = -30 付近)を通る動き。
ALIGN_KEYS = [
    (1, 0, 0, 0, 0), (30, 0, 0, 0, -90), (60, 20, 0, 0, -90), (150, -80, 0, 0, -90), (180, -80, 0, 0, -90),
    (250, 10, 0, 0, -90), (280, 0, -40, 20, -100), (330, -60, -40, 20, -100), (361, 0, 0, 0, 0),
]
# 案B のスイングの上限(度)。
SWING_LIMIT = 60.0
# ローカルの回転値だけで打ち消す方式を加えた3列(motion="problem" で使う)。
LOCAL_METHODS = [("raw", "NO CANCEL", "tail rx = -120"),
                 ("cancel", "SWING-TWIST CANCEL", "-120 - twist(bone vs clavicle)"),
                 ("local", "LOCAL VALUE CANCEL", "-120 - sum of local rotateX")]


def _node(kind, name, **values):
    """標準ノードを作り、定数を設定する。"""
    node = cmds.createNode(kind, name=name)
    for attr, value in values.items():
        cmds.setAttr(node+"."+attr, value)
    return node


def _matrix(node):
    """ワールド行列。"""
    return om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))


def twistPlug(prefix, bone, reference):
    """bone の、reference から見た初期ポーズからの回転のうち、bone の X 軸まわりのツイスト角(度)のプラグ。"""
    rest = list((_matrix(bone)*_matrix(reference).inverse()).inverse())
    mult = _node("multMatrix", prefix+"TwistRelative")
    cmds.connectAttr(bone+".worldMatrix[0]", mult+".matrixIn[0]")
    cmds.connectAttr(reference+".worldInverseMatrix[0]", mult+".matrixIn[1]")
    cmds.setAttr(mult+".matrixIn[2]", rest, type="matrix")
    decompose = _node("decomposeMatrix", prefix+"TwistDecompose")
    cmds.connectAttr(mult+".matrixSum", decompose+".inputMatrix")
    # X 軸まわりの成分だけ残す。y・z は0のまま。
    normalize = _node("quatNormalize", prefix+"TwistQuat")
    cmds.connectAttr(decompose+".outputQuatX", normalize+".inputQuatX")
    cmds.connectAttr(decompose+".outputQuatW", normalize+".inputQuatW")
    euler = _node("quatToEuler", prefix+"TwistEuler")
    cmds.connectAttr(normalize+".outputQuat", euler+".inputQuat")
    degrees = _node("unitConversion", prefix+"TwistDegrees", conversionFactor=180/math.pi)
    cmds.connectAttr(euler+".outputRotateX", degrees+".input")
    return degrees+".output"


def _tail(prefix, joints, kind, parent, root, side, color):
    """付け根に尻尾の関節・先端・表示線を作る。右は jointOrientX = 180。"""
    tail = cmds.createNode("joint", name="{}tail_{}{}".format(prefix, kind, side), parent=joints[parent+side])
    cmds.xform(tail, worldSpace=True, translation=cmds.xform(joints[root+side], query=True, worldSpace=True,
                                                              translation=True))
    cmds.setAttr(tail+".jointOrient", 180 if side == "_r" else 0, 0, 0)
    cmds.setAttr(tail+".rx", REST_RX)
    tip = cmds.createNode("joint", name=tail+"_tip", parent=tail)
    cmds.setAttr(tip+".ty", TAIL_LENGTH)
    curve = cmds.curve(degree=1, point=[(0, 0, 0), (0, TAIL_LENGTH, 0)], name=tail+"_display")
    shape = cmds.listRelatives(curve, shapes=True)[0]
    cmds.parent(shape, tail, shape=True, relative=True)
    cmds.delete(curve)
    cmds.setAttr(shape+".overrideEnabled", True)
    cmds.setAttr(shape+".overrideRGBColors", True)
    cmds.setAttr(shape+".overrideColorRGB", *color)
    cmds.setAttr(shape+".lineWidth", 4)
    cmds.setAttr(shape+".alwaysDrawOnTop", True)
    for node in (tail, tip):
        cmds.setAttr(node+".radius", 1.5)
    return tail


def localTwistPlugs(prefix, joints, side):
    """ローカルの rotateX の値(度)を合算したプラグ。upperarm は upperarm.rx、lowerarm は upperarm.rx + lowerarm.rx。"""
    plugs, total = {}, []
    for bone in ("upperarm", "lowerarm"):
        degrees = _node("unitConversion", "{}{}{}_localTwist".format(prefix, bone, side), conversionFactor=180/math.pi)
        cmds.connectAttr(joints[bone+side]+".rotateX", degrees+".input")
        total.append(degrees+".output")
        add = _node("plusMinusAverage", "{}{}{}_localTwistSum".format(prefix, bone, side))
        for i, plug in enumerate(total):
            cmds.connectAttr(plug, add+".input1D[{}]".format(i))
        plugs[bone+side] = add+".output1D"
    return plugs


def _direction(name, node, axis):
    """node の axis(ローカル)をワールドの単位ベクトルにしたプラグ。"""
    product = _node("vectorProduct", name, operation=3, normalizeOutput=True)
    cmds.setAttr(product+".input1", *axis)
    cmds.connectAttr(node+".worldMatrix[0]", product+".matrix")
    return product+".output"


def _aimTarget(name, root, directions):
    """root の位置から directions の和の向きへ尻尾の長さだけ進んだ点の transform(aimConstraint の狙い)。"""
    position = _node("decomposeMatrix", name+"_rootPosition")
    cmds.connectAttr(root+".worldMatrix[0]", position+".inputMatrix")
    total = _node("plusMinusAverage", name+"_sum")
    cmds.connectAttr(position+".outputTranslate", total+".input3D[0]")
    for i, direction in enumerate(directions, 1):
        scaled = _node("multiplyDivide", "{}_scaled{}".format(name, i))
        cmds.connectAttr(direction, scaled+".input1")
        cmds.setAttr(scaled+".input2", TAIL_LENGTH, TAIL_LENGTH, TAIL_LENGTH)
        cmds.connectAttr(scaled+".output", total+".input3D[{}]".format(i))
    target = cmds.createNode("transform", name=name)
    cmds.connectAttr(total+".output3D", target+".translate")
    return target


def _fixTail(prefix, joints, tail, parent, root, side, mode, upper_tail, twist):
    """肘・手首の尻尾に、交差を防ぐスイングをつなぐ。

    - "parallel": upperarm の尻尾と同じ向きへ aimConstraint で向ける。上方向を前腕の X 軸にするので、
      回り方は「前腕の軸まわりのひねり + 骨に沿う傾き」の2軸だけになる。
    - "swing": ひねりはローカル値の打ち消し(rx = -120 - twist)のまま、骨に沿う傾き(rotateZ、回転順 zyx)だけを
      parallel の向きに合わせる。傾き = (upperarm の尻尾と前腕の X 軸のなす角) - 90、±SWING_LIMIT に制限。
    - "half": ローカル値の打ち消しの向きと parallel の向きの和(二等分)へ aimConstraint で向ける。
    - "elbow": ひねりはローカル値の打ち消し(rx = -120 - twist)、肘の曲げ(lowerarm の rotateY)を尻尾の rotateY で
      打ち消す(回転順 xyz なので X → Y の順に戻る)。左は ry = -肘の曲げ、右は jointOrientX = 180 なので ry = +肘の曲げ。
      upperarm の尻尾と平行になる。
    """
    bone = joints[parent+side]
    if mode == "elbow":
        _localTail(tail, twist)
        bend = _node("unitConversion", tail+"_elbowCancel", conversionFactor=-1 if side == "_l" else 1)
        cmds.connectAttr(joints["lowerarm"+side]+".rotateY", bend+".input")
        cmds.connectAttr(bend+".output", tail+".ry")
        cmds.setAttr(tail+".rz", lock=True)
        return
    if mode == "elbowcone":
        _forearmConeTail(joints, tail, root, side, twist)
        return
    upper_direction = _direction(tail+"_upperDirection", upper_tail, (0, 1, 0))
    if mode == "swing":
        cmds.setAttr(tail+".rotateOrder", 5)
        _localTail(tail, twist)
        between = _node("angleBetween", tail+"_alongBone")
        cmds.connectAttr(upper_direction, between+".vector1")
        cmds.connectAttr(_direction(tail+"_boneAxis", bone, (1, 0, 0)), between+".vector2")
        degrees = _node("unitConversion", tail+"_alongBoneDegrees", conversionFactor=180/math.pi)
        cmds.connectAttr(between+".angle", degrees+".input")
        swing = _node("plusMinusAverage", tail+"_swing")
        cmds.connectAttr(degrees+".output", swing+".input1D[0]")
        cmds.setAttr(swing+".input1D[1]", -90)
        limit = _node("clamp", tail+"_swingLimit", minR=-SWING_LIMIT, maxR=SWING_LIMIT)
        cmds.connectAttr(swing+".output1D", limit+".inputR")
        radians = _node("unitConversion", tail+"_swingRadians", conversionFactor=math.pi/180)
        cmds.connectAttr(limit+".outputR", radians+".input")
        cmds.connectAttr(radians+".output", tail+".rz")
        cmds.setAttr(tail+".ry", lock=True)
        return
    directions = [upper_direction]
    if mode == "half":
        # ローカル値の打ち消しの向きを、同じ位置・同じ親の補助の関節で作る。
        helper = cmds.createNode("joint", name=tail+"_localReference", parent=bone)
        cmds.xform(helper, worldSpace=True, translation=cmds.xform(tail, query=True, worldSpace=True,
                                                                    translation=True))
        cmds.setAttr(helper+".jointOrient", *cmds.getAttr(tail+".jointOrient")[0])
        cmds.setAttr(helper+".drawStyle", 2)
        _localTail(helper, twist)
        directions.append(_direction(tail+"_localDirection", helper, (0, 1, 0)))
    target = _aimTarget(tail+"_aimTarget", joints[root+side], directions)
    cmds.aimConstraint(target, tail, aimVector=(0, 1, 0), upVector=(1, 0, 0), worldUpType="objectrotation",
                       worldUpObject=bone, worldUpVector=(1, 0, 0))


def _referenceJoint(tail, name, twist, bend=None):
    """尻尾と同じ位置・親・jointOrient の補助の関節。rotateX = REST_RX - twist、bend を渡すと rotateY にもつなぐ。"""
    helper = cmds.createNode("joint", name=tail+name, parent=cmds.listRelatives(tail, parent=True)[0])
    cmds.xform(helper, worldSpace=True, translation=cmds.xform(tail, query=True, worldSpace=True, translation=True))
    cmds.setAttr(helper+".jointOrient", *cmds.getAttr(tail+".jointOrient")[0])
    cmds.setAttr(helper+".drawStyle", 2)
    _localTail(helper, twist)
    if bend:
        cmds.connectAttr(bend, helper+".ry")
    return helper


def _forearmConeTail(joints, tail, root, side, twist):
    """案D の向きが前腕の軸に近づいたら、ConeReader の重みの分だけ前腕の軸から離す。

    - d: 案D の向き(rx = ローカル値、ry = -肘の曲げ の補助の関節の Y 軸)。
    - L: ローカル値の打ち消しの向き(rx だけの補助の関節の Y 軸)。前腕の軸と常に直角。
    - a: 尻尾が骨の中を通る前腕の軸の向き(手首の尻尾は -X、肘の尻尾は +X)。
    - w: ConeReader(矢印 = d、コーン = a、半角 FOREARM_CONE、なめらか)の重み。軸上で1、半角で0。
    - d' = cos(半角) a + sin(半角) L: コーンの縁のうち L 側の向き。
    - 尻尾は (1 - w) d + w d' の向きへ aimConstraint(上方向は前腕の X 軸なので、前腕の軸まわりのひねりと
      骨に沿う傾きの2軸)。w = 0 では案D と同じ。
    """
    lowerarm = joints["lowerarm"+side]
    bend = _node("unitConversion", tail+"_elbowCancel", conversionFactor=-1 if side == "_l" else 1)
    cmds.connectAttr(lowerarm+".rotateY", bend+".input")
    d_joint = _referenceJoint(tail, "_dReference", twist, bend+".output")
    l_joint = _referenceJoint(tail, "_localReference", twist)
    name = tail.split("|")[-1]+"_forearmCone"
    reader = ConeReader.create(driverJoint=d_joint, coneJoint=lowerarm, name=name, coneAngle=FOREARM_CONE,
                               driverAxis="y", size=8.0, falloff="smooth")
    # コーンを前腕の軸へ向ける(GRP は lowerarm に重ねてあるので、ローカルの回転だけで決まる)。
    cmds.setAttr(reader.cone+".rotate", 0, 180 if root == "hand" else 0, 0)
    for group in (name+"_driver_GRP", name+"_cone_GRP"):
        cmds.setAttr(group+".visibility", False)
    d = _direction(tail+"_dDirection", d_joint, (0, 1, 0))
    local = _direction(tail+"_localDirection", l_joint, (0, 1, 0))
    axis = _direction(tail+"_coneAxis", lowerarm, (-1 if root == "hand" else 1, 0, 0))
    edge = _node("plusMinusAverage", tail+"_coneEdge")
    for i, (vector, factor) in enumerate(((axis, math.cos(math.radians(FOREARM_CONE))),
                                          (local, math.sin(math.radians(FOREARM_CONE))))):
        scaled = _node("multiplyDivide", "{}_coneEdge{}".format(tail, i))
        cmds.connectAttr(vector, scaled+".input1")
        cmds.setAttr(scaled+".input2", factor, factor, factor)
        cmds.connectAttr(scaled+".output", edge+".input3D[{}]".format(i))
    blend = _node("blendColors", tail+"_conePush")
    cmds.connectAttr(name+".weight", blend+".blender")
    cmds.connectAttr(edge+".output3D", blend+".color1")
    cmds.connectAttr(d, blend+".color2")
    target = _aimTarget(tail+"_aimTarget", joints[root+side], [blend+".output"])
    cmds.aimConstraint(target, tail, aimVector=(0, 1, 0), upVector=(1, 0, 0), worldUpType="objectrotation",
                       worldUpObject=lowerarm, worldUpVector=(1, 0, 0))


def _localTail(tail, twist):
    """尻尾の rotateX = REST_RX - twist(度)をつなぐ。"""
    value = _node("plusMinusAverage", tail+"_cancel", operation=2)
    cmds.setAttr(value+".input1D[0]", REST_RX)
    cmds.connectAttr(twist, value+".input1D[1]")
    radians = _node("unitConversion", tail+"_radians", conversionFactor=math.pi/180)
    cmds.connectAttr(value+".output1D", radians+".input")
    cmds.connectAttr(radians+".output", tail+".rx")


def build(prefix, offset, cancel):
    """Aポーズの骨格と6本の尻尾を作る。

    Args:
        cancel (bool | str): False は打ち消しなし、True(または "cancel")はスイング・ツイスト分解の打ち消し、
            "local" はローカルの rotateX の値の合算での打ち消し。"parallel"・"swing"・"half" は、upperarm の
            尻尾はローカル値の打ち消しのまま、肘・手首の尻尾に交差を防ぐスイングを足す(_fixTail)。

    Returns:
        dict: joints、tails(名前 → (尻尾, 親の骨))、twists(骨 → ツイスト角のプラグ)、rest(初期の向き)。
    """
    result = humanoid.build(prefix=prefix, pose="A")
    joints = result["joints"]
    cmds.setAttr(prefix+"humanProxy_mat.transparency", 0.6, 0.6, 0.6, type="double3")
    cmds.setAttr(result["root"]+".tx", offset)
    for side in SIDES:
        # 肘は一般的な IK を想定した1軸(lowerarm は rotateY だけ)。
        for attr in ("rx", "rz"):
            cmds.setAttr(joints["lowerarm"+side]+"."+attr, lock=True)
    tails, twists, rest = {}, {}, {}
    avoid = cancel == "avoid"
    if avoid:
        cancel = "elbowcone"
    local = cancel in ("local", "parallel", "swing", "half", "elbow", "elbowcone")
    fix = cancel if cancel in ("parallel", "swing", "half", "elbow", "elbowcone") else None
    deltas = {}
    if avoid:
        deltas = _bodyAvoid(prefix, joints, offset)
    for side in SIDES:
        clavicle = joints["clavicle"+side]
        if local:
            twists.update(localTwistPlugs(prefix, joints, side))
        if side in deltas:
            # 尻尾の rotateX = -120 - twist なので、twist から Δ を引くと3本とも Δ だけ回る。
            for bone in ("upperarm", "lowerarm"):
                twists[bone+side] = _node_sum(prefix+bone+side+"_avoidTwist", twists[bone+side],
                                              deltas[side]["delta"])
        for bone in ("upperarm", "lowerarm"):
            if cancel and not local:
                twists[bone+side] = twistPlug(prefix+bone+side, joints[bone+side], clavicle)
            # 検査用: 鎖骨の空間での骨の X 軸。
            m = _matrix(joints[bone+side])*_matrix(clavicle).inverse()
            rest["bone:"+bone+side] = om.MVector(m[0], m[1], m[2]).normal()
        for kind, parent, root, color in TAILS:
            tail = _tail(prefix, joints, kind, parent, root, side, color)
            tails[kind+side] = (tail, parent+side)
            m = _matrix(tail)*_matrix(clavicle).inverse()
            rest[kind+side] = om.MVector(m[4], m[5], m[6]).normal()
            if fix and kind != "upperarm":
                _fixTail(prefix, joints, tail, parent, root, side, fix, tails["upperarm"+side][0],
                         twists[parent+side])
                continue
            if cancel:
                _localTail(tail, twists[parent+side])
            for attr in ("ry", "rz"):
                cmds.setAttr(tail+"."+attr, lock=True)
    return {"joints": joints, "tails": tails, "twists": twists, "rest": rest, "avoid": deltas}


def _node_sum(name, plug, minus):
    """plug - minus のプラグ。"""
    node = _node("plusMinusAverage", name, operation=2)
    cmds.connectAttr(plug, node+".input1D[0]")
    cmds.connectAttr(minus, node+".input1D[1]")
    return node+".output1D"


def _bodyAvoid(prefix, joints, offset):
    """当たり判定の球と胴の中心を作り、左右それぞれの共通の回避角 Δ を tail_shared_avoid で作る。

    胴がいる方向の平均 m は、upperarm の rotateY・rotateZ を振って、ひねりを打ち消した空間 F の中の胴の方向
    から求める(F は rotateX = 0 の upperarm の空間と同じ)。

    Returns:
        dict: 側(_l/_r) → buildDelta の戻り値。
    """
    import demo_humanoid_tail_avoid
    original = demo_humanoid_tail_avoid.BODY
    demo_humanoid_tail_avoid.BODY = AVOID_BODY
    try:
        balls = demo_humanoid_tail_avoid._bodyBalls(prefix, joints, offset)
    finally:
        demo_humanoid_tail_avoid.BODY = original
    center = cmds.spaceLocator(name=prefix+"torsoCenter_LOC")[0]
    cmds.xform(center, worldSpace=True, translation=(TORSO_CENTER[0]+offset, TORSO_CENTER[1], TORSO_CENTER[2]))
    center = cmds.parent(center, joints["spine_02"])[0]
    cmds.setAttr(center+".visibility", False)
    result = {}
    for side in SIDES:
        upperarm = joints["upperarm"+side]
        sines, cosines = 0.0, 0.0
        for ry in range(-120, 121, 20):
            for rz in range(-120, 121, 20):
                cmds.setAttr(upperarm+".rotate", 0, ry, rz)
                p = om.MPoint(*cmds.xform(center, query=True, worldSpace=True, translation=True))*_matrix(upperarm).inverse()
                angle = math.atan2(p.z, p.y)
                sines, cosines = sines+math.sin(angle), cosines+math.cos(angle)
        cmds.setAttr(upperarm+".rotate", 0, 0, 0)
        mean = math.degrees(math.atan2(sines, cosines))
        rest = REST_RX+(180 if side == "_r" else 0)
        roots = [joints[name+side] for name in ("upperarm", "lowerarm", "hand")]
        result[side] = tail_shared_avoid.buildDelta(prefix+"avoid"+side+"_", upperarm, roots, balls, center, mean,
                                                    rest, TAIL_LENGTH)
        result[side]["mean"] = mean
    return result


def _bodyMeshes(prefix):
    """体のプロキシの MFnMesh(ワールドで交差を調べる)。"""
    result = []
    for name in BODY_PROXIES:
        shape = cmds.listRelatives(prefix+name+"_proxy", shapes=True, fullPath=True)[0]
        result.append(om.MFnMesh(om.MSelectionList().add(shape).getDagPath(0)))
    return result


def bodyHit(tail, meshes):
    """尻尾の線分が体のプロキシの面を横切るか(リグと独立)。横切る点までの長さ(cm)、なければ None。"""
    m = cmds.xform(tail, query=True, worldSpace=True, matrix=True)
    origin, direction = om.MFloatPoint(*m[12:15]), om.MFloatVector(*m[4:7]).normal()
    nearest = None
    for fn in meshes:
        hit = fn.anyIntersection(origin, direction, om.MSpace.kWorld, TAIL_LENGTH, False)
        if hit and hit[0] is not None and hit[1] > 0:
            nearest = hit[1] if nearest is None else min(nearest, hit[1])
    return nearest


def segmentDistance(first, second):
    """2本の尻尾の線分の最短距離(cm)。"""
    ends = []
    for tail in (first, second):
        m = cmds.xform(tail, query=True, worldSpace=True, matrix=True)
        root = om.MVector(*m[12:15])
        ends.append((root, root+om.MVector(*m[4:7]).normal()*TAIL_LENGTH))
    (p1, q1), (p2, q2) = ends
    d1, d2, r = q1-p1, q2-p2, p1-p2
    a, e, f, c, b = d1*d1, d2*d2, d2*r, d1*r, d1*d2
    den = a*e-b*b
    s = min(1.0, max(0.0, (b*f-c*e)/den)) if den > 1e-9 else 0.0
    t = (b*s+f)/e
    if t < 0:
        t, s = 0.0, min(1.0, max(0.0, -c/a))
    elif t > 1:
        t, s = 1.0, min(1.0, max(0.0, (b-c)/a))
    return ((p1+d1*s)-(p2+d2*t)).length()


def _swingError(rig, key, side):
    """ツイストなしの向き(骨の軸を最短で回した回転を初期の尻尾の向きにかけた向き)と実際の向きの角度差(度)。"""
    tail, bone = rig["tails"][key]
    clavicle = _matrix(rig["joints"]["clavicle"+side]).inverse()
    m = _matrix(rig["joints"][bone])*clavicle
    axis = om.MVector(m[0], m[1], m[2]).normal()
    swing = om.MQuaternion(rig["rest"]["bone:"+bone], axis)
    expected = rig["rest"][key].rotateBy(swing)
    m = _matrix(tail)*clavicle
    actual = om.MVector(m[4], m[5], m[6]).normal()
    return math.degrees(expected.angle(actual))


def _twistAngle(rig, bone, side):
    """リグと独立に求めた、骨の鎖骨から見たツイスト角(度)。初期の X 軸から最短で回した向きとの Y 軸の差。"""
    clavicle = _matrix(rig["joints"]["clavicle"+side]).inverse()
    m = _matrix(rig["joints"][bone+side])*clavicle
    axis = om.MVector(m[0], m[1], m[2]).normal()
    y = om.MVector(m[4], m[5], m[6]).normal()
    rest = om.MMatrix(rig["restBone"][bone+side])
    swing = om.MQuaternion(rig["rest"]["bone:"+bone+side], axis)
    rest_y = om.MVector(rest[4], rest[5], rest[6]).normal().rotateBy(swing)
    return math.degrees(math.atan2((rest_y ^ y)*axis, rest_y*y))


def main(record=True, motion="wave", view="back"):
    """打ち消しなし・ありの2体を同じ腕の動きで動かし、録画して検査する。

    Args:
        record (bool): False なら録画せず、タイムラインで確認できるシーンを作る。
        motion (str): "wave" は sin で振る動き、"problem" は調査で食い込みが多かった姿勢を通る動き、
            "cross" は肘を90度以上曲げたまま upperarm をひねる動き(尻尾どうしの交差)。"cross_fix"・
            "problem_fix" は同じ動きで、交差を防ぐ案(FIX_METHODS)を比べる。
        view (str): "back" は斜め後ろからの透視投影、"top" は真上・"front" は正面からの平行投影。
    """
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    if PANEL in cmds.getPanel(allPanels=True):
        cmds.deleteUI(PANEL, panel=True)
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW, window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")
    for plugin in ("matrixNodes", "quatNodes"):
        if not cmds.pluginInfo(plugin, query=True, loaded=True):
            cmds.loadPlugin(plugin, quiet=True)

    methods = (FIX_METHODS if motion.endswith("_fix") else CONE_METHODS if motion.endswith("_cone") else
               AVOID_METHODS if motion.endswith("_avoid") else
               LOCAL_METHODS if motion in ("problem", "cross") else METHODS)
    base = motion.replace("_fix", "").replace("_cone", "").replace("_avoid", "")
    keys = {"problem": PROBLEM_KEYS, "cross": CROSS_KEYS, "align": ALIGN_KEYS}.get(base, ())
    rigs = {}
    for i, (key, _, _) in enumerate(methods):
        # 1列目(打ち消しなし)が画面の左に来るように置く。真上・正面からは +X が画面の右、斜め後ろからは左右が反転する。
        rig = build(key+"_", (i-(len(methods)-1)/2.0)*SPACING*(-1 if view == "back" else 1),
                    {"raw": False, "cancel": True}.get(key, key))
        rig["meshes"] = _bodyMeshes(key+"_")
        rig["restBone"] = {}
        for side in SIDES:
            clavicle = _matrix(rig["joints"]["clavicle"+side]).inverse()
            for bone in ("upperarm", "lowerarm"):
                rig["restBone"][bone+side] = list(_matrix(rig["joints"][bone+side])*clavicle)
        for side in SIDES if keys else ():
            for frame, rx, ry, rz, bend in keys:
                for joint, attr, value in (("upperarm", "rx", rx), ("upperarm", "ry", ry), ("upperarm", "rz", rz),
                                           ("lowerarm", "ry", bend)):
                    cmds.setKeyframe(rig["joints"][joint+side], attribute=attr, time=frame, value=value)
        for joint, attr, amplitude, period, phase, middle in MOTION if motion == "wave" else ():
            for side in SIDES:
                for frame in range(0, COUNT, 3):
                    value = middle+amplitude*math.sin(2*math.pi*frame/period+phase)
                    cmds.setKeyframe(rig["joints"][joint+side], attribute=attr, time=frame+1, value=value)
        rigs[key] = rig
    cmds.playbackOptions(minTime=1, maxTime=COUNT)

    if view == "top":
        # 真上から見下ろす。画面の右が +X、画面の上が -Z(体の後ろ)。
        camera, camera_shape = cmds.camera(name="tailTwistCamera", orthographic=True)
        cmds.setAttr(camera+".translate", 0, 400, -10)
        cmds.setAttr(camera+".rotate", -90, 0, 0)
        cmds.setAttr(camera_shape+".orthographicWidth", SPACING*len(methods)+150)
    elif view == "front":
        # 正面から見る。画面の右が +X(キャラクターの左)。
        camera, camera_shape = cmds.camera(name="tailTwistCamera", orthographic=True)
        cmds.setAttr(camera+".translate", 0, 115, 400)
        cmds.setAttr(camera_shape+".orthographicWidth", SPACING*len(methods)+150)
    else:
        camera, camera_shape = cmds.camera(name="tailTwistCamera")
        if len(methods) <= 2:
            cmds.setAttr(camera+".translate", 250, 230, -330)
            cmds.setAttr(camera+".rotate", -14, 142, 0)
            cmds.setAttr(camera_shape+".focalLength", 30)
        else:
            # 3列以上は、後ろ寄りの斜め上から全員が同じくらいの大きさで並ぶようにする。
            cmds.setAttr(camera+".translate", 190, 290, -620)
            cmds.setAttr(camera+".rotate", -15, 163, 0)
            cmds.setAttr(camera_shape+".focalLength", 32)
    if cmds.windowPref(WINDOW, exists=True):
        cmds.windowPref(WINDOW, remove=True)
    window = cmds.window(WINDOW, widthHeight=(1600, 860))
    pane = cmds.paneLayout(parent=window)
    panel = cmds.modelPanel(PANEL, parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", grid=view == "back", cameras=False, joints=True,
                     headsUpDisplay=True, manipulators=False, selectionHiliteDisplay=False, locators=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1600, 860))
    cmds.setFocus(panel)
    cmds.select(clear=True)
    demo_interactive.clearHuds(window)
    texts = {}
    for column, section in enumerate({2: (0, 4), 3: (0, 2, 4), 4: (0, 1, 3, 4)}[len(methods)]):
        for row in range(3):
            for prefix, base, block in (("twistTop", section, row), ("twistBottom", section+5, 2-row)):
                name = "{}{}_{}".format(prefix, column, row)
                texts[name] = ""
                cmds.headsUpDisplay(name, section=base, block=block, blockSize="large", dataFontSize="large",
                                    command=lambda n=name: texts[n])

    last = {}

    def evaluate(frame):
        """尻尾ごとに、ツイストなしの向きとの角度差・体との交差・1フレームの向きの変化を測る。"""
        demo_interactive.setTime(frame)
        result = {"frame": frame}
        for key, _, _ in methods:
            rig = rigs[key]
            errors = {name: _swingError(rig, name, name[-2:]) for name in rig["tails"]}
            twists = {bone+side: _twistAngle(rig, bone, side) for bone in ("upperarm", "lowerarm") for side in SIDES}
            result[key] = {"swing_error_degrees": errors, "twist_degrees": twists,
                           "tail_rx": {name: cmds.getAttr(tail+".rx") for name, (tail, _) in rig["tails"].items()}}
            result[key]["body_hit_cm"] = {name: bodyHit(tail, rig["meshes"]) for name, (tail, _) in rig["tails"].items()}
            steps = {}
            for name, (tail, _) in rig["tails"].items():
                m = cmds.xform(tail, query=True, worldSpace=True, matrix=True)
                direction = om.MVector(*m[4:7]).normal()
                previous = last.get((key, name))
                steps[name] = math.degrees(previous.angle(direction)) if previous is not None and frame > 0 else 0.0
                last[(key, name)] = direction
            result[key]["step_degrees"] = steps
            tails = rig["tails"]
            result[key]["tail_distance_cm"] = {
                pair: segmentDistance(tails[pair.split("-")[0]+"_l"][0], tails[pair.split("-")[1]+"_l"][0])
                for pair in ("upperarm-hand", "upperarm-elbow", "elbow-hand")}
            if key == "cancel":
                result[key]["rig_twist_degrees"] = {bone: cmds.getAttr(plug) for bone, plug in rig["twists"].items()}
        result["ok"] = "cancel" not in result or max(result["cancel"]["swing_error_degrees"].values()) < 0.1
        if "local" in rigs:
            # ローカル方式は尻尾の rotateX が -120 - (合算した rotateX) になっているか。
            j = rigs["local"]["joints"]
            expected = {"upperarm": ("upperarm",), "elbow": ("upperarm", "lowerarm"), "hand": ("upperarm", "lowerarm")}
            result["local"]["rx_error"] = max(
                abs(result["local"]["tail_rx"][kind+side]-(REST_RX-sum(cmds.getAttr(j[b+side]+".rx") for b in bones)))
                for kind, bones in expected.items() for side in SIDES)
            result["ok"] = result["ok"] and result["local"]["rx_error"] < 1e-3
        for key in ("parallel", "swing", "half", "elbow", "elbowcone", "avoid"):
            if key not in rigs:
                continue
            # 案ごとの形の検査(リグと独立)。尻尾と upperarm の尻尾のなす角、尻尾と自分の骨のなす角。
            info = {}
            for kind in ("elbow", "hand"):
                for side in SIDES:
                    tail, bone = rigs[key]["tails"][kind+side]
                    upper = rigs[key]["tails"]["upperarm"+side][0]
                    m, u = _matrix(tail), _matrix(upper)
                    b = _matrix(rigs[key]["joints"][bone])
                    direction = om.MVector(m[4], m[5], m[6]).normal()
                    info[kind+side] = {
                        "angle_to_upper_tail": math.degrees(direction.angle(om.MVector(u[4], u[5], u[6]))),
                        "angle_to_bone": math.degrees(direction.angle(om.MVector(b[0], b[1], b[2])))}
            result[key]["shape"] = info
            if key in ("elbowcone", "avoid"):
                result[key]["cone_weight"] = {kind+side: cmds.getAttr(
                    "{}_tail_{}{}_forearmCone.weight".format(key, kind, side)) for kind in ("elbow", "hand")
                    for side in SIDES}
            if key == "avoid":
                result[key]["delta"] = {side: {name: cmds.getAttr(plug) for name, plug in values.items()
                                               if isinstance(plug, str)}
                                        for side, values in rigs[key]["avoid"].items()}
            if key in ("parallel", "elbow"):
                result["ok"] = result["ok"] and max(v["angle_to_upper_tail"] for v in info.values()) < 0.5
        for column, (key, title, formula) in enumerate(methods):
            r = result[key]
            worst = max(r["swing_error_degrees"].values())
            texts["twistTop{}_0".format(column)] = title
            texts["twistTop{}_1".format(column)] = formula
            hits = sorted(name for name, value in r["body_hit_cm"].items() if value is not None)
            if motion.startswith(("cross", "align")) or motion.endswith("_cone"):
                gaps = r["tail_distance_cm"]
                crossed = [pair for pair, value in gaps.items() if value < CROSS_DISTANCE]
                texts["twistTop{}_2".format(column)] = "upper-hand {:.1f}cm  upper-elbow {:.1f}cm{}".format(
                    gaps["upperarm-hand"], gaps["upperarm-elbow"], "  CROSS!" if crossed else "")
            else:
                deep = sorted(name for name, value in r["body_hit_cm"].items()
                              if value is not None and value > ROOT_ZONE)
                near = sorted(name for name, value in r["body_hit_cm"].items()
                              if value is not None and value <= ROOT_ZONE)
                texts["twistTop{}_2".format(column)] = "BODY HIT: {}{}".format(
                    ", ".join(deep) if deep else "none", "  (near root: {})".format(len(near)) if near else "")
            spin = max(r["step_degrees"].values())
            texts["twistBottom{}_2".format(column)] = "twist-free diff {:.0f} deg  max turn {:.1f} deg/frame".format(
                worst, spin)
            texts["twistBottom{}_0".format(column)] = "twist(swing-twist)  upper {:+.0f}  lower {:+.0f}".format(
                r["twist_degrees"]["upperarm_l"], r["twist_degrees"]["lowerarm_l"])
            texts["twistBottom{}_1".format(column)] = "tail rx  upper {:.0f}  elbow {:.0f}  hand {:.0f}".format(
                r["tail_rx"]["upperarm_l"], r["tail_rx"]["elbow_l"], r["tail_rx"]["hand_l"])
            if "delta" in r:
                v = r["delta"]["_l"]
                texts["twistBottom{}_0".format(column)] = "delta {:+.0f}  blocked {:.0f}..{:.0f}  w {:.2f}".format(
                    v["delta"], v["low"], v["high"], v["weight"])
            elif motion.endswith(("_fix", "_cone", "_avoid")):
                shape = r.get("shape", {}).get("hand_l")
                cone = r.get("cone_weight", {}).get("hand_l")
                texts["twistBottom{}_0".format(column)] = (
                    "hand tail: to upper tail {:.0f}  to forearm {:.0f} deg{}".format(
                        shape["angle_to_upper_tail"], shape["angle_to_bone"],
                        "  w {:.2f}".format(cone) if cone is not None else "") if shape else
                    "hand/elbow tails: rotateX only")
            if column == 0:
                texts["twistTop{}_1".format(column)] = formula+"  arm {:.0f} {:.0f} {:.0f} / {:.0f}".format(
                    *cmds.getAttr(rigs[key]["joints"]["upperarm_l"]+".rotate")[0],
                    cmds.getAttr(rigs[key]["joints"]["lowerarm_l"]+".ry"))
        for name in texts:
            cmds.headsUpDisplay(name, refresh=True)
        return result

    if not record:
        demo_interactive.attachInteractive(window, COUNT, evaluate)
        logger.info("尻尾のツイスト打ち消しのシーンを作成しました。タイムラインで確認できます。")
        return
    title = "全身骨格(Aポーズ): 腕のツイストを打ち消す尻尾（初期 rx=-120）"
    if motion == "problem":
        title += "・食い込みが多い姿勢"
    elif motion == "cross":
        title += "・肘を曲げてひねると尻尾どうしが交差"
    elif motion == "cross_fix":
        title += "・尻尾どうしの交差を防ぐ案(交差する動き)"
    elif motion == "problem_fix":
        title += "・尻尾どうしの交差を防ぐ案(食い込みが多い姿勢)"
    elif motion.endswith("_cone"):
        title += "・案Dと前腕のConeReader({})".format(base)
    elif motion.endswith("_avoid"):
        title += "・案D＋前腕のコーン＋3本共通の体の回避({})".format(base)
    folder = recordVideo(title+{"top": "・上面", "front": "・正面"}.get(view, ""), COUNT, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1600, height=860)
    cmds.file(rename=str(folder/"tail-twist-cancel-{}-{}.ma".format(motion, view)))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-tail-twist-cancel-{}-{}.json".format(
        motion, view)).write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("尻尾のツイスト打ち消しの検証に失敗: {}".format(folder))
    logger.info("尻尾のツイスト打ち消しの検証を保存しました: {}".format(folder))
    return folder


if __name__ == "__main__":
    main()
