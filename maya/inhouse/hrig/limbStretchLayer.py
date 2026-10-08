"""腕脚の骨長と断面を、独立した伸縮レイヤーで制御する。"""

import math
import hlib

from hrig.setups import LengthCompensation
from hlib.decorator import undoTransaction


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
        source = root.getPlug("stretchGroup").getSourceWithConversion() if root.hasAttr("stretchGroup") else None
        return source.getNode() if source is not None else None

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
        return hlib.nodes.Container(owner).createNode(kind, name=owner.getName() + "_" + role)

    @undoTransaction("hrig.LimbStretchLayer.add")
    def add(self):
        """長さ・体積のレイヤーを追加する。骨長比率は維持する。

        Returns:
            Node: 設定グループ。
        """
        if self.settings() is not None:
            return self.settings()
        rig, root = self.rig, self.rig.root
        lengths = [
            hlib.common.units.distanceFromUi(
                hlib.getAttr(rig._member("ik" + str(i)) + ".translateX").getu()
            )
            for i in (1, 2)
        ]
        owner = LengthCompensation.create(sum(lengths), root.getName() + "_stretchGraph").container
        if root.hasAttr("channel_stretch"):
            group = hlib.getNode(rig._member("channel_stretch"))
        else:
            parent = (
                rig._member("channelModule") if root.hasAttr("channelModule") else root.getFullName()
            )
            group = hlib.createNode(
                "transform", name=root.getName() + "_stretch_layer", parent=parent, skipSelect=True
            )
            rig._bind("channel_stretch", group.getFullName())
            group.addAttr(longName="enabled", attributeType="bool", defaultValue=True)
            group.addAttr(longName="active", attributeType="bool", defaultValue=False)
            group.setAttrFlags(["enabled", "active"], channelBox=True)
            group.setAttrFlags(["active"], locked=True)
            group.getPlug("useOutlinerColor").set(True)
        group.setAttrFlags(["translate", "rotate", "scale"], locked=True, keyable=False)
        group.addAttr(longName="graph", attributeType="message")
        owner.getPlug("message").connectTo(group.getPlug("graph"))
        rig._bind("stretchGroup", group.getFullName())
        if not root.hasAttr("hrigEnabled_stretch"):
            root.addAttr(
                longName="hrigEnabled_stretch", attributeType="bool", defaultValue=True
            )
        group.addAttr(longName="restLengths", dataType="string").set(
            hlib.json.JsonText.dumps(lengths)
        )
        for attr in ("inputLength", "softDistance"):
            group.addAttr(longName=attr, attributeType="double")
        for attr in ("outputs", "matrices"):
            group.addAttr(longName=attr, attributeType="message", multi=True)
        group.addAttr(longName="softNormalize", attributeType="message")
        for attr, value, low, high in (
            ("stretch", 1, 0, 1),
            ("squash", 0, 0, 1),
            ("volume", 1, 0, 1),
            ("minSquash", 0.1, 0.01, 1),
            ("maxStretch", 2, 1, 100),
        ):
            group.addAttr(
                longName=attr,
                attributeType="double",
                defaultValue=value,
                minValue=low,
                maxValue=high,
                keyable=True,
            )
            group.getPlug(attr).connectTo(owner.getPlug(attr))
        distance = hlib.getPlug(rig._member("distance") + ".distance")
        units = self._node(owner, "unitConversion", "distanceCm")
        distance.connectTo(units.getPlug("input"))
        units.getPlug("conversionFactor").set(1)
        units.getPlug("output").connectTo(group.getPlug("inputLength"))
        soft_input = hlib.getPlug(rig._member("softGraph") + ".distance")
        soft_input.getSourceWithConversion().connectTo(group.getPlug("softDistance"))
        normalize = self._node(owner, "multiplyDivide", "normalizedSoftDistance")
        normalize.getPlug("operation").set(2)
        group.getPlug("softDistance").connectTo(normalize.getPlug("input1X"))
        owner.getPlug("lengthScale").connectTo(normalize.getPlug("input2X"))
        normalize.getPlug("message").connectTo(group.getPlug("softNormalize"))
        for i, length in enumerate(lengths):
            multiply = self._node(owner, "multiplyDivide", "boneLength" + str(i))
            multiply.getPlug("input1X").set(length)
            owner.getPlug("lengthScale").connectTo(multiply.getPlug("input2X"))
            convert = self._node(owner, "unitConversion", "lengthUnits" + str(i))
            multiply.getPlug("outputX").connectTo(convert.getPlug("input"))
            convert.getPlug("conversionFactor").set(1)
            convert.getPlug("message").connectTo(group.getPlug("outputs")[i])
        shape = self._node(owner, "composeMatrix", "crossSection")
        inverse = self._node(owner, "multiplyDivide", "inverseVolume")
        inverse.getPlug("operation").set(2)
        inverse.getPlug("input1X").set(1)
        owner.getPlug("volumeScale").connectTo(inverse.getPlug("input2X"))
        unshape = self._node(owner, "composeMatrix", "parentCompensation")
        for axis in "YZ":
            owner.getPlug("volumeScale").connectTo(shape.getPlug("inputScale" + axis))
            inverse.getPlug("outputX").connectTo(unshape.getPlug("inputScale" + axis))
        for i in range(3):
            matrix = self._node(owner, "multMatrix", "deform" + str(i))
            # 親の断面scaleを打ち消し、子の位置や回転に歪みが累積しないようにする。
            shape.getPlug("outputMatrix").connectTo(matrix.getPlug("matrixIn")[0])
            hlib.getPlug(rig._local_matrix("ik" + str(i))).connectTo(matrix.getPlug("matrixIn")[1])
            if i:
                unshape.getPlug("outputMatrix").connectTo(matrix.getPlug("matrixIn")[2])
            matrix.getPlug("message").connectTo(group.getPlug("matrices")[i])
        for node in (group, owner):
            root.getPlug("hrigOwned").appendMessage(node)
        rig._update_evaluation()
        from . import channel_controls

        jobs = channel_controls._jobs.pop(root.getUuid(), None)
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
        rest = sum(hlib.json.JsonText.loads(group.getPlug("restLengths").get()))
        settings = {
            a: group.getPlug(a).get() for a in ("stretch", "squash", "minSquash", "maxStretch")
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
        owner = group.getPlug("graph").getSourceWithConversion().getNode()
        target = owner.getPlug("inputLength")
        if target.getSourceWithConversion() is not None:
            target.disconnect(target.getSourceWithConversion())
        if active:
            group.getPlug("inputLength").connectTo(target)
        else:
            target.set(owner.getPlug("restLength").get())
        for i, length in enumerate(hlib.json.JsonText.loads(group.getPlug("restLengths").get())):
            target = hlib.getPlug(rig._member("ik" + str(i + 1)) + ".translateX")
            if target.getSourceWithConversion() is not None:
                target.disconnect(target.getSourceWithConversion())
            if active:
                group.getPlug("outputs")[i].getSourceWithConversion().getNode().getPlug("output").connectTo(target)
            else:
                target.set(length)
        soft = hlib.getPlug(rig._member("softGraph") + ".distance")
        if soft.getSourceWithConversion() is not None:
            soft.disconnect(soft.getSourceWithConversion())
        source = (
            group.getPlug("softNormalize").getSourceWithConversion().getNode().getPlug("outputX")
            if active
            else group.getPlug("softDistance")
        )
        source.connectTo(soft)
        for i in range(3):
            target = hlib.getPlug(rig._member("joint" + str(i)) + ".offsetParentMatrix")
            if target.getSourceWithConversion() is not None:
                target.disconnect(target.getSourceWithConversion())
            source = (
                group.getPlug("matrices")[i].getSourceWithConversion().getNode().getPlug("matrixSum")
                if active
                else hlib.getPlug(rig._local_matrix(("ik" if rig.mode() == "ik" else "fk") + str(i)))
            )
            source.connectTo(target)
