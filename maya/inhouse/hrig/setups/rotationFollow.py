"""ローカル回転の全成分・Twist・Swingを割合で追従する。"""

import hlib

import math

from hlib.maths import Matrix

from hrig.setups.swingTwist import SwingTwist
from hlib.decorators.undo import undoTransaction


class RotationFollow(SwingTwist):
    """基準姿勢からの回転をQuaternion補間する標準DG。"""

    @classmethod
    @undoTransaction("hrig.RotationFollow.create")
    def create(cls, joint, name="rotationFollow", mode="full", axis="x", ratio=0.5):
        """親空間での追従行列を生成する。

        Args:
            joint (str | Node): 親transformを持つjoint。
            name (str): 一意なcontainer名。
            mode (str): full/twist/swing。
            axis (str): 基準姿勢でのTwist軸x/y/z。
            ratio (float): 0〜1の追従割合。0.5で半分。

        Returns:
            RotationFollow: matrixとrestMatrix出力の所有者。

        Note:
            位置は入力の現在位置、回転だけを割合追従する。スケールは出力しない。
            出力は入力と同じ親空間のidentity TRSノードのOPMへ接続する。
            180度境界、多回転、負・非一様scale、shearは対象外。
        """
        if mode not in ("full", "twist", "swing"):
            raise ValueError("mode must be full, twist or swing")
        if not math.isfinite(ratio) or not 0 <= ratio <= 1:
            raise ValueError("ratio must be between 0 and 1")
        joint = hlib.nodes.Node(joint)
        rest = Matrix(joint.plug("matrix").get()) * Matrix(joint.plug("offsetParentMatrix").get())
        rest_rotation = rest.quaternion.asMatrix()
        base = SwingTwist.create(joint, name=name, axis=axis)
        graph = cls(base.container)
        owner = graph.container
        owner.addAttr(
            longName="followMode",
            attributeType="enum",
            enumName="Full:Twist:Swing",
            defaultValue=("full", "twist", "swing").index(mode),
        )
        owner.addAttr(
            longName="ratio",
            attributeType="double",
            defaultValue=ratio,
            minValue=0,
            maxValue=1,
            keyable=True,
        )
        for attr in ("matrix", "restMatrix"):
            owner.addAttr(longName=attr, dataType="matrix")
        # restDeltaより手前の実ローカル行列から位置を取得する。
        relative = graph._node("multMatrix", "sourceLocal")
        joint.plug("matrix").connectTo(relative.plug("matrixIn")[0])
        joint.plug("offsetParentMatrix").connectTo(relative.plug("matrixIn")[1])
        position = graph._node("decomposeMatrix", "sourcePosition")
        relative.plug("matrixSum").connectTo(position.plug("inputMatrix"))
        full = graph._node("multMatrix", "fullRotation")
        owner.plug("twistMatrix").connectTo(full.plug("matrixIn")[0])
        owner.plug("swingMatrix").connectTo(full.plug("matrixIn")[1])
        choice = graph._node("choice", "component")
        for index, source in enumerate(
            (full.plug("matrixSum"), owner.plug("twistMatrix"), owner.plug("swingMatrix"))
        ):
            source.connectTo(choice.plug("input")[index])
        owner.plug("followMode").connectTo(choice.plug("selector"))
        limits = graph._node("clamp", "ratioLimit")
        limits.plug("maxR").set(1)
        owner.plug("ratio").connectTo(limits.plug("inputR"))
        blend = graph._node("blendMatrix", "rotationRatio")
        choice.plug("output").connectTo(blend.plug("target")[0]["targetMatrix"])
        limits.plug("outputR").connectTo(blend.plug("target")[0]["weight"])
        orient = graph._node("multMatrix", "restoreOrientation")
        blend.plug("outputMatrix").connectTo(orient.plug("matrixIn")[0])
        orient.plug("matrixIn")[1].set(rest_rotation)
        rotation = graph._node("decomposeMatrix", "resultRotation")
        orient.plug("matrixSum").connectTo(rotation.plug("inputMatrix"))
        result = graph._node("composeMatrix", "result")
        result.plug("useEulerRotation").set(False)
        rotation.plug("outputQuat").connectTo(result.plug("inputQuat"))
        position.plug("outputTranslate").connectTo(result.plug("inputTranslate"))
        result.plug("outputMatrix").connectTo(owner.plug("matrix"))
        rest_output = Matrix.compose(translate=rest.translate, rotate=rest.quaternion)
        owner.plug("restMatrix").set(rest_output)
        return graph
