"""駆動輪の連続した回転から、ゼネバ機構(外歯車形)の従動輪が間欠的に回る角度を求める標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

TURN = 2.0 * math.pi


def _clamp(value, low, high):
    """value を low〜high に止める。"""
    return min(max(value, low), high)


class GenevaDrive(TwistDistribution):
    """溝が slots 本の従動輪を、駆動輪のピンが1回転に1回だけ溝1つ分(360°/slots)送るゼネバ機構。

    ピンの半径 r と軸間距離 c は、ピンが溝へ接線方向に入る標準の比 λ = r / c = sin(π/n) に固定する。
    駆動輪の角度 θ を1回転ごとの段 k = floor(θ / 2π) と、軸間の線から測ったピンの角度
    α = θ - π - 2πk (-π〜π) に分け、|α| ≤ α0 = π/2 - π/n の間だけピンが溝に入って従動輪を回す。
    溝の角度は β = atan2(λ sin α, 1 - λ cos α) で、α を ±α0 に止めると休止中は β = ±π/n で固定される
    (β は α0 で最大になるので、止めた α から求めた β は連続する)。フレームごとのPython・エクスプレッションは
    使わない。
    """

    @classmethod
    def motion(cls, theta, slots):
        """駆動輪の角度から従動輪の送りを計算する(DGと同じ式のPython版)。

        Args:
            theta (float): 生成時からの駆動輪の回転(ラジアン)。
            slots (int): 従動輪の溝の数(3以上)。

        Returns:
            dict: ``indexAngle`` (従動輪が送られた角度 φ、ラジアン)、``crankAngle`` (α、ラジアン)、
            ``engaged`` (ピンが溝に入っていれば1.0)、``speedRatio`` (dφ/dθ)、``step`` (k)。
        """
        ratio = math.sin(math.pi / slots)
        limit = math.pi / 2.0 - math.pi / slots
        step = math.floor(theta / TURN)
        crank = theta - math.pi - step * TURN
        clamped = _clamp(crank, -limit, limit)
        slot = math.atan2(ratio * math.sin(clamped), 1.0 - ratio * math.cos(clamped))
        cosine = math.cos(clamped)
        return {
            "indexAngle": step * TURN / slots + math.pi / slots + slot,
            "crankAngle": crank,
            "engaged": 1.0 if -limit <= crank <= limit else 0.0,
            "speedRatio": ratio * (cosine - ratio) / (1.0 + ratio * ratio - 2.0 * ratio * cosine),
            "step": float(step),
        }

    @classmethod
    @undoTransaction("mlrig.GenevaDrive.create")
    def create(cls, driver, wheel, slots=4, name="genevaDrive", axis="z", connect=True):
        """駆動輪の回転に連動して、休止と送りを繰り返す従動輪の回転を生成する。

        Args:
            driver (str | Node): 駆動輪(ピンの付いた輪)のtransform。ローカルの ``rotate<axis>`` を回す。
                生成時の姿勢を、ピンが従動輪と反対側にある休止の中央(θ = 0)とする。
            wheel (str | Node): 従動輪(溝の付いた輪)のtransform。
            slots (int): 従動輪の溝の数(3以上の整数)。生成時に固定する。
            name (str): 一意なcontainer名。
            axis (str): 両方の輪のローカルの回転軸 x/y/z。
            connect (bool): Trueなら従動輪の ``rotate<axis>`` へ出力を接続する。

        Returns:
            GenevaDrive: rotate・indexAngle・crankAngle・engaged・speedRatio・step の所有者。
                containerに phase(従動輪の向きの合わせ)を持つ。

        Raises:
            ValueError: 軸・溝の数が不正な場合、transformでない・同じノードの場合、従動輪の回転が既に
                接続されている場合(connect=True)、またはnameが既に存在する場合。

        Note:
            θ = 駆動輪の rotate<axis> - 生成時の値、k = floor(θ / 2π)、α = θ - π - 2πk、
            α' = clamp(α, -α0, α0)、β = atan2(λ sin α', 1 - λ cos α')、
            indexAngle = φ = k·2π/n + π/n + β、rotate = 生成時の従動輪の rotate<axis> + phase - φ
            (外歯車形なので従動輪は駆動輪と逆向きに回る)。engaged = 1 (|α| ≤ α0)、
            speedRatio = λ(cos α' - λ) / (1 + λ² - 2λ cos α')(休止中は0、溝の中央で最大 λ / (1 - λ))。
            θ = 0 では φ = 0 なので、接続しても従動輪は跳ねない。駆動輪を1回転させると従動輪は 360°/n 送られ、
            逆に回すと戻る。休止中の駆動輪の三日月形のカム(ロック)は形状として扱わない。
        """
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        if isinstance(slots, bool) or not isinstance(slots, int) or slots < 3:
            raise ValueError("slots must be an integer of 3 or more")
        if mlib.objExists(name):
            raise ValueError("GenevaDrive container already exists: " + name)
        driver, wheel = mlib.Node(driver), mlib.Node(wheel)
        if not isinstance(driver, mlib.Transform) or not isinstance(wheel, mlib.Transform):
            raise ValueError("Expected transforms for the driver and the wheel")
        if driver.getFullName() == wheel.getFullName():
            raise ValueError("The driver and the wheel must be different nodes")
        channel = "rotate" + axis.upper()
        if connect and wheel.getPlug(channel).getSource(skipConversionNodes=True) is not None:
            raise ValueError("The rotation of the wheel is already connected: " + wheel.getFullName())

        ratio = math.sin(math.pi / slots)
        limit = math.pi / 2.0 - math.pi / slots
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="phase", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        for attribute, kind in (("rotate", "doubleAngle"), ("indexAngle", "doubleAngle"),
                                ("crankAngle", "doubleAngle"), ("engaged", "double"),
                                ("speedRatio", "double"), ("step", "double")):
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

        # θ = 駆動輪の回転(内部単位のラジアンのまま数値) - 生成時の値
        theta = total("theta", [(scale("driveNumber", driver.getPlug(channel), 1.0), 1.0)],
                      -driver.getPlug(channel).get(unit="rad"))
        # k = floor(θ / 2π)。floor の入出力は版により長さの型なので、係数を明示した unitConversion で数値のまま渡す。
        floor = graph._node("floor", "step")
        scale("turns", theta, 1.0 / TURN).connectTo(floor.getPlug("input"))
        step = scale("stepCount", floor.getPlug("output"), 1.0)
        step.connectTo(owner.getPlug("step"))
        # α = θ - π - 2πk
        crank = total("crank", [(theta, 1.0), (step, -TURN)], -math.pi)
        scale("crankOut", crank, 1.0).connectTo(owner.getPlug("crankAngle"))
        # α' = clamp(α, -α0, α0)。condition の判定(0か1)で blendTwoAttr が倍精度のまま端の値へ切り替える
        # (判定は単精度だが、β は ±α0 で極値なので切り替えの角度の誤差は結果にほぼ影響しない)。
        clamped, beyondFlags = crank, []
        for label, operation, bound in (("high", 2, limit), ("low", 4, -limit)):
            beyond = graph._node("condition", label + "Beyond")
            beyond.getPlug("operation").set(operation)
            crank.connectTo(beyond.getPlug("firstTerm"))
            beyond.getPlug("secondTerm").set(bound)
            beyond.getPlug("colorIfTrueR").set(1.0)
            beyond.getPlug("colorIfFalseR").set(0.0)
            pick = graph._node("blendTwoAttr", label + "Clamp")
            clamped.connectTo(pick.getPlug("input")[0])
            pick.getPlug("input")[1].set(bound)
            beyond.getPlug("outColorR").connectTo(pick.getPlug("attributesBlender"))
            clamped = pick.getPlug("output")
            beyondFlags.append((beyond.getPlug("outColorR"), -1.0))
        # engaged = 1 - high - low
        total("engaged", beyondFlags, 1.0).connectTo(owner.getPlug("engaged"))
        # sin α'・cos α'(入出力は版により長さの型なので、係数を明示した unitConversion で渡す)
        trig = {}
        for kind in ("sin", "cos"):
            node = graph._node(kind, kind)
            scale(kind + "Input", clamped, 1.0).connectTo(node.getPlug("input"))
            trig[kind] = scale(kind + "Number", node.getPlug("output"), 1.0)
        # β = atan2(λ sin α', 1 - λ cos α')
        slot = graph._node("atan2", "slotAngle")
        scale("slotY", trig["sin"], ratio).connectTo(slot.getPlug("input1"))
        scale("slotX", total("slotX", [(trig["cos"], -ratio)], 1.0), 1.0).connectTo(slot.getPlug("input2"))
        beta = scale("slotNumber", slot.getPlug("output"), 1.0)
        # φ = k·2π/n + π/n + β、rotate = 生成時の値 + phase - φ
        index = total("index", [(step, TURN / slots), (beta, 1.0)], math.pi / slots)
        scale("indexOut", index, 1.0).connectTo(owner.getPlug("indexAngle"))
        rotate = total("rotate", [(scale("phaseNumber", owner.getPlug("phase"), 1.0), 1.0), (index, -1.0)],
                       wheel.getPlug(channel).get(unit="rad"))
        scale("rotateOut", rotate, 1.0).connectTo(owner.getPlug("rotate"))
        # speedRatio = λ(cos α' - λ) / (1 + λ² - 2λ cos α')
        divide = graph._node("divide", "speedRatio")
        numerator = total("speedNumerator", [(trig["cos"], ratio)], -ratio * ratio)
        denominator = total("speedDenominator", [(trig["cos"], -2.0 * ratio)], 1.0 + ratio * ratio)
        scale("speedNumeratorInput", numerator, 1.0).connectTo(divide.getPlug("input1"))
        scale("speedDenominatorInput", denominator, 1.0).connectTo(divide.getPlug("input2"))
        scale("speedOut", divide.getPlug("output"), 1.0).connectTo(owner.getPlug("speedRatio"))
        if connect:
            owner.getPlug("rotate").connectTo(wheel.getPlug(channel))
        owner.setAttrFlags(["rotate", "indexAngle", "crankAngle", "engaged", "speedRatio", "step"],
                           keyable=False, channelBox=True)
        return graph
