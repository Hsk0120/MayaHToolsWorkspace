"""hip〜l_lowerArm のチェーンと3つの球の体で、尻尾1軸回避を複雑な動きで検証する。

ジョイントは hip・spine0・spine1・spine2・l_shoulder・l_upperArm・l_lowerArm。体は
hip・spine1(お腹)・spine2(胸)に付けた3つの球で近似し、尻尾は肘(l_lowerArm)から
前腕の軸(ローカルX)まわりの rotateX だけで回す。背骨のひねり・曲げ、肩の上げ下げ、
腕の振り・肘の曲げを周期の違う正弦波で重ね、尻尾の入力は体の中心を両側から越える。

各ジョイントの回転は個別に使わず、球の中心を前腕の空間へ移した値だけを使う。
ワールド行列を通すので、チェーンの動きはすべてここに反映される。

    球kごと: ρ=√((R+gap)²-cx²)、d=√(cy²+cz²)、中心角 θ=atan2(cz,cy)、半幅 asin(ρ/d)
    塞がれる範囲 [θ-半幅, θ+半幅] を、回転面と交わる球について合わせる:
        A=min(θ-半幅)、B=max(θ+半幅)、中心 c=(A+B)/2、半幅 H=(B-A)/2
    外向き=c+180、折り返さない相対角 rel=rx-外向き、接線 L=180-H

- 球の接線止め: 出力 = 外向き + clamp(rel, -L, L)。
- UE RBF: ドライバー (rel/20, H/10) のポーズ補間(なだらかに避ける値)。最後に clamp。
  範囲は下の soft で求める(球の交わり始めでドライバーが跳ばないようにする)。

交わる球が一つもなければ入力を通す。球が回転面と交わり始めた瞬間、その球の
中心角が今の範囲の外にあると範囲が広がって出力が跳ぶことがあり、検査で記録する。

球は肘から見ると、頂点が肘・軸が球の中心方向・半角 asin((R+gap)/距離) のコーンになり、
上の範囲はこのコーンを回転面で切った幅と一致する。case="cone_c" では、このコーンの角度を
固定値 γ0、または距離の比で補正した γ0·d0/d に置き換えたコーンドライバー版と比べる。

跳びの対策(soft): 球ごとの掛かり具合 q=(R+gap-|cx|)/(R+gap)(回転面が球に入り込んだ
深さ。掛かり始め0、中心で1)から重み w=smoothstep(q/0.25) を求め、範囲へ足すときに「足す前」と「足した後」を w で
混ぜる。掛かり始めは w=0 なので範囲が変わらず跳ばない。代わりに浅く掛かっている
間は、その球の手前まで寄りきらず少し食い込むことがある。
"""

import json
import math
import os
from pathlib import Path

from maya import cmds
import maya.api.OpenMaya as om
from mlib import logger
from demo_top_view_moving_tangent import _line, _node, _connect
from demo_joint_twist_tangent import _sum, _multiply, _condition, _sqrt, _degrees
from demo_joint_sweep_compare import _compare, _divide, _clampRange, _tail
import demo_joint_rbf_pose
from demo_joint_rbf_pose import poseValue
from verification_video import recordVideo
import demo_interactive

GAP = 0.03
LENGTH = 8.0
SPACING = 26.0
COLUMN_SHIFT = -3.0
SEGMENT_FRAMES = 30
REL_STEP = 20.0
H_STEP = 10.0
REL_RANGE = 17
H_RANGE = 10
RBF_RADIUS = 0.7
# 掛かり具合 q(回転面が球に入り込んだ深さの割合)がこの値以上で、球の範囲を完全に効かせる。
SOFT_FULL = 0.25

# (名前, 親, 位置(親からの移動)) 。lowerArm 以外は向きなし(ワールド軸)。
JOINTS = [
    ("hip", None, (0, 10, 0)),
    ("spine0", "hip", (0, 1.5, 0)),
    ("spine1", "spine0", (0, 1.5, 0)),
    ("spine2", "spine1", (0, 1.5, 0)),
    ("l_shoulder", "spine2", (1.5, 1.6, 0)),
    ("l_upperArm", "l_shoulder", (2.0, 0, 0)),
    ("l_lowerArm", "l_upperArm", (0, -4.0, 0)),
]
# (球の名前, 付けるジョイント, 中心のオフセット, 半径)
BODY = [("hipBall", "hip", (0, 0, 0), 2.3), ("bellyBall", "spine1", (0, 0, 0.2), 2.3),
        ("chestBall", "spine2", (0, 0.6, 0.1), 2.6)]
