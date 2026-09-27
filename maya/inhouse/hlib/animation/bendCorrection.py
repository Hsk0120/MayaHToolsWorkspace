"""基準姿勢からの曲げを、補間姿勢と二つの補正距離へ変換する。"""

import math

from maya import cmds

from ..nodes.node import Node
from ..maths.matrix import Matrix
from ..decorators.undo import undo_transaction


class BendCorrection:
    """標準DGノードを所有し、ヒンジ関節の補正出力を提供する。"""

    def __init__(self, container):
        """生成済みcontainerを保持する。

        Args:
            container (str | Node): 計算ノードの所有者。
        """
        self.container = Node(container)

    def _node(self, kind, suffix):
        """所有する演算ノードを作成する。

        Args:
            kind (str): Maya標準ノード型。
            suffix (str): 名前の用途部分。

        Returns:
            Node: 新しい演算ノード。
        """
        node = Node.create(kind, name=self.container.name() + "_" + suffix, skipSelect=True)
        cmds.container(self.container.full_name(), edit=True, addNode=node.full_name())
        return node

    @classmethod
    @undo_transaction("hlib.BendCorrection.create")
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
        parent, joint = Node(parent), Node(joint)
        if (cmds.listRelatives(joint.full_name(), parent=True, fullPath=True) or []) != [
            parent.full_name()
        ]:
            raise ValueError("Expected a direct parent-child pair")
        if cmds.objExists(name):
            raise ValueError("Bend container already exists: " + name)
        conversions = set(cmds.ls(type="unitConversion"))
        graph = cls(cmds.container(name=name))
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
            owner.add_attr(
                long_name=attr,
                attribute_type="doubleLinear" if attr.endswith(("Rest", "Push")) else "double",
                default_value=value,
                **bounds
            )
            # addAttrの距離defaultは内部cmなので、初期値をUI距離単位で明示設定する。
            owner.plug(attr).set(value)
        owner.add_attr(long_name="matrix", data_type="matrix")
        owner.add_attr(long_name="restMatrix", data_type="matrix")
        for attr in ("inner", "outer", "response"):
            owner.add_attr(
                long_name=attr, attribute_type="double" if attr == "response" else "doubleLinear"
            )
        relative = graph._node("multMatrix", "relative")
        joint.plug("matrix").connect(relative.plug("matrixIn[0]"))
        joint.plug("offsetParentMatrix").connect(relative.plug("matrixIn[1]"))
        rest = Matrix(relative.plug("matrixSum").get())
        owner.plug("restMatrix").set_value(rest)
        blend = graph._node("blendMatrix", "halfRotation")
        blend.plug("inputMatrix").set_value(rest)
        relative.plug("matrixSum").connect(blend.plug("target[0].targetMatrix"))
        blend.plug("target[0].weight").set(1)
        if blend.has_attr("target[0].rotateWeight"):
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
        delta.plug("matrixIn[1]").set_value(rest.inverse())
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
        extra = set(cmds.ls(type="unitConversion")) - conversions
        if extra:
            cmds.container(owner.full_name(), edit=True, addNode=list(extra))
        return graph
