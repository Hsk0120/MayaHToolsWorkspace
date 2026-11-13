"""等速で回るクランクから、スロット付きレバーが往きはゆっくり・戻りは速く振れる早戻り機構の標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution


class QuickReturn(TwistDistribution):
    """クランクのピンがレバーの溝(スロット)を滑りながら、ピボットのまわりにレバーを振る早戻り機構。

    クランクの中心はレバーのピボットから距離 d、ピンの半径は r (d > r)。クランクの角度 θ (θ = 0 でピンが
    ピボットから最も遠く、レバーは中央)のとき、ピボットから見たピンは (r sin θ, d + r cos θ) にあり、
    レバーの角度は φ = atan2(r sin θ, d + r cos θ)。レバーは ±α (α = asin(r / d))の間を振れ、
    往きはクランクの 180° + 2α、戻りは 180° - 2α の間にあたるので、等速のクランクでも戻りが速い。
    高さ H の水平なラムの溝をレバーの先が押すと、ラムは H tan φ 動く。フレームごとのPython・エクスプレッションは
    使わない。
    """

    @classmethod
    def motion(cls, theta, crankRadius, pivotDistance, ramHeight=0.0):
        """クランクの角度からレバーとラムの動きを計算する(DGと同じ式のPython版)。

        Args:
            theta (float): 生成時からのクランクの回転 + phase (ラジアン)。
            crankRadius (float): ピンの半径 r (cm)。
            pivotDistance (float): クランクの中心とレバーのピボットの距離 d (cm、r より大きい)。
            ramHeight (float): ピボットからラムの溝までの高さ H (cm)。

        Returns:
            dict: ``leverAngle`` (φ、ラジアン)、``slotDistance`` (ピボットからピンまでの距離 ρ、cm)、
            ``ramOffset`` (H tan φ、cm)、``speedRatio`` (dφ/dθ)、``returnStroke`` (戻りの間1.0)。
        """
        x = crankRadius * math.sin(theta)
        y = pivotDistance + crankRadius * math.cos(theta)
        squared = x * x + y * y
        speed = crankRadius * (crankRadius + pivotDistance * math.cos(theta)) / squared
        return {
            "leverAngle": math.atan2(x, y),
            "slotDistance": math.sqrt(squared),
            "ramOffset": ramHeight * x / y,
            "speedRatio": speed,
            "returnStroke": 1.0 if speed < 0.0 else 0.0,
        }

    @classmethod
    def swing(cls, crankRadius, pivotDistance):
        """レバーの振れの片側の角度 α と、往きと戻りの時間比を返す。

        Args:
            crankRadius (float): ピンの半径 r (cm)。
            pivotDistance (float): クランクの中心とレバーのピボットの距離 d (cm)。

        Returns:
            tuple[float, float]: (α = asin(r / d)、ラジアン)、(往き / 戻り = (π + 2α) / (π - 2α))。
        """
        half = math.asin(crankRadius / pivotDistance)
        return half, (math.pi + 2.0 * half) / (math.pi - 2.0 * half)

    @classmethod
    @undoTransaction("mlrig.QuickReturn.create")
    def create(cls, crank, lever, ram=None, crankRadius=2.0, pivotDistance=5.0, ramHeight=8.0,
               name="quickReturn", axis="z", ramAxis="x", connect=True):
        """クランクの回転に連動して、早戻りで振れるレバー(と任意でラム)の動きを生成する。

        Args:
            crank (str | Node): クランクのtransform。ローカルの ``rotate<axis>`` を回す。生成時の姿勢を、
                ピンがピボットから最も遠い位置(θ = 0、レバーは中央)とする。
            lever (str | Node): レバーのtransform。ピボットに置き、ローカルの ``rotate<axis>`` を動かす。
                クランクと同じ向きの軸で回し、生成時はクランクの中心の方を向けておく。
            ram (str | Node | None): ラムのtransform。ローカルの ``translate<ramAxis>`` を動かす。Noneなら作らない。
            crankRadius (float): ピンの半径 r (cm、0より大きい)。生成時に固定する。
            pivotDistance (float): クランクの中心とピボットの距離 d (cm、r より大きい)。生成時に固定する。
            ramHeight (float): ピボットからラムの溝までの高さ H (cm)。containerの ``ramHeight`` (keyable)で
                後から変えられる。ラムの移動軸の正の向きがレバーの +φ の傾きと逆なら負の値にする。
            name (str): 一意なcontainer名。
            axis (str): クランクとレバーのローカルの回転軸 x/y/z。
            ramAxis (str): ラムのローカルの移動軸 x/y/z。
            connect (bool): Trueならレバーの ``rotate<axis>`` (とラムの ``translate<ramAxis>``)へ出力を接続する。

        Returns:
            QuickReturn: rotate・leverAngle・slotDistance・ramOffset・speedRatio・returnStroke
                (ram があれば ramTranslate)の所有者。containerに phase(クランクの角度に足す値)・ramHeight と、
                固定の swingAngle (α)・timeRatio (往き / 戻り)を持つ。

        Raises:
            ValueError: 軸・半径・距離が不正な場合、transformでない・同じノードの場合、レバーの回転・ラムの移動が
                既に接続されている場合(connect=True)、またはnameが既に存在する場合。

        Note:
            θ = クランクの rotate<axis> - 生成時の値 + phase、x = r sin θ、y = d + r cos θ、
            φ = atan2(x, y)、ρ = √(x² + y²) = √(d² + r² + 2dr cos θ)、ramOffset = H x / y = H tan φ、
            speedRatio = dφ/dθ = r (r + d cos θ) / ρ²(負の間が戻りで returnStroke = 1)、
            rotate = 生成時のレバーの rotate<axis> + φ、ramTranslate = 生成時のラムの translate<ramAxis> + ramOffset。
            α = asin(r / d)、timeRatio = (180° + 2α) / (180° - 2α)。θ = 0 では φ = 0 なので、接続しても
            レバーは跳ねない。d > r なので y > 0 で、atan2・割り算は折り返さない。履歴を持たない閉じた式なので、
            クランクを逆に回すとレバーも同じ経路を戻る。
        """
        if axis not in ("x", "y", "z") or ramAxis not in ("x", "y", "z"):
            raise ValueError("axis and ramAxis must be x, y or z")
        numbers = (crankRadius, pivotDistance, ramHeight)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers):
            raise ValueError("crankRadius, pivotDistance and ramHeight must be numbers")
        if crankRadius <= 0.0 or pivotDistance <= crankRadius:
            raise ValueError("crankRadius must be more than 0 and pivotDistance more than crankRadius")
        if mlib.objExists(name):
            raise ValueError("QuickReturn container already exists: " + name)
        crank, lever = mlib.Node(crank), mlib.Node(lever)
        nodes = [crank, lever] + ([mlib.Node(ram)] if ram is not None else [])
        if not all(isinstance(node, mlib.Transform) for node in nodes):
            raise ValueError("Expected transforms for the crank, the lever and the ram")
        if len({node.getFullName() for node in nodes}) != len(nodes):
            raise ValueError("The crank, the lever and the ram must be different nodes")
        ram = nodes[2] if ram is not None else None
        rotateChannel, translateChannel = "rotate" + axis.upper(), "translate" + ramAxis.upper()
        if connect:
            targets = [lever.getPlug(rotateChannel)] + ([ram.getPlug(translateChannel)] if ram else [])
            for target in targets:
                if target.getSource(skipConversionNodes=True) is not None:
                    raise ValueError("The target is already connected: " + str(target))

        radius, distance = float(crankRadius), float(pivotDistance)
        half, ratio = cls.swing(radius, distance)
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="phase", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="ramHeight", attributeType="doubleLinear", defaultValue=0.0, keyable=True)
        owner.getPlug("ramHeight").set(float(ramHeight))
        owner.addAttr(longName="swingAngle", attributeType="doubleAngle")
        owner.getPlug("swingAngle").set(half, unit="rad")
        owner.addAttr(longName="timeRatio", attributeType="double")
        owner.getPlug("timeRatio").set(ratio)
        outputs = [("rotate", "doubleAngle"), ("leverAngle", "doubleAngle"), ("slotDistance", "doubleLinear"),
                   ("ramOffset", "doubleLinear"), ("speedRatio", "double"), ("returnStroke", "double")]
        if ram is not None:
            outputs.append(("ramTranslate", "doubleLinear"))
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

        def binary(kind, label, first, second):
            """2入力の数学ノード(atan2・divide)の出力。入出力は版により長さの型なので unitConversion で挟む。"""
            node = graph._node(kind, label)
            scale(label + "Input1", first, 1.0).connectTo(node.getPlug("input1"))
            scale(label + "Input2", second, 1.0).connectTo(node.getPlug("input2"))
            return scale(label + "Number", node.getPlug("output"), 1.0)

        # θ = クランクの回転(内部単位のラジアンのまま数値) + phase - 生成時の値
        theta = total("theta", [(scale("crankNumber", crank.getPlug(rotateChannel), 1.0), 1.0),
                                (scale("phaseNumber", owner.getPlug("phase"), 1.0), 1.0)],
                      -crank.getPlug(rotateChannel).get(unit="rad"))
        trig = {}
        for kind in ("sin", "cos"):
            node = graph._node(kind, kind)
            scale(kind + "Input", theta, 1.0).connectTo(node.getPlug("input"))
            trig[kind] = scale(kind + "Number", node.getPlug("output"), 1.0)
        # ピボットから見たピンの位置 x = r sin θ、y = d + r cos θ
        x = scale("pinX", trig["sin"], radius)
        y = total("pinY", [(trig["cos"], radius)], distance)
        # φ = atan2(x, y)、rotate = 生成時の値 + φ
        lean = binary("atan2", "leverAngle", x, y)
        scale("leverAngleOut", lean, 1.0).connectTo(owner.getPlug("leverAngle"))
        rotate = total("rotate", [(lean, 1.0)], lever.getPlug(rotateChannel).get(unit="rad"))
        scale("rotateOut", rotate, 1.0).connectTo(owner.getPlug("rotate"))
        # ρ² = d² + r² + 2dr cos θ、ρ = (ρ²)^0.5
        squared = total("slotSquared", [(trig["cos"], 2.0 * distance * radius)], distance * distance + radius * radius)
        root = graph._node("power", "slotDistance")
        scale("slotSquaredInput", squared, 1.0).connectTo(root.getPlug("input"))
        root.getPlug("exponent").set(0.5)
        scale("slotDistanceOut", root.getPlug("output"), 1.0).connectTo(owner.getPlug("slotDistance"))
        # speedRatio = r(r + d cos θ) / ρ²、returnStroke = (speedRatio < 0)
        numerator = total("speedNumerator", [(trig["cos"], radius * distance)], radius * radius)
        speed = binary("divide", "speedRatio", numerator, squared)
        scale("speedRatioOut", speed, 1.0).connectTo(owner.getPlug("speedRatio"))
        stroke = graph._node("condition", "returnStroke")
        stroke.getPlug("operation").set(4)
        speed.connectTo(stroke.getPlug("firstTerm"))
        stroke.getPlug("secondTerm").set(0.0)
        stroke.getPlug("colorIfTrueR").set(1.0)
        stroke.getPlug("colorIfFalseR").set(0.0)
        scale("returnStrokeOut", stroke.getPlug("outColorR"), 1.0).connectTo(owner.getPlug("returnStroke"))
        # ramOffset = H·x / y(multDoubleLinear は倍精度。入出力が長さの型なので unitConversion で挟む)
        tangent = binary("divide", "tangent", x, y)
        product = graph._node("multDoubleLinear", "ramOffset")
        scale("ramHeightNumber", owner.getPlug("ramHeight"), 1.0).connectTo(product.getPlug("input1"))
        scale("tangentInput", tangent, 1.0).connectTo(product.getPlug("input2"))
        offset = scale("ramOffsetNumber", product.getPlug("output"), 1.0)
        scale("ramOffsetOut", offset, 1.0).connectTo(owner.getPlug("ramOffset"))
        if ram is not None:
            translate = total("ramTranslate", [(offset, 1.0)], ram.getPlug(translateChannel).get())
            scale("ramTranslateOut", translate, 1.0).connectTo(owner.getPlug("ramTranslate"))
        if connect:
            owner.getPlug("rotate").connectTo(lever.getPlug(rotateChannel))
            if ram is not None:
                owner.getPlug("ramTranslate").connectTo(ram.getPlug(translateChannel))
        owner.setAttrFlags([attribute for attribute, _ in outputs] + ["swingAngle", "timeRatio"],
                           keyable=False, channelBox=True)
        return graph
