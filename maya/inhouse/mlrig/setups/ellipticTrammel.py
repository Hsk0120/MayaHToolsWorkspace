"""直交する2本の溝を滑る2つのスライダーを長さ一定の棒でつなぎ、棒の上の点に楕円を描かせる楕円トランメルの標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution


class EllipticTrammel(TwistDistribution):
    """クランクで棒の中点を回し、2つのスライダーを直交する溝に沿って往復させる楕円トランメル(アルキメデスのトランメル)。

    溝の交点を O、棒の長さを L とすると、クランク(O → 棒の中点、長さ L/2)の角度 θ に対し、スライダーAは
    Aの溝に沿って L cos θ、スライダーBはBの溝に沿って L sin θ の位置にあり、棒はクランクと逆向きに同じ速さで回る。
    棒の上でAから距離 d の点は、半軸 |L - d| と |d| の楕円 ((L - d) cos θ, d sin θ) を描く。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def motion(cls, theta, rodLength, penDistance):
        """クランクの角度からスライダー・棒・棒の上の点の動きを計算する(DGと同じ式のPython版)。

        Args:
            theta (float): 生成時からのクランクの回転 + phase (ラジアン)。
            rodLength (float): 2つのスライダーの間の棒の長さ L (cm)。
            penDistance (float): 棒の上の点のスライダーAからの距離 d (cm)。

        Returns:
            dict: ``aOffset`` (生成時からのスライダーAの移動 L (cos θ - 1)、cm)、``bOffset`` (生成時からの
            スライダーBの移動 L sin θ、cm)、``rodAngle`` (生成時からの棒の回転 -θ、ラジアン)、``penX`` (棒の上の点の
            Aの溝に沿った移動 (L - d)(cos θ - 1)、cm)、``penY`` (Bの溝に沿った移動 d sin θ、cm)。
            いずれも向きの係数を掛ける前の値。
        """
        sine, cosine = math.sin(theta), math.cos(theta)
        return {
            "aOffset": rodLength * (cosine - 1.0),
            "bOffset": rodLength * sine,
            "rodAngle": -theta,
            "penX": (rodLength - penDistance) * (cosine - 1.0),
            "penY": penDistance * sine,
        }

    @classmethod
    @undoTransaction("mlrig.EllipticTrammel.create")
    def create(cls, crank, sliderA, sliderB, rod=None, rodLength=6.0, penDistance=None, name="ellipticTrammel",
               axis="z", aAxis="x", bAxis="y", aDirection=1.0, bDirection=1.0, rodDirection=1.0, connect=True):
        """クランクの回転に連動して、2つのスライダーの往復と棒(任意)の回転を生成する。

        Args:
            crank (str | Node): クランクのtransform。溝の交点に置き、ローカルの ``rotate<axis>`` を回す。生成時の姿勢を
                θ = 0 (棒がAの溝の上に寝て、スライダーAが交点から L、スライダーBが交点)とする。
            sliderA (str | Node): スライダーAのtransform。ローカルの ``translate<aAxis>`` を動かす。
            sliderB (str | Node): スライダーBのtransform。ローカルの ``translate<bAxis>`` を動かす。
            rod (str | Node | None): 棒のtransform。スライダーAの位置に置き(子にする)、ローカルの ``rotate<axis>`` を
                回す。Noneなら作らない。
            rodLength (float): 2つのスライダーの間の棒の長さ L (cm、0より大きい)。生成時に固定する。
            penDistance (float | None): 楕円を描く棒の上の点のスライダーAからの距離 d (cm)。Bを越えた先や
                Aの手前(負)でもよい。Noneなら 1.5 L。生成時に固定する。
            name (str): 一意なcontainer名。
            axis (str): クランクと棒のローカルの回転軸 x/y/z。
            aAxis (str): スライダーAのローカルの移動軸 x/y/z。Aの溝の向きに沿わせる。
            bAxis (str): スライダーBのローカルの移動軸 x/y/z。Bの溝の向きに沿わせる。
            aDirection (float): スライダーAの移動の向き(1.0 か -1.0)。交点からAへの向きとAの移動軸の正の向きが
                逆なら -1.0 にする。
            bDirection (float): スライダーBの移動の向き(1.0 か -1.0)。クランクが +θ 回ったとき棒の中点が向かう
                Bの溝の向きと、Bの移動軸の正の向きが逆なら -1.0 にする。
            rodDirection (float): 棒の回転の向き(1.0 か -1.0)。棒の回転軸がクランクと逆向きなら -1.0 にする。
            connect (bool): Trueならスライダーの ``translate<aAxis>``・``translate<bAxis>`` (と棒の
                ``rotate<axis>``)へ出力を接続する。

        Returns:
            EllipticTrammel: aTranslate・bTranslate・aOffset・bOffset・rodAngle・penX・penY (rod があれば
                rodRotate)の所有者。containerに phase(クランクの角度に足す値)と、固定の rodLength・penDistance・
                semiAxisA (|L - d|)・semiAxisB (|d|)を持つ。

        Raises:
            ValueError: 軸・長さ・距離・向きが不正な場合、transformでない・同じノードの場合、スライダー・棒の
                チャンネルが既に接続されている場合(connect=True)、またはnameが既に存在する場合。

        Note:
            θ = クランクの rotate<axis> - 生成時の値 + phase、
            aOffset = aDirection × L (cos θ - 1)、aTranslate = 生成時のAの translate<aAxis> + aOffset、
            bOffset = bDirection × L sin θ、bTranslate = 生成時のBの translate<bAxis> + bOffset、
            rodAngle = -θ、rodRotate = 生成時の棒の rotate<axis> + rodDirection × rodAngle、
            penX = aDirection × (L - d)(cos θ - 1)、penY = bDirection × d sin θ (棒の上の点のAの溝・Bの溝に沿った
            生成時からの移動)。θ = 0 ではすべて0なので、接続しても跳ねない。履歴を持たない閉じた式なので、
            クランクを逆に回すと同じ経路を戻る。
        """
        axes = (axis, aAxis, bAxis)
        if any(value not in ("x", "y", "z") for value in axes):
            raise ValueError("axis, aAxis and bAxis must be x, y or z")
        numbers = (rodLength, aDirection, bDirection, rodDirection) + ((penDistance,) if penDistance is not None else ())
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers):
            raise ValueError("rodLength, penDistance and the directions must be numbers")
        if rodLength <= 0.0:
            raise ValueError("rodLength must be more than 0")
        if any(value not in (1.0, -1.0) for value in (aDirection, bDirection, rodDirection)):
            raise ValueError("aDirection, bDirection and rodDirection must be 1.0 or -1.0")
        if mlib.objExists(name):
            raise ValueError("EllipticTrammel container already exists: " + name)
        nodes = [mlib.Node(crank), mlib.Node(sliderA), mlib.Node(sliderB)] + ([mlib.Node(rod)] if rod is not None else [])
        if not all(isinstance(node, mlib.Transform) for node in nodes):
            raise ValueError("Expected transforms for the crank, the sliders and the rod")
        if len({node.getFullName() for node in nodes}) != len(nodes):
            raise ValueError("The crank, the sliders and the rod must be different nodes")
        crank, sliderA, sliderB = nodes[:3]
        rod = nodes[3] if rod is not None else None
        rotateChannel = "rotate" + axis.upper()
        aChannel, bChannel = "translate" + aAxis.upper(), "translate" + bAxis.upper()
        if connect:
            targets = [sliderA.getPlug(aChannel), sliderB.getPlug(bChannel)]
            targets += [rod.getPlug(rotateChannel)] if rod is not None else []
            for target in targets:
                if target.getConnections(input=True, skipConversionNodes=True) is not None:
                    raise ValueError("The target is already connected: " + str(target))

        length = float(rodLength)
        distance = 1.5 * length if penDistance is None else float(penDistance)
        aSign, bSign, rodSign = float(aDirection), float(bDirection), float(rodDirection)
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="phase", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        constants = (("rodLength", length), ("penDistance", distance), ("semiAxisA", abs(length - distance)),
                     ("semiAxisB", abs(distance)))
        for attribute, value in constants:
            owner.addAttr(longName=attribute, attributeType="doubleLinear")
            owner.getPlug(attribute).set(value)
        outputs = [("aTranslate", "doubleLinear"), ("bTranslate", "doubleLinear"), ("aOffset", "doubleLinear"),
                   ("bOffset", "doubleLinear"), ("rodAngle", "doubleAngle"), ("penX", "doubleLinear"),
                   ("penY", "doubleLinear")]
        if rod is not None:
            outputs.append(("rodRotate", "doubleAngle"))
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
        # aOffset = dir L (cos θ - 1)、bOffset = dir L sin θ
        aOffset = total("aOffset", [(cosine, aSign * length)], -aSign * length)
        out("aOffsetOut", aOffset, "aOffset")
        bOffset = total("bOffset", [(sine, bSign * length)])
        out("bOffsetOut", bOffset, "bOffset")
        # 棒の上の点 penX = dir (L - d)(cos θ - 1)、penY = dir d sin θ
        out("penXOut", total("penX", [(cosine, aSign * (length - distance))], aSign * (distance - length)), "penX")
        out("penYOut", scale("penY", sine, bSign * distance), "penY")
        # 棒はクランクと逆向きに同じ速さで回る: rodAngle = -θ
        rodAngle = scale("rodAngle", theta, -1.0)
        out("rodAngleOut", rodAngle, "rodAngle")
        out("aTranslateOut", total("aTranslate", [(aOffset, 1.0)], sliderA.getPlug(aChannel).get()), "aTranslate")
        out("bTranslateOut", total("bTranslate", [(bOffset, 1.0)], sliderB.getPlug(bChannel).get()), "bTranslate")
        if rod is not None:
            rest = rod.getPlug(rotateChannel).get(unit="rad")
            out("rodRotateOut", total("rodRotate", [(rodAngle, rodSign)], rest), "rodRotate")
        if connect:
            owner.getPlug("aTranslate").connectTo(sliderA.getPlug(aChannel))
            owner.getPlug("bTranslate").connectTo(sliderB.getPlug(bChannel))
            if rod is not None:
                owner.getPlug("rodRotate").connectTo(rod.getPlug(rotateChannel))
        owner.setAttrFlags([attribute for attribute, _ in outputs] + [attribute for attribute, _ in constants],
                           keyable=False, channelBox=True)
        return graph
