"""入力の点の動きを、固定点を中心に一定の倍率で写すパンタグラフ(平行四辺形リンク)の標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

_PLANES = {"xy": "z", "yz": "x", "zx": "y"}


class Pantograph(TwistDistribution):
    """固定点 O・なぞる点 P・ペン Q が常に一直線で OQ = k·OP になるパンタグラフ。

    固定点 O から長い腕 O-A-B (|OA| = a、|OB| = k a)を出し、A から P へ長さ b の棒、B から Q へ長さ k b の棒、
    P から BQ の上の点 C へ長さ (k - 1) a の棒をつなぐと、A-P-C-B は平行四辺形になり、Q = O + k (P - O) になる。
    P が腕の届く範囲 (|a - b| 〜 a + b) を出たときは、O から見た向きを保ったまま範囲の端で止める。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def limits(cls, armLength, linkLength, minimumDistance=None):
        """なぞる点 P が届く、固定点からの距離の範囲を返す。

        Args:
            armLength (float): 固定点から肘 A までの腕の長さ a (cm)。
            linkLength (float): 肘 A からなぞる点 P までの棒の長さ b (cm)。
            minimumDistance (float | None): 近い側の端 (cm)。Noneなら max(|a - b|, 0.001 (a + b))。

        Returns:
            tuple: (近い側の端, 遠い側の端 a + b) (cm)。
        """
        nearest = max(abs(armLength - linkLength), 0.001 * (armLength + linkLength))
        if minimumDistance is not None:
            nearest = float(minimumDistance)
        return nearest, armLength + linkLength

    @classmethod
    def motion(cls, tracerU, tracerV, armLength, linkLength, ratio, elbow=1.0, minimumDistance=None):
        """固定点から見たなぞる点の位置から、止めた後の P・Q・A・B・C と棒の角度を計算する(DGと同じ式のPython版)。

        Args:
            tracerU (float): 固定点 O から見たなぞる点の u の位置 (cm)。
            tracerV (float): 固定点 O から見たなぞる点の v の位置 (cm)。
            armLength (float): 固定点から肘 A までの腕の長さ a (cm)。
            linkLength (float): 肘 A からなぞる点 P までの棒の長さ b (cm)。
            ratio (float): 倍率 k。
            elbow (float): 肘 A を O→P の線のどちら側へ曲げるか(1.0 は u から v へ回る側、-1.0 は逆)。
            minimumDistance (float | None): 近い側の端 (cm)。Noneなら :meth:`limits` の既定。

        Returns:
            dict: ``tracerDistance`` (|OP|、止める前)、``clampedDistance`` (止めた後)、``excess`` (止めた量。遠すぎると
            正、近すぎると負)、``tracerAngle`` (O→P の u からの角度、ラジアン)、``armAngle`` (腕 O→A の角度)、
            ``linkAngle`` (棒 A→P の角度)、``pU``・``pV``・``qU``・``qV``・``aU``・``aV``・``bU``・``bV``・``cU``・``cV``
            (固定点 O から見た位置、cm)。
        """
        nearest, farthest = cls.limits(armLength, linkLength, minimumDistance)
        distance = math.hypot(tracerU, tracerV)
        angle = math.atan2(tracerV, tracerU)
        clamped = min(max(distance, nearest), farthest)
        along = 0.5 * clamped + 0.5 * (armLength * armLength - linkLength * linkLength) / clamped
        height = math.sqrt(max(armLength * armLength - along * along, 0.0))
        cosine, sine = math.cos(angle), math.sin(angle)
        pU, pV = clamped * cosine, clamped * sine
        aU = along * cosine - elbow * height * sine
        aV = along * sine + elbow * height * cosine
        return {
            "tracerDistance": distance,
            "clampedDistance": clamped,
            "excess": distance - clamped,
            "tracerAngle": angle,
            "armAngle": angle + elbow * math.atan2(height, along),
            "linkAngle": angle - elbow * math.atan2(height, clamped - along),
            "pU": pU,
            "pV": pV,
            "qU": ratio * pU,
            "qV": ratio * pV,
            "aU": aU,
            "aV": aV,
            "bU": ratio * aU,
            "bV": ratio * aV,
            "cU": pU + (ratio - 1.0) * aU,
            "cV": pV + (ratio - 1.0) * aV,
        }

    @classmethod
    @undoTransaction("mlrig.Pantograph.create")
    def create(cls, tracer, pen, arm=None, link=None, armLength=4.0, linkLength=4.0, ratio=2.0, name="pantograph",
               plane="xy", pivot=(0.0, 0.0), elbow=1.0, minimumDistance=None, linkRelative=False, connect=True):
        """なぞる点の移動に連動して、k 倍の動きをするペンと、腕・棒(任意)の回転を生成する。

        Args:
            tracer (str | Node): なぞる点 P のtransform(入力)。ローカルの ``translate`` の plane の2軸を読む。
            pen (str | Node): ペン Q のtransform。ローカルの ``translate`` の plane の2軸を動かす。生成時の位置を
                基準にして動くので、 tracer と同じ親の下で ``pivot + k (P - pivot)`` に置くと本物のパンタグラフと
                同じ位置になる。
            arm (str | Node | None): 固定点 O に置く長い腕 O-A-B のtransform。plane に垂直な軸の ``rotate`` を回す。
                Noneなら作らない。
            link (str | Node | None): 肘 A に置く棒 A-P のtransform。plane に垂直な軸の ``rotate`` を回す。
                Noneなら作らない。
            armLength (float): 腕の長さ a = |OA| (cm、0より大きい)。生成時に固定する。
            linkLength (float): 棒の長さ b = |AP| (cm、0より大きい)。生成時に固定する。
            ratio (float): 倍率 k (0以外。負なら固定点の反対側へ逆さに写す)。生成時に固定する。
            name (str): 一意なcontainer名。
            plane (str): 機構が動く平面 xy/yz/zx。1文字目が u、2文字目が v の軸で、残りの軸が回転軸
                (u から v へ回る向きが正)。
            pivot (tuple): tracer の親の空間での固定点 O の (u, v) の位置 (cm)。生成時に固定する。
            elbow (float): 肘 A を O→P の線のどちら側へ曲げるか(1.0 は u から v へ回る側、-1.0 は逆)。
            minimumDistance (float | None): P を止める近い側の端 (cm)。Noneなら max(|a - b|, 0.001 (a + b))。
                指定するときは既定の値以上で a + b より小さいこと。
            linkRelative (bool): Trueなら link を arm の子として扱い、腕に対する角度(linkAngle - armAngle)で回す。
            connect (bool): Trueならペンの ``translate`` の2軸(と腕・棒の ``rotate``)へ出力を接続する。

        Returns:
            Pantograph: penTranslateU・penTranslateV・tracerDistance・clampedDistance・excess・tracerAngle・armAngle・
                linkAngle・pU・pV・qU・qV・aU・aV・bU・bV・cU・cV (腕・棒があれば armRotate・linkRotate)の所有者。
                containerに固定の armLength・linkLength・ratio・minimumDistance・maximumDistance・pivotU・pivotV を持つ。

        Raises:
            ValueError: 平面・長さ・倍率・固定点・向きが不正な場合、transformでない・同じノードの場合、ペン・腕・棒の
                チャンネルが既に接続されている場合(connect=True)、またはnameが既に存在する場合。

        Note:
            p = tracer の translate - pivot、d = |p|、ψ = atan2(pV, pU)、d' = clamp(d, 近い端, a + b)、
            excess = d - d'、P = d' (cos ψ, sin ψ)、Q = k P、m = d'/2 + (a² - b²) / (2 d')、h = √(a² - m²)、
            A = m ê + elbow h ê⊥ (ê = (cos ψ, sin ψ))、B = k A、C = P + (k - 1) A、
            armAngle = ψ + elbow atan2(h, m)、linkAngle = ψ - elbow atan2(h, d' - m)、
            penTranslate = 生成時の translate + (Q - 生成時の Q)、armRotate = 生成時の rotate + (armAngle - 生成時の値)。
            生成時は移動・回転の変化が0なので、接続しても跳ねない。
        """
        if plane not in _PLANES:
            raise ValueError("plane must be xy, yz or zx")
        if (not isinstance(pivot, (tuple, list))) or len(pivot) != 2:
            raise ValueError("pivot must be a pair of numbers")
        numbers = [armLength, linkLength, ratio, elbow] + list(pivot)
        if minimumDistance is not None:
            numbers.append(minimumDistance)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers):
            raise ValueError("The lengths, the ratio, the pivot and the elbow must be numbers")
        if armLength <= 0.0 or linkLength <= 0.0 or ratio == 0.0:
            raise ValueError("armLength and linkLength must be more than 0, ratio must not be 0")
        if elbow not in (1.0, -1.0):
            raise ValueError("elbow must be 1.0 or -1.0")
        a, b, k, side = float(armLength), float(linkLength), float(ratio), float(elbow)
        nearest, farthest = cls.limits(a, b)
        if minimumDistance is not None:
            if not nearest <= minimumDistance < farthest:
                raise ValueError("minimumDistance must be between the default and armLength + linkLength")
            nearest = float(minimumDistance)
        if not all(isinstance(value, bool) for value in (linkRelative, connect)):
            raise ValueError("linkRelative and connect must be bool")
        if mlib.objExists(name):
            raise ValueError("Pantograph container already exists: " + name)
        bars = [(label, mlib.Node(node)) for label, node in (("arm", arm), ("link", link)) if node is not None]
        tracer, pen = mlib.Node(tracer), mlib.Node(pen)
        nodes = [tracer, pen] + [node for _, node in bars]
        if not all(isinstance(node, mlib.Transform) for node in nodes):
            raise ValueError("Expected transforms for the tracer, the pen, the arm and the link")
        if len({node.getName(full=True) for node in nodes}) != len(nodes):
            raise ValueError("The tracer, the pen, the arm and the link must be different nodes")
        channels = ["translate" + letter.upper() for letter in plane]
        rotateChannel = "rotate" + _PLANES[plane].upper()
        if connect:
            targets = [pen.getPlug(channel) for channel in ["translate"] + channels]
            for _, node in bars:
                targets += [node.getPlug("rotate"), node.getPlug(rotateChannel)]
            for target in targets:
                if target.getConnections(input=True, skipConversionNodes=True) is not None:
                    raise ValueError("The target is already connected: " + str(target))

        pivotU, pivotV = float(pivot[0]), float(pivot[1])
        startU = tracer.getPlug(channels[0]).get() - pivotU
        startV = tracer.getPlug(channels[1]).get() - pivotV
        rest = cls.motion(startU, startV, a, b, k, side, nearest)
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        constants = (("armLength", "doubleLinear", a), ("linkLength", "doubleLinear", b), ("ratio", "double", k),
                     ("minimumDistance", "doubleLinear", nearest), ("maximumDistance", "doubleLinear", farthest),
                     ("pivotU", "doubleLinear", pivotU), ("pivotV", "doubleLinear", pivotV))
        for attribute, kind, value in constants:
            owner.addAttr(longName=attribute, attributeType=kind)
            owner.getPlug(attribute).set(value)
        outputs = [("penTranslateU", "doubleLinear"), ("penTranslateV", "doubleLinear"),
                   ("tracerDistance", "doubleLinear"), ("clampedDistance", "doubleLinear"), ("excess", "doubleLinear"),
                   ("tracerAngle", "doubleAngle"), ("armAngle", "doubleAngle"), ("linkAngle", "doubleAngle")]
        outputs += [(point + coordinate, "doubleLinear") for point in "pqabc" for coordinate in "UV"]
        outputs += [(label + "Rotate", "doubleAngle") for label, _ in bars]
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

        def root(label, source):
            """source の平方根。source は0以上にしてから渡す。"""
            node = graph._node("power", label)
            scale(label + "Input", source, 1.0).connectTo(node.getPlug("input"))
            node.getPlug("exponent").set(0.5)
            return scale(label + "Number", node.getPlug("output"), 1.0)

        def out(source, attribute):
            """source を係数1の unitConversion を通して container の出力へつなぐ。"""
            scale(attribute + "Out", source, 1.0).connectTo(owner.getPlug(attribute))

        # p = tracer の translate(内部単位の cm のまま数値) - pivot、d = |p|、ψ = atan2(pV, pU)
        inputU = total("inputU", [(scale("tracerU", tracer.getPlug(channels[0]), 1.0), 1.0)], -pivotU)
        inputV = total("inputV", [(scale("tracerV", tracer.getPlug(channels[1]), 1.0), 1.0)], -pivotV)
        squared = total("distanceSquared", [(product("inputUSquared", inputU, inputU), 1.0),
                                            (product("inputVSquared", inputV, inputV), 1.0)])
        distance = root("tracerDistance", squared)
        out(distance, "tracerDistance")
        angle = binary("atan2", "tracerAngle", inputV, inputU)
        out(angle, "tracerAngle")
        # 腕の届く範囲 (近い端 〜 a + b) に止める。向き ψ は保つ
        clamped = clamp("clampedDistance", distance, nearest, farthest)
        out(clamped, "clampedDistance")
        out(total("excess", [(distance, 1.0), (clamped, -1.0)]), "excess")
        cosine = unary("cos", "tracerCos", angle)
        sine = unary("sin", "tracerSin", angle)
        pU = product("pU", clamped, cosine)
        pV = product("pV", clamped, sine)
        # m = d'/2 + (a² - b²) / (2 d') (肘 A から O→P の線へ下ろした垂線の足)、h = √(a² - m²)
        along = total("along", [(clamped, 0.5), (binary("divide", "alongOffset", 0.5 * (a * a - b * b), clamped), 1.0)])
        heightSquared = total("heightSquared", [(product("alongSquared", along, along), -1.0)], a * a)
        # 範囲の端では丸め誤差でわずかに負になるので 0 で止める
        height = root("height", clamp("heightSquaredClamp", heightSquared, 0.0, a * a))
        # A = m ê + elbow h ê⊥
        aU = total("aU", [(product("alongCos", along, cosine), 1.0), (product("heightSin", height, sine), -side)])
        aV = total("aV", [(product("alongSin", along, sine), 1.0), (product("heightCos", height, cosine), side)])
        points = {"p": (pU, pV), "a": (aU, aV), "q": (scale("qU", pU, k), scale("qV", pV, k)),
                  "b": (scale("bU", aU, k), scale("bV", aV, k)),
                  "c": (total("cU", [(pU, 1.0), (aU, k - 1.0)]), total("cV", [(pV, 1.0), (aV, k - 1.0)]))}
        for point, (first, second) in points.items():
            out(first, point + "U")
            out(second, point + "V")
        # armAngle = ψ + elbow atan2(h, m)、linkAngle = ψ - elbow atan2(h, d' - m)
        linkAlong = total("linkAlong", [(clamped, 1.0), (along, -1.0)])
        angles = {
            "arm": total("armAngle", [(angle, 1.0), (binary("atan2", "armOffset", height, along), side)]),
            "link": total("linkAngle", [(angle, 1.0), (binary("atan2", "linkOffset", height, linkAlong), -side)]),
        }
        out(angles["arm"], "armAngle")
        out(angles["link"], "linkAngle")
        # ペンは生成時の位置から Q の変化だけ動く
        for index, coordinate in enumerate("UV"):
            start = pen.getPlug(channels[index]).get() - rest["q" + coordinate]
            out(total("penTranslate" + coordinate, [(points["q"][index], 1.0)], start), "penTranslate" + coordinate)
        for label, node in bars:
            start = node.getPlug(rotateChannel).get(unit="rad") - rest[label + "Angle"]
            terms = [(angles[label], 1.0)]
            if label == "link" and linkRelative:
                start += rest["armAngle"]
                terms.append((angles["arm"], -1.0))
            out(total(label + "Rotate", terms, start), label + "Rotate")
        if connect:
            for index, coordinate in enumerate("UV"):
                owner.getPlug("penTranslate" + coordinate).connectTo(pen.getPlug(channels[index]))
            for label, node in bars:
                owner.getPlug(label + "Rotate").connectTo(node.getPlug(rotateChannel))
        owner.setAttrFlags([attribute for attribute, _ in outputs] + [attribute for attribute, _, _ in constants],
                           keyable=False, channelBox=True)
        return graph
