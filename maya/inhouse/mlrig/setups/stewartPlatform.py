"""台座と天板の取り付け点の距離から、スチュワートプラットフォームの脚の長さ・超過・向きを求める標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution


class StewartPlatform(TwistDistribution):
    """天板の位置と向きから、伸縮する脚(ふつう6本)の長さを求めるスチュワートプラットフォーム(パラレルリンクの逆運動学)。

    天板(と台座)のtransformを自由に動かすと、脚ごとに台座側の取り付け点と天板側の取り付け点の距離が決まる。
    脚の長さは ``minimum``〜``maximum`` に止め、止めた量を ``excess`` に出す。シリンダーは台座側の取り付け点から
    天板側の取り付け点を向き、ロッドはシリンダーの軸に沿って止めた長さだけ進む。天板は止めない。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def legs(cls, basePoints, platformPoints, minimum, maximum):
        """取り付け点の位置から脚の長さと超過を計算する(DGと同じ式のPython版)。

        Args:
            basePoints (list): 台座側の取り付け点のワールド位置 (x, y, z) のlist (cm)。
            platformPoints (list): 天板側の取り付け点のワールド位置 (x, y, z) のlist (cm)。同じ数。
            minimum (float): 最も縮んだ脚の長さ (cm)。
            maximum (float): 最も伸びた脚の長さ (cm)。

        Returns:
            dict: ``length`` (取り付け点の距離のlist、cm)、``clampedLength`` (minimum〜maximum に止めた長さのlist)、
            ``excess`` (length - clampedLength のlist。伸びすぎは正、縮みすぎは負)、``stroke`` (行程のどこにいるか
            (length - minimum) / (maximum - minimum) のlist。止めない)、``maxExcess`` (|excess| の最大)、
            ``reachable`` (すべての脚が範囲内なら1.0、そうでなければ0.0)。

        Raises:
            ValueError: 点の数が合わない・空の場合。
        """
        if len(basePoints) != len(platformPoints) or not basePoints:
            raise ValueError("basePoints and platformPoints must be non-empty lists of the same size")
        lengths = [math.sqrt(sum((b - a) ** 2 for a, b in zip(base, top))) for base, top in zip(basePoints, platformPoints)]
        clamped = [min(max(length, minimum), maximum) for length in lengths]
        excess = [length - limit for length, limit in zip(lengths, clamped)]
        worst = max(abs(value) for value in excess)
        return {
            "length": lengths,
            "clampedLength": clamped,
            "excess": excess,
            "stroke": [(length - minimum) / (maximum - minimum) for length in lengths],
            "maxExcess": worst,
            "reachable": 1.0 if worst <= 0.0 else 0.0,
        }

    @classmethod
    @undoTransaction("mlrig.StewartPlatform.create")
    def create(cls, baseAnchors, platformAnchors, cylinders=None, rods=None, minimum=None, maximum=None,
               name="stewartPlatform", aimAxis="y", upAxis="x", connect=True):
        """台座側と天板側の取り付け点の組から、脚の長さ・超過・シリンダーの向き・ロッドの進みを生成する。

        Args:
            baseAnchors (list): 台座側の取り付け点のtransformのlist(ふつう6つ。台座の子に置く)。
            platformAnchors (list): 天板側の取り付け点のtransformのlist(同じ数。天板の子に置く)。i 番目どうしを脚で結ぶ。
            cylinders (list | None): 脚のシリンダーのtransformのlist(同じ数)。台座側の取り付け点の位置へ置き、
                ローカルの aimAxis を天板側の取り付け点へ向ける。jointは使えない。Noneなら動かさない。
            rods (list | None): 脚のロッドのtransformのlist(同じ数)。i 番目のシリンダーの子に置き、ローカルの
                ``translate<aimAxis>`` を止めた脚の長さにする(範囲内ではロッドの原点が天板側の取り付け点に重なる)。
                cylinders が必要。Noneなら動かさない。
            minimum (float | None): 最も縮んだ脚の長さ (cm)。Noneなら生成時の最も短い脚の0.75倍。
            maximum (float | None): 最も伸びた脚の長さ (cm)。Noneなら生成時の最も長い脚の1.25倍。
            name (str): 一意なcontainer名。
            aimAxis (str): シリンダーのローカルで相手へ向ける軸 x/y/z。
            upAxis (str): シリンダーのローカルで、台座側の取り付け点の同じ軸へ寄せる軸 x/y/z。aimAxis と異なる。
            connect (bool): Trueならシリンダーの translate・rotate とロッドの ``translate<aimAxis>`` へ出力を接続する。

        Returns:
            StewartPlatform: length[]・extension[]・clampedLength[]・excess[]・stroke[]・cylinderMatrix[]・maxExcess・
                reachable の所有者。containerに keyable の minimum・maximum と、固定の restLength[]・legCount を持つ。

        Raises:
            ValueError: 軸・長さが不正な場合、listの数が合わない・空の場合、transformでない・同じノードがある場合、
                シリンダーがjointの場合、ロッドがシリンダーの子でない場合、生成時に取り付け点が重なっている場合、
                出力先が既に接続されている場合(connect=True)、またはnameが既に存在する場合。

        Note:
            length_i = |天板側の取り付け点 i のワールド位置 - 台座側の取り付け点 i のワールド位置|、
            extension_i = length_i - restLength_i (restLength_i は生成時の length_i)、
            clampedLength_i = clamp(length_i, minimum, maximum)、excess_i = length_i - clampedLength_i、
            stroke_i = (length_i - minimum) / (maximum - minimum)、maxExcess = max_i |excess_i|、
            reachable = (maxExcess <= 0)。
            cylinderMatrix_i は台座側の取り付け点のワールドマトリクスを、aimAxis が天板側の取り付け点を向き、upAxis が
            台座側の取り付け点の upAxis に最も近くなるよう回したワールドマトリクス(aimMatrix)。シリンダーへは親の逆を掛けて
            分解した translate・rotate を接続する。脚が台座側の取り付け点の upAxis と平行になると向きが不定。
            取り付け点・シリンダーの親の scale は1を前提とする。天板の位置は制限しない(範囲を超えるとロッドの先が
            天板側の取り付け点から excess だけ離れる)。
        """
        axes = ("x", "y", "z")
        if aimAxis not in axes or upAxis not in axes or aimAxis == upAxis:
            raise ValueError("aimAxis and upAxis must be two different axes of x, y and z")
        groups = {"baseAnchors": baseAnchors, "platformAnchors": platformAnchors, "cylinders": cylinders, "rods": rods}
        for label, group in groups.items():
            if group is None and label in ("cylinders", "rods"):
                continue
            if isinstance(group, (str, mlib.Node)) or not group:
                raise ValueError(label + " must be a non-empty list of transforms")
        count = len(baseAnchors)
        if any(group is not None and len(group) != count for group in groups.values()):
            raise ValueError("baseAnchors, platformAnchors, cylinders and rods must have the same size")
        if rods is not None and cylinders is None:
            raise ValueError("rods need cylinders")
        for value in (minimum, maximum):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value)):
                raise ValueError("minimum and maximum must be finite numbers")
        if mlib.objExists(name):
            raise ValueError("StewartPlatform container already exists: " + name)
        resolved = {label: [mlib.Node(node) for node in group] for label, group in groups.items() if group is not None}
        nodes = [node for group in resolved.values() for node in group]
        if not all(isinstance(node, mlib.Transform) for node in nodes):
            raise ValueError("Expected transforms for the anchors, the cylinders and the rods")
        if len({node.getFullName() for node in nodes}) != len(nodes):
            raise ValueError("The anchors, the cylinders and the rods must be different nodes")
        bases, tops = resolved["baseAnchors"], resolved["platformAnchors"]
        barrels, pistons = resolved.get("cylinders"), resolved.get("rods")
        if barrels is not None and any(isinstance(node, mlib.Joint) for node in barrels):
            raise ValueError("The cylinders must not be joints")
        if pistons is not None:
            for barrel, piston in zip(barrels, pistons):
                parent = piston.getParent()
                if parent is None or parent.getFullName() != barrel.getFullName():
                    raise ValueError("Each rod must be a child of its cylinder: " + str(piston))
        slideChannel = "translate" + aimAxis.upper()
        if connect:
            targets = []
            for barrel in barrels or []:
                targets += [barrel.getPlug(channel + axis) for channel in ("translate", "rotate") for axis in ("", "X", "Y", "Z")]
            targets += [piston.getPlug(slideChannel) for piston in pistons or []]
            for target in targets:
                if target.getConnections(input=True, skipConversionNodes=True) is not None:
                    raise ValueError("The target is already connected: " + str(target))

        def position(node):
            """ノードのワールド位置。"""
            matrix = node.getPlug("worldMatrix")[0].get()
            return (matrix[12], matrix[13], matrix[14])

        rest = cls.legs([position(node) for node in bases], [position(node) for node in tops], 0.0, 1.0)["length"]
        if min(rest) < 1e-6:
            raise ValueError("Each base anchor and its platform anchor must be at different positions")
        low = min(rest) * 0.75 if minimum is None else float(minimum)
        high = max(rest) * 1.25 if maximum is None else float(maximum)
        if not 0.0 < low < high:
            raise ValueError("minimum and maximum must satisfy 0 < minimum < maximum")

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        for attribute, value in (("minimum", low), ("maximum", high)):
            owner.addAttr(longName=attribute, attributeType="doubleLinear", minValue=0.001, keyable=True)
            owner.getPlug(attribute).set(value)
        owner.addAttr(longName="legCount", attributeType="long")
        owner.getPlug("legCount").set(count)
        owner.addAttr(longName="restLength", attributeType="doubleLinear", multi=True)
        outputs = [("maxExcess", "doubleLinear"), ("reachable", "double")]
        multis = [("length", "doubleLinear"), ("extension", "doubleLinear"), ("clampedLength", "doubleLinear"),
                  ("excess", "doubleLinear"), ("stroke", "double")]
        for attribute, kind in outputs:
            owner.addAttr(longName=attribute, attributeType=kind)
        for attribute, kind in multis:
            owner.addAttr(longName=attribute, attributeType=kind, multi=True)
        owner.addAttr(longName="cylinderMatrix", dataType="matrix", multi=True)

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

        def out(label, source, target):
            """source を係数1の unitConversion を通して container の出力へつなぐ。"""
            scale(label, source, 1.0).connectTo(target)

        lowNumber = scale("minimumNumber", owner.getPlug("minimum"), 1.0)
        highNumber = scale("maximumNumber", owner.getPlug("maximum"), 1.0)
        span = total("span", [(highNumber, 1.0), (lowNumber, -1.0)])
        worst = graph._node("max", "maxExcess")
        aimVector = [float(axis == aimAxis) for axis in axes]
        upVector = [float(axis == upAxis) for axis in axes]
        for index, (base, top) in enumerate(zip(bases, tops)):
            prefix = "leg" + str(index)
            owner.getPlug("restLength")[index].set(rest[index])
            # length = 取り付け点どうしの距離(倍精度の distanceBetween。内部単位のcm)
            distance = graph._node("distanceBetween", prefix + "Distance")
            base.getPlug("worldMatrix")[0].connectTo(distance.getPlug("inMatrix1"))
            top.getPlug("worldMatrix")[0].connectTo(distance.getPlug("inMatrix2"))
            length = scale(prefix + "LengthNumber", distance.getPlug("distance"), 1.0)
            out(prefix + "LengthOut", length, owner.getPlug("length")[index])
            out(prefix + "ExtensionOut", total(prefix + "Extension", [(length, 1.0)], -rest[index]),
                owner.getPlug("extension")[index])
            # clampedLength = clamp(length, minimum, maximum)、excess = length - clampedLength
            limit = graph._node("clampRange", prefix + "Clamp")
            scale(prefix + "ClampInput", length, 1.0).connectTo(limit.getPlug("input"))
            lowNumber.connectTo(limit.getPlug("minimum"))
            highNumber.connectTo(limit.getPlug("maximum"))
            clamped = scale(prefix + "ClampNumber", limit.getPlug("output"), 1.0)
            out(prefix + "ClampedOut", clamped, owner.getPlug("clampedLength")[index])
            excess = total(prefix + "Excess", [(length, 1.0), (clamped, -1.0)])
            out(prefix + "ExcessOut", excess, owner.getPlug("excess")[index])
            magnitude = graph._node("absolute", prefix + "ExcessAbs")
            excess.connectTo(magnitude.getPlug("input"))
            magnitude.getPlug("output").connectTo(worst.getPlug("input")[index])
            # stroke = (length - minimum) / (maximum - minimum)
            ratio = graph._node("divide", prefix + "Stroke")
            total(prefix + "Travel", [(length, 1.0), (lowNumber, -1.0)]).connectTo(ratio.getPlug("input1"))
            span.connectTo(ratio.getPlug("input2"))
            out(prefix + "StrokeOut", ratio.getPlug("output"), owner.getPlug("stroke")[index])
            # cylinderMatrix = 台座側の取り付け点で、aimAxis を天板側の取り付け点へ向けたワールドマトリクス
            aim = graph._node("aimMatrix", prefix + "Aim")
            base.getPlug("worldMatrix")[0].connectTo(aim.getPlug("inputMatrix"))
            top.getPlug("worldMatrix")[0].connectTo(aim.getPlug("primaryTargetMatrix"))
            aim.getPlug("primaryMode").set(1)
            aim.getPlug("primaryInputAxis").set(aimVector)
            aim.getPlug("primaryTargetVector").set((0, 0, 0))
            aim.getPlug("secondaryMode").set(2)
            aim.getPlug("secondaryInputAxis").set(upVector)
            aim.getPlug("secondaryTargetVector").set(upVector)
            base.getPlug("worldMatrix")[0].connectTo(aim.getPlug("secondaryTargetMatrix"))
            aim.getPlug("outputMatrix").connectTo(owner.getPlug("cylinderMatrix")[index])
            if not connect or barrels is None:
                continue
            barrel = barrels[index]
            local = graph._node("multMatrix", prefix + "Local")
            aim.getPlug("outputMatrix").connectTo(local.getPlug("matrixIn")[0])
            barrel.getPlug("parentInverseMatrix")[0].connectTo(local.getPlug("matrixIn")[1])
            decompose = graph._node("decomposeMatrix", prefix + "Decompose")
            local.getPlug("matrixSum").connectTo(decompose.getPlug("inputMatrix"))
            barrel.getPlug("rotateOrder").connectTo(decompose.getPlug("inputRotateOrder"))
            decompose.getPlug("outputTranslate").connectTo(barrel.getPlug("translate"))
            decompose.getPlug("outputRotate").connectTo(barrel.getPlug("rotate"))
            if pistons is not None:
                owner.getPlug("clampedLength")[index].connectTo(pistons[index].getPlug(slideChannel))
        out("maxExcessOut", worst.getPlug("output"), owner.getPlug("maxExcess"))
        # reachable = (maxExcess <= 0)
        inside = graph._node("condition", "reachable")
        inside.getPlug("operation").set(5)
        worst.getPlug("output").connectTo(inside.getPlug("firstTerm"))
        inside.getPlug("secondTerm").set(0.0)
        inside.getPlug("colorIfTrueR").set(1.0)
        inside.getPlug("colorIfFalseR").set(0.0)
        out("reachableOut", inside.getPlug("outColorR"), owner.getPlug("reachable"))
        owner.setAttrFlags([attribute for attribute, _ in outputs] + ["legCount"], keyable=False, channelBox=True)
        return graph
