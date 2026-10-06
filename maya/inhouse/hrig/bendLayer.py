"""肘・膝の回転補間骨と内外の補正骨を管理する。"""

from maya import cmds

import re

import hlib

from hrig.setups.bendCorrection import BendCorrection
from hlib.decorators.undo import undoTransaction


class BendLayer:
    """ヒンジ補助骨を独立したEnabled/LODレイヤーとして登録する。"""

    def __init__(self, rig):
        """部位の参照を保持する。

        Args:
            rig (LimbRig): 所属するリグ。
        """
        self.rig = rig

    def groups(self):
        """保存された補正部位を取得する。

        Returns:
            dict[str, Node]: IDと設定グループ。
        """
        root = self.rig.root
        if not root.hasAttr("bendGroups"):
            return {}
        return {
            node.getPlug("bendId").get(): node
            for node in root.getPlug("bendGroups").getSourceNodes().values()
        }

    def getJoints(self, identifier=None):
        """補間・内側・外側の順に骨を取得する。

        Args:
            identifier (str | None): 部位ID。Noneなら全て。

        Returns:
            tuple[str]: 骨の完全名。
        """
        groups = self.groups()
        selected = [groups[identifier]] if identifier is not None else groups.values()
        return tuple(
            group.getPlug(role).getSourceWithConversion().getNode().getFullName()
            for group in selected
            for role in ("half", "inner", "outer")
        )

    @undoTransaction("hrig.BendLayer.add")
    def add(self, identifier, joint, bend_axis="z", push_axis="y"):
        """関節の親空間に50%回転骨、その子に内外骨を生成する。

        Args:
            identifier (str): 部位内で一意な英数字ID。
            joint (str | Node): 親jointを持つ、基準姿勢のヒンジ関節。
            bend_axis (str): 回転軸x/y/z。
            push_axis (str): 内外の配置・移動軸x/y/z。回転軸とは別。

        Returns:
            tuple[str]: 補間・内側・外側の補助骨。

        Note:
            グループ属性で距離、割合、曲げ方向を調整する。スキン前に追加する。
        """
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*", identifier
        ):
            raise ValueError("Invalid bend identifier")
        if identifier in self.groups():
            raise ValueError("Bend identifier already exists")
        if (
            bend_axis not in "xyz"
            or push_axis not in "xyz"
            or len(bend_axis) != 1
            or len(push_axis) != 1
            or bend_axis == push_axis
        ):
            raise ValueError("Choose two different axes from x, y, z")
        joint = hlib.getNode(joint)
        parents = [
            item.getFullName()
            for item in [
                hlib.getNode(value)
                for value in (
                    cmds.listRelatives(joint.getFullName(), parent=True, fullPath=True) or []
                )
            ]
        ] or []
        if joint.getType() != "joint" or not parents or hlib.getNode(parents[0]).getType() != "joint":
            raise ValueError("Expected a joint with a parent joint")
        parent = hlib.getNode(parents[0])
        stem = self.rig.getNodeName("bendSet").removesuffix("_set") + "_" + identifier
        names = [
            stem + suffix for suffix in ("_grp", "_graph", "_half_jnt", "_inner_jnt", "_outer_jnt")
        ]
        if any(cmds.objExists(name) for name in names):
            raise ValueError("Bend node names already exist")
        root = self.rig.root
        owned = []
        if not root.hasAttr("bendSet"):
            selection = hlib.createSet(empty=True, name=self.rig.getNodeName("bendSet")).getFullName()
            self.rig._bind("bendSet", selection)
            self.rig._layer_members("moduleSet", [selection])
            root.addAttr(longName="bendGroups", attributeType="message", multi=True)
            owned.append(hlib.getNode(selection))
        group = hlib.createNode("transform", name=names[0], parent=parent, skipSelect=True)
        group.addAttr(longName="bendId", dataType="string").set(identifier)
        group.addAttr(longName="pushAxis", dataType="string").set(push_axis)
        graph = BendCorrection.create(parent, joint, names[1], bend_axis)
        owner = graph.container
        group.addAttr(longName="graph", attributeType="message")
        owner.getPlug("message").connectTo(group.getPlug("graph"))
        for attr in (
            "rotationRatio",
            "referenceAngle",
            "bendSign",
            "innerRest",
            "outerRest",
            "innerPush",
            "outerPush",
        ):
            bounds = {"minValue": 0, "maxValue": 1} if attr == "rotationRatio" else {}
            if attr == "referenceAngle":
                bounds = {"minValue": 0.001}
            if attr == "bendSign":
                bounds = {"minValue": -1, "maxValue": 1}
            group.addAttr(
                longName=attr,
                attributeType="doubleLinear" if attr.endswith(("Rest", "Push")) else "double",
                defaultValue=owner.getPlug(attr).get(),
                **bounds
            )
            group.getPlug(attr).set(owner.getPlug(attr).get())
            group.setAttrFlags([attr], keyable=False, channelBox=True)
            group.getPlug(attr).connectTo(owner.getPlug(attr))
        joints = []
        for role, name in zip(("half", "inner", "outer"), names[2:]):
            bone = hlib.createNode(
                "joint", name=name, parent=group if role == "half" else joints[0], skipSelect=True
            )
            bone.getPlug("segmentScaleCompensate").set(False)
            bone.getPlug("radius").set(0.35 if role == "half" else 0.25)
            group.addAttr(longName=role, attributeType="message")
            bone.getPlug("message").connectTo(group.getPlug(role))
            joints.append(bone)
        root.getPlug("bendGroups").appendMessage(group)
        owned.extend([group, owner])
        for node in owned:
            root.getPlug("hrigOwned").appendMessage(node)
        self.rig._layer_members(
            "bendSet", [group.getFullName(), owner.getFullName()] + [n.getFullName() for n in joints]
        )
        from .limb import _lock_group

        _lock_group(group)
        self.update()
        from .channel_controls import sync_display

        sync_display(self.rig)
        return tuple(n.getFullName() for n in joints)

    def update(self):
        """無効時に出力を切断して基準姿勢へ戻し、親だけを継承する。"""
        active = self.rig.lod() == 1 and self.rig.layer_enabled("bend")
        for group in self.groups().values():
            owner = group.getPlug("graph").getSourceWithConversion().getNode()
            owner.getPlug("nodeState").set(0 if active else 2)
            group.getPlug("visibility").set(active)
            for role in ("half", "inner", "outer"):
                bone = group.getPlug(role).getSourceWithConversion().getNode()
                attr = (
                    "offsetParentMatrix"
                    if role == "half"
                    else "translate" + group.getPlug("pushAxis").get().upper()
                )
                destination = bone.getPlug(attr)
                source = destination.getSourceWithConversion()
                if active and source is None:
                    owner.getPlug("matrix" if role == "half" else role).connectTo(destination)
                elif not active:
                    if source is not None:
                        destination.disconnect(source)
                    if role == "half":
                        destination.set(owner.getPlug("restMatrix").get())
                    else:
                        destination.set(group.getPlug(role + "Rest").get())