# (ジョイント, 軸, 振幅deg, 周期frame, 位相rad, 中心deg)。周期の違う正弦波を重ねる。
MOTION = [
    ("hip", "ry", 20, 240, 0.0, 0), ("spine0", "rx", 10, 170, 0.5, 0), ("spine0", "rz", 10, 200, 0.0, 0),
    ("spine1", "ry", 12, 260, 1.0, 0), ("spine2", "rx", 10, 300, 0.0, 0), ("spine2", "rz", 8, 150, 2.0, 0),
    ("l_shoulder", "rz", 12, 220, 0.0, 0), ("l_upperArm", "rx", 30, 180, 0.0, 0),
    ("l_upperArm", "rz", 12, 260, 0.0, 20), ("l_lowerArm", "ry", 15, 200, 1.5, 0),
]
# 尻尾の入力。外向き基準の折り返さない相対角(deg)と段階名。
INPUT = [
    (-40, "1 INITIAL"), (-40, "2 ENTER FROM +"), (100, "2 ENTER FROM +"), (180, "2 ENTER FROM +"),
    (205, "2 ENTER FROM +"), (205, "3 BACK"), (-40, "3 BACK"), (-40, "4 ENTER FROM -"),
    (-180, "4 ENTER FROM -"), (-205, "4 ENTER FROM -"), (-205, "5 BACK"), (170, "6 HOLD NEAR CENTER"),
    (190, "6 HOLD NEAR CENTER"), (170, "6 HOLD NEAR CENTER"), (190, "6 HOLD NEAR CENTER"),
    (170, "7 KEEP TWISTING +"), (290, "7 KEEP TWISTING +"), (290, "8 RETURN"), (-40, "8 RETURN"),
]
# 交わり始めのケースだけ、hipの下・外側・少し前に太ももの球を足す。体の球と方向が
# 離れているので、先に交わり始めると塞がれる範囲が一気に広がる。
BODY_ACTIVATION = BODY+[("thighBall", "hip", (1.6, -3.0, 0.8), 1.6)]
# 球が回転面と交わり始める瞬間を起こすケース。背骨を前に曲げ(胸の球が前へ出る)、
# 腕を前へ大きく振って回転面を球から離し、戻すときに球が順に交わり始める。
# 尻尾は -側/+側の接線に当てて待たせ、範囲が広がったときの出力の跳びを測る。
MOTION_ACTIVATION = [
    ("spine0", "rx", 0, 1, 0.0, 20), ("l_upperArm", "rz", 0, 1, 0.0, 20),
    ("l_upperArm", "rx", 35, 240, math.pi/2, -35),
]
INPUT_ACTIVATION = [
    (-40, "1 INITIAL"), (-170, "2 REST ON - TANGENT"), (-170, "2 REST ON - TANGENT"),
    (-170, "2 REST ON - TANGENT"), (-170, "2 REST ON - TANGENT"), (-170, "2 REST ON - TANGENT"),
    (-170, "2 REST ON - TANGENT"), (-170, "2 REST ON - TANGENT"), (-170, "2 REST ON - TANGENT"),
    (170, "3 REST ON + TANGENT"), (170, "3 REST ON + TANGENT"), (170, "3 REST ON + TANGENT"),
    (170, "3 REST ON + TANGENT"), (170, "3 REST ON + TANGENT"), (170, "3 REST ON + TANGENT"),
    (170, "3 REST ON + TANGENT"), (170, "3 REST ON + TANGENT"), (-40, "4 RETURN"),
]
# 列の並び。(キー, 見出し, 式の要約, 出力の色, 種類)。種類は input/keep/soft/rbf。
METHODS = [
    ("input", "INPUT (red)", "hip/spine0-2/shoulder/upperArm/lowerArm", None, "input"),
    ("keep", "3 SPHERES: tangent stop", "clamp(rel,-L,L), L=180-H", (1, 0.5, 0.1), "keep"),
    ("rbf", "UE RBF: pose interpolation (soft entry)", "clamp(sum(w_i*pose_i),-L,L)", (0.1, 1, 0.1), "rbf"),
]
SOFT_METHODS = [
    ("input", "INPUT (red)", "hip/spine0-2/shoulder/upperArm/lowerArm", None, "input"),
    ("keep", "BEFORE: hard union", "union = min/max of all cut balls", (1, 0.5, 0.1), "keep"),
    ("soft", "AFTER: soft entry", "blend ball in by w=smoothstep(q/0.25)", (0.1, 1, 0.1), "soft"),
    ("rbf", "AFTER: UE RBF (soft entry)", "clamp(sum(w_i*pose_i),-L,L)", (0.2, 0.9, 1), "rbf"),
]
# 範囲をなだらかに合わせる(soft)列の種類。
SOFT_KINDS = ("soft", "rbf", "rbf_cone_fixed", "rbf_cone")
# UE RBF で後半を作る列の種類。
RBF_KINDS = ("rbf", "rbf_cone_fixed", "rbf_cone")
# ケース名 → (動き, 尻尾の入力, 体の球, 列, 録画の題名, 保存名)
CASES = {
    "mixed": (MOTION, INPUT, BODY, METHODS,
              "尻尾1軸回避: hip〜l_lowerArmのチェーンと3球の体（球の接線止めとUE RBF）", "joint-chain-rbf"),
    "activation": (MOTION_ACTIVATION, INPUT_ACTIVATION, BODY_ACTIVATION, METHODS,
                   "尻尾1軸回避: 球が回転面と交わり始める瞬間の跳び（チェーンと3球）", "joint-chain-activation"),
    "soft_entry": (MOTION_ACTIVATION, INPUT_ACTIVATION, BODY_ACTIVATION, SOFT_METHODS,
                   "尻尾1軸回避: 球の交わり始めをなだらかに効かせて跳びを防ぐ（直す前と後）", "joint-chain-soft-entry"),
}
CONE_METHODS = [
    ("input", "INPUT (red)", "classic cone weight shown for reference", None, "input"),
    ("rbf", "A: spheres (auto cone)", "gamma = asin(R/d)", (1, 0.5, 0.1), "rbf"),
    ("fixed", "C: fixed cone angle", "gamma = gamma0 (rest pose)", (0.1, 1, 0.1), "rbf_cone_fixed"),
    ("cone", "C: distance-corrected cone", "gamma = gamma0 * d0 / d", (0.2, 0.9, 1), "rbf_cone"),
]
CASES["cone_c"] = (MOTION, INPUT, BODY, CONE_METHODS,
                   "尻尾1軸回避: 前半を肘からのコーンで近似（球・固定角・距離補正）", "joint-chain-cone-c")
