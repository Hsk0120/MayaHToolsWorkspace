"""肘・膝の回転補間骨と内外の補正骨を管理する。"""

from maya import cmds

import re

import hlib

from hrig.setups.bendCorrection import BendCorrection
from hlib.decorators.undo import undo_transaction


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
        if not root.has_attr("bendGroups"):
            return {}
        return {
            node.plug("bendId").get(): node
            for node in root.plug("bendGroups").source_nodes().values()
        }

    def joints(self, identifier=None):
        """補間・内側・外側の順に骨を取得する。

        Args:
            identifier (str | None): 部位ID。Noneなら全て。

        Returns:
            tuple[str]: 骨の完全名。
        """
        groups = self.groups()
        selected = [groups[identifier]] if identifier is not None else groups.values()
        return tuple(
            group.plug(role).source().node.full_name()
            for group in selected
            for role in ("half", "inner", "outer")
        )

    @undo_transaction("hrig.BendLayer.add")
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
            item.full_name()
            for item in [
                hlib.getNode(value)
                for value in (
                    cmds.listRelatives(joint.full_name(), parent=True, fullPath=True) or []
                )
            ]
        ] or []
        if joint.type() != "joint" or not parents or hlib.getNode(parents[0]).type() != "joint":
            raise ValueError("Expected a joint with a parent joint")
        parent = hlib.getNode(parents[0])
        stem = self.rig.node_name("bendSet").removesuffix("_set") + "_" + identifier
        names = [
            stem + suffix for suffix in ("_grp", "_graph", "_half_jnt", "_inner_jnt", "_outer_jnt")
        ]
        if any(cmds.objExists(name) for name in names):
            raise ValueError("Bend node names already exist")
        root = self.rig.root
        owned = []
        if not root.has_attr("bendSet"):
            selection = hlib.createSet(empty=True, name=self.rig.node_name("bendSet")).full_name()
            self.rig._bind("bendSet", selection)
            self.rig._layer_members("moduleSet", [selection])
            root.add_attr(long_name="bendGroups", attribute_type="message", multi=True)
            owned.append(hlib.getNode(selection))
        group = hlib.createNode("transform", name=names[0], parent=parent, skipSelect=True)
        group.add_attr(long_name="bendId", data_type="string").set(identifier)
        group.add_attr(long_name="pushAxis", data_type="string").set(push_axis)
        graph = BendCorrection.create(parent, joint, names[1], bend_axis)
        owner = graph.container
        group.add_attr(long_name="graph", attribute_type="message")
        owner.plug("message").connect(group.plug("graph"))
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
            group.add_attr(
                long_name=attr,
                attribute_type="doubleLinear" if attr.endswith(("Rest", "Push")) else "double",
                default_value=owner.plug(attr).get(),
                **bounds
            )
            group.plug(attr).set(owner.plug(attr).get())
            group.set_attr_flags([attr], keyable=False, channel_box=True)
            group.plug(attr).connect(owner.plug(attr))
        joints = []
        for role, name in zip(("half", "inner", "outer"), names[2:]):
            bone = hlib.createNode(
                "joint", name=name, parent=group if role == "half" else joints[0], skipSelect=True
            )
            bone.plug("segmentScaleCompensate").set(False)
            bone.plug("radius").set(0.35 if role == "half" else 0.25)
            group.add_attr(long_name=role, attribute_type="message")
            bone.plug("message").connect(group.plug(role))
            joints.append(bone)
        root.plug("bendGroups").append_message(group)
        owned.extend([group, owner])
        for node in owned:
            root.plug("hrigOwned").append_message(node)
        self.rig._layer_members(
            "bendSet", [group.full_name(), owner.full_name()] + [n.full_name() for n in joints]
        )
        from .limb import _lock_group

        _lock_group(group)
        self.update()
        from .channel_controls import sync_display

        sync_display(self.rig)
        return tuple(n.full_name() for n in joints)

    def update(self):
        """無効時に出力を切断して基準姿勢へ戻し、親だけを継承する。"""
        active = self.rig.lod() == 1 and self.rig.layer_enabled("bend")
        for group in self.groups().values():
            owner = group.plug("graph").source().node
            owner.plug("nodeState").set(0 if active else 2)
            group.plug("visibility").set(active)
            for role in ("half", "inner", "outer"):
                bone = group.plug(role).source().node
                attr = (
                    "offsetParentMatrix"
                    if role == "half"
                    else "translate" + group.plug("pushAxis").get().upper()
                )
                destination = bone.plug(attr)
                source = destination.source()
                if active and source is None:
                    owner.plug("matrix" if role == "half" else role).connect(destination)
                elif not active:
                    if source is not None:
                        source.disconnect(destination)
                    if role == "half":
                        destination.set_value(owner.plug("restMatrix").get())
                    else:
                        destination.set(group.plug(role + "Rest").get())
