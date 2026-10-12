"""案D(肘・手首の尻尾を upperarm の尻尾と平行にする)の3本に、共通の回避角 Δ を標準ノードで作る。

3本の尻尾は平行なので、どれも upperarm の X 軸に垂直な面の中で同じ角度だけ回る。角度は
「upperarm のひねり(rotateX)を打ち消した空間」F で測る。F では尻尾の角度はひねりによらず一定(初期の向き)。

1. F の中で、肩から見た胴の中心の方向 τ を、rotateX だけの aimConstraint のグループで連続に求める
   (狙う軸は胴がいる方向の平均 m。境目は m の真反対)。
2. 3本の尻尾の付け根それぞれで、当たり判定の球が尻尾の回る面を塞ぐ角度の範囲を求める。
   - 球の中心を付け根の空間(F と同じ向き)へ移し、(h, y, z) とする。h は面からの距離。
   - 面での断面の半径 ρ = sqrt(max(r² - h², 0))、面での中心までの距離 d = sqrt(y² + z²)。
   - 半幅 = asin(ρ/d)(接点までの長さ sqrt(d² - ρ²) が尻尾の長さ ℓ 以下のとき)、届かなければ
     acos((ℓ² + d² - ρ²) / (2ℓd))(尻尾の先が断面に届く角度)。
     asin・acos は remapValue の曲線で近似する。
   - 中心の角度 c = atan2(z, y)(angleBetween と z の符号)。胴の方向からの角度 c - τ を ±180 に折り返す。
   - 範囲 [c - τ - 半幅, c - τ + 半幅] を、半幅に応じた重み(0〜1)で胴の方向(0)から伸ばす。半幅が0の球は
     効かず、塞ぎ始めた球はなめらかに効き始める。
3. 胴の方向から見た塞がれる範囲 a = min(0, 各範囲の下端)、b = max(0, 各範囲の上端)(胴の中心から
   つながった体とみなす)。
4. 案1と同じ clamp: 外向き(τ + 180)からの尻尾の角度 r = 尻尾 - τ - 180(連続)を
   [b - 180 + 余裕, a + 180 - 余裕] に収める。Δ = w · (clamp(r) - r)。w は塞いでいる球の重みの最大
   (何も塞いでいなければ Δ = 0)。
"""

import math

from maya import cmds

# 尻尾の向きと胴の方向の間にとる余裕(度)。
MARGIN = 5.0
# 半幅がこの角度(度)まで育つ間に、球の範囲の重みを0から1へ上げる。
GROW = 10.0
# asin・acos の曲線の点の数。
CURVE_POINTS = 25


def _node(kind, name, **values):
    """標準ノードを作り、定数を設定する。"""
    node = cmds.createNode(kind, name=name)
    for attr, value in values.items():
        cmds.setAttr(node+"."+attr, value)
    return node


def _sum(name, plugs, constants=(), subtract=False):
    """plusMinusAverage(1D)。"""
    node = _node("plusMinusAverage", name, operation=2 if subtract else 1)
    for i, plug in enumerate(plugs):
        cmds.connectAttr(plug, "{}.input1D[{}]".format(node, i))
    for i, value in enumerate(constants, len(plugs)):
        cmds.setAttr("{}.input1D[{}]".format(node, i), value)
    return node+".output1D"


def _mul(name, a, b=None, constant=1.0):
    """multDoubleLinear。b がなければ定数を掛ける。"""
    node = _node("multDoubleLinear", name, input2=constant)
    cmds.connectAttr(a, node+".input1")
    if b:
        cmds.connectAttr(b, node+".input2")
    return node+".output"


def _clamp(name, plug, low, high):
    """clamp(R)。"""
    node = _node("clamp", name, minR=low, maxR=high)
    cmds.connectAttr(plug, node+".inputR")
    return node+".outputR"


def _pick(name, first, second, yes, no, operation):
    """condition(R)。first・second・yes・no はプラグか数値。operation は condition の比較。"""
    node = _node("condition", name, operation=operation)
    for attr, value in (("firstTerm", first), ("secondTerm", second), ("colorIfTrueR", yes),
                        ("colorIfFalseR", no)):
        if isinstance(value, str):
            cmds.connectAttr(value, node+"."+attr)
        else:
            cmds.setAttr(node+"."+attr, value)
    return node+".outColorR"


def _sqrt(name, plug):
    """非負の平方根。"""
    node = _node("multiplyDivide", name, operation=3, input2X=0.5)
    cmds.connectAttr(plug, node+".input1X")
    return node+".outputX"


