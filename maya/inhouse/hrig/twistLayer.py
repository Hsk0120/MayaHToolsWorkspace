"""二関節間のツイスト補助骨を登録・再生成するレイヤー。"""
from hlib.maths import MSpace

from maya import cmds

import re

import hlib

from hrig.setups import TwistDistribution
from hlib.maths import Matrix
from hlib.decorators.undo import undoTransaction


class TwistLayer:
    """複数区間の補助骨と計算containerを、部位の所有物として管理する。"""

    def __init__(self, rig):
        """操作対象を保持する。

        Args:
            rig (LimbRig): 所属する部位。
        """
        self.rig = rig

    def segments(self):
        """保存済みの区間IDとグループを取得する。

        Returns:
            dict[str, Node]: 改名に追従する区間参照。
        """
        root = self.rig.root
        if not root.hasAttr("twistSegments"):
            return {}
        return {
            node.getPlug("segmentId").get(): node
            for node in root.getPlug("twistSegments").getSourceNodes().values()
        }

    def getJoints(self, segment=None):
        """区間内の骨を始点からの割合順に取得する。

        Args:
            segment (str | None): 区間ID。Noneなら全区間。

        Returns:
            tuple[str]: ツイスト補助骨の完全名。
        """
        groups = self.segments()
        selected = [groups[segment]] if segment is not None else list(groups.values())
        result = []
        for group in selected:
            children = [
                item.getFullName()
                for item in [
                    hlib.getNode(value)
                    for value in (
                        cmds.listRelatives(
                            group.getFullName(), children=True, type="joint", fullPath=True
                        )
                        or []
                    )
                ]
            ] or []
            result.extend(
                sorted(children, key=lambda node: hlib.getPlug(node + ".twistFraction").get())
            )
        return tuple(result)

    def _own(self, nodes):
        """生成物をリグの削除対象と選択セットへ登録する。

        Args:
            nodes (Sequence[Node]): 所有ノード。両端の参照骨は含めない。
        """
        root = self.rig.root
        for node in nodes:
            root.getPlug("hrigOwned").appendMessage(node)
        members = [n.getFullName() for n in nodes if n.getFullName() != self.rig._member("twistSet")]
        if members:
            self.rig._layer_members("twistSet", members)

    @undoTransaction("hrig.TwistLayer.add")
    def add(self, segment, start, end, count=3, axis="x"):
        """両端を含まないN本の補助骨をi/(N+1)で配置する。

        Args:
            segment (str): 部位内で一意な区間ID。
            start (str | Node): 始点のjoint。
            end (str | Node): 終点のjoint。
            count (int): 1以上の補助骨数。
            axis (str): 始点の長手軸x/y/z。

        Returns:
            tuple[str]: 生成した補助骨。
        """
        if not isinstance(segment, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", segment):
            raise ValueError("Invalid twist segment id")
        if type(count) is not int or count < 1:
            raise ValueError("count must be a positive integer")
        if segment in self.segments():
            raise ValueError("Twist segment already exists")
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        start, end = hlib.getNode(start), hlib.getNode(end)
        if start.getType() != "joint" or end.getType() != "joint" or start == end:
            raise ValueError("Expected two different joints")
        relative = end.getMatrix(ws=True) * start.getMatrix(ws=True).inverse()
        position = tuple(relative)[12:15]
        if sum(value * value for value in position) < 1e-12:
            raise ValueError("Twist endpoints must not coincide")
        if any(abs(position[i]) > 1e-5 for i in range(3) if i != "xyz".index(axis)):
            raise ValueError("Endpoints must align with the chosen start-local axis at creation")
        root = self.rig.root
        stem = self.rig.getNodeName("twistSet").removesuffix("_set") + "_" + segment
        for name in [stem + "_grp", stem + "_graph"] + [
            stem + "_{:02d}_jnt".format(i + 1) for i in range(count)
        ]:
            if cmds.objExists(name):
                raise ValueError("Twist node already exists: " + name)
        if not root.hasAttr("twistSet"):
            selection = hlib.createSet(empty=True, name=self.rig.getNodeName("twistSet")).getFullName()
            self.rig._bind("twistSet", selection)
            self.rig._layer_members("moduleSet", [selection])
            self._own([hlib.getNode(selection)])
            root.addAttr(longName="twistSegments", attributeType="message", multi=True)
        group = hlib.createNode("transform", name=stem + "_grp", parent=start, skipSelect=True)
        for attr, value in (("segmentId", segment), ("twistAxis", axis)):
            group.addAttr(longName=attr, dataType="string").set(value)
        group.addAttr(longName="count", attributeType="long", defaultValue=count)
        group.setAttrFlags(["count"], locked=True, keyable=False, channelBox=True)
        graph = TwistDistribution.create(start, end, stem + "_graph", axis)
        for attr, node in (("start", start), ("end", end), ("graph", graph.container)):
            group.addAttr(longName=attr, attributeType="message")
            node.getPlug("message").connectTo(group.getPlug(attr))
        root.getPlug("twistSegments").appendMessage(group)
        joints = []
        for index in range(count):
            fraction = (index + 1) / (count + 1)
            joint = hlib.createNode(
                "joint", name=stem + "_{:02d}_jnt".format(index + 1), parent=group, skipSelect=True
            )
            joint.getPlug("segmentScaleCompensate").set(False)
            joint.getPlug("radius").set(0.3)
            joint.addAttr(
                longName="twistFraction", attributeType="double", defaultValue=fraction
            )
            joint.addAttr(longName="twistOutput", attributeType="message")
            output = graph.sample(fraction, "sample{:02d}".format(index + 1))
            output.getNode().getPlug("message").connectTo(joint.getPlug("twistOutput"))
            rest = Matrix()
            for i in range(3):
                rest[12 + i] = position[i] * fraction
            joint.addAttr(longName="twistRest", dataType="matrix").set(rest)
            output.connectTo(joint.getPlug("offsetParentMatrix"))
            joints.append(joint.getFullName())
        self._own([group, graph.container])
        self.rig._layer_members("twistSet", joints)
        from .limb import _lock_group

        _lock_group(group)
        self.update()
        from .channel_controls import sync_display

        sync_display(self.rig)
        return tuple(joints)

    @undoTransaction("hrig.TwistLayer.set_count")
    def set_count(self, segment, count):
        """未使用の区間を指定本数で再生成する。0なら区間を削除する。

        Args:
            segment (str): 登録済み区間ID。
            count (int): 新しい本数。0以上。

        Returns:
            tuple[str]: 再生成した骨。0の場合は空。

        Note:
            スキンや外部ノードへ接続済みの骨は削除しない。バインド前に本数を決める。
        """
        if type(count) is not int or count < 0:
            raise ValueError("count must be a non-negative integer")
        group = self.segments()[segment]
        if count == group.getPlug("count").get():
            return self.getJoints(segment)
        for joint in self.getJoints(segment):
            downstream = [
                item.getFullName()
                for item in [
                    hlib.getNode(value)
                    for value in (
                        cmds.listConnections(
                            joint, source=False, destination=True, type="skinCluster"
                        )
                        or []
                    )
                ]
            ] or []
            other = [
                item.getFullName()
                for item in [
                    hlib.getNode(value)
                    for value in (cmds.listConnections(joint, source=False, destination=True) or [])
                ]
            ] or []
            if downstream or any(
                hlib.getNode(n).getType() not in ("objectSet", "dagPose") for n in other
            ):
                raise ValueError("Twist joints are in use; choose the count before binding")
            if [
                item.getFullName()
                for item in [
                    hlib.getNode(value)
                    for value in (
                        cmds.listConnections(
                            joint, source=True, destination=False, type="animCurve"
                        )
                        or []
                    )
                ]
            ]:
                raise ValueError("Animated twist joints cannot be rebuilt")
        start = group.getPlug("start").getSourceWithConversion().getNode()
        end = group.getPlug("end").getSourceWithConversion().getNode()
        axis = group.getPlug("twistAxis").get()
        graph = group.getPlug("graph").getSourceWithConversion().getNode()
        # container削除が空になった関連セットまで削除しないよう、先に所属を外す。
        hlib.getNode(self.rig._member("twistSet")).removeMembers(
            [group.getFullName(), graph.getFullName()] + list(self.getJoints(segment))
        )
        hlib.delete([group, graph])
        if count:
            return self.add(segment, start, end, count, axis)
        from .channel_controls import sync_display

        sync_display(self.rig)
        return ()

    def update(self):
        """LOD/Enabledに応じて出力を接続し、無効時は基準位置で始点へ追従させる。"""
        active = self.rig.lod() == 1 and self.rig.layer_enabled("twist")
        for group in self.segments().values():
            graph = group.getPlug("graph").getSourceWithConversion().getNode()
            graph.getPlug("nodeState").set(0 if active else 2)
            group.getPlug("visibility").set(active)
        for name in self.getJoints():
            joint = hlib.getNode(name)
            destination = joint.getPlug("offsetParentMatrix")
            source = destination.getSourceWithConversion()
            if active:
                output = joint.getPlug("twistOutput").getSourceWithConversion().getNode().getPlug("matrixSum")
                if source is None:
                    output.connectTo(destination)
            elif source is not None:
                destination.disconnect(source)
                destination.set(joint.getPlug("twistRest").get())
