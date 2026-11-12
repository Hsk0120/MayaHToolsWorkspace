"""回転する板カムの角度から、直動の従動節が休止・上昇・休止・下降を繰り返す変位を求める標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

TURN = 2.0 * math.pi
#: 運動曲線ごとの係数。f(u) = a·u + b·sin(ku) + c·cos(ku) + d、f'(u) = e·sin(ku) + g·cos(ku) + h。
#: ``(k, (a, b, c, d), (e, g, h))`` の順。
LAWS = {
    "cycloidal": (TURN, (1.0, -1.0 / TURN, 0.0, 0.0), (0.0, -1.0, 1.0)),
    "harmonic": (math.pi, (0.0, 0.0, -0.5, 0.5), (math.pi / 2.0, 0.0, 0.0)),
}


def _clamp(value, low, high):
    """value を low〜high に止める。"""
    return min(max(value, low), high)


def _curve(law, progress):
    """運動曲線の (f(u), f'(u)) を返す(DGと同じ係数のPython版)。"""
    frequency, (a, b, c, d), (e, g, h) = LAWS[law]
    sine, cosine = math.sin(frequency * progress), math.cos(frequency * progress)
    return a * progress + b * sine + c * cosine + d, e * sine + g * cosine + h


class CamFollower(TwistDistribution):
    """回転する板カムに押される直動の従動節(フォロワー)の変位を、カムの1回転を4つの区間に分けて求める。

    カムの角度を1回転の中の角度 w (0〜360°)へ折り返し、上昇の進み u1 = clamp(w / β1, 0, 1) と
    下降の進み u2 = clamp((w - β1 - βd) / β2, 0, 1) から、変位 lift = h (f(u1) - f(u2)) を求める。
    運動曲線 f は f(0) = 0・f(1) = 1 なので、下の休止・上昇・上の休止・下降のどの区間でも同じ式になり、
    区間の切り替えで値も速度も連続する。フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def motion(cls, theta, rise, riseAngle, dwellAngle, returnAngle, law="cycloidal"):
        """カムの角度から従動節の変位を計算する(DGと同じ式のPython版)。

        Args:
            theta (float): 生成時からのカムの回転 + phase (ラジアン)。
            rise (float): 上昇量 h (cm)。
            riseAngle (float): 上昇区間の角度 β1 (ラジアン)。
            dwellAngle (float): 上の休止区間の角度 βd (ラジアン)。
            returnAngle (float): 下降区間の角度 β2 (ラジアン)。
            law (str): 運動曲線 ``"cycloidal"`` / ``"harmonic"`` 。

        Returns:
            dict: ``lift`` (変位 cm)、``velocity`` (ds/dθ、cm/ラジアン)、``camAngle`` (w、ラジアン)、
            ``riseProgress`` (u1)、``returnProgress`` (u2)、``turn`` (カムの回転数)。
        """
        turn = math.floor(theta / TURN)
        wrapped = theta - turn * TURN
        upward = _clamp(wrapped / riseAngle, 0.0, 1.0)
        downward = _clamp((wrapped - riseAngle - dwellAngle) / returnAngle, 0.0, 1.0)
        (upValue, upSlope), (downValue, downSlope) = _curve(law, upward), _curve(law, downward)
        return {
            "lift": rise * (upValue - downValue),
            "velocity": rise * (upSlope / riseAngle - downSlope / returnAngle),
            "camAngle": wrapped,
            "riseProgress": upward,
            "returnProgress": downward,
            "turn": float(turn),
        }

    @classmethod
    @undoTransaction("mlrig.CamFollower.create")
    def create(cls, cam, follower, rise=2.0, riseAngle=120.0, dwellAngle=60.0, returnAngle=120.0,
               law="cycloidal", name="camFollower", axis="z", followerAxis="y", connect=True):
        """カムの回転に連動して、休止・上昇・休止・下降を繰り返す従動節の移動を生成する。

        Args:
            cam (str | Node): カムのtransform。ローカルの ``rotate<axis>`` を回す。生成時の姿勢を、
                上昇が始まる直前(下の休止の終わり、θ = 0)とする。
            follower (str | Node): 従動節のtransform。ローカルの ``translate<followerAxis>`` を動かす。
            rise (float): 上昇量 h (cm)。containerの ``rise`` (keyable)で後から変えられる。
            riseAngle (float): 上昇区間のカムの角度 β1 (度、0より大きい)。生成時に固定する。
            dwellAngle (float): 上の休止区間の角度 βd (度、0以上)。生成時に固定する。
            returnAngle (float): 下降区間の角度 β2 (度、0より大きい)。β1 + βd + β2 ≤ 360 で、
                残りが下の休止区間になる。生成時に固定する。
            law (str): 上昇・下降の運動曲線。 ``"cycloidal"`` (速度・加速度とも端で0)か
                ``"harmonic"`` (単弦、速度は端で0、加速度は端で跳ぶ)。
            name (str): 一意なcontainer名。
            axis (str): カムのローカルの回転軸 x/y/z。
            followerAxis (str): 従動節のローカルの移動軸 x/y/z。
            connect (bool): Trueなら従動節の ``translate<followerAxis>`` へ出力を接続する。

        Returns:
            CamFollower: translate・lift・velocity・camAngle・riseProgress・returnProgress・turn の所有者。
                containerに rise と phase(カムの角度に足す値)を持つ。

        Raises:
            ValueError: 軸・運動曲線・角度・上昇量が不正な場合、transformでない・同じノードの場合、
                従動節の移動が既に接続されている場合(connect=True)、またはnameが既に存在する場合。

        Note:
            θ = カムの rotate<axis> - 生成時の値 + phase、w = θ - 360°·floor(θ / 360°)、
            u1 = clamp(w / β1, 0, 1)、u2 = clamp((w - β1 - βd) / β2, 0, 1)、
            lift = h (f(u1) - f(u2))、velocity = h (f'(u1) / β1 - f'(u2) / β2)(角度はラジアン)、
            translate = 生成時の従動節の translate<followerAxis> + lift。
            cycloidal は f(u) = u - sin(2πu) / 2π、harmonic は f(u) = (1 - cos πu) / 2。
            θ = 0 では lift = 0 なので、接続しても従動節は跳ねない。履歴を持たない閉じた式なので、
            カムを逆に回すと従動節も同じ経路を戻る。カムの形状(輪郭)は作らない。
        """
        if axis not in ("x", "y", "z") or followerAxis not in ("x", "y", "z"):
            raise ValueError("axis and followerAxis must be x, y or z")
        if law not in LAWS:
            raise ValueError("law must be one of: " + ", ".join(sorted(LAWS)))
        numbers = (rise, riseAngle, dwellAngle, returnAngle)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers):
            raise ValueError("rise and the angles must be numbers")
        if rise < 0.0 or riseAngle <= 0.0 or returnAngle <= 0.0 or dwellAngle < 0.0:
            raise ValueError("rise and dwellAngle must be 0 or more, riseAngle and returnAngle more than 0")
        if riseAngle + dwellAngle + returnAngle > 360.0 + 1e-9:
            raise ValueError("riseAngle + dwellAngle + returnAngle must be 360 or less")
        if mlib.objExists(name):
            raise ValueError("CamFollower container already exists: " + name)
        cam, follower = mlib.Node(cam), mlib.Node(follower)
        if not isinstance(cam, mlib.Transform) or not isinstance(follower, mlib.Transform):
            raise ValueError("Expected transforms for the cam and the follower")
        if cam.getFullName() == follower.getFullName():
            raise ValueError("The cam and the follower must be different nodes")
        rotateChannel, translateChannel = "rotate" + axis.upper(), "translate" + followerAxis.upper()
        if connect and follower.getPlug(translateChannel).getSource(skipConversionNodes=True) is not None:
            raise ValueError("The translation of the follower is already connected: " + follower.getFullName())

        upAngle, holdAngle, downAngle = (math.radians(value) for value in (riseAngle, dwellAngle, returnAngle))
        frequency, valueTerms, slopeTerms = LAWS[law]
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="rise", attributeType="doubleLinear", defaultValue=0.0, minValue=0.0, keyable=True)
        owner.getPlug("rise").set(float(rise))
        owner.addAttr(longName="phase", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        outputs = (("translate", "doubleLinear"), ("lift", "doubleLinear"), ("velocity", "double"),
                   ("camAngle", "doubleAngle"), ("riseProgress", "double"), ("returnProgress", "double"),
                   ("turn", "double"))
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

        def clamp(label, source):
            """source を 0〜1 に止める。condition の判定(0か1)で blendTwoAttr が倍精度のまま端の値へ切り替える。"""
            current = source
            for side, operation, bound in (("High", 2, 1.0), ("Low", 4, 0.0)):
                beyond = graph._node("condition", label + side + "Beyond")
                beyond.getPlug("operation").set(operation)
                source.connectTo(beyond.getPlug("firstTerm"))
                beyond.getPlug("secondTerm").set(bound)
                beyond.getPlug("colorIfTrueR").set(1.0)
                beyond.getPlug("colorIfFalseR").set(0.0)
                pick = graph._node("blendTwoAttr", label + side + "Clamp")
                current.connectTo(pick.getPlug("input")[0])
                pick.getPlug("input")[1].set(bound)
                beyond.getPlug("outColorR").connectTo(pick.getPlug("attributesBlender"))
                current = pick.getPlug("output")
            return current

        def curve(label, progress, weight, slopeWeight):
            """運動曲線の f(u)·weight と f'(u)·slopeWeight の項(和に渡す (source, 係数) の列)を返す。"""
            trig = {}
            for kind in ("sin", "cos"):
                node = graph._node(kind, label + kind.capitalize())
                # 入出力は版により長さの型なので、係数を明示した unitConversion で数値のまま渡す。
                scale(label + kind.capitalize() + "Input", progress, frequency).connectTo(node.getPlug("input"))
                trig[kind] = scale(label + kind.capitalize() + "Number", node.getPlug("output"), 1.0)
            a, b, c, d = valueTerms
            e, g, h = slopeTerms
            value = [(progress, a * weight), (trig["sin"], b * weight), (trig["cos"], c * weight)]
            slope = [(trig["sin"], e * slopeWeight), (trig["cos"], g * slopeWeight)]
            return value, d * weight, slope, h * slopeWeight

        # θ = カムの回転(内部単位のラジアンのまま数値) + phase - 生成時の値
        theta = total("theta", [(scale("camNumber", cam.getPlug(rotateChannel), 1.0), 1.0),
                                (scale("phaseNumber", owner.getPlug("phase"), 1.0), 1.0)],
                      -cam.getPlug(rotateChannel).get(unit="rad"))
        # 回転数 = floor(θ / 2π)、w = θ - 2π·回転数(0〜2π)
        floor = graph._node("floor", "turn")
        scale("turns", theta, 1.0 / TURN).connectTo(floor.getPlug("input"))
        turn = scale("turnCount", floor.getPlug("output"), 1.0)
        turn.connectTo(owner.getPlug("turn"))
        wrapped = total("wrapped", [(theta, 1.0), (turn, -TURN)])
        scale("camAngleOut", wrapped, 1.0).connectTo(owner.getPlug("camAngle"))
        # u1 = clamp(w / β1, 0, 1)、u2 = clamp((w - β1 - βd) / β2, 0, 1)
        upward = clamp("rise", scale("riseRaw", wrapped, 1.0 / upAngle))
        downward = clamp("return", total("returnRaw", [(wrapped, 1.0 / downAngle)],
                                         -(upAngle + holdAngle) / downAngle))
        scale("riseProgressOut", upward, 1.0).connectTo(owner.getPlug("riseProgress"))
        scale("returnProgressOut", downward, 1.0).connectTo(owner.getPlug("returnProgress"))
        # 正規化した変位 f(u1) - f(u2) と、速度 f'(u1) / β1 - f'(u2) / β2
        upValue, upConstant, upSlope, upSlopeConstant = curve("riseCurve", upward, 1.0, 1.0 / upAngle)
        downValue, downConstant, downSlope, downSlopeConstant = curve("returnCurve", downward, -1.0,
                                                                      -1.0 / downAngle)
        unitLift = total("unitLift", [term for term in upValue + downValue if term[1] != 0.0],
                         upConstant + downConstant)
        unitVelocity = total("unitVelocity", [term for term in upSlope + downSlope if term[1] != 0.0],
                             upSlopeConstant + downSlopeConstant)
        # lift = h·(f(u1) - f(u2))、velocity = h·(f'(u1) / β1 - f'(u2) / β2)(multDoubleLinear は倍精度)
        products = {}
        for label, source in (("lift", unitLift), ("velocity", unitVelocity)):
            product = graph._node("multDoubleLinear", label)
            scale(label + "Rise", owner.getPlug("rise"), 1.0).connectTo(product.getPlug("input1"))
            # multDoubleLinear の入出力は長さの型なので、係数を明示した unitConversion で数値のまま渡す。
            scale(label + "Unit", source, 1.0).connectTo(product.getPlug("input2"))
            products[label] = scale(label + "Number", product.getPlug("output"), 1.0)
            scale(label + "Out", products[label], 1.0).connectTo(owner.getPlug(label))
        translate = total("translate", [(products["lift"], 1.0)], follower.getPlug(translateChannel).get())
        scale("translateOut", translate, 1.0).connectTo(owner.getPlug("translate"))
        if connect:
            owner.getPlug("translate").connectTo(follower.getPlug(translateChannel))
        owner.setAttrFlags([attribute for attribute, _ in outputs], keyable=False, channelBox=True)
        return graph