def _curve(name, plug, function, low, high, scale):
    """remapValue の曲線で function を近似する(入力 low〜high、出力 0〜scale)。"""
    node = _node("remapValue", name, inputMin=low, inputMax=high, outputMin=0, outputMax=scale)
    cmds.connectAttr(plug, node+".inputValue")
    for i in range(CURVE_POINTS):
        u = i/float(CURVE_POINTS-1)
        cmds.setAttr("{}.value[{}].value_Position".format(node, i), u)
        cmds.setAttr("{}.value[{}].value_FloatValue".format(node, i), function(low+(high-low)*u)/scale)
        cmds.setAttr("{}.value[{}].value_Interp".format(node, i), 1)
    return node+".outValue"


def _signedAngle(name, local):
    """local(ベクトルのプラグ)の y・z から atan2(z, y)(度、-180〜180)。"""
    planar = _node("multiplyDivide", name+"_planar", input2X=0, input2Y=1, input2Z=1)
    cmds.connectAttr(local, planar+".input1")
    between = _node("angleBetween", name+"_between", vector2X=0, vector2Y=1, vector2Z=0)
    cmds.connectAttr(planar+".output", between+".vector1")
    degrees = _node("unitConversion", name+"_degrees", conversionFactor=180/math.pi)
    cmds.connectAttr(between+".angle", degrees+".input")
    angle = degrees+".output"
    return _pick(name+"_signed", local+"Z", 0, angle, _mul(name+"_negative", angle, constant=-1), 2)


def _wrap(name, plug):
    """±180 に折り返す(入力は ±540 まで)。"""
    for i in range(2):
        plug = _pick("{}_down{}".format(name, i), plug, 180, _sum("{}_minus{}".format(name, i), (plug,), (-360,)),
                     plug, 2)
        plug = _pick("{}_up{}".format(name, i), plug, -180, _sum("{}_plus{}".format(name, i), (plug,), (360,)),
                     plug, 4)
    return plug


def _extreme(name, plugs, smaller):
    """plugs の最小(smaller=True)または最大。"""
    result = plugs[0]
    for i, plug in enumerate(plugs[1:]):
        result = _pick("{}{}".format(name, i), result, plug, result, plug, 4 if smaller else 2)
    return result


