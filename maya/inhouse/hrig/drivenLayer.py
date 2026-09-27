"""Swing/Twist成分と単一属性のSDKを部位の所有レイヤーへ登録する。"""

import math
import re

from maya import cmds

import hlib
from hlib.animation.swingTwist import SwingTwist
from hlib.animation.drivenKey import DrivenKey
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
        result = {}
        for index in cmds.getAttr(root.full_name() + ".drivenGraphs", multiIndices=True) or []:
            source = root.plug("drivenGraphs[{}]".format(index)).source()
            if source:
                result[source.node.plug("drivenId").get()] = source.node
        return result

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
        joint, driven = hlib.node(joint), hlib.plug(driven)
        kind = cmds.getAttr(driven.full_name(), type=True)
        if (
            kind not in ("double", "float", "doubleAngle", "doubleLinear", "long")
            or driven.source()
            or driven.is_locked()
        ):
            raise ValueError("Driven must be an unlocked, unconnected numeric scalar")
        upstream = set(cmds.ls(cmds.listHistory(joint.full_name()) or [], long=True) or [])
        upstream.add(joint.full_name())
        cursor = joint.full_name()
        while True:
            parents = cmds.listRelatives(cursor, parent=True, fullPath=True) or []
            if not parents:
                break
            cursor = parents[0]
            upstream.add(cursor)
        # IK内部の暗黙依存を含む部位の主制御を駆動先にしない。
        upstream.update(self.rig.controls().values())
        upstream.update(self.rig.joints()[:3])
        if driven.node.full_name() in upstream:
            raise ValueError("Driven target must not feed the source joint or its controls")
        before = set(cmds.ls())
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
        members = set(cmds.container(owner.full_name(), query=True, nodeList=True) or [])
        extra = set(cmds.ls()) - before - members - {owner.name()}
        if extra:
            cmds.container(owner.full_name(), edit=True, addNode=list(extra))
        root = self.rig.root
        owned = [owner]
        if not root.has_attr("drivenSet"):
            selection = cmds.sets(empty=True, name=self.rig.node_name("drivenSet"))
            self.rig._bind("drivenSet", selection)
            self.rig._layer_members("moduleSet", [selection])
            owned.append(hlib.node(selection))
            root.add_attr(long_name="drivenGraphs", attribute_type="message", multi=True)
        indices = cmds.getAttr(root.full_name() + ".drivenGraphs", multiIndices=True) or []
        owner.plug("message").connect(
            root.plug("drivenGraphs[{}]".format(max(indices, default=-1) + 1))
        )
        indices = cmds.getAttr(root.full_name() + ".hrigOwned", multiIndices=True) or []
        for index, node in enumerate(owned, max(indices, default=-1) + 1):
            node.plug("message").connect(root.plug("hrigOwned[{}]".format(index)))
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
