"""ジョイントの基準ローカル回転をSwingとTwistへ分解する。"""

from maya import cmds

import math

import hlib

from hrig.setups.twistDistribution import TwistDistribution
from hlib.maths.matrix import Matrix
from hlib.decorators.undo import undo_transaction


class SwingTwist(TwistDistribution):
    """標準ノードで分解し、度単位のスカラー出力を公開する。"""

    @classmethod
    @undo_transaction("hrig.SwingTwist.create")
    def create(cls, joint, name="swingTwist", axis="x", rest=True):
        """直接の親空間で、作成時の姿勢を基準に回転を分解する。

        Args:
            joint (str | Node): 親transformを持つjoint。
            name (str): 新規container名。
            axis (str): Twistの長手軸x/y/z。
            rest (bool): Trueなら生成時の回転をゼロ基準とする。

        Returns:
            SwingTwist: twist、swingX/Y/Z、swingMatrix、twistMatrix出力の所有者。

        Note:
            Mayaの行ベクトル規約でtwistMatrix * swingMatrix = 基準からの回転。
            swingX/Y/Zは分解後SwingのXYZ Euler角。全出力角は常に度。
            最短回転を扱い、180度境界・多回転は連続ではない。
        """
        joint = hlib.nodes.Node(joint)
        parents = [
            hlib.getNode(value)
            for value in (cmds.listRelatives(joint.fullName(), parent=True, fullPath=True) or [])
        ] or []
        if joint.type() != "joint" or not parents:
            raise ValueError("Expected a joint with a parent transform")
        conversions = {node.uuid() for node in hlib.ls(type="unitConversion")}
        base = TwistDistribution.create(parents[0], joint, name=name, axis=axis)
        graph = cls(base.container)
        owner = graph.container
        decomposition = owner.plug("relativeDecompose").source().node
        source = decomposition.plug("inputMatrix").source()
        if rest:
            delta = graph._node("multMatrix", "restDelta")
            delta.plug("matrixIn[1]").set(Matrix(source.get()).inverse())
            source.disconnect(decomposition.plug("inputMatrix"))
            source.connect(delta.plug("matrixIn[0]"))
            delta.plug("matrixSum").connect(decomposition.plug("inputMatrix"))
        rotation = graph._node("composeMatrix", "rotation")
        rotation.plug("useEulerRotation").set(False)
        decomposition.plug("outputQuat").connect(rotation.plug("inputQuat"))
        twist_rotation = graph._node("decomposeMatrix", "twistQuaternion")
        owner.plug("twistMatrix").connect(twist_rotation.plug("inputMatrix"))
        conjugate = graph._node("multiplyDivide", "conjugate")
        twist_rotation.plug("outputQuat" + axis.upper()).connect(conjugate.plug("input1X"))
        conjugate.plug("input2X").set(-1)
        inverse = graph._node("composeMatrix", "twistInverse")
        inverse.plug("useEulerRotation").set(False)
        conjugate.plug("outputX").connect(inverse.plug("inputQuat" + axis.upper()))
        twist_rotation.plug("outputQuatW").connect(inverse.plug("inputQuatW"))
        swing = graph._node("multMatrix", "swing")
        inverse.plug("outputMatrix").connect(swing.plug("matrixIn[0]"))
        rotation.plug("outputMatrix").connect(swing.plug("matrixIn[1]"))
        owner.addAttribute(longName="swingMatrix", dataType="matrix")
        swing.plug("matrixSum").connect(owner.plug("swingMatrix"))
        angles = graph._node("decomposeMatrix", "swingAngles")
        swing.plug("matrixSum").connect(angles.plug("inputMatrix"))
        for component in "XYZ":
            owner.addAttribute(longName="swing" + component, attributeType="double")
            degrees = graph._node("unitConversion", "swing" + component + "Degrees")
            angles.plug("outputRotate" + component).connect(degrees.plug("input"))
            degrees.plug("conversionFactor").set(180 / math.pi)
            degrees.plug("output").connect(owner.plug("swing" + component))
        direction = graph._node("vectorProduct", "twistDirection")
        direction.plug("operation").set(3)
        perpendicular = "yzx"["xyz".index(axis)].upper()
        direction.plug("input1" + perpendicular).set(1)
        owner.plug("twistMatrix").connect(direction.plug("matrix"))
        angle = graph._node("angleBetween", "twistAngle")
        angle.plug("vector1").set((0, 0, 0))
        angle.plug("vector1" + perpendicular).set(1)
        direction.plug("output").connect(angle.plug("vector2"))
        degrees = graph._node("unitConversion", "twistDegrees")
        angle.plug("angle").connect(degrees.plug("input"))
        degrees.plug("conversionFactor").set(180 / math.pi)
        product = graph._node("multiplyDivide", "twistSignProduct")
        decomposition.plug("outputQuat" + axis.upper()).connect(product.plug("input1X"))
        decomposition.plug("outputQuatW").connect(product.plug("input2X"))
        sign = graph._node("condition", "twistSign")
        sign.plug("operation").set(4)
        product.plug("outputX").connect(sign.plug("firstTerm"))
        sign.plug("colorIfTrueR").set(-1)
        sign.plug("colorIfFalseR").set(1)
        signed = graph._node("multiplyDivide", "signedTwist")
        degrees.plug("output").connect(signed.plug("input1X"))
        sign.plug("outColorR").connect(signed.plug("input2X"))
        owner.addAttribute(longName="twist", attributeType="double")
        signed.plug("outputX").connect(owner.plug("twist"))
        for attr in ("twist", "swingX", "swingY", "swingZ"):
            owner.setAttributeFlags([attr], keyable=False, channelBox=True)
        extra = [node for node in hlib.ls(type="unitConversion") if node.uuid() not in conversions]
        if extra:
            hlib.nodes.Container(owner).addMembers(*extra)
        return graph
