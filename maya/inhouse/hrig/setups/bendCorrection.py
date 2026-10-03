"""基準姿勢からの曲げを、補間姿勢と二つの補正距離へ変換する。"""

from maya import cmds

import math

import hlib

from hlib.maths.matrix import Matrix
from hlib.decorators.undo import undoTransaction


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
            kind, name=self.container.name() + "_" + suffix, skipSelect=True
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
            node.uuid()
            for node in [
                hlib.getNode(value) for value in (cmds.listRelatives(joint, parent=True) or [])
            ]
        ] != [parent.uuid()]:
            raise ValueError("Expected a direct parent-child pair")
        if cmds.objExists(name):
            raise ValueError("Bend container already exists: " + name)
        conversions = {node.uuid() for node in hlib.ls(type="unitConversion")}
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
            owner.addAttribute(
                longName=attr,
                attributeType="doubleLinear" if attr.endswith(("Rest", "Push")) else "double",
                defaultValue=value,
                **bounds
            )
            # addAttrの距離defaultは内部cmなので、初期値をUI距離単位で明示設定する。
            owner.plug(attr).set(
                hlib.utils.units.distanceFromUi(value)
                if attr.endswith(("Rest", "Push")) else value
            )
        owner.addAttribute(longName="matrix", dataType="matrix")
        owner.addAttribute(longName="restMatrix", dataType="matrix")
        for attr in ("inner", "outer", "response"):
            owner.addAttribute(
                longName=attr, attributeType="double" if attr == "response" else "doubleLinear"
            )
        relative = graph._node("multMatrix", "relative")
        joint.plug("matrix").connect(relative.plug("matrixIn[0]"))
        joint.plug("offsetParentMatrix").connect(relative.plug("matrixIn[1]"))
        rest = Matrix(relative.plug("matrixSum").get())
        owner.plug("restMatrix").set(rest)
        blend = graph._node("blendMatrix", "halfRotation")
        blend.plug("inputMatrix").set(rest)
        relative.plug("matrixSum").connect(blend.plug("target[0].targetMatrix"))
        blend.plug("target[0].weight").set(1)
        if blend.hasAttribute("target[0].rotateWeight"):
            owner.plug("rotationRatio").connect(blend.plug("target[0].rotateWeight"))
            for part in ("scale", "shear"):
                blend.plug("target[0]." + part + "Weight").set(0)
        else:
            # 2022では成分別weightがないため、回転だけを別途補間する。
            owner.plug("rotationRatio").connect(blend.plug("target[0].weight"))
            for part in ("Translate", "Scale", "Shear"):
                blend.plug("target[0].use" + part).set(False)
            position = graph._node("decomposeMatrix", "position")
            relative.plug("matrixSum").connect(position.plug("inputMatrix"))
            rotation = graph._node("pickMatrix", "rotation")
            blend.plug("outputMatrix").connect(rotation.plug("inputMatrix"))
            rotation.plug("useTranslate").set(False)
            translation = graph._node("composeMatrix", "translation")
            position.plug("outputTranslate").connect(translation.plug("inputTranslate"))
            result = graph._node("multMatrix", "result")
            rotation.plug("outputMatrix").connect(result.plug("matrixIn[0]"))
            translation.plug("outputMatrix").connect(result.plug("matrixIn[1]"))
            result.plug("matrixSum").connect(owner.plug("matrix"))
        if owner.plug("matrix").source() is None:
            blend.plug("outputMatrix").connect(owner.plug("matrix"))
        delta = graph._node("multMatrix", "delta")
        relative.plug("matrixSum").connect(delta.plug("matrixIn[0]"))
        delta.plug("matrixIn[1]").set(rest.inverse())
        angles = graph._node("decomposeMatrix", "angles")
        delta.plug("matrixSum").connect(angles.plug("inputMatrix"))
        orientation = graph._node("composeMatrix", "orientation")
        orientation.plug("useEulerRotation").set(False)
        angles.plug("outputQuat").connect(orientation.plug("inputQuat"))
        direction = graph._node("vectorProduct", "direction")
        direction.plug("operation").set(3)
        perpendicular = "yzx"["xyz".index(axis)].upper()
        direction.plug("input1" + perpendicular).set(1)
        orientation.plug("outputMatrix").connect(direction.plug("matrix"))
        angle = graph._node("angleBetween", "bendAngle")
        angle.plug("vector1").set((0, 0, 0))
        angle.plug("vector1" + perpendicular).set(1)
        direction.plug("output").connect(angle.plug("vector2"))
        sign_product = graph._node("multiplyDivide", "quaternionSign")
        angles.plug("outputQuat" + axis.upper()).connect(sign_product.plug("input1X"))
        angles.plug("outputQuatW").connect(sign_product.plug("input2X"))
        sign = graph._node("condition", "sign")
        sign.plug("operation").set(4)
        sign_product.plug("outputX").connect(sign.plug("firstTerm"))
        sign.plug("colorIfTrueR").set(-1)
        sign.plug("colorIfFalseR").set(1)
        degrees = graph._node("unitConversion", "degrees")
        angle.plug("angle").connect(degrees.plug("input"))
        degrees.plug("conversionFactor").set(180 / math.pi)
        signed_degrees = graph._node("multiplyDivide", "signedDegrees")
        degrees.plug("output").connect(signed_degrees.plug("input1X"))
        sign.plug("outColorR").connect(signed_degrees.plug("input2X"))
        signed = graph._node("multiplyDivide", "signedAngle")
        signed_degrees.plug("outputX").connect(signed.plug("input1X"))
        owner.plug("bendSign").connect(signed.plug("input2X"))
        response = graph._node("remapValue", "response")
        signed.plug("outputX").connect(response.plug("inputValue"))
        owner.plug("referenceAngle").connect(response.plug("inputMax"))
        response.plug("value[0].value_Interp").set(1)
        response.plug("value[1].value_Interp").set(1)
        response.plug("outValue").connect(owner.plug("response"))
        for side in ("inner", "outer"):
            amount = graph._node("multiplyDivide", side + "Amount")
            response.plug("outValue").connect(amount.plug("input1X"))
            owner.plug(side + "Push").connect(amount.plug("input2X"))
            offset = graph._node("plusMinusAverage", side + "Offset")
            owner.plug(side + "Rest").connect(offset.plug("input1D[0]"))
            amount.plug("outputX").connect(offset.plug("input1D[1]"))
            offset.plug("output1D").connect(owner.plug(side))
        extra = [node for node in hlib.ls(type="unitConversion") if node.uuid() not in conversions]
        if extra:
            hlib.nodes.Container(owner).addMembers(*extra)
        return graph
