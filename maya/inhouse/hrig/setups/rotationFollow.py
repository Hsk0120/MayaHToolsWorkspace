"""ローカル回転の全成分・Twist・Swingを割合で追従する。"""

import hlib

import math

from hlib.maths import Matrix

from hrig.setups.swingTwist import SwingTwist
from hlib.decorators.undo import undo_transaction


class RotationFollow(SwingTwist):
    """基準姿勢からの回転をQuaternion補間する標準DG。"""

    @classmethod
    @undo_transaction("hrig.RotationFollow.create")
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
        owner.add_attribute(
            long_name="followMode",
            attribute_type="enum",
            enumName="Full:Twist:Swing",
            default_value=("full", "twist", "swing").index(mode),
        )
        owner.add_attribute(
            long_name="ratio",
            attribute_type="double",
            default_value=ratio,
            minValue=0,
            maxValue=1,
            keyable=True,
        )
        for attr in ("matrix", "restMatrix"):
            owner.add_attribute(long_name=attr, data_type="matrix")
        # restDeltaより手前の実ローカル行列から位置を取得する。
        relative = graph._node("multMatrix", "sourceLocal")
        joint.plug("matrix").connect(relative.plug("matrixIn[0]"))
        joint.plug("offsetParentMatrix").connect(relative.plug("matrixIn[1]"))
        position = graph._node("decomposeMatrix", "sourcePosition")
        relative.plug("matrixSum").connect(position.plug("inputMatrix"))
        full = graph._node("multMatrix", "fullRotation")
        owner.plug("twistMatrix").connect(full.plug("matrixIn[0]"))
        owner.plug("swingMatrix").connect(full.plug("matrixIn[1]"))
        choice = graph._node("choice", "component")
        for index, source in enumerate(
            (full.plug("matrixSum"), owner.plug("twistMatrix"), owner.plug("swingMatrix"))
        ):
            source.connect(choice.plug("input[{}]".format(index)))
        owner.plug("followMode").connect(choice.plug("selector"))
        limits = graph._node("clamp", "ratioLimit")
        limits.plug("maxR").set(1)
        owner.plug("ratio").connect(limits.plug("inputR"))
        blend = graph._node("blendMatrix", "rotationRatio")
        choice.plug("output").connect(blend.plug("target[0].targetMatrix"))
        limits.plug("outputR").connect(blend.plug("target[0].weight"))
        orient = graph._node("multMatrix", "restoreOrientation")
        blend.plug("outputMatrix").connect(orient.plug("matrixIn[0]"))
        orient.plug("matrixIn[1]").set(rest_rotation)
        rotation = graph._node("decomposeMatrix", "resultRotation")
        orient.plug("matrixSum").connect(rotation.plug("inputMatrix"))
        result = graph._node("composeMatrix", "result")
        result.plug("useEulerRotation").set(False)
        rotation.plug("outputQuat").connect(result.plug("inputQuat"))
        position.plug("outputTranslate").connect(result.plug("inputTranslate"))
        result.plug("outputMatrix").connect(owner.plug("matrix"))
        rest_output = Matrix.compose(translate=rest.translate, rotate=rest.quaternion)
        owner.plug("restMatrix").set(rest_output)
        return graph
