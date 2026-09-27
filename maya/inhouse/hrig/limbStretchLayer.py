"""腕脚の骨長と断面を、独立した伸縮レイヤーで制御する。"""

import json
import math
from maya import cmds
from maya.api import OpenMaya as om

import hlib
from hlib.animation import LengthCompensation
from hlib.decorators.undo import undo_transaction


class LimbStretchLayer:
    """部位空間の目標距離を使い、Soft IKとの合成も管理する。"""

    def __init__(self, rig):
        """対象を保持する。

        Args:
            rig (LimbRig): 腕または脚。
        """
        self.rig = rig

    def settings(self):
        """設定グループを取得する。

        Returns:
            Node | None: 未追加ならNone。
        """
        root = self.rig.root
        source = root.plug("stretchGroup").source() if root.has_attr("stretchGroup") else None
        return source.node if source is not None else None

    @staticmethod
    def _node(owner, kind, role):
        """ノードを所有containerへ登録する。

        Args:
            owner (Node): 所有先。
            kind (str): 型。
            role (str): 用途。

        Returns:
            Node: 新規ノード。
        """
        node = hlib.createNode(kind, name=owner.name() + "_" + role, skipSelect=True)
        cmds.container(owner.full_name(), edit=True, addNode=node.full_name())
        return node

    @undo_transaction("hrig.LimbStretchLayer.add")
    def add(self):
        """長さ・体積のレイヤーを追加する。骨長比率は維持する。

        Returns:
            Node: 設定グループ。
        """
        if self.settings() is not None:
            return self.settings()
        rig, root = self.rig, self.rig.root
        lengths = [
            om.MDistance(
                cmds.getAttr(rig._member("ik" + str(i)) + ".translateX"), om.MDistance.uiUnit()
            ).asCentimeters()
            for i in (1, 2)
        ]
        owner = LengthCompensation.create(sum(lengths), root.name() + "_stretchGraph").container
        if root.has_attr("channel_stretch"):
            group = hlib.node(rig._member("channel_stretch"))
        else:
            parent = (
                rig._member("channelModule") if root.has_attr("channelModule") else root.full_name()
            )
            group = hlib.createNode(
                "transform", name=root.name() + "_stretch_layer", parent=parent, skipSelect=True
            )
            rig._bind("channel_stretch", group.full_name())
            group.add_attr(long_name="enabled", attribute_type="bool", default_value=True)
            group.add_attr(long_name="active", attribute_type="bool", default_value=False)
            group.set_attr_flags(["enabled", "active"], channel_box=True)
            group.set_attr_flags(["active"], locked=True)
            group.plug("useOutlinerColor").set(True)
        group.set_attr_flags(["translate", "rotate", "scale"], locked=True, keyable=False)
        group.add_attr(long_name="graph", attribute_type="message")
        owner.plug("message").connect(group.plug("graph"))
        rig._bind("stretchGroup", group.full_name())
        if not root.has_attr("hrigEnabled_stretch"):
            root.add_attr(
                long_name="hrigEnabled_stretch", attribute_type="bool", default_value=True
            )
        group.add_attr(long_name="restLengths", data_type="string").set(json.dumps(lengths))
        for attr in ("inputLength", "softDistance"):
            group.add_attr(long_name=attr, attribute_type="double")
        for attr in ("outputs", "matrices"):
            group.add_attr(long_name=attr, attribute_type="message", multi=True)
        group.add_attr(long_name="softNormalize", attribute_type="message")
        for attr, value, low, high in (
            ("stretch", 1, 0, 1),
            ("squash", 0, 0, 1),
            ("volume", 1, 0, 1),
            ("minSquash", 0.1, 0.01, 1),
            ("maxStretch", 2, 1, 100),
        ):
            group.add_attr(
                long_name=attr,
                attribute_type="double",
                default_value=value,
                minValue=low,
                maxValue=high,
                keyable=True,
            )
            group.plug(attr).connect(owner.plug(attr))
        distance = hlib.plug(rig._member("distance") + ".distance")
        units = self._node(owner, "unitConversion", "distanceCm")
        distance.connect(units.plug("input"))
        units.plug("conversionFactor").set(1)
        units.plug("output").connect(group.plug("inputLength"))
        soft_input = hlib.plug(rig._member("softGraph") + ".distance")
        soft_input.source().connect(group.plug("softDistance"))
        normalize = self._node(owner, "multiplyDivide", "normalizedSoftDistance")
        normalize.plug("operation").set(2)
        group.plug("softDistance").connect(normalize.plug("input1X"))
        owner.plug("lengthScale").connect(normalize.plug("input2X"))
        normalize.plug("message").connect(group.plug("softNormalize"))
        for i, length in enumerate(lengths):
            multiply = self._node(owner, "multiplyDivide", "boneLength" + str(i))
            multiply.plug("input1X").set(length)
            owner.plug("lengthScale").connect(multiply.plug("input2X"))
            convert = self._node(owner, "unitConversion", "lengthUnits" + str(i))
            multiply.plug("outputX").connect(convert.plug("input"))
            convert.plug("conversionFactor").set(1)
            convert.plug("message").connect(group.plug("outputs[{}]".format(i)))
        shape = self._node(owner, "composeMatrix", "crossSection")
        inverse = self._node(owner, "multiplyDivide", "inverseVolume")
        inverse.plug("operation").set(2)
        inverse.plug("input1X").set(1)
        owner.plug("volumeScale").connect(inverse.plug("input2X"))
        unshape = self._node(owner, "composeMatrix", "parentCompensation")
        for axis in "YZ":
            owner.plug("volumeScale").connect(shape.plug("inputScale" + axis))
            inverse.plug("outputX").connect(unshape.plug("inputScale" + axis))
        for i in range(3):
            matrix = self._node(owner, "multMatrix", "deform" + str(i))
            # 親の断面scaleを打ち消し、子の位置や回転に歪みが累積しないようにする。
            shape.plug("outputMatrix").connect(matrix.plug("matrixIn[0]"))
            hlib.plug(rig._local_matrix("ik" + str(i))).connect(matrix.plug("matrixIn[1]"))
            if i:
                unshape.plug("outputMatrix").connect(matrix.plug("matrixIn[2]"))
            matrix.plug("message").connect(group.plug("matrices[{}]".format(i)))
        indices = cmds.getAttr(root.full_name() + ".hrigOwned", multiIndices=True) or []
        for i, node in enumerate((group, owner), max(indices, default=-1) + 1):
            node.plug("message").connect(root.plug("hrigOwned[{}]".format(i)))
        rig._update_evaluation()
        from . import channel_controls

        jobs = channel_controls._jobs.pop(root.uuid(), None)
        if jobs is not None:
            jobs.stop()
        channel_controls.install()
        return group

    def active(self):
        """評価状態を取得する。

        Returns:
            bool: IK・Full・Enabledの場合True。
        """
        return (
            self.settings() is not None
            and self.rig.mode() == "ik"
            and self.rig.lod() == 1
            and self.rig.layer_enabled("stretch")
        )

    def match_distance(self, distance, softness, base_length):
        """伸縮とSoft IKを合成した到達距離を二分探索で逆算する。

        Args:
            distance (float): 現在の先端距離。部位空間。
            softness (float): 元のSoft IK設定。
            base_length (float): Soft IKの基準長。

        Returns:
            float: 目標コントロールの距離。

        Raises:
            ValueError: 設定の上限を超えて到達できない姿勢。
        """
        group = self.settings()
        rest = sum(json.loads(group.plug("restLengths").get()))
        settings = {
            a: group.plug(a).get() for a in ("stretch", "squash", "minSquash", "maxStretch")
        }
        lo, hi = 0.0, max(rest, distance, 1) * 1e6
        for iteration in range(82):
            value = hi if iteration == 0 else (lo + hi) * 0.5
            ratio = min(settings["maxStretch"], max(settings["minSquash"], value / rest))
            scale = 1 + (ratio - 1) * settings["stretch" if ratio > 1 else "squash"]
            normalized = value / scale * base_length / rest
            if softness > 0 and normalized > base_length - softness:
                resolved = base_length - softness * math.exp(
                    -(normalized - (base_length - softness)) / softness
                )
            else:
                resolved = min(normalized, base_length)
            reached = value * resolved / normalized if normalized else 0
            if iteration == 0:
                if reached <= distance + 1e-8 and softness > 0:
                    raise ValueError(
                        "Pose exceeds the stretch/Soft IK reach; adjust limits before matching"
                    )
                if reached < distance - 1e-8:
                    raise ValueError("Pose exceeds the maximum stretch")
            elif reached < distance:
                lo = value
            else:
                hi = value
        return (lo + hi) * 0.5

    def update(self):
        """骨長・断面・Soft IK距離の接続を切り替える。"""
        group = self.settings()
        if group is None:
            return
        rig, active = self.rig, self.active()
        owner = group.plug("graph").source().node
        target = owner.plug("inputLength")
        if target.source() is not None:
            target.source().disconnect(target)
        if active:
            group.plug("inputLength").connect(target)
        else:
            target.set(owner.plug("restLength").get())
        for i, length in enumerate(json.loads(group.plug("restLengths").get())):
            target = hlib.plug(rig._member("ik" + str(i + 1)) + ".translateX")
            if target.source() is not None:
                target.source().disconnect(target)
            if active:
                group.plug("outputs[{}]".format(i)).source().node.plug("output").connect(target)
            else:
                target.set(om.MDistance(length).asUnits(om.MDistance.uiUnit()))
        soft = hlib.plug(rig._member("softGraph") + ".distance")
        if soft.source() is not None:
            soft.source().disconnect(soft)
        source = (
            group.plug("softNormalize").source().node.plug("outputX")
            if active
            else group.plug("softDistance")
        )
        source.connect(soft)
        for i in range(3):
            target = hlib.plug(rig._member("joint" + str(i)) + ".offsetParentMatrix")
            if target.source() is not None:
                target.source().disconnect(target)
            source = (
                group.plug("matrices[{}]".format(i)).source().node.plug("matrixSum")
                if active
                else hlib.plug(rig._local_matrix(("ik" if rig.mode() == "ik" else "fk") + str(i)))
            )
            source.connect(target)
