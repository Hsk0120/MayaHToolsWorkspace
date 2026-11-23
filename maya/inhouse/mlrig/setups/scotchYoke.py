"""等速で回るクランクのピンが溝付きのヨークを押し、ヨークを単振動で往復させるスコッチヨークの標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution


class ScotchYoke(TwistDistribution):
    """クランクのピンがヨークの溝(移動軸に垂直)の中を滑り、ヨークを x = r cos θ の単振動で往復させるスコッチヨーク。

    連接棒の無いクランクスライダー(:class:`CrankSlider` の棒の長さを無限にした極限)で、ヨークの位置・速さ・加速度は
    純粋な正弦波になる。溝の中のスライドブロック(ピンに付く)はヨークに対して r sin θ だけ溝に沿って動く。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def motion(cls, theta, crankRadius):
        """クランクの角度からヨークとブロックの動きを計算する(DGと同じ式のPython版)。

        Args:
            theta (float): 生成時からのクランクの回転 + phase (ラジアン)。
            crankRadius (float): ピンの半径 r (cm)。

        Returns:
            dict: ``yokeOffset`` (生成時からのヨークの移動 r (cos θ - 1)、cm)、``blockOffset`` (ヨークに対する
            ブロックの溝に沿った移動 r sin θ、cm)、``velocity`` (dx/dθ、cm/rad)、``acceleration`` (d²x/dθ²、cm/rad²)、
            ``travel`` (行程のどこにいるか (1 - cos θ) / 2、0〜1)、``returnStroke`` (生成時の端へ戻る間1.0)。
            いずれも向きの係数を掛ける前の値。
        """
        sine, cosine = math.sin(theta), math.cos(theta)
        return {
            "yokeOffset": crankRadius * (cosine - 1.0),
            "blockOffset": crankRadius * sine,
            "velocity": -crankRadius * sine,
            "acceleration": -crankRadius * cosine,
            "travel": 0.5 * (1.0 - cosine),
            "returnStroke": 1.0 if sine < 0.0 else 0.0,
        }

    @classmethod
    @undoTransaction("mlrig.ScotchYoke.create")
    def create(cls, crank, yoke, block=None, crankRadius=3.0, name="scotchYoke", axis="z", yokeAxis="x",
               blockAxis="y", yokeDirection=1.0, blockDirection=1.0, connect=True):
        """クランクの回転に連動して、ヨークの往復と溝の中のブロック(任意)の動きを生成する。

        Args:
            crank (str | Node): クランクのtransform。ローカルの ``rotate<axis>`` を回す。生成時の姿勢を θ = 0
                (ピンがヨークの移動軸の正の向きにあり、ヨークが行程の正の端)とする。
            yoke (str | Node): ヨークのtransform。ローカルの ``translate<yokeAxis>`` を動かす。
            block (str | Node | None): 溝の中のブロックのtransform。ヨークの子に置き、ローカルの
                ``translate<blockAxis>`` を溝に沿って動かす。Noneなら作らない。
            crankRadius (float): ピンの半径 r (cm、0より大きい)。生成時に固定する。
            name (str): 一意なcontainer名。
            axis (str): クランクのローカルの回転軸 x/y/z。
            yokeAxis (str): ヨークのローカルの移動軸 x/y/z。生成時のピンの向きに沿わせる。
            blockAxis (str): ブロックのローカルの移動軸 x/y/z。溝の向き(ヨークの移動軸に垂直)に沿わせる。
            yokeDirection (float): ヨークの移動の向き(1.0 か -1.0)。生成時のピンの向きとヨークの移動軸の正の向きが
                逆なら -1.0 にする。
            blockDirection (float): ブロックの移動の向き(1.0 か -1.0)。クランクが +θ 回ったときピンが動く溝の向きと、
                ブロックの移動軸の正の向きが逆なら -1.0 にする。
            connect (bool): Trueならヨークの ``translate<yokeAxis>`` (とブロックの ``translate<blockAxis>``)へ
                出力を接続する。

        Returns:
            ScotchYoke: yokeTranslate・yokeOffset・blockOffset・velocity・acceleration・travel・returnStroke
                (block があれば blockTranslate)の所有者。containerに phase(クランクの角度に足す値)と、
                固定の stroke (2r)を持つ。

        Raises:
            ValueError: 軸・半径・向きが不正な場合、transformでない・同じノードの場合、ヨーク・ブロックの移動が
                既に接続されている場合(connect=True)、またはnameが既に存在する場合。

        Note:
            θ = クランクの rotate<axis> - 生成時の値 + phase、
            yokeOffset = yokeDirection × r (cos θ - 1)、yokeTranslate = 生成時のヨークの translate<yokeAxis> + yokeOffset、
            blockOffset = blockDirection × r sin θ、blockTranslate = 生成時のブロックの translate<blockAxis> + blockOffset、
            velocity = dx/dθ = -yokeDirection × r sin θ、acceleration = -yokeDirection × r cos θ、
            travel = (1 - cos θ) / 2 (生成時の端で0、反対の端で1)、returnStroke = (sin θ < 0)、stroke = 2r。
            θ = 0 ではヨーク・ブロックとも移動0なので、接続しても跳ねない。履歴を持たない閉じた式なので、
            クランクを逆に回すと同じ経路を戻る。
        """
        if axis not in ("x", "y", "z") or yokeAxis not in ("x", "y", "z") or blockAxis not in ("x", "y", "z"):
            raise ValueError("axis, yokeAxis and blockAxis must be x, y or z")
        numbers = (crankRadius, yokeDirection, blockDirection)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers):
            raise ValueError("crankRadius, yokeDirection and blockDirection must be numbers")
        if crankRadius <= 0.0:
            raise ValueError("crankRadius must be more than 0")
        if yokeDirection not in (1.0, -1.0) or blockDirection not in (1.0, -1.0):
            raise ValueError("yokeDirection and blockDirection must be 1.0 or -1.0")
        if mlib.objExists(name):
            raise ValueError("ScotchYoke container already exists: " + name)
        crank, yoke = mlib.Node(crank), mlib.Node(yoke)
        nodes = [crank, yoke] + ([mlib.Node(block)] if block is not None else [])
        if not all(isinstance(node, mlib.Transform) for node in nodes):
            raise ValueError("Expected transforms for the crank, the yoke and the block")
        if len({node.getFullName() for node in nodes}) != len(nodes):
            raise ValueError("The crank, the yoke and the block must be different nodes")
        block = nodes[2] if block is not None else None
        rotateChannel = "rotate" + axis.upper()
        yokeChannel, blockChannel = "translate" + yokeAxis.upper(), "translate" + blockAxis.upper()
        if connect:
            targets = [yoke.getPlug(yokeChannel)] + ([block.getPlug(blockChannel)] if block else [])
            for target in targets:
                if target.getConnections(input=True, skipConversionNodes=True) is not None:
                    raise ValueError("The target is already connected: " + str(target))

        radius = float(crankRadius)
        yokeSign, blockSign = float(yokeDirection), float(blockDirection)
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="phase", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="stroke", attributeType="doubleLinear")
        owner.getPlug("stroke").set(2.0 * radius)
        outputs = [("yokeTranslate", "doubleLinear"), ("yokeOffset", "doubleLinear"), ("blockOffset", "doubleLinear"),
                   ("velocity", "double"), ("acceleration", "double"), ("travel", "double"), ("returnStroke", "double")]
        if block is not None:
            outputs.append(("blockTranslate", "doubleLinear"))
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

        # θ = クランクの回転(内部単位のラジアンのまま数値) + phase - 生成時の値
        theta = total("theta", [(scale("crankNumber", crank.getPlug(rotateChannel), 1.0), 1.0),
                                (scale("phaseNumber", owner.getPlug("phase"), 1.0), 1.0)],
                      -crank.getPlug(rotateChannel).get(unit="rad"))
        trig = []
        for kind in ("sin", "cos"):
            node = graph._node(kind, "theta" + kind.capitalize())
            scale("theta" + kind.capitalize() + "Input", theta, 1.0).connectTo(node.getPlug("input"))
            trig.append(scale("theta" + kind.capitalize() + "Number", node.getPlug("output"), 1.0))
        sine, cosine = trig
        # yokeOffset = dir r (cos θ - 1)、blockOffset = dir r sin θ
        yokeOffset = total("yokeOffset", [(cosine, yokeSign * radius)], -yokeSign * radius)
        out("yokeOffsetOut", yokeOffset, "yokeOffset")
        blockOffset = total("blockOffset", [(sine, blockSign * radius)])
        out("blockOffsetOut", blockOffset, "blockOffset")
        # velocity = -dir r sin θ、acceleration = -dir r cos θ、travel = (1 - cos θ) / 2
        out("velocityOut", scale("velocity", sine, -yokeSign * radius), "velocity")
        out("accelerationOut", scale("acceleration", cosine, -yokeSign * radius), "acceleration")
        out("travelOut", total("travel", [(cosine, -0.5)], 0.5), "travel")
        # returnStroke = (sin θ < 0)。生成時の端へ戻る半周
        stroke = graph._node("condition", "returnStroke")
        stroke.getPlug("operation").set(4)
        sine.connectTo(stroke.getPlug("firstTerm"))
        stroke.getPlug("secondTerm").set(0.0)
        stroke.getPlug("colorIfTrueR").set(1.0)
        stroke.getPlug("colorIfFalseR").set(0.0)
        out("returnStrokeOut", stroke.getPlug("outColorR"), "returnStroke")
        out("yokeTranslateOut", total("yokeTranslate", [(yokeOffset, 1.0)], yoke.getPlug(yokeChannel).get()),
            "yokeTranslate")
        if block is not None:
            out("blockTranslateOut", total("blockTranslate", [(blockOffset, 1.0)], block.getPlug(blockChannel).get()),
                "blockTranslate")
        if connect:
            owner.getPlug("yokeTranslate").connectTo(yoke.getPlug(yokeChannel))
            if block is not None:
                owner.getPlug("blockTranslate").connectTo(block.getPlug(blockChannel))
        owner.setAttrFlags([attribute for attribute, _ in outputs] + ["stroke"], keyable=False, channelBox=True)
        return graph
