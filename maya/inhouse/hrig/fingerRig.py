"""各指のFKへCurlとSpreadを加算する。"""

import math
import hlib
from hlib.decorator import undoTransaction
from .controlRig import ControlRig
from hrig.setups import ControlShape


class FingerRig(ControlRig):
    """正X方向の指列を作り、曲げZと開きYを別レイヤーで操作する。"""

    @classmethod
    @undoTransaction("hrig.FingerRig.create")
    def create(cls, name="hand01", finger_count=5, joint_count=3, length=3.0, spacing=1.0):
        """等間隔の指サンプルを作成する。親指の解剖学的配置は手動で調整する。

        Args:
            name (str): 一意名。
            finger_count (int): 1〜8列。
            joint_count (int): 各列の操作関節数、1〜8。
            length (float): 現在の距離単位での全長。
            spacing (float): 現在の距離単位での列間隔。

        Returns:
            FingerRig: 指モジュール。
        """
        if (
            type(finger_count) is not int
            or not 1 <= finger_count <= 8
            or type(joint_count) is not int
            or not 1 <= joint_count <= 8
        ):
            raise ValueError("Counts must be integers in 1..8")
        if not all(math.isfinite(v) and v > 0 for v in (length, spacing)):
            raise ValueError("Lengths must be positive finite values")
        rig = cls._create(name, "finger")
        settings = rig.group("layer")
        for attr in ("curl", "spread"):
            settings.addAttr(longName=attr, attributeType="doubleAngle", keyable=True)
        for f in range(finger_count):
            for attr, default in (
                ("curl{}".format(f + 1), 0),
                (
                    "spreadWeight{}".format(f + 1),
                    0 if finger_count == 1 else 2 * f / (finger_count - 1) - 1,
                ),
            ):
                settings.addAttr(
                    longName=attr,
                    attributeType="doubleAngle" if attr.startswith("curl") else "double",
                    defaultValue=default,
                    keyable=True,
                )
            parent = rig.group("control")
            bone_parent = rig.group("deform")
            for j in range(joint_count + 1):
                stem = "{}_finger{:02d}_{:02d}".format(name, f + 1, j + 1)
                layer = hlib.createNode(
                    "transform", name=stem + "_layer_grp", parent=parent, skipSelect=True
                )
                layer.getPlug("translateX").set(length / joint_count if j else 0)
                layer.getPlug("translateZ").set(
                    (f - (finger_count - 1) / 2) * spacing if j == 0 else 0
                )
                control = hlib.createNode(
                    "transform", name=stem + "_ctrl", parent=layer, skipSelect=True
                )
                bone = hlib.createNode(
                    "joint", name=stem + "_jnt", parent=bone_parent, skipSelect=True
                )
                bone.getPlug("segmentScaleCompensate").set(False)
                matrix = hlib.createNode("multMatrix", name=stem + "_matrix", skipSelect=True)
                control.getPlug("matrix").connectTo(matrix.getPlug("matrixIn")[0])
                layer.getPlug("matrix").connectTo(matrix.getPlug("matrixIn")[1])
                matrix.getPlug("matrixSum").connectTo(bone.getPlug("offsetParentMatrix"))
                rig.own(matrix)
                rig.register("deform", bone)
                if j < joint_count:
                    ControlShape.circle(control, spacing * 0.25, (1, 0, 0), 17)
                    rig.register("controls", control)
                    weight_attr = "curlWeight{}_{}".format(f + 1, j + 1)
                    settings.addAttr(
                        longName=weight_attr,
                        attributeType="double",
                        defaultValue=1,
                        keyable=True,
                    )
                    total = hlib.createNode(
                        "plusMinusAverage", name=stem + "_curl", skipSelect=True
                    )
                    settings.getPlug("curl").connectTo(total.getPlug("input1D")[0])
                    settings.getPlug("curl{}".format(f + 1)).connectTo(total.getPlug("input1D")[1])
                    multiply = hlib.createNode(
                        "multiplyDivide", name=stem + "_weights", skipSelect=True
                    )
                    total.getPlug("output1D").connectTo(multiply.getPlug("input1Z"))
                    settings.getPlug(weight_attr).connectTo(multiply.getPlug("input2Z"))
                    if j == 0:
                        settings.getPlug("spread").connectTo(multiply.getPlug("input1Y"))
                        settings.getPlug("spreadWeight{}".format(f + 1)).connectTo(
                            multiply.getPlug("input2Y")
                        )
                    rig.own(total)
                    rig.own(multiply)
                    for axis_index, axis in enumerate("XYZ"):
                        multiply.getPlug("output" + axis).connectTo(
                            rig.root.getPlug("angles")[(f * joint_count + j) * 3 + axis_index]
                        )
                    rig.register("sources", multiply)
                    rig.register("targets", layer)
                control.setAttrFlags(
                    ["translate", "scale", "visibility"], locked=True, keyable=False
                )
                parent, bone_parent = control, bone
        rig.update()
        from .channel_controls import install

        install()
        return rig