# 列数ごとのHUDの区画。区画0〜4は画面の左から右。
HUD_SECTIONS = {3: (0, 2, 4), 4: (0, 1, 3, 4)}
WINDOW = "chainRbfWindow"
PANEL = "chainRbfPanel"


def _minimum(name, a, b):
    """2つのプラグの小さい方。"""
    return _compare(name, a, b, a, b, operation=4)


def _maximum(name, a, b):
    """2つのプラグの大きい方。"""
    return _compare(name, a, b, a, b, operation=2)


def _lowerArmOrient():
    """前腕の向き。X=前(+Z)、Y=体の内側(-X)、Z=下(-Y) になる jointOrient(度)。"""
    matrix = om.MMatrix([0, 0, 1, 0, -1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 0, 1])
    rotation = om.MTransformationMatrix(matrix).rotation()
    return [math.degrees(v) for v in (rotation.x, rotation.y, rotation.z)]


def _buildRig(prefix, index, material_group, body=BODY, columns=3):
    """1列ぶんのチェーン・体の球・尻尾を作る。

    Returns:
        dict: joints(名前→ノード)、balls(球のtransformと半径)、source、group。
    """
    group = cmds.createNode("transform", name=prefix+"Column_GRP")
    cmds.setAttr(group+".tx", (index-(columns-1)/2.0)*SPACING+COLUMN_SHIFT)
    joints = {}
    for name, parent, offset in JOINTS:
        node = cmds.createNode("joint", name=prefix+"_"+name, parent=joints[parent] if parent else group)
        cmds.setAttr(node+".translate", *offset)
        cmds.setAttr(node+".radius", 0.3)
        joints[name] = node
    cmds.setAttr(joints["l_lowerArm"]+".jointOrient", *_lowerArmOrient())
    _line(prefix+"Forearm", [(0, 0, 0), (3.5, 0, 0)], (0.1, 0.65, 1), joints["l_lowerArm"])
    balls = []
    for name, parent, offset, radius in body:
        sphere = cmds.polySphere(name=prefix+"_"+name, radius=radius, subdivisionsX=32, subdivisionsY=20,
                                constructionHistory=False)[0]
        sphere = cmds.parent(sphere, joints[parent], relative=True)[0]
        cmds.setAttr(sphere+".translate", *offset)
        cmds.sets(sphere, edit=True, forceElement=material_group)
        balls.append((sphere, radius))
    source = _tail(prefix+"TailInput_JNT", (1, 0.1, 0.1), joints["l_lowerArm"])
    cmds.setAttr(source+".displayLocalAxis", False)
    return {"group": group, "joints": joints, "balls": balls, "source": source}


def coneParameters(rig, corrected):
    """初期姿勢での肘から各部位までの距離から、コーンの角度の基準値を決める。

    γ0=asin((R+gap)/d0)。補正ありは γ=γ0·d0/d(距離の比で伸び縮み)。球のコーン角
    asin((R+gap)/d) は距離に対して下に凸なので、d0 での接線(一次近似)はどこでも小さく
    なり食い込む。比の補正は遠ざかると少し大きめ(安全側)、近づくと少し小さめになる。

    Args:
        rig (dict): _buildRig の結果。キーを打つ前(初期姿勢)に呼ぶ。
        corrected (bool): False なら角度を γ0 に固定する。

    Returns:
        list[tuple]: 部位ごとの (γ0 deg, d0 cm, 補正の有無)。
    """
    elbow = cmds.xform(rig["joints"]["l_lowerArm"], query=True, worldSpace=True, translation=True)
    result = []
    for ball, radius in rig["balls"]:
        center = cmds.xform(ball, query=True, worldSpace=True, translation=True)
        d0 = math.sqrt(sum((a-b)**2 for a, b in zip(center, elbow)))
        r = radius+GAP
        gamma0 = math.degrees(math.asin(min(1.0, r/d0)))
        result.append((gamma0, d0, corrected))
    return result


