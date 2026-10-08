"""ジョイントの基準ローカル回転をSwingとTwistへ分解する。"""

from maya import cmds

import math

import hlib

from hrig.setups.twistDistribution import TwistDistribution
from hlib.maths.matrix import Matrix
from hlib.decorator import undoTransaction


class SwingTwist(TwistDistribution):
    """標準ノードで分解し、度単位のスカラー出力を公開する。"""

    @classmethod
    @undoTransaction("hrig.SwingTwist.create")
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
            for value in (cmds.listRelatives(joint.getFullName(), parent=True, fullPath=True) or [])
        ] or []
        if joint.getType() != "joint" or not parents:
            raise ValueError("Expected a joint with a parent transform")
        conversions = {node.getUuid() for node in hlib.ls(type="unitConversion")}
        base = TwistDistribution.create(parents[0], joint, name=name, axis=axis)
        graph = cls(base.container)
        owner = graph.container
        decomposition = owner.getPlug("relativeDecompose").getSourceWithConversion().getNode()
        source = decomposition.getPlug("inputMatrix").getSourceWithConversion()
        if rest:
            delta = graph._node("multMatrix", "restDelta")
            delta.getPlug("matrixIn")[1].set(Matrix(source.get()).inverse())
            decomposition.getPlug("inputMatrix").disconnect(source)
            source.connectTo(delta.getPlug("matrixIn")[0])
            delta.getPlug("matrixSum").connectTo(decomposition.getPlug("inputMatrix"))
        rotation = graph._node("composeMatrix", "rotation")
        rotation.getPlug("useEulerRotation").set(False)
        decomposition.getPlug("outputQuat").connectTo(rotation.getPlug("inputQuat"))
        twist_rotation = graph._node("decomposeMatrix", "twistQuaternion")
        owner.getPlug("twistMatrix").connectTo(twist_rotation.getPlug("inputMatrix"))
        conjugate = graph._node("multiplyDivide", "conjugate")
        twist_rotation.getPlug("outputQuat" + axis.upper()).connectTo(conjugate.getPlug("input1X"))
        conjugate.getPlug("input2X").set(-1)
        inverse = graph._node("composeMatrix", "twistInverse")
        inverse.getPlug("useEulerRotation").set(False)
        conjugate.getPlug("outputX").connectTo(inverse.getPlug("inputQuat" + axis.upper()))
        twist_rotation.getPlug("outputQuatW").connectTo(inverse.getPlug("inputQuatW"))
        swing = graph._node("multMatrix", "swing")
        inverse.getPlug("outputMatrix").connectTo(swing.getPlug("matrixIn")[0])
        rotation.getPlug("outputMatrix").connectTo(swing.getPlug("matrixIn")[1])
        owner.addAttr(longName="swingMatrix", dataType="matrix")
        swing.getPlug("matrixSum").connectTo(owner.getPlug("swingMatrix"))
        angles = graph._node("decomposeMatrix", "swingAngles")
        swing.getPlug("matrixSum").connectTo(angles.getPlug("inputMatrix"))
        for component in "XYZ":
            owner.addAttr(longName="swing" + component, attributeType="double")
            degrees = graph._node("unitConversion", "swing" + component + "Degrees")
            angles.getPlug("outputRotate" + component).connectTo(degrees.getPlug("input"))
            degrees.getPlug("conversionFactor").set(180 / math.pi)
            degrees.getPlug("output").connectTo(owner.getPlug("swing" + component))
        direction = graph._node("vectorProduct", "twistDirection")
        direction.getPlug("operation").set(3)
        perpendicular = "yzx"["xyz".index(axis)].upper()
        direction.getPlug("input1" + perpendicular).set(1)
        owner.getPlug("twistMatrix").connectTo(direction.getPlug("matrix"))
        angle = graph._node("angleBetween", "twistAngle")
        angle.getPlug("vector1").set((0, 0, 0))
        angle.getPlug("vector1" + perpendicular).set(1)
        direction.getPlug("output").connectTo(angle.getPlug("vector2"))
        degrees = graph._node("unitConversion", "twistDegrees")
        angle.getPlug("angle").connectTo(degrees.getPlug("input"))
        degrees.getPlug("conversionFactor").set(180 / math.pi)
        product = graph._node("multiplyDivide", "twistSignProduct")
        decomposition.getPlug("outputQuat" + axis.upper()).connectTo(product.getPlug("input1X"))
        decomposition.getPlug("outputQuatW").connectTo(product.getPlug("input2X"))
        sign = graph._node("condition", "twistSign")
        sign.getPlug("operation").set(4)
        product.getPlug("outputX").connectTo(sign.getPlug("firstTerm"))
        sign.getPlug("colorIfTrueR").set(-1)
        sign.getPlug("colorIfFalseR").set(1)
        signed = graph._node("multiplyDivide", "signedTwist")
        degrees.getPlug("output").connectTo(signed.getPlug("input1X"))
        sign.getPlug("outColorR").connectTo(signed.getPlug("input2X"))
        owner.addAttr(longName="twist", attributeType="double")
        signed.getPlug("outputX").connectTo(owner.getPlug("twist"))
        for attr in ("twist", "swingX", "swingY", "swingZ"):
            owner.setAttrFlags([attr], keyable=False, channelBox=True)
        extra = [node for node in hlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if extra:
            hlib.nodes.Container(owner).addMembers(*extra)
        return graph
