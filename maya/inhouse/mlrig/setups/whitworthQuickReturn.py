"""等速で回るクランクから、全周回るスロット付きレバーと連接棒でラムを往復させるWhitworth形の早戻り機構の標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution


class WhitworthQuickReturn(TwistDistribution):
    """クランクのピンがレバーの溝を滑りながら、レバーを全周回すWhitworth形の早戻り機構。

    レバーのピボットはクランクの中心から距離 d、ピンの半径は r (d < r)。ピボットがクランクの円の内側にあるので、
    レバーはクランクと一緒に全周回るが、速さが揺れる。クランクの角度 θ のとき、レバーの角度は
    φ = θ + δ、δ = atan2(-d sin θ, r + d cos θ)。r + d cos θ > 0 なので δ は ±90° の内側で連続し、
    回転数を追わなくても φ は跳ばない。レバーの腕(長さ a)の先から連接棒(長さ L)でピボットを通る直線上の
    ラムを押すと、ラムは a sin φ + √(L² - a² cos² φ) にあり、行程は 2a、戻りはクランクの 2β (β = acos(d / r))の
    間なので、時間比は (180° - β) / β。フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def motion(cls, theta, crankRadius, pivotDistance, armLength=3.0, rodLength=8.0):
        """クランクの角度からレバーとラムの動きを計算する(DGと同じ式のPython版)。

        Args:
            theta (float): 生成時からのクランクの回転 + phase (ラジアン)。
            crankRadius (float): ピンの半径 r (cm)。
            pivotDistance (float): クランクの中心とレバーのピボットの距離 d (cm、0以上で r より小さい)。
            armLength (float): レバーの腕の長さ a (cm)。
            rodLength (float): 連接棒の長さ L (cm、a より大きい)。

        Returns:
            dict: ``leverAngle`` (φ = θ + δ、連続した角度、ラジアン)、``lag`` (δ、ラジアン)、
            ``slotDistance`` (ピボットからピンまでの距離 ρ、cm)、``speedRatio`` (dφ/dθ)、
            ``ramOffset`` (生成時からのラムの移動、cm)、``returnStroke`` (戻りの間1.0)。
        """
        sine, cosine = math.sin(theta), math.cos(theta)
        lag = math.atan2(-pivotDistance * sine, crankRadius + pivotDistance * cosine)
        squared = pivotDistance * pivotDistance + crankRadius * crankRadius + 2.0 * pivotDistance * crankRadius * cosine
        angle = theta + lag
        reach = math.sqrt(rodLength * rodLength - (armLength * math.cos(angle)) ** 2)
        return {
            "leverAngle": angle,
            "lag": lag,
            "slotDistance": math.sqrt(squared),
            "speedRatio": crankRadius * (crankRadius + pivotDistance * cosine) / squared,
            "ramOffset": armLength * math.sin(angle) + reach - math.sqrt(rodLength * rodLength - armLength * armLength),
            "returnStroke": 1.0 if pivotDistance + crankRadius * cosine < 0.0 else 0.0,
        }

    @classmethod
    def timing(cls, crankRadius, pivotDistance):
        """戻りにあたるクランクの角度 2β と、往きと戻りの時間比を返す。

        Args:
            crankRadius (float): ピンの半径 r (cm)。
            pivotDistance (float): クランクの中心とレバーのピボットの距離 d (cm)。

        Returns:
            tuple[float, float]: (2β = 2 acos(d / r)、ラジアン)、(往き / 戻り = (π - β) / β)。
        """
        half = math.acos(pivotDistance / crankRadius)
        return 2.0 * half, (math.pi - half) / half

    @classmethod
    @undoTransaction("mlrig.WhitworthQuickReturn.create")
    def create(cls, crank, lever, ram=None, crankRadius=3.0, pivotDistance=1.5, armLength=3.0, rodLength=8.0,
               name="whitworthQuickReturn", axis="z", ramAxis="x", ramDirection=1.0, connect=True):
        """クランクの回転に連動して、全周回るレバーと連接棒で押されるラム(任意)の動きを生成する。

        Args:
            crank (str | Node): クランクのtransform。ローカルの ``rotate<axis>`` を回す。生成時の姿勢を θ = 0
                (ピンがピボットから最も遠く、レバーがクランクと同じ向き)とする。
            lever (str | Node): レバーのtransform。ピボットに置き、ローカルの ``rotate<axis>`` を動かす。
                クランクと同じ向きの軸で回し、生成時はクランクのピンの方を向けておく。
            ram (str | Node | None): ラムのtransform。ローカルの ``translate<ramAxis>`` を動かす。Noneなら作らない。
            crankRadius (float): ピンの半径 r (cm、0より大きい)。生成時に固定する。
            pivotDistance (float): クランクの中心とピボットの距離 d (cm、0以上で r より小さい)。生成時に固定する。
            armLength (float): レバーの腕の長さ a (cm、0より大きい)。生成時に固定する。
            rodLength (float): 連接棒の長さ L (cm、a より大きい)。生成時に固定する。
            name (str): 一意なcontainer名。
            axis (str): クランクとレバーのローカルの回転軸 x/y/z。
            ramAxis (str): ラムのローカルの移動軸 x/y/z。ピボットを通り、生成時のレバーに垂直な直線に沿わせる。
            ramDirection (float): ラムの移動の向き(1.0 か -1.0)。レバーが +φ 回ったとき腕の先が動く向きと、
                ラムの移動軸の正の向きが逆なら -1.0 にする。
            connect (bool): Trueならレバーの ``rotate<axis>`` (とラムの ``translate<ramAxis>``)へ出力を接続する。

        Returns:
            WhitworthQuickReturn: rotate・leverAngle・lag・slotDistance・speedRatio・ramOffset・returnStroke
                (ram があれば ramTranslate)の所有者。containerに phase(クランクの角度に足す値)と、
                固定の returnAngle (2β)・timeRatio (往き / 戻り)・stroke (2a)を持つ。

        Raises:
            ValueError: 軸・半径・距離・長さ・向きが不正な場合、transformでない・同じノードの場合、レバーの回転・
                ラムの移動が既に接続されている場合(connect=True)、またはnameが既に存在する場合。

        Note:
            θ = クランクの rotate<axis> - 生成時の値 + phase、δ = atan2(-d sin θ, r + d cos θ)、φ = θ + δ、
            ρ = √(d² + r² + 2dr cos θ)、speedRatio = dφ/dθ = r (r + d cos θ) / ρ² (r/(r+d)〜r/(r-d)、常に正)、
            ramOffset = ramDirection × (a sin φ + √(L² - a² cos² φ) - √(L² - a²))、
            rotate = 生成時のレバーの rotate<axis> + φ、ramTranslate = 生成時のラムの translate<ramAxis> + ramOffset。
            ラムの速さは a cos φ と同じ符号なので、cos φ < 0 (d + r cos θ < 0)の間が戻りで returnStroke = 1。
            β = acos(d / r)、returnAngle = 2β、timeRatio = (180° - β) / β、stroke = 2a。θ = 0 では φ = 0 なので、
            接続してもレバーとラムは跳ねない。履歴を持たない閉じた式なので、クランクを逆に回すと同じ経路を戻る。
        """
        if axis not in ("x", "y", "z") or ramAxis not in ("x", "y", "z"):
            raise ValueError("axis and ramAxis must be x, y or z")
        numbers = (crankRadius, pivotDistance, armLength, rodLength, ramDirection)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers):
            raise ValueError("crankRadius, pivotDistance, armLength, rodLength and ramDirection must be numbers")
        if crankRadius <= 0.0 or pivotDistance < 0.0 or pivotDistance >= crankRadius:
            raise ValueError("crankRadius must be more than 0 and pivotDistance from 0 to less than crankRadius")
        if armLength <= 0.0 or rodLength <= armLength:
            raise ValueError("armLength must be more than 0 and rodLength more than armLength")
        if ramDirection not in (1.0, -1.0):
            raise ValueError("ramDirection must be 1.0 or -1.0")
        if mlib.objExists(name):
            raise ValueError("WhitworthQuickReturn container already exists: " + name)
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
                if target.getConnections(input=True, skipConversionNodes=True) is not None:
                    raise ValueError("The target is already connected: " + str(target))

        radius, distance = float(crankRadius), float(pivotDistance)
        arm, rod, direction = float(armLength), float(rodLength), float(ramDirection)
        returnAngle, ratio = cls.timing(radius, distance)
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="phase", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="returnAngle", attributeType="doubleAngle")
        owner.getPlug("returnAngle").set(returnAngle, unit="rad")
        owner.addAttr(longName="timeRatio", attributeType="double")
        owner.getPlug("timeRatio").set(ratio)
        owner.addAttr(longName="stroke", attributeType="doubleLinear")
        owner.getPlug("stroke").set(2.0 * arm)
        outputs = [("rotate", "doubleAngle"), ("leverAngle", "doubleAngle"), ("lag", "doubleAngle"),
                   ("slotDistance", "doubleLinear"), ("speedRatio", "double"), ("ramOffset", "doubleLinear"),
                   ("returnStroke", "double")]
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

        def trig(label, source):
            """source (ラジアンの数値)の sin と cos。"""
            result = []
            for kind in ("sin", "cos"):
                node = graph._node(kind, label + kind.capitalize())
                scale(label + kind.capitalize() + "Input", source, 1.0).connectTo(node.getPlug("input"))
                result.append(scale(label + kind.capitalize() + "Number", node.getPlug("output"), 1.0))
            return result

        # θ = クランクの回転(内部単位のラジアンのまま数値) + phase - 生成時の値
        theta = total("theta", [(scale("crankNumber", crank.getPlug(rotateChannel), 1.0), 1.0),
                                (scale("phaseNumber", owner.getPlug("phase"), 1.0), 1.0)],
                      -crank.getPlug(rotateChannel).get(unit="rad"))
        sine, cosine = trig("theta", theta)
        # δ = atan2(-d sin θ, r + d cos θ)、φ = θ + δ(r + d cos θ > 0 なので δ は折り返さない)
        lag = binary("atan2", "lag", scale("lagY", sine, -distance), total("lagX", [(cosine, distance)], radius))
        scale("lagOut", lag, 1.0).connectTo(owner.getPlug("lag"))
        angle = total("leverAngle", [(theta, 1.0), (lag, 1.0)])
        scale("leverAngleOut", angle, 1.0).connectTo(owner.getPlug("leverAngle"))
        rotate = total("rotate", [(angle, 1.0)], lever.getPlug(rotateChannel).get(unit="rad"))
        scale("rotateOut", rotate, 1.0).connectTo(owner.getPlug("rotate"))
        # ρ² = d² + r² + 2dr cos θ、ρ = (ρ²)^0.5
        squared = total("slotSquared", [(cosine, 2.0 * distance * radius)], distance * distance + radius * radius)
        root = graph._node("power", "slotDistance")
        scale("slotSquaredInput", squared, 1.0).connectTo(root.getPlug("input"))
        root.getPlug("exponent").set(0.5)
        scale("slotDistanceOut", root.getPlug("output"), 1.0).connectTo(owner.getPlug("slotDistance"))
        # speedRatio = r(r + d cos θ) / ρ²
        numerator = total("speedNumerator", [(cosine, radius * distance)], radius * radius)
        speed = binary("divide", "speedRatio", numerator, squared)
        scale("speedRatioOut", speed, 1.0).connectTo(owner.getPlug("speedRatio"))
        # returnStroke = (d + r cos θ < 0)。cos φ と同じ符号なのでラムが戻る間
        pinY = total("pinY", [(cosine, radius)], distance)
        stroke = graph._node("condition", "returnStroke")
        stroke.getPlug("operation").set(4)
        pinY.connectTo(stroke.getPlug("firstTerm"))
        stroke.getPlug("secondTerm").set(0.0)
        stroke.getPlug("colorIfTrueR").set(1.0)
        stroke.getPlug("colorIfFalseR").set(0.0)
        scale("returnStrokeOut", stroke.getPlug("outColorR"), 1.0).connectTo(owner.getPlug("returnStroke"))
        # ramOffset = dir (a sin φ + √(L² - a² cos² φ) - √(L² - a²))(multDoubleLinear は倍精度)
        leverSine, leverCosine = trig("lever", angle)
        product = graph._node("multDoubleLinear", "cosineSquared")
        scale("cosineSquaredInput1", leverCosine, 1.0).connectTo(product.getPlug("input1"))
        scale("cosineSquaredInput2", leverCosine, 1.0).connectTo(product.getPlug("input2"))
        cosineSquared = scale("cosineSquaredNumber", product.getPlug("output"), 1.0)
        reachSquared = total("reachSquared", [(cosineSquared, -arm * arm)], rod * rod)
        reach = graph._node("power", "reach")
        scale("reachSquaredInput", reachSquared, 1.0).connectTo(reach.getPlug("input"))
        reach.getPlug("exponent").set(0.5)
        reachNumber = scale("reachNumber", reach.getPlug("output"), 1.0)
        offset = total("ramOffset", [(leverSine, direction * arm), (reachNumber, direction)],
                       -direction * math.sqrt(rod * rod - arm * arm))
        scale("ramOffsetOut", offset, 1.0).connectTo(owner.getPlug("ramOffset"))
        if ram is not None:
            translate = total("ramTranslate", [(offset, 1.0)], ram.getPlug(translateChannel).get())
            scale("ramTranslateOut", translate, 1.0).connectTo(owner.getPlug("ramTranslate"))
        if connect:
            owner.getPlug("rotate").connectTo(lever.getPlug(rotateChannel))
            if ram is not None:
                owner.getPlug("ramTranslate").connectTo(ram.getPlug(translateChannel))
        owner.setAttrFlags([attribute for attribute, _ in outputs] + ["returnAngle", "timeRatio", "stroke"],
                           keyable=False, channelBox=True)
        return graph
