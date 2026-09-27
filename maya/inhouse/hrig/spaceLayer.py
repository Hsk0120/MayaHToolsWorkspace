"""IKとポールの参照空間を管理する、LODから独立した操作レイヤー。"""

from maya import cmds

import hlib
from hlib.animation import SpaceSwitch
from hlib.decorators.undo import undo_transaction


class SpaceLayer:
    """汎用SpaceSwitchを部位の所有関係とチャンネル操作へ接続する。"""

    def __init__(self, rig):
        """対象部位を保持する。

        Args:
            rig (LimbRig): 操作対象。
        """
        self.rig = rig

    @staticmethod
    def _role(control):
        """公開ロールを内部ロールへ変換する。

        Args:
            control (str): ikまたはpole（targetも許可）。

        Returns:
            str: targetまたはpole。
        """
        if control not in ("ik", "target", "pole"):
            raise ValueError("Expected ik or pole")
        return "target" if control == "ik" else control

    def switcher(self, control):
        """保存済みの汎用空間切替を取得する。

        Args:
            control (str): ikまたはpole。

        Returns:
            SpaceSwitch: 対象コントローラーの切替。
        """
        return SpaceSwitch(self.rig._member(self._role(control) + "Space"))

    def _own(self, nodes):
        """生成ノードを部位とレイヤー選択セットへ登録する。

        Args:
            nodes (Sequence[Node]): 所有する生成物。外部参照先は含めない。
        """
        root = self.rig.root.full_name()
        indices = cmds.getAttr(root + ".hrigOwned", multiIndices=True) or []
        for index, node in enumerate(nodes, max(indices, default=-1) + 1):
            node.plug("message").connect(root + ".hrigOwned[{}]".format(index))
        members = [
            node.full_name() for node in nodes if node.full_name() != self.rig._member("spaceSet")
        ]
        if members:
            self.rig._layer_members("spaceSet", members)

    @undo_transaction("hrig.SpaceLayer.attach")
    def attach(self):
        """IK Local/World、Pole Local/World/Footの空間切替を追加する。"""
        if self.rig.root.has_attr("targetSpace"):
            return
        layer_set = cmds.sets(empty=True, name=self.rig.node_name("spaceSet"))
        self.rig._bind("spaceSet", layer_set)
        self.rig._layer_members("moduleSet", [layer_set])
        self._own([hlib.node(layer_set)])
        for role in ("target", "pole"):
            offset = hlib.node(self.rig._member(role + "Offset"))
            parent = offset.parent_node()
            buffer = hlib.createNode(
                "transform", name=self.rig.node_name(role + "Space"), parent=parent, skipSelect=True
            )
            offset.set_parent(buffer, relative=True)
            switch = SpaceSwitch.create(buffer)
            switch.add("local", parent)
            switch.add("world")
            if role == "pole":
                switch.add("foot", self.rig._member("target"))
            self.rig._bind(role + "Space", buffer.full_name())
            self._own(switch.nodes())
            control = hlib.node(self.rig._member(role))
            control.add_attr(
                long_name="space", attribute_type="enum", enumName=":".join(switch.labels())
            )
            control.set_attr_flags(["space"], keyable=False, channel_box=True)
            from .limb import _lock_group

            _lock_group(buffer)
        # 既存のtargetローカル合成へ空間レイヤー分だけ追加する。
        # worldMatrixへ置換せず、リバースフットやSoft IKへ部位空間で渡す。
        hlib.plug(self.rig._member("targetSpace") + ".offsetParentMatrix").connect(
            self.rig._member("targetMatrix") + ".matrixIn[2]"
        )

    @undo_transaction("hrig.SpaceLayer.add")
    def add(self, control, label, target=None):
        """任意ノードを参照空間へ追加する。Noneはワールドを表す。

        Args:
            control (str): ikまたはpole。
            label (str): 空間名（英数字とアンダースコア）。
            target (str | Node | None): 参照先のtransform。
        """
        switch = self.switcher(control)
        if target is not None:
            path = hlib.node(target).full_name()
            # IKソルバーの内部依存は通常のDG入力列挙だけでは検出できない。
            # この部位の変形結果と計算用階層を、操作空間の入力には使わない。
            for role in ("moduleJoints", "moduleSetup"):
                parent = self.rig._member(role)
                if path == parent or path.startswith(parent + "|"):
                    raise ValueError("Rig output cannot drive its own control space")
        switch.add(label, target)
        self._own([switch.nodes()[-1]])
        node = self.rig._member(self._role(control))
        cmds.addAttr(node + ".space", edit=True, enumName=":".join(switch.labels()))

    @undo_transaction("hrig.SpaceLayer.switch")
    def switch(self, control, label):
        """姿勢とコントローラーのチャンネルを保持して参照空間を変更する。

        Args:
            control (str): ikまたはpole。
            label (str): 登録済み空間名。
        """
        node = hlib.node(self.rig._member(self._role(control)))
        if node.plug("space").source() is not None:
            raise ValueError("Space is a configuration attribute; remove keys or connections")
        switch = self.switcher(control)
        switch.switch(label)
        node.plug("space").set_if_changed(switch.labels().index(switch.current()))

    def sync(self):
        """適用済みの空間をチャンネル表示へ反映する。"""
        for role in ("target", "pole"):
            switch = self.switcher(role)
            hlib.plug(self.rig._member(role) + ".space").set_if_changed(
                switch.labels().index(switch.current())
            )
