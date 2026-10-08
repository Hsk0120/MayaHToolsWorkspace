"""指・Aimの小規模モジュールに共通の所有と評価管理。"""

from maya import cmds

from functools import partial
import re

import hlib
from hlib.decorator import undoTransaction


class ControlRig:
    """標準ノードの出力をEnabled/LODで切断するモジュール基盤。"""

    _jobs = {}

    def __init__(self, root):
        """保存済みルートを保持する。

        Args:
            root (str | Node): モジュールルート。
        """
        self.root = hlib.getNode(root)
        if not self.root.hasAttr("hrigControlDefinition"):
            raise ValueError("Not a control module")

    @classmethod
    def _create(cls, name, kind):
        """共通階層を作る。呼出側のUndo内で使用する。

        Args:
            name (str): 一意名。
            kind (str): finger/aim。

        Returns:
            ControlRig: 作成したルートの参照。
        """
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or [
            item.getName() for item in hlib.ls(name + "*")
        ]:
            raise ValueError("Use a unique module name")
        root = hlib.createNode("transform", name=name, skipSelect=True)
        root.addAttr(longName="hrigControlDefinition", dataType="string").set(
            hlib.json.JsonText.dumps(dict(kind=kind))
        )
        root.addAttr(longName="lod", attributeType="enum", enumName="Low:Full", defaultValue=1)
        root.addAttr(longName="enabled", attributeType="bool", defaultValue=True)
        root.setAttrFlags(["lod", "enabled"], channelBox=True)
        root.addAttr(longName="angles", attributeType="doubleAngle", multi=True)
        for attr in ("controls", "deform", "sources", "targets"):
            root.addAttr(longName=attr, attributeType="message", multi=True)
        for role in ("control", "deform", "layer"):
            node = hlib.createNode(
                "transform", name=name + "_" + role + "_grp", parent=root, skipSelect=True
            )
            root.addAttr(longName=role + "Group", attributeType="message")
            node.getPlug("message").connectTo(root.getPlug(role + "Group"))
        root.addAttr(longName="graph", attributeType="message")
        hlib.nodes.Container.create(name=name + "_graph").getPlug("message").connectTo(
            root.getPlug("graph")
        )
        return cls(root)

    def kind(self):
        """保存した機能種別を取得する。

        Returns:
            str: finger/aim。
        """
        return hlib.json.JsonText.loads(self.root.getPlug("hrigControlDefinition").get())["kind"]

    def group(self, role):
        """用途別グループを取得する。

        Args:
            role (str): control/deform/layer。

        Returns:
            Node: グループ。
        """
        return self.root.getPlug(role + "Group").getSourceWithConversion().getNode()

    def register(self, attr, node):
        """配列の末尾へ参照を保存する。

        Args:
            attr (str): message配列名。
            node (Node): 登録対象。
        """
        self.root.getPlug(attr).appendMessage(node)

    def getMembers(self, attr):
        """登録順にノードを取得する。

        Args:
            attr (str): 配列名。

        Returns:
            list[Node]: 登録ノード。
        """
        return list(self.root.getPlug(attr).getSourceNodes().values())

    def own(self, node):
        """DGノードの寿命をモジュールにまとめる。

        Args:
            node (Node): 所有ノード。
        """
        hlib.nodes.Container(self.root.getPlug("graph").getSourceWithConversion().getNode()).addMembers(node)

    def getJoints(self):
        """変形骨とTweak骨を取得する。

        Returns:
            tuple[str]: スキン対象。
        """
        from .tweakLayer import TweakLayer

        return tuple(n.getFullName() for n in self.getMembers("deform")) + TweakLayer(self).getJoints()

    def lod(self):
        """LOD値を取得する。

        Returns:
            int: Low=0/Full=1。
        """
        return self.root.getPlug("lod").get()

    def layer_enabled(self, layer):
        """機能の使用設定を取得する。

        Args:
            layer (str): モジュールのkind。

        Returns:
            bool: 使用設定。
        """
        if layer != self.kind():
            raise ValueError("Unknown layer")
        return bool(self.root.getPlug("enabled").get())

    @undoTransaction("hrig.ControlRig.enabled")
    def set_layer_enabled(self, layer, enabled):
        """レイヤーを切り替える。

        Args:
            layer (str): 機能種別。
            enabled (bool): 使用設定。
        """
        self.layer_enabled(layer)
        self.root.getPlug("enabled").set(bool(enabled))
        self.update()

    @undoTransaction("hrig.ControlRig.lod")
    def set_lod(self, value):
        """LODを切り替える。

        Args:
            value (int): 0/1。
        """
        if value not in (0, 1):
            raise ValueError("Use lod 0/1")
        self.root.getPlug("lod").set(value)
        self.update()

    @undoTransaction("hrig.ControlRig.update")
    def update(self):
        """重ねる回転のみを停止し、手付けFKを維持する。"""
        active = self.lod() == 1 and self.layer_enabled(self.kind())
        for index, (source, target) in enumerate(
            zip(self.getMembers("sources"), self.getMembers("targets"))
        ):
            for axis_index, axis in enumerate("XYZ"):
                output = (
                    self.root.getPlug("angles")[index * 3 + axis_index]
                    if self.kind() == "finger"
                    else source.getPlug("constraintRotate" + axis)
                )
                destination = target.getPlug("rotate" + axis)
                previous = destination.getSourceWithConversion()
                if active and previous is None:
                    output.connectTo(destination)
                elif not active and previous is not None:
                    destination.disconnect(previous)
                    destination.set(0)
            source.getPlug("nodeState").setIfChanged(0 if active else 2)
        from .tweakLayer import TweakLayer

        TweakLayer(self).update()

    @classmethod
    def refresh_jobs(cls):
        """保存読込とUndo後に属性監視を復元する。"""
        if cmds.about(batch=True):
            return
        for key, jobs in list(cls._jobs.items()):
            if not [item.getName() for item in hlib.ls(key)] or not jobs.exists():
                jobs.stop()
                del cls._jobs[key]
        for attr in [
            item.getFullName() for item in hlib.ls("*.hrigControlDefinition", recursive=True)
        ] or []:
            rig = cls(attr.rsplit(".", 1)[0])
            key = rig.root.getUuid()
            if key in cls._jobs:
                continue
            jobs = hlib.common.ScriptJobs()
            for name in ("lod", "enabled"):
                jobs.add(
                    name,
                    attribute=rig.root.getPlug(name),
                    callback=partial(cls._changed, key),
                    kill_with_scene=True,
                    compress_undo=True,
                )
            cls._jobs[key] = jobs

    @classmethod
    def _changed(cls, key):
        """接続状態に差があるときだけ変更する。

        Args:
            key (str): ルートUUID。
        """
        names = [item.getFullName() for item in hlib.ls(key, long=True)] or []
        if names:
            rig = cls(names[0])
            active = rig.lod() == 1 and rig.layer_enabled(rig.kind())
            if any(bool(n.getPlug("rotateX").getSourceWithConversion()) != active for n in rig.getMembers("targets")):
                rig.update()

    @undoTransaction("hrig.ControlRig.delete")
    def delete(self):
        """スキン未使用のモジュールを所有DGとともに削除する。"""
        if any(hlib.getNode(j).getConnections(type="skinCluster") for j in self.getJoints()):
            raise ValueError("Unbind before deleting")
        hlib.delete(self.root.getPlug("graph").getSourceWithConversion().getNode())
        hlib.delete(self.root)
