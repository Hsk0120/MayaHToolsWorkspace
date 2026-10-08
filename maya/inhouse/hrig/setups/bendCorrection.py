"""基準姿勢からの曲げを、補間姿勢と二つの補正距離へ変換する。"""

from maya import cmds

import math

import hlib

from hlib.maths.matrix import Matrix
from hlib.decorator import undoTransaction


class BendCorrection:
    """標準DGノードを所有し、ヒンジ関節の補正出力を提供する。"""

    def __init__(self, container):
        """生成済みcontainerを保持する。

        Args:
            container (str | Node): 計算ノードの所有者。
        """
        self.container = hlib.nodes.Container(container)

    def _node(self, kind, suffix):
        """所有する演算ノードを作成する。

        Args:
            kind (str): Maya標準ノード型。
            suffix (str): 名前の用途部分。

        Returns:
            Node: 新しい演算ノード。
        """
        node = hlib.nodes.Node.create(
            kind, name=self.container.getName() + "_" + suffix, skipSelect=True
        )
        self.container.addMembers(node)
        return node

    @classmethod
    @undoTransaction("hrig.BendCorrection.create")
    def create(cls, parent, joint, name="bend", axis="z"):
        """直接の親子から、基準姿勢に対する回転補間と曲げ応答を生成する。

        Args:
            parent (str | Node): 関節の直接の親transform。
            joint (str | Node): 曲げるtransform。生成時を基準姿勢とする。
            name (str): 新規container名。
            axis (str): ヒンジの回転軸x/y/z。

        Returns:
            BendCorrection: matrix、inner、outer出力を持つ計算オブジェクト。

        Note:
            回転割合は0〜1。referenceAngleは度、距離はシーン単位。
            正方向のヒンジ曲げを0〜referenceAngleへクランプする。
            指定軸に直交する方向ベクトルから曲げ角を求める。多軸関節には使用しない。
        """
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        parent, joint = hlib.nodes.Node(parent), hlib.nodes.Node(joint)
        if [
            node.getUuid()
            for node in [
                hlib.getNode(value) for value in (cmds.listRelatives(joint, parent=True) or [])
            ]
        ] != [parent.getUuid()]:
            raise ValueError("Expected a direct parent-child pair")
        if cmds.objExists(name):
            raise ValueError("Bend container already exists: " + name)
        conversions = {node.getUuid() for node in hlib.ls(type="unitConversion")}
        graph = cls(hlib.nodes.Container.create(name=name))
        owner = graph.container
        for attr, value, bounds in (
            ("rotationRatio", 0.5, {"minValue": 0, "maxValue": 1}),
            ("referenceAngle", 90.0, {"minValue": 0.001}),
            ("bendSign", 1.0, {"minValue": -1, "maxValue": 1}),
            ("innerRest", 0.5, {}),
            ("outerRest", -0.5, {}),
            ("innerPush", -0.2, {}),
            ("outerPush", -0.2, {}),
        ):
            owner.addAttr(
                longName=attr,
                attributeType="doubleLinear" if attr.endswith(("Rest", "Push")) else "double",
                defaultValue=value,
                **bounds
            )
            # addAttrの距離defaultは内部cmなので、初期値をUI距離単位で明示設定する。
            owner.getPlug(attr).set(
                hlib.common.units.distanceFromUi(value)
                if attr.endswith(("Rest", "Push")) else value
            )
        owner.addAttr(longName="matrix", dataType="matrix")
        owner.addAttr(longName="restMatrix", dataType="matrix")
        for attr in ("inner", "outer", "response"):
            owner.addAttr(
                longName=attr, attributeType="double" if attr == "response" else "doubleLinear"
            )
        relative = graph._node("multMatrix", "relative")
        joint.getPlug("matrix").connectTo(relative.getPlug("matrixIn")[0])
        joint.getPlug("offsetParentMatrix").connectTo(relative.getPlug("matrixIn")[1])
        rest = Matrix(relative.getPlug("matrixSum").get())
        owner.getPlug("restMatrix").set(rest)
        blend = graph._node("blendMatrix", "halfRotation")
        blend.getPlug("inputMatrix").set(rest)
        relative.getPlug("matrixSum").connectTo(blend.getPlug("target")[0]["targetMatrix"])
        blend.getPlug("target")[0]["weight"].set(1)
        if blend.hasAttr("target[0].rotateWeight"):
            owner.getPlug("rotationRatio").connectTo(blend.getPlug("target")[0]["rotateWeight"])
            for part in ("scale", "shear"):
                blend.getPlug("target")[0][part + "Weight"].set(0)
        else:
            # 2022では成分別weightがないため、回転だけを別途補間する。
            owner.getPlug("rotationRatio").connectTo(blend.getPlug("target")[0]["weight"])
            for part in ("Translate", "Scale", "Shear"):
                blend.getPlug("target")[0]["use" + part].set(False)
            position = graph._node("decomposeMatrix", "position")
            relative.getPlug("matrixSum").connectTo(position.getPlug("inputMatrix"))
            rotation = graph._node("pickMatrix", "rotation")
            blend.getPlug("outputMatrix").connectTo(rotation.getPlug("inputMatrix"))
            rotation.getPlug("useTranslate").set(False)
            translation = graph._node("composeMatrix", "translation")
            position.getPlug("outputTranslate").connectTo(translation.getPlug("inputTranslate"))
            result = graph._node("multMatrix", "result")
            rotation.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[0])
            translation.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[1])
            result.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))
        if owner.getPlug("matrix").getSourceWithConversion() is None:
            blend.getPlug("outputMatrix").connectTo(owner.getPlug("matrix"))
        delta = graph._node("multMatrix", "delta")
        relative.getPlug("matrixSum").connectTo(delta.getPlug("matrixIn")[0])
        delta.getPlug("matrixIn")[1].set(rest.inverse())
        angles = graph._node("decomposeMatrix", "angles")
        delta.getPlug("matrixSum").connectTo(angles.getPlug("inputMatrix"))
        orientation = graph._node("composeMatrix", "orientation")
        orientation.getPlug("useEulerRotation").set(False)
        angles.getPlug("outputQuat").connectTo(orientation.getPlug("inputQuat"))
        direction = graph._node("vectorProduct", "direction")
        direction.getPlug("operation").set(3)
        perpendicular = "yzx"["xyz".index(axis)].upper()
        direction.getPlug("input1" + perpendicular).set(1)
        orientation.getPlug("outputMatrix").connectTo(direction.getPlug("matrix"))
        angle = graph._node("angleBetween", "bendAngle")
        angle.getPlug("vector1").set((0, 0, 0))
        angle.getPlug("vector1" + perpendicular).set(1)
        direction.getPlug("output").connectTo(angle.getPlug("vector2"))
        sign_product = graph._node("multiplyDivide", "quaternionSign")
        angles.getPlug("outputQuat" + axis.upper()).connectTo(sign_product.getPlug("input1X"))
        angles.getPlug("outputQuatW").connectTo(sign_product.getPlug("input2X"))
        sign = graph._node("condition", "sign")
        sign.getPlug("operation").set(4)
        sign_product.getPlug("outputX").connectTo(sign.getPlug("firstTerm"))
        sign.getPlug("colorIfTrueR").set(-1)
        sign.getPlug("colorIfFalseR").set(1)
        degrees = graph._node("unitConversion", "degrees")
        angle.getPlug("angle").connectTo(degrees.getPlug("input"))
        degrees.getPlug("conversionFactor").set(180 / math.pi)
        signed_degrees = graph._node("multiplyDivide", "signedDegrees")
        degrees.getPlug("output").connectTo(signed_degrees.getPlug("input1X"))
        sign.getPlug("outColorR").connectTo(signed_degrees.getPlug("input2X"))
        signed = graph._node("multiplyDivide", "signedAngle")
        signed_degrees.getPlug("outputX").connectTo(signed.getPlug("input1X"))
        owner.getPlug("bendSign").connectTo(signed.getPlug("input2X"))
        response = graph._node("remapValue", "response")
        signed.getPlug("outputX").connectTo(response.getPlug("inputValue"))
        owner.getPlug("referenceAngle").connectTo(response.getPlug("inputMax"))
        response.getPlug("value")[0]["value_Interp"].set(1)
        response.getPlug("value")[1]["value_Interp"].set(1)
        response.getPlug("outValue").connectTo(owner.getPlug("response"))
        for side in ("inner", "outer"):
            amount = graph._node("multiplyDivide", side + "Amount")
            response.getPlug("outValue").connectTo(amount.getPlug("input1X"))
            owner.getPlug(side + "Push").connectTo(amount.getPlug("input2X"))
            offset = graph._node("plusMinusAverage", side + "Offset")
            owner.getPlug(side + "Rest").connectTo(offset.getPlug("input1D")[0])
            amount.getPlug("outputX").connectTo(offset.getPlug("input1D")[1])
            offset.getPlug("output1D").connectTo(owner.getPlug(side))
        extra = [node for node in hlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if extra:
            hlib.nodes.Container(owner).addMembers(*extra)
        return graph
