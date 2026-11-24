"""クランクの円運動を、反転(|OP|·|OQ| = 一定)で厳密な直線運動へ変えるポーセリエ・リプキン機構の標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution


class PeaucellierLinkage(TwistDistribution):
    """固定点 O の2本の腕と菱形で、円の上を回る点 P を直線の上を動く点 Q へ写すポーセリエ・リプキン機構。

    固定点 O から長さ a の2本の腕 OA・OB を出し、辺の長さ b の菱形 APBQ をつなぐと、P と Q は O を通る直線の上にあり
    |OP|·|OQ| = a² - b² = k (反転)になる。P を O を通る円(中心 C、|OC| = r)の上でクランクで回すと、Q は O→C の
    向きから距離 k / (2r) の直線の上を動く。O→C の向きを u、クランクが +θ 回ったとき P が向かう側を v とすると、
    P = (r + r cos θ, r sin θ)、φ = θ/2 として |OP| = 2r cos φ、Q = (k / (2r), (k / (2r)) tan φ)。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def limits(cls, crankLength, armLength, sideLength):
        """菱形が成り立つクランクの角度の範囲 θmax = 2 acos((a - b) / (2r)) を返す。

        Args:
            crankLength (float): クランクの長さ r (cm)。
            armLength (float): 固定点からの腕の長さ a (cm)。
            sideLength (float): 菱形の辺の長さ b (cm)。

        Returns:
            float: θmax (ラジアン)。クランクの角度は -θmax 〜 θmax の範囲で使える。
        """
        return 2.0 * math.acos((armLength - sideLength) / (2.0 * crankLength))

    @classmethod
    def motion(cls, theta, crankLength, armLength, sideLength):
        """クランクの角度から P・Q・A・B と腕の角度を計算する(DGと同じ式のPython版)。

        Args:
            theta (float): 生成時からのクランクの回転 + phase (ラジアン)。範囲の外は ±θmax に止める。
            crankLength (float): クランクの長さ r (cm)。
            armLength (float): 固定点からの腕の長さ a (cm)。
            sideLength (float): 菱形の辺の長さ b (cm)。

        Returns:
            dict: ``crankAngle`` (止めた後の角度、ラジアン)、``excessAngle`` (止めた量、ラジアン)、``pX``・``pY``・
            ``qX``・``qY``・``aX``・``aY``・``bX``・``bY`` (固定点 O から見た u・v の位置、cm)、``armAngleA``・
            ``armAngleB`` (腕の u からの角度 φ ± α、ラジアン)、``opDistance``・``oqDistance`` (|OP|・|OQ|、cm)。
        """
        limit = cls.limits(crankLength, armLength, sideLength)
        clamped = min(max(theta, -limit), limit)
        phi = 0.5 * clamped
        near = 2.0 * crankLength * math.cos(phi)
        far = (armLength * armLength - sideLength * sideLength) / near
        middle = 0.5 * (near + far)
        half = math.sqrt(max(armLength * armLength - middle * middle, 0.0))
        alpha = math.atan2(half, middle)
        return {
            "crankAngle": clamped,
            "excessAngle": theta - clamped,
            "pX": crankLength + crankLength * math.cos(clamped),
            "pY": crankLength * math.sin(clamped),
            "qX": far * math.cos(phi),
            "qY": far * math.sin(phi),
            "aX": armLength * math.cos(phi + alpha),
            "aY": armLength * math.sin(phi + alpha),
            "bX": armLength * math.cos(phi - alpha),
            "bY": armLength * math.sin(phi - alpha),
            "armAngleA": phi + alpha,
            "armAngleB": phi - alpha,
            "opDistance": near,
            "oqDistance": far,
        }

    @classmethod
    @undoTransaction("mlrig.PeaucellierLinkage.create")
    def create(cls, crank, pen, armA=None, armB=None, crankLength=2.0, armLength=5.0, sideLength=2.0,
               name="peaucellierLinkage", axis="z", penAxis="y", penDirection=1.0, armDirection=1.0, connect=True):
        """クランクの回転に連動して、直線の上を動く点(ペン)と2本の腕(任意)の回転を生成する。

        Args:
            crank (str | Node): クランクのtransform。円の中心 C に置き、ローカルの ``rotate<axis>`` を回す。
                生成時の姿勢を θ = 0 (P が O から最も遠い 2r の位置、Q は直線と O→C の線の交点)とする。
            pen (str | Node): 直線の上を動く点 Q のtransform。ローカルの ``translate<penAxis>`` を動かす。
                直線に沿わせて置く。
            armA (str | Node | None): 固定点 O に置く腕 OA のtransform。ローカルの ``rotate<axis>`` を回す。
                A は生成時に v の正の側の腕。Noneなら作らない。
            armB (str | Node | None): 固定点 O に置く腕 OB (v の負の側)のtransform。Noneなら作らない。
            crankLength (float): クランクの長さ r = |OC| = |CP| (cm、0より大きい)。生成時に固定する。
            armLength (float): 腕の長さ a (cm)。sideLength より大きい。生成時に固定する。
            sideLength (float): 菱形の辺の長さ b (cm、0より大きい)。a - b < 2r ≤ a + b を満たすこと。
            name (str): 一意なcontainer名。
            axis (str): クランクと腕のローカルの回転軸 x/y/z。
            penAxis (str): ペンのローカルの移動軸 x/y/z。直線(v の向き)に沿わせる。
            penDirection (float): ペンの移動の向き(1.0 か -1.0)。v とペンの移動軸の正の向きが逆なら -1.0。
            armDirection (float): 腕の回転の向き(1.0 か -1.0)。腕の回転軸がクランクと逆向きなら -1.0。
            connect (bool): Trueならペンの ``translate<penAxis>`` (と腕の ``rotate<axis>``)へ出力を接続する。

        Returns:
            PeaucellierLinkage: penTranslate・crankAngle・excessAngle・pX・pY・qX・qY・aX・aY・bX・bY・armAngleA・
                armAngleB・opDistance・oqDistance (腕があれば armARotate・armBRotate)の所有者。containerに phase
                (クランクの角度に足す値)と、固定の crankLength・armLength・sideLength・inversionConstant (k)・
                lineDistance (k / (2r))・maxAngle (θmax)を持つ。

        Raises:
            ValueError: 軸・長さ・向きが不正な場合、長さが a - b < 2r ≤ a + b を満たさない場合、transformでない・
                同じノードの場合、ペン・腕のチャンネルが既に接続されている場合(connect=True)、またはnameが既に
                存在する場合。

        Note:
            θ = クランクの rotate<axis> - 生成時の値 + phase、crankAngle = clamp(θ, -θmax, θmax)、
            excessAngle = θ - crankAngle、φ = crankAngle / 2、|OP| = 2r cos φ、|OQ| = k / |OP|、
            qX = |OQ| cos φ (常に k / (2r))、qY = |OQ| sin φ、penTranslate = 生成時の translate<penAxis> +
            penDirection × qY、m = (|OP| + |OQ|) / 2、h = √(a² - m²)、α = atan2(h, m)、
            armAngleA = φ + α、armAngleB = φ - α、armARotate = 生成時の rotate<axis> + armDirection ×
            (armAngleA - α0) (α0 は θ = 0 の α。B も同様)。θ = 0 では移動・回転が0なので、接続しても跳ねない。
        """
        if any(value not in ("x", "y", "z") for value in (axis, penAxis)):
            raise ValueError("axis and penAxis must be x, y or z")
        numbers = (crankLength, armLength, sideLength, penDirection, armDirection)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers):
            raise ValueError("The lengths and the directions must be numbers")
        if crankLength <= 0.0 or sideLength <= 0.0 or armLength <= sideLength:
            raise ValueError("crankLength and sideLength must be more than 0, armLength more than sideLength")
        if not armLength - sideLength < 2.0 * crankLength <= armLength + sideLength:
            raise ValueError("The lengths must satisfy armLength - sideLength < 2 crankLength <= armLength + sideLength")
        if any(value not in (1.0, -1.0) for value in (penDirection, armDirection)):
            raise ValueError("penDirection and armDirection must be 1.0 or -1.0")
        if mlib.objExists(name):
            raise ValueError("PeaucellierLinkage container already exists: " + name)
        arms = [arm for arm in (armA, armB) if arm is not None]
        nodes = [mlib.Node(crank), mlib.Node(pen)] + [mlib.Node(arm) for arm in arms]
        if not all(isinstance(node, mlib.Transform) for node in nodes):
            raise ValueError("Expected transforms for the crank, the pen and the arms")
        if len({node.getName(full=True) for node in nodes}) != len(nodes):
            raise ValueError("The crank, the pen and the arms must be different nodes")
        crank, pen = nodes[:2]
        remaining = iter(nodes[2:])
        armA = next(remaining) if armA is not None else None
        armB = next(remaining) if armB is not None else None
        rotateChannel = "rotate" + axis.upper()
        penChannel = "translate" + penAxis.upper()
        armPairs = [(label, arm) for label, arm in (("A", armA), ("B", armB)) if arm is not None]
        if connect:
            targets = [pen.getPlug(penChannel)] + [arm.getPlug(rotateChannel) for _, arm in armPairs]
            for target in targets:
                if target.getConnections(input=True, skipConversionNodes=True) is not None:
                    raise ValueError("The target is already connected: " + str(target))

        radius, arm, side = float(crankLength), float(armLength), float(sideLength)
        constant = arm * arm - side * side
        limit = cls.limits(radius, arm, side)
        rest = cls.motion(0.0, radius, arm, side)
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="phase", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        constants = (("crankLength", "doubleLinear", radius), ("armLength", "doubleLinear", arm),
                     ("sideLength", "doubleLinear", side), ("inversionConstant", "double", constant),
                     ("lineDistance", "doubleLinear", constant / (2.0 * radius)), ("maxAngle", "doubleAngle", limit))
        for attribute, kind, value in constants:
            owner.addAttr(longName=attribute, attributeType=kind)
            if kind == "doubleAngle":
                owner.getPlug(attribute).set(value, unit="rad")
            else:
                owner.getPlug(attribute).set(value)
        outputs = [("penTranslate", "doubleLinear"), ("crankAngle", "doubleAngle"), ("excessAngle", "doubleAngle"),
                   ("pX", "doubleLinear"), ("pY", "doubleLinear"), ("qX", "doubleLinear"), ("qY", "doubleLinear"),
                   ("aX", "doubleLinear"), ("aY", "doubleLinear"), ("bX", "doubleLinear"), ("bY", "doubleLinear"),
                   ("armAngleA", "doubleAngle"), ("armAngleB", "doubleAngle"), ("opDistance", "doubleLinear"),
                   ("oqDistance", "doubleLinear")]
        outputs += [("arm" + label + "Rotate", "doubleAngle") for label, _ in armPairs]
        for attribute, kind in outputs:
            owner.addAttr(longName=attribute, attributeType=kind)

        def scale(label, source, factor):
            """source を係数倍した数値(係数を明示した unitConversion。角度・長さの自動変換を入れない)。"""
            node = graph._node("unitConversion", label)
            node.getPlug("conversionFactor").set(factor)
            source.connectTo(node.getPlug("input"))
            return node.getPlug("output")

        def total(label, terms, constant=0.0):
            """定数と (source, 係数) の和。animBlendNodeAdditive を連ねて倍精度のまま足す(plusMinusAverageは単精度)。"""
            current = constant
            for index, (source, weight) in enumerate(terms):
                node = graph._node("animBlendNodeAdditive", label + str(index))
                if isinstance(current, float):
                    node.getPlug("inputA").set(current)
                else:
                    current.connectTo(node.getPlug("inputA"))
                node.getPlug("weightA").set(1.0)
                source.connectTo(node.getPlug("inputB"))
                node.getPlug("weightB").set(weight)
                current = node.getPlug("output")
            return current

        def unary(kind, label, source):
            """1入力の数学ノード(sin・cos)の出力を数値で返す。"""
            node = graph._node(kind, label)
            scale(label + "Input", source, 1.0).connectTo(node.getPlug("input"))
            return scale(label + "Number", node.getPlug("output"), 1.0)

        def binary(kind, label, first, second):
            """2入力の数学ノード(atan2・divide)の出力を数値で返す。first・second は plug か定数。"""
            node = graph._node(kind, label)
            for attribute, value in (("input1", first), ("input2", second)):
                if isinstance(value, float):
                    node.getPlug(attribute).set(value)
                else:
                    scale(label + attribute.capitalize(), value, 1.0).connectTo(node.getPlug(attribute))
            return scale(label + "Number", node.getPlug("output"), 1.0)

        def product(label, first, second):
            """2つの数値の積(倍精度の multDoubleLinear。入出力が長さの型なので unitConversion で挟む)。"""
            node = graph._node("multDoubleLinear", label)
            scale(label + "Input1", first, 1.0).connectTo(node.getPlug("input1"))
            scale(label + "Input2", second, 1.0).connectTo(node.getPlug("input2"))
            return scale(label + "Number", node.getPlug("output"), 1.0)

        def clamp(label, source, low, high):
            """source を low〜high に止める(倍精度の clampRange)。"""
            node = graph._node("clampRange", label)
            scale(label + "Input", source, 1.0).connectTo(node.getPlug("input"))
            node.getPlug("minimum").set(low)
            node.getPlug("maximum").set(high)
            return scale(label + "Number", node.getPlug("output"), 1.0)

        def out(label, source, attribute):
            """source を係数1の unitConversion を通して container の出力へつなぐ。"""
            scale(label, source, 1.0).connectTo(owner.getPlug(attribute))

        # θ = クランクの回転(内部単位のラジアンのまま数値) + phase - 生成時の値、菱形が成り立つ ±θmax に止める
        theta = total("theta", [(scale("crankNumber", crank.getPlug(rotateChannel), 1.0), 1.0),
                                (scale("phaseNumber", owner.getPlug("phase"), 1.0), 1.0)],
                      -crank.getPlug(rotateChannel).get(unit="rad"))
        clamped = clamp("crankAngle", theta, -limit, limit)
        out("crankAngleOut", clamped, "crankAngle")
        out("excessAngleOut", total("excessAngle", [(theta, 1.0), (clamped, -1.0)]), "excessAngle")
        # P = (r + r cos θ, r sin θ)
        out("pXOut", total("pX", [(unary("cos", "crankCos", clamped), radius)], radius), "pX")
        out("pYOut", scale("pY", unary("sin", "crankSin", clamped), radius), "pY")
        # φ = θ/2、|OP| = 2r cos φ、|OQ| = k / |OP|、Q = |OQ| (cos φ, sin φ)
        phi = scale("phi", clamped, 0.5)
        cosPhi = unary("cos", "phiCos", phi)
        sinPhi = unary("sin", "phiSin", phi)
        near = scale("opDistance", cosPhi, 2.0 * radius)
        out("opDistanceOut", near, "opDistance")
        far = binary("divide", "oqDistance", constant, near)
        out("oqDistanceOut", far, "oqDistance")
        out("qXOut", product("qX", far, cosPhi), "qX")
        qY = product("qY", far, sinPhi)
        out("qYOut", qY, "qY")
        out("penTranslateOut", total("penTranslate", [(qY, float(penDirection))], pen.getPlug(penChannel).get()),
            "penTranslate")
        # m = (|OP| + |OQ|)/2、h = √(a² - m²)、α = atan2(h, m)、腕は φ ± α
        middle = total("middle", [(near, 0.5), (far, 0.5)])
        squared = graph._node("power", "middleSquared")
        scale("middleSquaredInput", middle, 1.0).connectTo(squared.getPlug("input"))
        squared.getPlug("exponent").set(2.0)
        radicand = total("halfSquared", [(scale("middleSquaredNumber", squared.getPlug("output"), 1.0), -1.0)],
                         arm * arm)
        # 範囲の端では丸め誤差でわずかに負になるので 0 で止める
        root = graph._node("power", "half")
        scale("halfInput", clamp("halfSquaredClamp", radicand, 0.0, arm * arm), 1.0).connectTo(root.getPlug("input"))
        root.getPlug("exponent").set(0.5)
        alpha = binary("atan2", "alpha", scale("halfNumber", root.getPlug("output"), 1.0), middle)
        restAlpha = rest["armAngleA"]
        for label, sign in (("A", 1.0), ("B", -1.0)):
            angle = total("armAngle" + label, [(phi, 1.0), (alpha, sign)])
            out("armAngle" + label + "Out", angle, "armAngle" + label)
            for kind, coordinate in (("cos", "X"), ("sin", "Y")):
                point = label.lower() + coordinate
                out(point + "Out", scale(point, unary(kind, "arm" + label + kind.capitalize(), angle), arm), point)
            target = armA if label == "A" else armB
            if target is not None:
                restRotate = target.getPlug(rotateChannel).get(unit="rad")
                rotate = total("arm" + label + "Rotate", [(angle, float(armDirection))],
                               restRotate - float(armDirection) * sign * restAlpha)
                out("arm" + label + "RotateOut", rotate, "arm" + label + "Rotate")
        if connect:
            owner.getPlug("penTranslate").connectTo(pen.getPlug(penChannel))
            for label, target in armPairs:
                owner.getPlug("arm" + label + "Rotate").connectTo(target.getPlug(rotateChannel))
        owner.setAttrFlags([attribute for attribute, _ in outputs] + [attribute for attribute, _, _ in constants],
                           keyable=False, channelBox=True)
        return graph
