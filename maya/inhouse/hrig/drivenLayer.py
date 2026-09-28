"""Swing/Twist成分と単一属性のSDKを部位の所有レイヤーへ登録する。"""

from maya import cmds

import math
import re

import hlib

from hrig.setups.swingTwist import SwingTwist
from hlib.general.drivenKey import DrivenKey
from hlib.decorators.undo import undo_transaction


class DrivenLayer:
    """SDKの接続、保存参照、無効時の基準値を管理する。"""

    def __init__(self, rig):
        """所属部位を保持する。

        Args:
            rig (LimbRig): 所属先。
        """
        self.rig = rig

    def graphs(self):
        """登録済み計算グラフを照会する。

        Returns:
            dict[str, Node]: 識別子とcontainer。
        """
        root = self.rig.root
        if not root.has_attr("drivenGraphs"):
            return {}
        return {
            node.plug("drivenId").get(): node
            for node in root.plug("drivenGraphs").source_nodes().values()
        }

    @undo_transaction("hrig.DrivenLayer.add")
    def add(self, identifier, joint, driven, component="twist", axis="x", keys=None):
        """未接続の単一属性を、分解角とSDKで駆動する。

        Args:
            identifier (str): 部位内で一意な英数字ID。
            joint (str | Node): 分解元joint。作成姿勢をゼロとする。
            driven (str | Plug): 未接続の駆動先属性。
            component (str): twistまたはswingX/Y/Z。
            axis (str): Twistの長手軸。
            keys (Sequence[tuple] | None): (入力度, 出力UI単位)。省略は-90/-1,0/0,90/1。

        Returns:
            Node: カーブと分解を所有するcontainer。
        """
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*", identifier
        ):
            raise ValueError("Invalid driven identifier")
        if identifier in self.graphs():
            raise ValueError("Driven identifier already exists")
        if component not in ("twist", "swingX", "swingY", "swingZ"):
            raise ValueError("Choose twist or swingX/Y/Z")
        pairs = [
            (float(x), float(y))
            for x, y in (keys if keys is not None else [(-90, -1), (0, 0), (90, 1)])
        ]
        if (
            len(pairs) < 2
            or len({x for x, _ in pairs}) != len(pairs)
            or not all(math.isfinite(v) for p in pairs for v in p)
        ):
            raise ValueError("Provide at least two unique finite driver keys")
        joint, driven = hlib.getNode(joint), hlib.getPlug(driven)
        kind = driven.data_type()
        if (
            kind not in ("double", "float", "doubleAngle", "doubleLinear", "long")
            or driven.source()
            or driven.is_locked()
        ):
            raise ValueError("Driven must be an unlocked, unconnected numeric scalar")
        upstream = set(
            [
                item.full_name()
                for item in hlib.ls(
                    [
                        item.full_name()
                        for item in [
                            hlib.getNode(value)
                            for value in (cmds.listHistory(joint.full_name()) or [])
                        ]
                    ]
                    or [],
                    long=True,
                )
            ]
            or []
        )
        upstream.add(joint.full_name())
        cursor = joint.full_name()
        while True:
            parents = [
                item.full_name()
                for item in [
                    hlib.getNode(value)
                    for value in (cmds.listRelatives(cursor, parent=True, fullPath=True) or [])
                ]
            ] or []
            if not parents:
                break
            cursor = parents[0]
            upstream.add(cursor)
        # IK内部の暗黙依存を含む部位の主制御を駆動先にしない。
        upstream.update(self.rig.controls().values())
        upstream.update(self.rig.joints()[:3])
        if driven.node.full_name() in upstream:
            raise ValueError("Driven target must not feed the source joint or its controls")
        before = set([item.name() for item in hlib.ls()])
        stem = self.rig.node_name("drivenSet").removesuffix("_set") + "_" + identifier
        graph = SwingTwist.create(joint, name=stem + "_graph", axis=axis)
        owner = graph.container
        rest_value = driven.get()
        relation = DrivenKey(owner.plug(component), driven)
        for x, y in pairs:
            relation.set_key(x, y)
        curve = relation.curves()[0]
        output = driven.source()
        output.disconnect(driven)
        owner.add_attr(long_name="drivenOutput", attribute_type=kind)
        output.connect(owner.plug("drivenOutput"))
        owner.add_attr(long_name="restValue", attribute_type=kind).set(rest_value)
        for attr, value in (
            ("drivenId", identifier),
            ("drivenAttribute", driven.full_name().split(".", 1)[1]),
            ("component", component),
        ):
            owner.add_attr(long_name=attr, data_type="string").set(value)
        for attr, node in (("drivenNode", driven.node), ("curve", curve)):
            owner.add_attr(long_name=attr, attribute_type="message")
            node.plug("message").connect(owner.plug(attr))
        members = {n.name() for n in hlib.nodes.Container(owner).members()}
        extra = set([item.name() for item in hlib.ls()]) - before - members - {owner.name()}
        if extra:
            hlib.nodes.Container(owner).add_members(*extra)
        root = self.rig.root
        owned = [owner]
        if not root.has_attr("drivenSet"):
            selection = hlib.createSet(empty=True, name=self.rig.node_name("drivenSet")).full_name()
            self.rig._bind("drivenSet", selection)
            self.rig._layer_members("moduleSet", [selection])
            owned.append(hlib.getNode(selection))
            root.add_attr(long_name="drivenGraphs", attribute_type="message", multi=True)
        root.plug("drivenGraphs").append_message(owner)
        for node in owned:
            root.plug("hrigOwned").append_message(node)
        self.rig._layer_members("drivenSet", [owner.full_name()])
        self.update()
        from .channel_controls import sync_display

        sync_display(self.rig)
        return owner

    def update(self):
        """無効時は駆動先を基準値へ戻して計算需要を切断する。"""
        active = self.rig.lod() == 1 and self.rig.layer_enabled("driven")
        for owner in self.graphs().values():
            reference = owner.plug("drivenNode").source()
            if reference is None:
                continue
            destination = reference.node.plug(owner.plug("drivenAttribute").get())
            source = destination.source()
            output = owner.plug("drivenOutput")
            if source is not None and source.mplug() != output.mplug():
                raise RuntimeError("Driven connection was replaced externally")
            if active and source is None:
                output.connect(destination)
            elif not active:
                if source is not None:
                    source.disconnect(destination)
                destination.set(owner.plug("restValue").get())
            owner.plug("nodeState").set(0 if active else 2)
