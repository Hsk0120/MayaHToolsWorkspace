"""首と左右の視線を標準Aim constraintで操作するサンプル。"""

import math
import hlib
from hlib.decorator import undoTransaction
from .controlRig import ControlRig
from hrig.setups import ControlShape


class AimRig(ControlRig):
    """首と左右眼に独立ターゲットとUpを持つAimレイヤー。"""

    @classmethod
    @undoTransaction("hrig.AimRig.create")
    def create(cls, name="look01", size=2.0):
        """正Zを視線、正Yを上として作成する。

        Args:
            name (str): 一意名。
            size (float): 現在の距離単位での首の高さ。

        Returns:
            AimRig: 首と左右眼のFK/Aimサンプル。

        Note:
            各targetの移動で視線、各upの移動でロールを制御する。
            AimとUpの平行・ターゲットと原点の一致は避ける。
        """
        if not math.isfinite(size) or size <= 0:
            raise ValueError("Size must be positive finite")
        rig = cls._create(name, "aim")
        neck_control = None
        neck_bone = None
        for role, position in (
            ("neck", (0, 0, 0)),
            ("leftEye", (size * 0.25, size, 0)),
            ("rightEye", (-size * 0.25, size, 0)),
        ):
            stem = name + "_" + role
            offset = hlib.createNode(
                "transform",
                name=stem + "_ofs",
                parent=neck_control or rig.group("control"),
                skipSelect=True,
            )
            offset.getPlug("translate").set(position)
            layer = hlib.createNode(
                "transform", name=stem + "_aim_grp", parent=offset, skipSelect=True
            )
            control = hlib.createNode(
                "transform", name=stem + "_ctrl", parent=layer, skipSelect=True
            )
            ControlShape.circle(control, size * 0.15, (0, 0, 1), 17)
            target = hlib.createNode(
                "transform", name=stem + "_target_ctrl", parent=rig.group("layer"), skipSelect=True
            )
            target.getPlug("translate").set((position[0], position[1], size * 3))
            up = hlib.createNode(
                "transform", name=stem + "_up_ctrl", parent=rig.group("layer"), skipSelect=True
            )
            up.getPlug("translate").set((position[0], position[1] + size * 2, 0))
            for node in (target, up):
                ControlShape.circle(node, size * 0.12, (0, 0, 1), 18)
            constraint = hlib.addConstraint(
                target,
                layer,
                type="aim",
                aimVector=(0, 0, 1),
                upVector=(0, 1, 0),
                worldUpType="object",
                worldUpObject=up,
                maintainOffset=False,
            )
            bone = hlib.createNode(
                "joint",
                name=stem + "_jnt",
                parent=neck_bone or rig.group("deform"),
                skipSelect=True,
            )
            bone.getPlug("segmentScaleCompensate").set(False)
            matrix = hlib.createNode("multMatrix", name=stem + "_matrix", skipSelect=True)
            for i, node in enumerate((control, layer, offset)):
                node.getPlug("matrix").connectTo(matrix.getPlug("matrixIn")[i])
            matrix.getPlug("matrixSum").connectTo(bone.getPlug("offsetParentMatrix"))
            rig.own(matrix)
            rig.register("sources", constraint)
            rig.register("targets", layer)
            rig.register("deform", bone)
            for node in (control, target, up):
                rig.register("controls", node)
            if role == "neck":
                neck_control, neck_bone = control, bone
        rig.update()
        from .channel_controls import install

        install()
        return rig
