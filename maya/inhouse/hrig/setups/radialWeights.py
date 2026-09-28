"""円周上の方向を隣接する二方向へ分配する。"""

from maya import cmds

import math

import hlib

from hlib.decorators.undo import undo_transaction


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
            kind, name=self.container.name() + "_" + suffix, skipSelect=True
        )
        self.container.add_members(node)
        return node

    @classmethod
    @undo_transaction("hrig.RadialWeights.create")
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
            owner.add_attr(long_name=attr, attribute_type="long", default_value=value)
            owner.set_attr_flags([attr], locked=True)
        for attr, value, minimum, maximum in (("falloff", 1, 0.1, 8), ("blend", 1, 0, 1)):
            owner.add_attr(
                long_name=attr,
                attribute_type="double",
                default_value=value,
                minValue=minimum,
                maxValue=maximum,
                keyable=True,
            )
        for attr in ("weightA", "weightB", "restWeight"):
            owner.add_attr(long_name=attr, attribute_type="double")
        # 接続入力でも範囲を保証し、ゼロ除算と負のウェイトを避ける。
        limits = graph._node("clamp", "limits")
        limits.plug("minR").set(0.1)
        limits.plug("maxR").set(8)
        limits.plug("maxG").set(1)
        owner.plug("falloff").connect(limits.plug("inputR"))
        owner.plug("blend").connect(limits.plug("inputG"))
        power = graph._node("multiplyDivide", "power")
        power.plug("operation").set(3)
        total = graph._node("plusMinusAverage", "total")
        normalized = graph._node("multiplyDivide", "normalized")
        normalized.plug("operation").set(2)
        blended = graph._node("multiplyDivide", "blended")
        for i, axis in enumerate(("X", "Y")):
            power.plug("input1" + axis).set(values[i])
            limits.plug("outputR").connect(power.plug("input2" + axis))
            power.plug("output" + axis).connect(total.plug("input1D[{}]".format(i)))
            power.plug("output" + axis).connect(normalized.plug("input1" + axis))
            total.plug("output1D").connect(normalized.plug("input2" + axis))
            normalized.plug("output" + axis).connect(blended.plug("input1" + axis))
            limits.plug("outputG").connect(blended.plug("input2" + axis))
            blended.plug("output" + axis).connect(owner.plug(("weightA", "weightB")[i]))
        reverse = graph._node("reverse", "rest")
        limits.plug("outputG").connect(reverse.plug("inputX"))
        reverse.plug("outputX").connect(owner.plug("restWeight"))
        return graph
