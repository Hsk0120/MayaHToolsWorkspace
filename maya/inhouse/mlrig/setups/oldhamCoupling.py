"""平行にずれた2本の軸を、直交する2つの突起を持つ中間の円板でつなぐオルダム継手の標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

# 回転軸 × 偏心の軸 = 円板の面内でもう1つの軸(と向き)。右手系の外積。
_PERPENDICULAR = {
    ("z", "x"): ("y", 1.0),
    ("z", "y"): ("x", -1.0),
    ("x", "y"): ("z", 1.0),
    ("x", "z"): ("y", -1.0),
    ("y", "z"): ("x", 1.0),
    ("y", "x"): ("z", -1.0),
}


class OldhamCoupling(TwistDistribution):
    """入力軸の溝と出力軸の溝(互いに直交)に中間の円板の突起がはまり、ずれた2本の軸を同じ角速度で回すオルダム継手。

    入力軸の中心を O1、出力軸の中心を O2 (O1 から偏心の軸の向きに e)とすると、入力軸が θ 回ったとき、円板の中心 C は
    入力軸の溝の線と、それに直交して O2 を通る出力軸の溝の線の交点にある。∠O1 C O2 が直角なので C は O1O2 を直径とする
    円(半径 e/2)の上にあり、軸の2倍の速さ 2θ で回る。出力軸と円板は入力軸と同じ θ だけ回る(等速)。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def motion(cls, theta, offset):
        """入力軸の角度から円板と2つの溝の滑りを計算する(DGと同じ式のPython版)。

        Args:
            theta (float): 生成時からの入力軸の回転 + phase (ラジアン)。
            offset (float): 2本の軸の間の距離 e (cm)。

        Returns:
            dict: ``discOffsetU`` (生成時からの円板の中心の偏心の軸に沿った移動 e sin² θ、cm)、``discOffsetV``
            (面内のもう1つの軸に沿った移動 -e sin θ cos θ、cm)、``inputSlide`` (入力軸の溝の中の円板の中心の位置
            -e sin θ、cm)、``outputSlide`` (出力軸の溝の中の位置 -e cos θ、cm)、``orbitAngle`` (円板の中心の公転の
            生成時からの角度 2θ、ラジアン)。
        """
        sine, cosine = math.sin(theta), math.cos(theta)
        return {
            "discOffsetU": offset * sine * sine,
            "discOffsetV": -offset * sine * cosine,
            "inputSlide": -offset * sine,
            "outputSlide": -offset * cosine,
            "orbitAngle": 2.0 * theta,
        }

    @classmethod
    @undoTransaction("mlrig.OldhamCoupling.create")
    def create(cls, inputShaft, outputShaft, disc, offset=2.0, name="oldhamCoupling", axis="z", offsetAxis="x",
               outputDirection=1.0, connect=True):
        """入力軸の回転に連動して、出力軸の回転と、中間の円板の公転(移動)と自転を生成する。

        Args:
            inputShaft (str | Node): 入力軸のtransform。ローカルの ``rotate<axis>`` を回す。生成時の姿勢を θ = 0 (入力軸の
                溝が偏心の向きに直交し、円板の中心が入力軸の中心にある)とする。
            outputShaft (str | Node): 出力軸のtransform。ローカルの ``rotate<axis>`` を動かす。
            disc (str | Node): 中間の円板のtransform。生成時に入力軸の中心に置き、親の空間の ``translate<offsetAxis>``・
                ``translate<面内のもう1つの軸>`` と ``rotate<axis>`` を動かす。親の空間の ``axis`` が軸の向き、
                ``offsetAxis`` が入力軸から出力軸への向きである前提。
            offset (float): 2本の軸の間の距離 e (cm、0より大きい)。生成時に固定する。
            name (str): 一意なcontainer名。
            axis (str): 軸の回転軸 x/y/z。
            offsetAxis (str): 円板の親の空間で、入力軸から出力軸へ向かう軸 x/y/z (axis と別の軸)。
            outputDirection (float): 出力軸の回転の向き(1.0 か -1.0)。出力軸の回転軸の正の向きが入力軸と逆なら -1.0。
            connect (bool): Trueなら出力軸の ``rotate<axis>`` と円板の移動・回転へ出力を接続する。

        Returns:
            OldhamCoupling: outputRotate・discU・discV・discRotate・discOffsetU・discOffsetV・inputSlide・
                outputSlide・orbitAngle の所有者。containerに phase(入力軸の角度に足す値)と、固定の offset・
                orbitRadius (e/2)を持つ。

        Raises:
            ValueError: 軸・距離・向きが不正な場合、transformでない・同じノードの場合、出力軸・円板のチャンネルが既に
                接続されている場合(connect=True)、またはnameが既に存在する場合。

        Note:
            θ = 入力軸の rotate<axis> - 生成時の値 + phase、
            discOffsetU = e sin² θ = (e/2)(1 - cos 2θ)、discOffsetV = -e sin θ cos θ = -(e/2) sin 2θ、
            discU = 生成時の円板の translate<offsetAxis> + discOffsetU、
            discV = 生成時の円板の translate<面内のもう1つの軸> + (外積の向き) × discOffsetV、
            discRotate = 生成時の円板の rotate<axis> + θ、outputRotate = 生成時の出力軸の rotate<axis> + outputDirection × θ、
            inputSlide = -e sin θ、outputSlide = -e cos θ、orbitAngle = 2θ。θ = 0 では移動・回転が0なので、接続しても
            跳ねない。履歴を持たない閉じた式なので、入力軸を逆に回すと同じ経路を戻る。
        """
        if axis not in ("x", "y", "z") or offsetAxis not in ("x", "y", "z"):
            raise ValueError("axis and offsetAxis must be x, y or z")
        if axis == offsetAxis:
            raise ValueError("offsetAxis must be different from axis")
        numbers = (offset, outputDirection)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers):
            raise ValueError("offset and outputDirection must be numbers")
        if offset <= 0.0:
            raise ValueError("offset must be more than 0")
        if outputDirection not in (1.0, -1.0):
            raise ValueError("outputDirection must be 1.0 or -1.0")
        if mlib.objExists(name):
            raise ValueError("OldhamCoupling container already exists: " + name)
        nodes = [mlib.Node(inputShaft), mlib.Node(outputShaft), mlib.Node(disc)]
        if not all(isinstance(node, mlib.Transform) for node in nodes):
            raise ValueError("Expected transforms for the shafts and the disc")
        if len({node.getFullName() for node in nodes}) != len(nodes):
            raise ValueError("The shafts and the disc must be different nodes")
        inputShaft, outputShaft, disc = nodes
        perpendicular, vSign = _PERPENDICULAR[(axis, offsetAxis)]
        rotateChannel = "rotate" + axis.upper()
        uChannel, vChannel = "translate" + offsetAxis.upper(), "translate" + perpendicular.upper()
        if connect:
            targets = [outputShaft.getPlug(rotateChannel), disc.getPlug(uChannel), disc.getPlug(vChannel),
                       disc.getPlug(rotateChannel)]
            for target in targets:
                if target.getSource(skipConversionNodes=True) is not None:
                    raise ValueError("The target is already connected: " + str(target))

        distance = float(offset)
        outputSign = float(outputDirection)
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="phase", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        constants = (("offset", distance), ("orbitRadius", 0.5 * distance))
        for attribute, value in constants:
            owner.addAttr(longName=attribute, attributeType="doubleLinear")
            owner.getPlug(attribute).set(value)
        outputs = [("outputRotate", "doubleAngle"), ("discU", "doubleLinear"), ("discV", "doubleLinear"),
                   ("discRotate", "doubleAngle"), ("discOffsetU", "doubleLinear"), ("discOffsetV", "doubleLinear"),
                   ("inputSlide", "doubleLinear"), ("outputSlide", "doubleLinear"), ("orbitAngle", "doubleAngle")]
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

        def out(label, source, attribute):
            """source を係数1の unitConversion を通して container の出力へつなぐ。"""
            scale(label, source, 1.0).connectTo(owner.getPlug(attribute))

        def trig(label, angle):
            """angle の (sin, cos) を数値で返す。"""
            values = []
            for kind in ("sin", "cos"):
                node = graph._node(kind, label + kind.capitalize())
                scale(label + kind.capitalize() + "Input", angle, 1.0).connectTo(node.getPlug("input"))
                values.append(scale(label + kind.capitalize() + "Number", node.getPlug("output"), 1.0))
            return values

        # θ = 入力軸の回転(内部単位のラジアンのまま数値) + phase - 生成時の値
        theta = total("theta", [(scale("inputNumber", inputShaft.getPlug(rotateChannel), 1.0), 1.0),
                                (scale("phaseNumber", owner.getPlug("phase"), 1.0), 1.0)],
                      -inputShaft.getPlug(rotateChannel).get(unit="rad"))
        sine, cosine = trig("theta", theta)
        double = scale("doubleTheta", theta, 2.0)
        doubleSine, doubleCosine = trig("doubleTheta", double)
        # 円板の中心: C = (e/2)(1 - cos 2θ, -sin 2θ)。O1O2 を直径とする円を 2θ で回る
        discOffsetU = total("discOffsetU", [(doubleCosine, -0.5 * distance)], 0.5 * distance)
        out("discOffsetUOut", discOffsetU, "discOffsetU")
        discOffsetV = scale("discOffsetV", doubleSine, -0.5 * distance)
        out("discOffsetVOut", discOffsetV, "discOffsetV")
        out("discUOut", total("discU", [(discOffsetU, 1.0)], disc.getPlug(uChannel).get()), "discU")
        out("discVOut", total("discV", [(discOffsetV, vSign)], disc.getPlug(vChannel).get()), "discV")
        # 2つの溝の中の位置: 入力の溝 -e sin θ、出力の溝 -e cos θ
        out("inputSlideOut", scale("inputSlide", sine, -distance), "inputSlide")
        out("outputSlideOut", scale("outputSlide", cosine, -distance), "outputSlide")
        out("orbitAngleOut", double, "orbitAngle")
        # 円板と出力軸は入力軸と同じ θ だけ回る(等速)
        rest = disc.getPlug(rotateChannel).get(unit="rad")
        out("discRotateOut", total("discRotate", [(theta, 1.0)], rest), "discRotate")
        rest = outputShaft.getPlug(rotateChannel).get(unit="rad")
        out("outputRotateOut", total("outputRotate", [(theta, outputSign)], rest), "outputRotate")
        if connect:
            owner.getPlug("outputRotate").connectTo(outputShaft.getPlug(rotateChannel))
            owner.getPlug("discU").connectTo(disc.getPlug(uChannel))
            owner.getPlug("discV").connectTo(disc.getPlug(vChannel))
            owner.getPlug("discRotate").connectTo(disc.getPlug(rotateChannel))
        owner.setAttrFlags([attribute for attribute, _ in outputs] + [attribute for attribute, _ in constants],
                           keyable=False, channelBox=True)
        return graph