def buildDelta(prefix, upperarm, roots, balls, center, mean_angle, rest_angle, length):
    """共通の回避角 Δ(度、尻尾の rotateX に足す)のプラグを作る。

    Args:
        prefix (str): ノード名の接頭辞。
        upperarm (str): upperarm の関節。F はこの子で、rotateX = -upperarm.rotateX。
        roots (list[str]): 尻尾の付け根の関節(upperarm・lowerarm・hand)。
        balls (list[tuple[str, float]]): 当たり判定の球(transform, 半径)。
        center (str): 胴の中心のロケーター。
        mean_angle (float): F の中で胴がいる方向の平均(度)。aimConstraint の狙う軸。
        rest_angle (float): F の中での尻尾の初期の角度(度)。
        length (float): 尻尾の長さ(cm)。

    Returns:
        dict: delta(Δ)、low(a)、high(b)、weight(w)、torso(τ)、relative(r)のプラグ。
    """
    frame = cmds.createNode("transform", name=prefix+"twistFree_GRP", parent=upperarm)
    untwist = _node("unitConversion", prefix+"untwist", conversionFactor=-1)
    cmds.connectAttr(upperarm+".rotateX", untwist+".input")
    cmds.connectAttr(untwist+".output", frame+".rotateX")
    group = cmds.createNode("transform", name=prefix+"torsoDirection_GRP", parent=frame)
    aim = (0, math.cos(math.radians(mean_angle)), math.sin(math.radians(mean_angle)))
    cmds.aimConstraint(center, group, aimVector=aim, upVector=(1, 0, 0), worldUpType="objectrotation",
                       worldUpObject=frame, worldUpVector=(1, 0, 0), skip=("y", "z"))
    group_degrees = _node("unitConversion", prefix+"torsoDegrees", conversionFactor=180/math.pi)
    cmds.connectAttr(group+".rotateX", group_degrees+".input")
    torso = _sum(prefix+"torso", (group_degrees+".output",), (mean_angle,))
    # 尻尾の初期の角度を、外向き(m + 180)と同じ周にそろえる。
    rest = rest_angle+360*round(((mean_angle+180)-rest_angle)/360.0)
    relative = _sum(prefix+"relative", (_mul(prefix+"negTorso", torso, constant=-1),), (rest-180,))

    positions = []
    for i, (ball, _) in enumerate(balls):
        decompose = _node("decomposeMatrix", "{}ball{}_position".format(prefix, i))
        cmds.connectAttr(ball+".worldMatrix[0]", decompose+".inputMatrix")
        positions.append(decompose+".outputTranslate")
    lows, highs, weights = [], [], []
    for k, root in enumerate(roots):
        local_frame = cmds.createNode("transform", name="{}root{}_GRP".format(prefix, k), parent=frame)
        cmds.pointConstraint(root, local_frame)
        for i, (ball, radius) in enumerate(balls):
            name = "{}r{}b{}".format(prefix, k, i)
            local = _node("vectorProduct", name+"_local", operation=4)
            cmds.connectAttr(positions[i], local+".input1")
            cmds.connectAttr(local_frame+".worldInverseMatrix[0]", local+".matrix")
            square = _node("multiplyDivide", name+"_square")
            cmds.connectAttr(local+".output", square+".input1")
            cmds.connectAttr(local+".output", square+".input2")
            rho2 = _clamp(name+"_rho2", _sum(name+"_rho2Raw", (_mul(name+"_negH2", square+".outputX", constant=-1),),
                                             (radius**2,)), 0, 1e6)
            rho = _sqrt(name+"_rho", rho2)
            dist2 = _sum(name+"_dist2", (square+".outputY", square+".outputZ"))
            dist = _sqrt(name+"_dist", _clamp(name+"_dist2Safe", dist2, 1e-6, 1e9))
            ratio = _node("multiplyDivide", name+"_ratio", operation=2)
            cmds.connectAttr(rho, ratio+".input1X")
            cmds.connectAttr(dist, ratio+".input2X")
            half_cone = _curve(name+"_asin", _clamp(name+"_ratioSafe", ratio+".outputX", 0, 1),
                               lambda x: math.degrees(math.asin(x)), 0.0, 1.0, 90.0)
            # 長さ ℓ の尻尾の先が断面に届く角度: cos = (ℓ² + d² - ρ²) / (2ℓd)
            numerator = _sum(name+"_cosTop", (dist2, _mul(name+"_negRho2", rho2, constant=-1)), (length**2,))
            cosine = _node("multiplyDivide", name+"_cos", operation=2)
            cmds.connectAttr(numerator, cosine+".input1X")
            cmds.connectAttr(_mul(name+"_cosBottom", dist, constant=2*length), cosine+".input2X")
            half_reach = _curve(name+"_acos", _clamp(name+"_cosSafe", cosine+".outputX", -1, 1),
                                lambda x: math.degrees(math.acos(x)), -1.0, 1.0, 180.0)
            # 接点までの長さ sqrt(d² - ρ²) が尻尾の長さ以下なら接線まで届くので asin、届かなければ先端の acos。
            tangent2 = _sum(name+"_tangent2", (dist2, _mul(name+"_negRho2b", rho2, constant=-1)))
            half = _pick(name+"_half", tangent2, length**2, half_cone, half_reach, 5)
            angle = _signedAngle(name+"_angle", local+".output")
            offset = _wrap(name+"_rel", _sum(name+"_relRaw", (angle, _mul(name+"_negTorso", torso, constant=-1))))
            weight = _clamp(name+"_weight", _mul(name+"_growth", half, constant=1.0/GROW), 0, 1)
            lows.append(_mul(name+"_low", _sum(name+"_lowRaw", (offset, _mul(name+"_negHalf", half,
                                                                              constant=-1))), weight))
            highs.append(_mul(name+"_high", _sum(name+"_highRaw", (offset, half)), weight))
            weights.append(weight)
    low = _extreme(prefix+"low", [_sum(prefix+"zeroLow", (), (0,))]+lows, True)
    high = _extreme(prefix+"high", [_sum(prefix+"zeroHigh", (), (0,))]+highs, False)
    weight = _extreme(prefix+"weight", weights, False)
    clamp = _node("clamp", prefix+"clamp")
    cmds.connectAttr(relative, clamp+".inputR")
    cmds.connectAttr(_sum(prefix+"minLimit", (high,), (-180+MARGIN,)), clamp+".minR")
    cmds.connectAttr(_sum(prefix+"maxLimit", (low,), (180-MARGIN,)), clamp+".maxR")
    correction = _sum(prefix+"correction", (clamp+".outputR", relative), subtract=True)
    delta = _mul(prefix+"delta", correction, weight)
    return {"delta": delta, "low": low, "high": high, "weight": weight, "torso": torso, "relative": relative}