def _coneRange(p, cx, cy, cz, gamma0, d0, corrected):
    """肘を頂点として部位の点へ向くコーンが、回転面を塞ぐ半幅と掛かり具合の重みを作る。

    コーンの角度 γ=clamp(γ0·d0/d, 1, 89)(補正なしは γ0)。軸の回転面への投影の長さ s=√(cy²+cz²)/d に対し、
    半幅 h=acos(cosγ/s)(s<=cosγ なら届かず0)。掛かり具合は、軸と回転面のなす角 e に対する
    q=(γ-e)/γ(届き始め0、軸が面内で1)。

    Returns:
        tuple: (交わりの判定値(正なら交わる), 半幅 deg, なだらかに効かせる重み)。
    """
    planar2 = _sum(p+"Planar2", (_multiply(p+"CY2", cy, cy), _multiply(p+"CZ2", cz, cz)))
    planar = _sqrt(p+"Planar", planar2)
    distance = _sqrt(p+"Dist", _sum(p+"Dist2", (planar2, _multiply(p+"CX2", cx, cx))))
    if corrected:
        ratio = _node("multiplyDivide", p+"GammaRaw", operation=2, input1X=gamma0*d0)
        _connect(_clampRange(p+"DistGuard", distance, 1e-6, 1e9), ratio+".input2X")
        gamma = _clampRange(p+"Gamma", ratio+".outputX", 1, 89)
    else:
        gamma = _clampRange(p+"Gamma", _sum(p+"GammaRaw", (), (gamma0,)), 1, 89)
    # cosγ は Z軸まわりに γ 回した行列で X軸を変換して得る(標準ノードに cos がないため)。
    rotation = _node("composeMatrix", p+"GammaRotation")
    _connect(gamma, rotation+".inputRotateZ")
    unit = _node("vectorProduct", p+"GammaCos", operation=3, input1X=1, input1Y=0, input1Z=0)
    _connect(rotation+".outputMatrix", unit+".matrix")
    cos_gamma = unit+".outputX"
    projected = _divide(p+"S", planar, _clampRange(p+"DistSafe", distance, 1e-6, 1e9))
    reach2 = _sum(p+"Reach2", (_multiply(p+"S2", projected, projected),
                               _multiply(p+"Cos2", cos_gamma, cos_gamma)), subtract=True)
    section = _condition(p+"ValidReach", reach2, 0, reach2, 0)
    half = _node("angleBetween", p+"HalfAngle", vector1X=1, vector1Y=0, vector1Z=0, vector2Z=0)
    _connect(cos_gamma, half+".vector2X")
    _connect(_sqrt(p+"Reach", section), half+".vector2Y")
    width = _degrees(p+"Half", half+".angle")
    # 軸と回転面のなす角 e=90-φ。φ は (|cx|, √(cy²+cz²)) とX軸のなす角。
    tilt = _node("angleBetween", p+"AxisTilt", vector1X=1, vector1Y=0, vector1Z=0, vector2Z=0)
    _connect(_condition(p+"AbsCX", cx, 0, cx, _multiply(p+"NegCX", cx, constant=-1), operation=3),
             tilt+".vector2X")
    _connect(planar, tilt+".vector2Y")
    phi = _degrees(p+"Phi", tilt+".angle")
    depth = _divide(p+"Q", _sum(p+"QNum", (gamma, phi), (-90,)), gamma)
    t = _clampRange(p+"T", _multiply(p+"QScaled", depth, constant=1/SOFT_FULL), 0, 1)
    weight = _multiply(p+"W", _multiply(p+"T2", t, t),
                       _sum(p+"ThreeMinus2T", (_multiply(p+"TwoT", t, constant=-2),), (3,)))
    return section, width, weight


