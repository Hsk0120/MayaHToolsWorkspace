"""長さの変化から伸縮率と横方向の体積補正を標準DGで求める。"""

from maya import cmds

import math
import hlib

from hlib.decorators.undo import undoTransaction


class LengthCompensation:
    """距離の単位に依存しない、長さ比率の計算グラフ。"""

    def __init__(self, container):
        """既存containerを参照する。

        Args:
            container (str | Node): 保存済みグラフ。
        """
        self.container = hlib.nodes.Container(container)

    def _node(self, kind, role):
        """計算ノードを生成し所有する。

        Args:
            kind (str): ノード型。
            role (str): 用途。

        Returns:
            Node: 生成ノード。
        """
        node = hlib.nodes.Node.create(
            kind, name=self.container.name() + "_" + role, skipSelect=True
        )
        self.container.addMembers(node)
        return node

    @classmethod
    @undoTransaction("hrig.LengthCompensation.create")
    def create(cls, rest_length, name="lengthCompensation"):
        """伸長・圧縮を独立に調整できる計算グラフを生成する。

        Args:
            rest_length (float): 正の基準長。inputLengthと同じ単位を使う。
            name (str): 一意なcontainer名。

        Returns:
            LengthCompensation: lengthScale、volumeScaleを公開するグラフ。

        Note:
            volumeScaleはlengthScaleの逆平方根をvolumeで線形ブレンドする。
            体積維持は棒状断面の近似で、メッシュ体積の厳密な保証ではない。
        """
        if not math.isfinite(rest_length) or rest_length <= 0 or cmds.objExists(name):
            raise ValueError("Use a positive rest length and a unique name")
        graph = cls(hlib.nodes.Container.create(name=name))
        owner = graph.container
        for attr, value, low, high in (
            ("restLength", rest_length, 1e-8, None),
            ("inputLength", rest_length, 0, None),
            ("stretch", 1, 0, 1),
            ("squash", 1, 0, 1),
            ("volume", 1, 0, 1),
            ("minSquash", 0.1, 0.01, 1),
            ("maxStretch", 2, 1, 100),
        ):
            kwargs = dict(
                longName=attr, attributeType="double", defaultValue=value, minValue=low
            )
            if high is not None:
                kwargs["maxValue"] = high
            owner.addAttr(**kwargs)
        for attr in ("lengthScale", "volumeScale"):
            owner.addAttr(longName=attr, attributeType="double")
        ratio = graph._node("multiplyDivide", "ratio")
        ratio.plug("operation").set(2)
        owner.plug("inputLength").connectTo(ratio.plug("input1X"))
        owner.plug("restLength").connectTo(ratio.plug("input2X"))
        clamp = graph._node("clamp", "limits")
        ratio.plug("outputX").connectTo(clamp.plug("inputR"))
        owner.plug("minSquash").connectTo(clamp.plug("minR"))
        owner.plug("maxStretch").connectTo(clamp.plug("maxR"))
        weight = graph._node("condition", "direction")
        weight.plug("operation").set(2)
        clamp.plug("outputR").connectTo(weight.plug("firstTerm"))
        weight.plug("secondTerm").set(1)
        owner.plug("stretch").connectTo(weight.plug("colorIfTrueR"))
        owner.plug("squash").connectTo(weight.plug("colorIfFalseR"))
        blend = graph._node("blendTwoAttr", "lengthBlend")
        blend.plug("input")[0].set(1)
        clamp.plug("outputR").connectTo(blend.plug("input")[1])
        weight.plug("outColorR").connectTo(blend.plug("attributesBlender"))
        blend.plug("output").connectTo(owner.plug("lengthScale"))
        volume = graph._node("multiplyDivide", "inverseSqrt")
        volume.plug("operation").set(3)
        blend.plug("output").connectTo(volume.plug("input1X"))
        volume.plug("input2X").set(-0.5)
        volume_blend = graph._node("blendTwoAttr", "volumeBlend")
        volume_blend.plug("input")[0].set(1)
        volume.plug("outputX").connectTo(volume_blend.plug("input")[1])
        owner.plug("volume").connectTo(volume_blend.plug("attributesBlender"))
        volume_blend.plug("output").connectTo(owner.plug("volumeScale"))
        return graph
