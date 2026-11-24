"""ヘリコプターの斜板(スワッシュプレート)の傾きと高さから、回るブレードのピッチ角を作る標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution


class Swashplate(TwistDistribution):
    """傾いた斜板の面に乗ったピッチリンクが、ローターとともに回るブレードのピッチ角を変える斜板の機構。

    回らない斜板(下の板)を上下に動かす(コレクティブ)・傾ける(サイクリック)と、ローターとともに回る上の板の
    ピッチリンクの高さが方位角ごとに変わり、ホーン(長さ L)を押してブレードをピッチ軸のまわりに回す。
    ローターの回転軸を親の空間の +Y とし、斜板の面(ローカルの原点を通り、ローカルの +Y を法線とする面)の上で、
    ローターの軸から半径 Rs、方位角 ψ のピッチリンクの高さは y = G - Rs (a cos ψ - b sin ψ)
    (a = nx / ny、b = nz / ny、G は軸の上の面の高さ)。ブレードのピッチ角は θ = atan2(d, √(L² - d²))
    (d はリンクの高さの中立からの変化)。フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def motion(cls, rotorAngle, plateNormal, platePosition, rotorPosition, linkRadius, hornLength, count,
               linkAzimuth=0.0, neutralHeight=0.0, maxPitch=math.radians(30.0)):
        """斜板の面とローターの角度から、各ブレードのリンクの高さとピッチ角を計算する(DGと同じ式のPython版)。

        Args:
            rotorAngle (float): ローターの rotateY (ラジアン)。
            plateNormal (tuple): 斜板の面の法線 (nx, ny, nz)。ny は0より大きい。長さは問わない。
            platePosition (tuple): 斜板の面が通る点 (px, py, pz) (cm)。
            rotorPosition (tuple): ローターの軸の位置 (cx, cz) (cm)。
            linkRadius (float): ピッチリンクの軸からの半径 Rs (cm)。
            hornLength (float): ホーンの長さ L (cm)。
            count (int): ブレードの数 N。
            linkAzimuth (float): ブレードの方位角からピッチリンクまでの角度 (ラジアン)。
            neutralHeight (float): ピッチ角が0になるリンクの高さ (cm)。
            maxPitch (float): ピッチ角の上限 (ラジアン、0より大きく π/2 より小さい)。

        Returns:
            dict: ``collective`` (軸の上の面の高さ G - neutralHeight、cm)、``tiltA``・``tiltB`` (a・b)、
            各ブレードのlist ``azimuth`` (ブレードの方位角 ψ + 2πi/N、ラジアン)、``linkHeight`` (中立からの
            リンクの高さ d、cm)、``linkExcess`` (±L sin(maxPitch) を超えた量、cm)、``bladePitch`` (ラジアン)。
        """
        nx, ny, nz = (float(value) for value in plateNormal)
        tiltA, tiltB = nx / ny, nz / ny
        center = (platePosition[1] + tiltA * (platePosition[0] - rotorPosition[0])
                  + tiltB * (platePosition[2] - rotorPosition[1]))
        reach = hornLength * math.sin(maxPitch)
        result = {"collective": center - neutralHeight, "tiltA": tiltA, "tiltB": tiltB, "azimuth": [],
                  "linkHeight": [], "linkExcess": [], "bladePitch": []}
        for index in range(count):
            azimuth = rotorAngle + 2.0 * math.pi * index / count
            link = azimuth + linkAzimuth
            height = center - linkRadius * (tiltA * math.cos(link) - tiltB * math.sin(link)) - neutralHeight
            clamped = min(max(height, -reach), reach)
            result["azimuth"].append(azimuth)
            result["linkHeight"].append(height)
            result["linkExcess"].append(height - clamped)
            result["bladePitch"].append(math.atan2(clamped, math.sqrt(max(hornLength * hornLength - clamped * clamped,
                                                                            0.0))))
        return result

    @classmethod
    @undoTransaction("mlrig.Swashplate.create")
    def create(cls, swashplate, rotor, blades, linkRadius=2.0, hornLength=1.5, maxPitch=30.0, linkAzimuth=0.0,
               name="swashplate", pitchAxis="x", pitchDirection=1.0, connect=True):
        """斜板の高さ・傾きとローターの回転に連動する、ブレードのピッチ角(とブレードの回転)を生成する。

        Args:
            swashplate (str | Node): 回らない斜板のtransform。ローカルの原点を通り、ローカルの +Y を法線とする面を
                斜板の面とする。上下に動かす・X/Zまわりに傾ける。ローターと同じ親の下に置く。
            rotor (str | Node): ローターのtransform。ローカルの ``rotateY`` で回す(親の +Y が回転軸)。生成時の
                translateX・translateZ を回転軸の位置に固定する。
            blades (list): ブレードのtransform(1つ以上)。i 番目のブレードの方位角を ローターの rotateY + 2πi/N
                とし、ローカルの ``rotate<pitchAxis>`` を回す。ふつうはローターの子に置く。
            linkRadius (float): ピッチリンクの軸からの半径 Rs (cm、0より大きい)。生成時に固定する。
            hornLength (float): ホーンの長さ L (cm、0より大きい)。生成時に固定する。
            maxPitch (float): ピッチ角の上限 (度、0より大きく90より小さい)。リンクの高さを ±L sin(maxPitch) に
                止める。生成時に固定する。
            linkAzimuth (float): ブレードの方位角からピッチリンクまでの角度の初期値(度)。containerの
                ``linkAzimuth`` で後から変えられる(実機では斜板の傾きとローター面の傾きのずれ(位相)を補う)。
            name (str): 一意なcontainer名。
            pitchAxis (str): ブレードのローカルのピッチ軸 x/y/z。
            pitchDirection (float): ピッチの回転の向き(1.0 か -1.0)。リンクが上がると前縁が上がる向きが
                ピッチ軸の負の向きなら -1.0。
            connect (bool): Trueなら各ブレードの ``rotate<pitchAxis>`` へ ``bladeRotate[i]`` を接続する。

        Returns:
            Swashplate: collective・tiltA・tiltB と、ブレードごとの azimuth[]・linkHeight[]・linkExcess[]・
                bladePitch[]・bladeRotate[] の所有者。containerに linkAzimuth と、固定の linkRadius・hornLength・
                maxPitch・neutralHeight・bladeCount を持つ。

        Raises:
            ValueError: 軸・長さ・角度・向きが不正な場合、ブレードが無い場合、transformでない・同じノードの場合、
                斜板とローターの親が違う場合、生成時の斜板の法線が下向き・水平の場合、ブレードのチャンネルが既に
                接続されている場合(connect=True)、またはnameが既に存在する場合。

        Note:
            n = 斜板の matrix の +Y 軸の行、p = 斜板の matrix の移動、a = nx / ny、b = nz / ny、
            G = py + a (px - cx) + b (pz - cz)、collective = G - G0 (G0 は生成時の G = neutralHeight)、
            ψi = ローターの rotateY + 2πi/N、y_i = G - Rs (a cos(ψi + linkAzimuth) - b sin(ψi + linkAzimuth))、
            d_i = y_i - G0、dc_i = clamp(d_i, -L sin(maxPitch), L sin(maxPitch))、linkExcess_i = d_i - dc_i、
            bladePitch_i = atan2(dc_i, √(L² - dc_i²))、bladeRotate_i = 生成時の rotate<pitchAxis> +
            pitchDirection × (bladePitch_i - 生成時の bladePitch_i)。生成時は回転が変わらないので、接続しても跳ねない。
        """
        if pitchAxis not in ("x", "y", "z"):
            raise ValueError("pitchAxis must be x, y or z")
        numbers = (linkRadius, hornLength, maxPitch, linkAzimuth, pitchDirection)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers):
            raise ValueError("The lengths, the angles and the direction must be numbers")
        if linkRadius <= 0.0 or hornLength <= 0.0:
            raise ValueError("linkRadius and hornLength must be more than 0")
        if not 0.0 < maxPitch < 90.0:
            raise ValueError("maxPitch must be more than 0 and less than 90 degrees")
        if pitchDirection not in (1.0, -1.0):
            raise ValueError("pitchDirection must be 1.0 or -1.0")
        if isinstance(blades, (str, mlib.Node)) or not blades:
            raise ValueError("blades must be a non-empty list of transforms")
        if mlib.objExists(name):
            raise ValueError("Swashplate container already exists: " + name)
        nodes = [mlib.Node(swashplate), mlib.Node(rotor)] + [mlib.Node(blade) for blade in blades]
        if not all(isinstance(node, mlib.Transform) for node in nodes):
            raise ValueError("Expected transforms for the swashplate, the rotor and the blades")
        if len({node.getName(full=True) for node in nodes}) != len(nodes):
            raise ValueError("The swashplate, the rotor and the blades must be different nodes")
        plate, rotor, blades = nodes[0], nodes[1], nodes[2:]
        plateParent, rotorParent = plate.getParent(), rotor.getParent()
        if (plateParent.getName(full=True) if plateParent else None) != (rotorParent.getName(full=True) if rotorParent else None):
            raise ValueError("The swashplate and the rotor must have the same parent")
        pitchChannel = "rotate" + pitchAxis.upper()
        if connect:
            for blade in blades:
                target = blade.getPlug(pitchChannel)
                if target.getConnections(input=True, skipConversionNodes=True) is not None:
                    raise ValueError("The target is already connected: " + str(target))
        matrix = plate.getPlug("matrix").get()
        normal = (matrix[4], matrix[5], matrix[6])
        if normal[1] <= 1.0e-6:
            raise ValueError("The swashplate's local +Y must point up (the rotor axis side)")
        position = (matrix[12], matrix[13], matrix[14])
        axisX, axisZ = rotor.getPlug("translateX").get(), rotor.getPlug("translateZ").get()
        radius, horn, limit = float(linkRadius), float(hornLength), math.radians(float(maxPitch))
        count = len(blades)
        neutral = cls.motion(0.0, normal, position, (axisX, axisZ), radius, horn, 1)["collective"]
        rest = cls.motion(rotor.getPlug("rotateY").get(unit="rad"), normal, position, (axisX, axisZ), radius, horn,
                          count, math.radians(float(linkAzimuth)), neutral, limit)
        reach = horn * math.sin(limit)

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="linkAzimuth", attributeType="doubleAngle", keyable=True)
        owner.getPlug("linkAzimuth").set(float(linkAzimuth))
        constants = (("linkRadius", "doubleLinear", radius), ("hornLength", "doubleLinear", horn),
                     ("maxPitch", "doubleAngle", limit), ("neutralHeight", "doubleLinear", neutral),
                     ("bladeCount", "long", count))
        for attribute, kind, value in constants:
            owner.addAttr(longName=attribute, attributeType=kind)
            if kind == "doubleAngle":
                owner.getPlug(attribute).set(value, unit="rad")
            else:
                owner.getPlug(attribute).set(value)
        outputs = [("collective", "doubleLinear"), ("tiltA", "double"), ("tiltB", "double")]
        multis = [("azimuth", "doubleAngle"), ("linkHeight", "doubleLinear"), ("linkExcess", "doubleLinear"),
                  ("bladePitch", "doubleAngle"), ("bladeRotate", "doubleAngle")]
        for attribute, kind in outputs:
            owner.addAttr(longName=attribute, attributeType=kind)
        for attribute, kind in multis:
            owner.addAttr(longName=attribute, attributeType=kind, multi=True)

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
            """2入力の数学ノード(atan2・divide)の出力を数値で返す。"""
            node = graph._node(kind, label)
            for attribute, value in (("input1", first), ("input2", second)):
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

        def out(label, source, target):
            """source を係数1の unitConversion を通して container の出力へつなぐ。"""
            scale(label, source, 1.0).connectTo(target)

        # 斜板の面: 法線 n = matrix の +Y 行、通る点 p = matrix の移動(倍精度の rowFromMatrix で行を取り出す)
        vectors = {}
        for label, row in (("normal", 1), ("origin", 3)):
            node = graph._node("rowFromMatrix", label)
            plate.getPlug("matrix").connectTo(node.getPlug("matrix"))
            node.getPlug("input").set(row)
            vectors[label] = [node.getPlug("output" + axis) for axis in "XYZ"]
        nx, ny, nz = vectors["normal"]
        px, py, pz = vectors["origin"]
        # a = nx / ny、b = nz / ny、G = py + a (px - cx) + b (pz - cz)
        tiltA = binary("divide", "tiltA", nx, ny)
        tiltB = binary("divide", "tiltB", nz, ny)
        out("tiltAOut", tiltA, owner.getPlug("tiltA"))
        out("tiltBOut", tiltB, owner.getPlug("tiltB"))
        center = total("center", [(py, 1.0), (product("tiltAOffset", tiltA, total("offsetX", [(px, 1.0)], -axisX)), 1.0),
                                  (product("tiltBOffset", tiltB, total("offsetZ", [(pz, 1.0)], -axisZ)), 1.0)])
        out("collectiveOut", total("collective", [(center, 1.0)], -neutral), owner.getPlug("collective"))
        # ψi = ローターの rotateY(内部単位のラジアンのまま数値) + 2πi/N、リンクは ψi + linkAzimuth
        rotorAngle = scale("rotorNumber", rotor.getPlug("rotateY"), 1.0)
        offset = scale("linkAzimuthNumber", owner.getPlug("linkAzimuth"), 1.0)
        for index, blade in enumerate(blades):
            prefix = "blade" + str(index)
            azimuth = total(prefix + "Azimuth", [(rotorAngle, 1.0)], 2.0 * math.pi * index / count)
            out(prefix + "AzimuthOut", azimuth, owner.getPlug("azimuth")[index])
            link = total(prefix + "Link", [(azimuth, 1.0), (offset, 1.0)])
            cosLink = unary("cos", prefix + "Cos", link)
            sinLink = unary("sin", prefix + "Sin", link)
            # d = G - Rs (a cos - b sin) - G0
            height = total(prefix + "Height", [(center, 1.0), (product(prefix + "CosTerm", tiltA, cosLink), -radius),
                                               (product(prefix + "SinTerm", tiltB, sinLink), radius)], -neutral)
            out(prefix + "HeightOut", height, owner.getPlug("linkHeight")[index])
            clamped = clamp(prefix + "Clamp", height, -reach, reach)
            out(prefix + "ExcessOut", total(prefix + "Excess", [(height, 1.0), (clamped, -1.0)]),
                owner.getPlug("linkExcess")[index])
            # θ = atan2(dc, √(L² - dc²))。L sin(maxPitch) < L なので根号の中は正
            squared = graph._node("power", prefix + "Squared")
            scale(prefix + "SquaredInput", clamped, 1.0).connectTo(squared.getPlug("input"))
            squared.getPlug("exponent").set(2.0)
            root = graph._node("power", prefix + "Root")
            radicand = total(prefix + "Radicand", [(scale(prefix + "SquaredNumber", squared.getPlug("output"), 1.0),
                                                    -1.0)], horn * horn)
            scale(prefix + "RootInput", radicand, 1.0).connectTo(root.getPlug("input"))
            root.getPlug("exponent").set(0.5)
            pitch = binary("atan2", prefix + "Pitch", clamped, scale(prefix + "RootNumber", root.getPlug("output"), 1.0))
            out(prefix + "PitchOut", pitch, owner.getPlug("bladePitch")[index])
            restRotate = blade.getPlug(pitchChannel).get(unit="rad")
            rotate = total(prefix + "Rotate", [(pitch, float(pitchDirection))],
                           restRotate - float(pitchDirection) * rest["bladePitch"][index])
            out(prefix + "RotateOut", rotate, owner.getPlug("bladeRotate")[index])
            if connect:
                owner.getPlug("bladeRotate")[index].connectTo(blade.getPlug(pitchChannel))
        owner.setAttrFlags([attribute for attribute, _ in outputs] + [attribute for attribute, _, _ in constants],
                           keyable=False, channelBox=True)
        return graph