def _buildGeometry(prefix, rig, soft=False, cone=None):
    """球が回転面を塞ぐ範囲を合わせ、外向き・相対角・半幅H・接線Lを求める。

    Args:
        soft (bool): True なら球ごとの掛かり具合で範囲へなだらかに足す。
        cone (list[tuple] | None): coneParameters の結果。指定すると球の代わりに
            肘からのコーンで範囲を求める。

    Returns:
        dict: outward, relative, half, limit, active(交わる球があれば正)。
    """
    arm = rig["joints"]["l_lowerArm"]
    lows, highs, actives = [], [], []
    low = high = count = None
    for k, (ball, radius) in enumerate(rig["balls"]):
        p = "{}B{}".format(prefix, k)
        local = _node("multMatrix", p+"ToArm")
        _connect(ball+".worldMatrix[0]", local+".matrixIn[0]")
        _connect(arm+".worldInverseMatrix[0]", local+".matrixIn[1]")
        center = _node("decomposeMatrix", p+"Center")
        _connect(local+".matrixSum", center+".inputMatrix")
        cx, cy, cz = [center+".outputTranslate"+a for a in "XYZ"]
        if cone is not None:
            section, width, cone_weight = _coneRange(p, cx, cy, cz, *cone[k])
        else:
            section = width = cone_weight = None
        radius2 = None if cone is not None else _sum(p+"R2", (_multiply(p+"CX2Neg", _multiply(p+"CX2", cx, cx), constant=-1),),
                       ((radius+GAP)**2,))
        if cone is None:
            section = _condition(p+"ValidR2", radius2, 0, radius2, 0)
            rho = _sqrt(p+"Rho", section)
            planar2 = _sum(p+"Planar2", (_multiply(p+"CY2", cy, cy), _multiply(p+"CZ2", cz, cz)))
            tangent2 = _sum(p+"Tangent2", (planar2, section), subtract=True)
            tangent = _sqrt(p+"TangentLen", _condition(p+"ValidTangent", tangent2, 0, tangent2, 0))
            # asin(ρ/d) は (√(d²-ρ²), ρ) とX軸のなす角。肘が断面円の中なら90度になる。
            half = _node("angleBetween", p+"HalfAngle", vector1X=1, vector1Y=0, vector1Z=0, vector2Z=0)
            _connect(tangent, half+".vector2X")
            _connect(rho, half+".vector2Y")
            width = _degrees(p+"Half", half+".angle")
        direction = _node("angleBetween", p+"CenterAngle", vector1X=0, vector1Y=1, vector1Z=0, vector2X=0)
        _connect(cy, direction+".vector2Y")
        _connect(cz, direction+".vector2Z")
        unsigned = _degrees(p+"CenterUnsigned", direction+".angle")
        theta = _condition(p+"Theta", cz, 0, unsigned, _multiply(p+"ThetaNeg", unsigned, constant=-1))
        if soft:
            # 掛かり具合 q=(R+gap-|cx|)/(R+gap) から重み w を求め、足す前と足した後の範囲を w で混ぜる。
            # ρ は掛かり始めに急増するので、面の入り込みの深さに比例する q を使う。
            if cone is not None:
                weight = cone_weight
            else:
                distance = _condition(p+"AbsCX", cx, 0, cx, _multiply(p+"NegCX", cx, constant=-1), operation=3)
                inside = _sum(p+"Inside", (_multiply(p+"NegDist", distance, constant=-1),), (radius+GAP,))
                t = _clampRange(p+"T", _multiply(p+"Q", inside, constant=1/((radius+GAP)*SOFT_FULL)), 0, 1)
                weight = _multiply(p+"W", _multiply(p+"T2", t, t),
                                   _sum(p+"ThreeMinus2T", (_multiply(p+"TwoT", t, constant=-2),), (3,)))
            scaled = _multiply(p+"WWidth", width, weight)
            alone_low = _sum(p+"AloneLow", (theta, scaled), subtract=True)
            alone_high = _sum(p+"AloneHigh", (theta, scaled))
            entered = _condition(p+"Entered", section, 0, 1, 0)
            if low is None:
                low = _condition(p+"Low", section, 0, alone_low, 1e6)
                high = _condition(p+"High", section, 0, alone_high, -1e6)
                count = entered
                continue
            raw_low = _sum(p+"LowRaw", (theta, width), subtract=True)
            raw_high = _sum(p+"HighRaw", (theta, width))
            joined_low = _sum(p+"JoinedLow", (low, _multiply(p+"LowBlend", weight, _sum(
                p+"LowDelta", (_minimum(p+"LowMin", low, raw_low), low), subtract=True))))
            joined_high = _sum(p+"JoinedHigh", (high, _multiply(p+"HighBlend", weight, _sum(
                p+"HighDelta", (_maximum(p+"HighMax", high, raw_high), high), subtract=True))))
            low = _condition(p+"Low", section, 0, _condition(p+"LowHas", count, 0, joined_low, alone_low), low)
            high = _condition(p+"High", section, 0, _condition(p+"HighHas", count, 0, joined_high, alone_high),
                              high)
            count = _sum(p+"Count", (count, entered))
            continue
        # 交わらない球は範囲に入れない(下限を大きく、上限を小さくする)。
        lows.append(_condition(p+"Low", section, 0, _sum(p+"LowRaw", (theta, width), subtract=True), 1e6))
        highs.append(_condition(p+"High", section, 0, _sum(p+"HighRaw", (theta, width)), -1e6))
        actives.append(section)
    if not soft:
        low, high = lows[0], highs[0]
        for k in range(1, len(lows)):
            low = _minimum("{}Low{}".format(prefix, k), low, lows[k])
            high = _maximum("{}High{}".format(prefix, k), high, highs[k])
    span = _sum(prefix+"Span", (high, low), subtract=True)
    half = _multiply(prefix+"H", _clampRange(prefix+"SpanSafe", span, 0, 360), constant=0.5)
    middle = _multiply(prefix+"Middle", _sum(prefix+"LowPlusHigh", (low, high)), constant=0.5)
    outward = _sum(prefix+"Outward", (_condition(prefix+"MiddleSafe", span, -1e-9 if soft else 0, middle, 0),),
                   (180,))
    requested = _degrees(prefix+"Requested", rig["source"]+".rx")
    relative = _sum(prefix+"Relative", (requested, outward), subtract=True)
    limit = _sum(prefix+"Limit", (_multiply(prefix+"NegH", half, constant=-1),), (180,))
    # 交わる球があるか。soft では1つ目の球が掛かり始めた瞬間に幅0で範囲ができる。
    active = count if soft else span
    return {"outward": outward, "relative": relative, "half": half, "limit": limit, "active": active,
            "requested": requested}


