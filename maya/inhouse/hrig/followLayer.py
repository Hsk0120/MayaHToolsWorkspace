"""Twist/Swing/割合回転を追従する補助骨レイヤー。"""

from maya import cmds

import re

import hlib

from hrig.setups.rotationFollow import RotationFollow
from hlib.decorators.undo import undoTransaction


class FollowLayer:
    """腕脚とスカートに共通の、回転追従補助骨の所有・評価管理。"""

    def __init__(self, rig):
        """対象モジュールを保持する。

        Args:
            rig (LimbRig | SkirtRig): 所属モジュール。
        """
        self.rig = rig

    def groups(self):
        """保存済み設定グループを解決する。

        Returns:
            dict[str, Node]: IDと設定グループ。
        """
        root = self.rig.root
        if not root.hasAttr("followGroups"):
            return {}
        return {
            node.getPlug("followId").get(): node
            for node in root.getPlug("followGroups").getSourceNodes().values()
        }

    def getJoints(self, identifier=None):
        """生成した追従骨を取得する。

        Args:
            identifier (str | None): ID。省略時は全て。

        Returns:
            tuple[str]: 骨の完全名。
        """
        groups = self.groups()
        selected = [groups[identifier]] if identifier is not None else groups.values()
        return tuple(group.getPlug("joint").getSourceWithConversion().getNode().getFullName() for group in selected)

    @undoTransaction("hrig.FollowLayer.add")
    def add(self, identifier, joint, mode="full", axis="x", ratio=0.5):
        """入力と同じ親空間に独立した追従骨を追加する。

        Args:
            identifier (str): モジュール内で一意な英数字ID。
            joint (str | Node): モジュール配下の入力joint。
            mode (str): full/twist/swing。
            axis (str): Twist軸x/y/z。
            ratio (float): 0〜1の追従割合。

        Returns:
            str: 追従骨の完全名。設定はgroups()[identifier]で取得する。
        """
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*", identifier
        ):
            raise ValueError("Invalid follow identifier")
        if identifier in self.groups():
            raise ValueError("Follow identifier already exists")
        joint = hlib.getNode(joint)
        if joint.getType() != "joint" or not joint.getFullName().startswith(
            self.rig.root.getFullName() + "|"
        ):
            raise ValueError("Expected a joint inside the module")
        parent = (
            [
                item.getFullName()
                for item in [
                    hlib.getNode(value)
                    for value in (
                        cmds.listRelatives(joint.getFullName(), parent=True, fullPath=True) or []
                    )
                ]
            ]
            or [None]
        )[0]
        stem = self.rig.root.getName() + "_follow_" + identifier
        if [item.getName() for item in hlib.ls(stem + "_*")]:
            raise ValueError("Follow names already exist")
        graph = RotationFollow.create(
            joint, name=stem + "_graph", mode=mode, axis=axis, ratio=ratio
        )
        group = hlib.createNode("transform", name=stem + "_grp", parent=parent, skipSelect=True)
        group.addAttr(longName="followId", dataType="string").set(identifier)
        group.addAttr(longName="axis", dataType="string").set(axis)
        group.addAttr(
            longName="ratio",
            attributeType="double",
            defaultValue=ratio,
            minValue=0,
            maxValue=1,
            keyable=True,
        )
        group.addAttr(
            longName="followMode",
            attributeType="enum",
            enumName="Full:Twist:Swing",
            defaultValue=("full", "twist", "swing").index(mode),
        )
        group.setAttrFlags(["followMode"], channelBox=True)
        for attr in ("ratio", "followMode"):
            group.getPlug(attr).connectTo(graph.container.getPlug(attr))
        group.setAttrFlags(["followId", "axis"], locked=True)
        bone = hlib.createNode("joint", name=stem + "_jnt", parent=group, skipSelect=True)
        bone.getPlug("segmentScaleCompensate").set(False)
        bone.getPlug("radius").set(0.55)
        bone.getPlug("overrideEnabled").set(True)
        bone.getPlug("overrideColor").set(13)
        for attr, node in (("joint", bone), ("graph", graph.container), ("sourceJoint", joint)):
            group.addAttr(longName=attr, attributeType="message")
            node.getPlug("message").connectTo(group.getPlug(attr))
        root = self.rig.root
        for attr in ("followGroups", "hrigOwned"):
            if not root.hasAttr(attr):
                root.addAttr(longName=attr, attributeType="message", multi=True)
        if not root.hasAttr("hrigEnabled_follow"):
            root.addAttr(longName="hrigEnabled_follow", attributeType="bool", defaultValue=True)
        for attr, nodes in (("followGroups", (group,)), ("hrigOwned", (group, graph.container))):
            for node in nodes:
                root.getPlug(attr).appendMessage(node)
        group.setAttrFlags(["translate", "rotate", "scale"], locked=True, keyable=False)
        self.update()
        # スカートには腕脚の表示ノードを作らず、既存の監視入口を再登録する。
        from .skirtRig import SkirtRig

        if isinstance(self.rig, SkirtRig):
            root.setAttrFlags(["hrigEnabled_follow"], channelBox=True)
            jobs = SkirtRig._jobs.pop(root.getUuid(), None)
            if jobs is not None:
                jobs.stop()
            SkirtRig.refresh_jobs()
        else:
            from .channel_controls import sync_display

            sync_display(self.rig)
        return bone.getFullName()

    def update(self):
        """Enabled/LODに応じて出力を切断し、基準姿勢へ戻す。"""
        active = self.rig.lod() == 1 and self.rig.layer_enabled("follow")
        for group in self.groups().values():
            graph = group.getPlug("graph").getSourceWithConversion().getNode()
            target = group.getPlug("joint").getSourceWithConversion().getNode().getPlug("offsetParentMatrix")
            source = target.getSourceWithConversion()
            output = graph.getPlug("matrix")
            if source is not None and source.mplug() != output.mplug():
                raise ValueError("Follow output was replaced")
            if active and source is None:
                output.connectTo(target)
            elif not active:
                if source is not None:
                    target.disconnect(source)
                target.set(graph.getPlug("restMatrix").get())
            graph.getPlug("nodeState").set(0 if active else 2)
            group.getPlug("visibility").set(active)
