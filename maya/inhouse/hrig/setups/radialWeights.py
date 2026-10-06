"""円周上の方向を隣接する二方向へ分配する。"""

from maya import cmds

import math

import hlib

from hlib.decorators.undo import undoTransaction


class RadialWeights:
    """静止方向から求めた比率を、標準DGで調整できるウェイト計算。"""

    def __init__(self, container):
        """計算ノードの所有者を保持する。

        Args:
            container (str | Node): createで生成したcontainer。
        """
        self.container = hlib.nodes.Container(container)

    @staticmethod
    def directions(angle, count):
        """方向を挟む二方向と、正弦則による非正規化比率を返す。

        Args:
            angle (float): 先頭方向からの角度。ラジアン。
            count (int): 円周に等間隔で置く方向数。3以上。

        Returns:
            tuple: ((方向Aの番号, 方向Bの番号), (A比率, B比率))。
        """
        if isinstance(count, bool) or not isinstance(count, int) or count < 3:
            raise ValueError("count must be an integer >= 3")
        if not math.isfinite(angle):
            raise ValueError("angle must be finite")
        step = math.tau / count
        position = (angle % math.tau) / step
        index = int(math.floor(position)) % count
        offset = (position - math.floor(position)) * step
        values = (math.sin(step - offset), math.sin(offset))
        return (index, (index + 1) % count), tuple(max(0.0, v) for v in values)

    @staticmethod
    def weights(angle, count, falloff=1.0):
        """調整後の正規化ウェイトを計算する。

        Args:
            angle (float): ラジアン。
            count (int): 方向数。
            falloff (float): 0.1〜8。1が方向ベクトルの比率。

        Returns:
            tuple: (隣接方向の番号ペア, 合計1のウェイトペア)。
        """
        if not math.isfinite(falloff) or not 0.1 <= falloff <= 8:
            raise ValueError("falloff must be between 0.1 and 8")
        indices, values = RadialWeights.directions(angle, count)
        values = tuple(v**falloff for v in values)
        total = sum(values)
        return indices, tuple(v / total for v in values)

    def _node(self, kind, suffix):
        """内部ノードを所有containerへ登録する。

        Args:
            kind (str): 標準ノード型。
            suffix (str): 名前の用途部分。

        Returns:
            Node: 新規ノード。
        """
        node = hlib.nodes.Node.create(
            kind, name=self.container.getName() + "_" + suffix, skipSelect=True
        )
        self.container.addMembers(node)
        return node

    @classmethod
    @undoTransaction("hrig.RadialWeights.create")
    def create(cls, angle, count, name="radialWeights"):
        """FalloffとBlendから二方向・基準姿勢のウェイトを出力する。

        Args:
            angle (float): バインド時の方向。ラジアン。
            count (int): 方向数。
            name (str): 一意なcontainer名。

        Returns:
            RadialWeights: weightA/weightB/restWeightを持つ計算。
        """
        indices, values = cls.directions(angle, count)
        if cmds.objExists(name):
            raise ValueError("Container already exists: " + name)
        graph = cls(hlib.nodes.Container.create(name=name))
        owner = graph.container
        for attr, value in zip(("directionA", "directionB"), indices):
            owner.addAttr(longName=attr, attributeType="long", defaultValue=value)
            owner.setAttrFlags([attr], locked=True)
        for attr, value, minimum, maximum in (("falloff", 1, 0.1, 8), ("blend", 1, 0, 1)):
            owner.addAttr(
                longName=attr,
                attributeType="double",
                defaultValue=value,
                minValue=minimum,
                maxValue=maximum,
                keyable=True,
            )
        for attr in ("weightA", "weightB", "restWeight"):
            owner.addAttr(longName=attr, attributeType="double")
        # 接続入力でも範囲を保証し、ゼロ除算と負のウェイトを避ける。
        limits = graph._node("clamp", "limits")
        limits.getPlug("minR").set(0.1)
        limits.getPlug("maxR").set(8)
        limits.getPlug("maxG").set(1)
        owner.getPlug("falloff").connectTo(limits.getPlug("inputR"))
        owner.getPlug("blend").connectTo(limits.getPlug("inputG"))
        power = graph._node("multiplyDivide", "power")
        power.getPlug("operation").set(3)
        total = graph._node("plusMinusAverage", "total")
        normalized = graph._node("multiplyDivide", "normalized")
        normalized.getPlug("operation").set(2)
        blended = graph._node("multiplyDivide", "blended")
        for i, axis in enumerate(("X", "Y")):
            power.getPlug("input1" + axis).set(values[i])
            limits.getPlug("outputR").connectTo(power.getPlug("input2" + axis))
            power.getPlug("output" + axis).connectTo(total.getPlug("input1D")[i])
            power.getPlug("output" + axis).connectTo(normalized.getPlug("input1" + axis))
            total.getPlug("output1D").connectTo(normalized.getPlug("input2" + axis))
            normalized.getPlug("output" + axis).connectTo(blended.getPlug("input1" + axis))
            limits.getPlug("outputG").connectTo(blended.getPlug("input2" + axis))
            blended.getPlug("output" + axis).connectTo(owner.getPlug(("weightA", "weightB")[i]))
        reverse = graph._node("reverse", "rest")
        limits.getPlug("outputG").connectTo(reverse.getPlug("inputX"))
        reverse.getPlug("outputX").connectTo(owner.getPlug("restWeight"))
        return graph