def _finish(prefix, rig, geometry, relative_out, color):
    """補正後の相対角を -L〜L に制限して出力尾の rotateX へつなぐ。交わる球がなければ入力を通す。"""
    output = _tail(prefix+"TailOutput_JNT", color, rig["joints"]["l_lowerArm"])
    guard = _node("clamp", prefix+"Guard")
    _connect(relative_out, guard+".inputR")
    _connect(geometry["limit"], guard+".maxR")
    _connect(_multiply(prefix+"NegLimit", geometry["limit"], constant=-1), guard+".minR")
    corrected = _sum(prefix+"World", (geometry["outward"], guard+".outputR"))
    selected = _condition(prefix+"Bypass", geometry["active"], 0, corrected, geometry["requested"])
    radians = _node("unitConversion", prefix+"Radians", conversionFactor=math.pi/180)
    _connect(selected, radians+".input")
    _connect(radians+".output", output+".rx")
    for attr in ("ry", "rz"):
        cmds.setAttr(output+"."+attr, lock=True)
    return output


def _buildRbf(prefix, geometry):
    """ドライバー (rel/20, H/10) のUE RBFでなだらかに避ける相対角を作る。

    Returns:
        tuple: (正規化した出力プラグ, ソルバー, ポーズ一覧)。
    """
    driver = _node("composeMatrix", prefix+"Driver")
    _connect(_multiply(prefix+"DriverX", geometry["relative"], constant=1/REL_STEP), driver+".inputTranslateX")
    _connect(_multiply(prefix+"DriverY", _clampRange(prefix+"HClamp", geometry["half"], 0, H_RANGE*H_STEP),
                       constant=1/H_STEP), driver+".inputTranslateY")
    solver = _node("UERBFSolverNode", prefix+"PoseSolver", mode=0, inputMode=0, distanceMethod=0, functionType=0,
                   normalizeMethod=1, automaticRadius=False, radius=RBF_RADIUS)
    _connect(driver+".outputMatrix", solver+".inputs[0]")
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    cmds.setAttr(solver+".inputsRest[0]", identity, type="matrix")
    blend = _node("plusMinusAverage", prefix+"PoseBlendSum")
    total = _node("plusMinusAverage", prefix+"WeightSum")
    grid = [(i, j, poseValue(i*REL_STEP, j*H_STEP))
            for i in range(-REL_RANGE, REL_RANGE+1) for j in range(H_RANGE+1)]
    for i, (x, y, value) in enumerate(grid):
        cmds.setAttr(solver+".targets[{}].targetValues[0]".format(i), identity[:12]+[x, y, 0, 1], type="matrix")
        weighted = _node("multDoubleLinear", prefix+"Pose{}".format(i), input2=value)
        _connect(solver+".outputs[{}]".format(i), weighted+".input1")
        _connect(weighted+".output", blend+".input1D[{}]".format(i))
        _connect(solver+".outputs[{}]".format(i), total+".input1D[{}]".format(i))
    normalized = _divide(prefix+"PoseBlend", blend+".output1D",
                         _clampRange(prefix+"WeightSumSafe", total+".output1D", 1e-6, 1e9))
    return normalized, solver, grid


def referenceGeometry(rig, soft=False, cone=None):
    """リグと独立に、行列から塞がれる範囲・外向き・半幅を求める。

    Args:
        soft (bool): True なら掛かり具合の重みで範囲へなだらかに足す。
        cone (list[tuple] | None): coneParameters の結果。指定すると肘からのコーンで求める。

    Returns:
        tuple: (外向き deg, 半幅H deg, 交わる球の数)。交わらなければ (None, 0, 0)。
    """
    arm = om.MMatrix(cmds.xform(rig["joints"]["l_lowerArm"], query=True, worldSpace=True, matrix=True))
    inverse = arm.inverse()
    lows, highs = [], []
    low = high = None
    for k, (ball, radius) in enumerate(rig["balls"]):
        w = cmds.xform(ball, query=True, worldSpace=True, translation=True)
        c = om.MPoint(*w)*inverse
        theta = math.degrees(math.atan2(c.z, c.y))
        if cone is not None:
            gamma0, d0, corrected = cone[k]
            distance = math.sqrt(c.x**2+c.y**2+c.z**2)
            gamma = min(89.0, max(1.0, gamma0*d0/distance if corrected else gamma0))
            projected = math.hypot(c.y, c.z)/distance
            cos_gamma = math.cos(math.radians(gamma))
            if projected**2-cos_gamma**2 <= 0:
                continue
            width = math.degrees(math.acos(min(1.0, cos_gamma/projected)))
            phi = math.degrees(math.atan2(math.hypot(c.y, c.z), abs(c.x)))
            t = min(1.0, max(0.0, (gamma+phi-90)/gamma/SOFT_FULL))
        else:
            r2 = (radius+GAP)**2-c.x**2
            if r2 <= 0:
                continue
            rho = math.sqrt(r2)
            d = math.hypot(c.y, c.z)
            width = math.degrees(math.asin(rho/d)) if d > rho else 90.0
            t = min(1.0, max(0.0, (radius+GAP-abs(c.x))/((radius+GAP)*SOFT_FULL)))
        lows.append(theta-width)
        highs.append(theta+width)
        if soft:
            weight = t*t*(3-2*t)
            if low is None:
                low, high = theta-weight*width, theta+weight*width
            else:
                low += weight*(min(low, theta-width)-low)
                high += weight*(max(high, theta+width)-high)
    if not lows:
        return None, 0.0, 0
    if not soft:
        low, high = min(lows), max(highs)
    return 180+(low+high)/2, (high-low)/2, len(lows)


