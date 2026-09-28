"""Twist/Swing/割合回転を追従する補助骨レイヤー。"""

from maya import cmds

import re

import hlib

from hrig.setups.rotationFollow import RotationFollow
from hlib.decorators.undo import undo_transaction


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
        if not root.has_attr("followGroups"):
            return {}
        return {
            node.plug("followId").get(): node
            for node in root.plug("followGroups").source_nodes().values()
        }

    def joints(self, identifier=None):
        """生成した追従骨を取得する。

        Args:
            identifier (str | None): ID。省略時は全て。

        Returns:
            tuple[str]: 骨の完全名。
        """
        groups = self.groups()
        selected = [groups[identifier]] if identifier is not None else groups.values()
        return tuple(group.plug("joint").source().node.full_name() for group in selected)

    @undo_transaction("hrig.FollowLayer.add")
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
        if joint.type() != "joint" or not joint.full_name().startswith(
            self.rig.root.full_name() + "|"
        ):
            raise ValueError("Expected a joint inside the module")
        parent = (
            [
                item.full_name()
                for item in [
                    hlib.getNode(value)
                    for value in (
                        cmds.listRelatives(joint.full_name(), parent=True, fullPath=True) or []
                    )
                ]
            ]
            or [None]
        )[0]
        stem = self.rig.root.name() + "_follow_" + identifier
        if [item.name() for item in hlib.ls(stem + "_*")]:
            raise ValueError("Follow names already exist")
        graph = RotationFollow.create(
            joint, name=stem + "_graph", mode=mode, axis=axis, ratio=ratio
        )
        group = hlib.createNode("transform", name=stem + "_grp", parent=parent, skipSelect=True)
        group.add_attr(long_name="followId", data_type="string").set(identifier)
        group.add_attr(long_name="axis", data_type="string").set(axis)
        group.add_attr(
            long_name="ratio",
            attribute_type="double",
            default_value=ratio,
            minValue=0,
            maxValue=1,
            keyable=True,
        )
        group.add_attr(
            long_name="followMode",
            attribute_type="enum",
            enumName="Full:Twist:Swing",
            default_value=("full", "twist", "swing").index(mode),
        )
        group.set_attr_flags(["followMode"], channel_box=True)
        for attr in ("ratio", "followMode"):
            group.plug(attr).connect(graph.container.plug(attr))
        group.set_attr_flags(["followId", "axis"], locked=True)
        bone = hlib.createNode("joint", name=stem + "_jnt", parent=group, skipSelect=True)
        bone.plug("segmentScaleCompensate").set(False)
        bone.plug("radius").set(0.55)
        bone.plug("overrideEnabled").set(True)
        bone.plug("overrideColor").set(13)
        for attr, node in (("joint", bone), ("graph", graph.container), ("sourceJoint", joint)):
            group.add_attr(long_name=attr, attribute_type="message")
            node.plug("message").connect(group.plug(attr))
        root = self.rig.root
        for attr in ("followGroups", "hrigOwned"):
            if not root.has_attr(attr):
                root.add_attr(long_name=attr, attribute_type="message", multi=True)
        if not root.has_attr("hrigEnabled_follow"):
            root.add_attr(long_name="hrigEnabled_follow", attribute_type="bool", default_value=True)
        for attr, nodes in (("followGroups", (group,)), ("hrigOwned", (group, graph.container))):
            for node in nodes:
                root.plug(attr).append_message(node)
        group.set_attr_flags(["translate", "rotate", "scale"], locked=True, keyable=False)
        self.update()
        # スカートには腕脚の表示ノードを作らず、既存の監視入口を再登録する。
        from .skirtRig import SkirtRig

        if isinstance(self.rig, SkirtRig):
            root.set_attr_flags(["hrigEnabled_follow"], channel_box=True)
            jobs = SkirtRig._jobs.pop(root.uuid(), None)
            if jobs is not None:
                jobs.stop()
            SkirtRig.refresh_jobs()
        else:
            from .channel_controls import sync_display

            sync_display(self.rig)
        return bone.full_name()

    def update(self):
        """Enabled/LODに応じて出力を切断し、基準姿勢へ戻す。"""
        active = self.rig.lod() == 1 and self.rig.layer_enabled("follow")
        for group in self.groups().values():
            graph = group.plug("graph").source().node
            target = group.plug("joint").source().node.plug("offsetParentMatrix")
            source = target.source()
            output = graph.plug("matrix")
            if source is not None and source.mplug() != output.mplug():
                raise ValueError("Follow output was replaced")
            if active and source is None:
                output.connect(target)
            elif not active:
                if source is not None:
                    source.disconnect(target)
                target.set(graph.plug("restMatrix").get())
            graph.plug("nodeState").set(0 if active else 2)
            group.plug("visibility").set(active)