def main(record=True, case="mixed"):
    """専用GUIで3列を同じ入力で動かし、正面から録画して検査する。

    Args:
        record (bool): True なら録画して検証する。False なら録画せず、タイムラインの
            再生・スクラブでHUDと数値が更新されるシーンを作る。
        case (str): "mixed" は複雑な動きの総合確認、"activation" は球が回転面と
            交わり始める瞬間の跳びの確認、"soft_entry" は跳びの対策の前後比較、
            "cone_c" は前半を肘からのコーンで近似した版との比較。
    """
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    motion, inputs, body, columns, title, save_name = CASES[case]
    kinds = {key: kind for key, _, _, _, kind in columns}
    corrected_keys = [key for key in kinds if kinds[key] != "input"]
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
    rigs = {key: _buildRig(key, i, material_group, body, len(columns)) for i, (key, *_) in enumerate(columns)}
    # コーンの角度はキーを打つ前の初期姿勢で決める。
    cones = {key: coneParameters(rigs[key], kinds[key] == "rbf_cone")
             for key in kinds if kinds[key] in ("rbf_cone_fixed", "rbf_cone")}
    geometries = {key: _buildGeometry(key, rigs[key], soft=kinds[key] in SOFT_KINDS, cone=cones.get(key))
                  for key in kinds}
    outputs = {}
    solvers = {}
    for key, _, _, color, kind in columns:
        if kind in ("keep", "soft"):
            outputs[key] = _finish(key, rigs[key], geometries[key], geometries[key]["relative"], color)
        elif kind in RBF_KINDS:
            rbf_plug, solver, grid = _buildRbf(key, geometries[key])
            solvers[key] = (solver, len(grid))
            outputs[key] = _finish(key, rigs[key], geometries[key], rbf_plug, color)

    camera, camera_shape = cmds.camera(name="chainRbfCamera", orthographic=True)
    cmds.setAttr(camera+".translate", 0, 12.5, 60)
    cmds.setAttr(camera_shape+".orthographicWidth", SPACING*len(columns))
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
    rows = 3
    texts = {}
    for column, section in enumerate(HUD_SECTIONS[len(columns)]):
        for row in range(rows):
            for prefix, base, block in (("chainTop", section, row), ("chainBottom", section+5, rows-1-row)):
                name = "{}{}_{}".format(prefix, column, row)
                texts[name] = ""
                cmds.headsUpDisplay(name, section=base, block=block, blockSize="large", dataFontSize="large",
                                    command=lambda n=name: texts[n])

    # 体と腕の動き。周期の違う正弦波を全列に同じキーで打つ。
    count = (len(inputs)-1)*SEGMENT_FRAMES+1
    for rig in rigs.values():
        for joint, attr, amplitude, period, phase, offset in motion:
            node = rig["joints"][joint]
            for frame in range(0, count, 3):
                value = offset+amplitude*math.sin(2*math.pi*frame/period+phase)
                cmds.setKeyframe(node, attribute=attr, time=frame+1, value=value)
    # 尻尾の入力。各フレームの外向き(DGの連続値)に、折り返さない相対角を足す。
    stages = []
    for frame in range(count):
        phase = frame/SEGMENT_FRAMES
        index = min(int(phase), len(inputs)-2)
        w = phase-index
        w = w*w*(3-2*w)
        rel = inputs[index][0]+(inputs[index+1][0]-inputs[index][0])*w
        stages.append(inputs[index][1] if frame else inputs[0][1])
        outward = cmds.getAttr(geometries["input"]["outward"], time=frame+1)
        for rig in rigs.values():
            cmds.setKeyframe(rig["source"], attribute="rx", time=frame+1, value=outward+rel)
    cmds.playbackOptions(minTime=1, maxTime=count)

    last = dict.fromkeys(corrected_keys+["balls"])
    flash = dict.fromkeys(corrected_keys+["balls"], -1)
    flash["ballText"] = ""

    def penetration(rig, joint):
        """リグに接続しない線分と球の交差検査。最も深い食い込み(cm)。交差しなければ0以下。"""
        m = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
        origin, direction = m[12:15], m[4:7]
        deepest = -1e9
        for ball, radius in rig["balls"]:
            c = cmds.xform(ball, query=True, worldSpace=True, translation=True)
            o = [a-b for a, b in zip(origin, c)]
            t = max(0, min(LENGTH, -sum(a*b for a, b in zip(o, direction))))
            distance = math.sqrt(sum((a+t*b)**2 for a, b in zip(o, direction)))
            deepest = max(deepest, radius-distance)
        return deepest

    def hits(rig, joint):
        """交差しているか。"""
        return penetration(rig, joint) > 0

    def classicWeight(rig, joint, parameters):
        """一般的なコーンドライバーの出力。尻尾の向きが各コーンにどれだけ入っているか(0〜1)の最大値。

        向きと軸のなす角 a に対して clamp(1-a/γ, 0, 1)。左右の区別や接線の位置は持たない。
        """
        m = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
        best = 0.0
        for (ball, _), (gamma0, d0, corrected) in zip(rig["balls"], parameters):
            c = cmds.xform(ball, query=True, worldSpace=True, translation=True)
            axis = [a-b for a, b in zip(c, m[12:15])]
            distance = math.sqrt(sum(v*v for v in axis))
            gamma = min(89.0, max(1.0, gamma0*d0/distance if corrected else gamma0))
            dot = sum(a*b for a, b in zip(axis, m[4:7]))/distance
            angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
            best = max(best, min(1.0, max(0.0, 1-angle/gamma)))
        return best

    def evaluate(frame):
        """球列は独立計算と照合し、RBF列は重み・交差・連続性を記録する。"""
        demo_interactive.setTime(frame)
        requested_value = cmds.getAttr(rigs["input"]["source"]+".rx")
        result = {"frame": frame, "stage": stages[frame], "requested_degrees": requested_value,
                  "input_hits": hits(rigs["input"], rigs["input"]["source"])}
        ok = True
        lines = {}
        for key in corrected_keys:
            rig = rigs[key]
            outward, half, active = referenceGeometry(rig, soft=kinds[key] in SOFT_KINDS, cone=cones.get(key))
            actual = cmds.getAttr(outputs[key]+".rx")
            if outward is None:
                rel, limit, expected = None, 180.0, requested_value
            else:
                rel = requested_value-outward
                limit = 180-half
                expected = outward+max(-limit, min(limit, rel))
            depth = max(0.0, penetration(rig, outputs[key]))
            body = depth > 0
            step = abs((actual-last[key]+180) % 360-180) if last[key] is not None else 0.0
            last[key] = actual
            if step > 15:
                flash[key] = frame+24
            entry = {"output_degrees": actual, "step_degrees": step, "body_hits": body, "penetration_cm": depth,
                     "active_balls": active,
                     "half_width_degrees": half, "relative_degrees": rel}
            if kinds[key] in ("keep", "soft"):
                entry["error_degrees"] = abs((actual-expected+180) % 360-180)
                ok = ok and entry["error_degrees"] < 1e-3
            else:
                solver, pose_count = solvers[key]
                weights = [cmds.getAttr(solver+".outputs[{}]".format(i)) for i in range(pose_count)]
                entry["weight_sum"] = sum(weights)
                entry["formula_relative_degrees"] = poseValue(rel, half) if rel is not None else None
                entry["relative_output_degrees"] = actual-outward if outward is not None else None
                ok = ok and (outward is None or abs(sum(weights)-1) < 0.05)
            # soft は浅く掛かっている間の食い込みを許容し、深さを記録する。
            ok = ok and (kinds[key] in SOFT_KINDS or not body) and cmds.getAttr(outputs[key]+".ry") == 0 and cmds.getAttr(outputs[key]+".rz") == 0
            result[key] = entry
            out_rel = (actual-outward) if outward is not None else None
            lines[key] = ("out rel {}".format("{:+.1f}".format(out_rel) if out_rel is not None else "-"),
                          ("BODY HIT {:.2f}cm".format(depth) if body else "clear") + "  step {:.1f}".format(step)
                          + ("  JUMP!" if frame <= flash[key] else ""))
        result["ok"] = ok
        outward, half, active = referenceGeometry(rigs["input"])
        if last["balls"] is not None and active != last["balls"]:
            flash["balls"] = frame+24
            flash["ballText"] = "BALL ENTERED" if active > last["balls"] else "BALL LEFT"
        last["balls"] = active
        rel = requested_value-outward if outward is not None else None
        lines["input"] = ("rel={}  H={:.1f}  L={:.1f}".format("{:+.1f}".format(rel) if rel is not None else "-",
                                                                half, 180-half),
                          "{} ball(s) cut the twist plane".format(active)
                          + ("  "+flash["ballText"] if frame <= flash["balls"] else "")
                          + ("  BODY HIT" if result["input_hits"] else ""))
        for column, (key, title, formula, _, _) in enumerate(columns):
            texts["chainTop{}_0".format(column)] = title
            texts["chainTop{}_1".format(column)] = formula
            texts["chainTop{}_2".format(column)] = lines[key][0]
            texts["chainBottom{}_0".format(column)] = lines[key][1]
            if key == "input" and "cone" in cones:
                classic = classicWeight(rigs["input"], rigs["input"]["source"], cones["cone"])
                result["input_classic_cone_weight"] = classic
                texts["chainBottom{}_1".format(column)] = "classic cone driver output (0-1): {:.2f}".format(classic)
            else:
                texts["chainBottom{}_1".format(column)] = ("H = half of union of blocked ranges" if key == "input"
                                                           else "H={:.1f}".format(result[key]["half_width_degrees"]))
            texts["chainBottom{}_2".format(column)] = stages[frame] if key == "input" else ""
        for name in texts:
            cmds.headsUpDisplay(name, refresh=True)
        return result

    if not record:
        demo_interactive.attachInteractive(window, count, evaluate, [(last, None), (flash, -1)])
        logger.info("チェーンと3球のシーンを作成しました。タイムラインで再生・スクラブして確認できます。")
        return
    folder = recordVideo(title, count, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1800, height=760)
    cmds.file(rename=str(folder/(save_name+".ma")))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-{}.json".format(save_name)).write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("チェーンと3球の検証に失敗: {}".format(folder))
    logger.info("チェーンと3球の検証を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
