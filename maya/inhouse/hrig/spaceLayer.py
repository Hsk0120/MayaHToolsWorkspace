"""IKとポールの参照空間を管理する、LODから独立した操作レイヤー。"""

import hlib

from hrig.setups import SpaceSwitch
from hlib.decorators.undo import undoTransaction


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
        root = self.rig.root.fullName()
        for node in nodes:
            hlib.getNode(root).plug("hrigOwned").appendMessage(node)
        members = [
            node.fullName() for node in nodes if node.fullName() != self.rig._member("spaceSet")
        ]
        if members:
            self.rig._layer_members("spaceSet", members)

    @undoTransaction("hrig.SpaceLayer.attach")
    def attach(self):
        """IK Local/World、Pole Local/World/Footの空間切替を追加する。"""
        if self.rig.root.hasAttr("targetSpace"):
            return
        layer_set = hlib.createSet(empty=True, name=self.rig.nodeName("spaceSet")).fullName()
        self.rig._bind("spaceSet", layer_set)
        self.rig._layer_members("moduleSet", [layer_set])
        self._own([hlib.getNode(layer_set)])
        for role in ("target", "pole"):
            offset = hlib.getNode(self.rig._member(role + "Offset"))
            parent = offset.parent()
            buffer = hlib.createNode(
                "transform", name=self.rig.nodeName(role + "Space"), parent=parent, skipSelect=True
            )
            offset.setParent(buffer, relative=True)
            switch = SpaceSwitch.create(buffer)
            switch.add("local", parent)
            switch.add("world")
            if role == "pole":
                switch.add("foot", self.rig._member("target"))
            self.rig._bind(role + "Space", buffer.fullName())
            self._own(switch.nodes())
            control = hlib.getNode(self.rig._member(role))
            control.addAttr(
                longName="space", attributeType="enum", enumName=":".join(switch.labels())
            )
            control.setAttributeFlags(["space"], keyable=False, channelBox=True)
            from .limb import _lock_group

            _lock_group(buffer)
        # 既存のtargetローカル合成へ空間レイヤー分だけ追加する。
        # worldMatrixへ置換せず、リバースフットやSoft IKへ部位空間で渡す。
        hlib.getPlug(self.rig._member("targetSpace") + ".offsetParentMatrix").connectTo(
            self.rig._member("targetMatrix") + ".matrixIn[2]"
        )

    @undoTransaction("hrig.SpaceLayer.add")
    def add(self, control, label, target=None):
        """任意ノードを参照空間へ追加する。Noneはワールドを表す。

        Args:
            control (str): ikまたはpole。
            label (str): 空間名（英数字とアンダースコア）。
            target (str | Node | None): 参照先のtransform。
        """
        switch = self.switcher(control)
        if target is not None:
            path = hlib.getNode(target).fullName()
            # IKソルバーの内部依存は通常のDG入力列挙だけでは検出できない。
            # この部位の変形結果と計算用階層を、操作空間の入力には使わない。
            for role in ("moduleJoints", "moduleSetup"):
                parent = self.rig._member(role)
                if path == parent or path.startswith(parent + "|"):
                    raise ValueError("Rig output cannot drive its own control space")
        switch.add(label, target)
        self._own([switch.nodes()[-1]])
        node = self.rig._member(self._role(control))
        hlib.getPlug(node + ".space").setEnumNames(switch.labels())

    @undoTransaction("hrig.SpaceLayer.switch")
    def switch(self, control, label):
        """姿勢とコントローラーのチャンネルを保持して参照空間を変更する。

        Args:
            control (str): ikまたはpole。
            label (str): 登録済み空間名。
        """
        node = hlib.getNode(self.rig._member(self._role(control)))
        if node.plug("space").sourceWithConversion() is not None:
            raise ValueError("Space is a configuration attribute; remove keys or connections")
        switch = self.switcher(control)
        switch.switch(label)
        node.plug("space").setIfChanged(switch.labels().index(switch.current()))

    def sync(self):
        """適用済みの空間をチャンネル表示へ反映する。"""
        for role in ("target", "pole"):
            switch = self.switcher(role)
            hlib.getPlug(self.rig._member(role) + ".space").setIfChanged(
                switch.labels().index(switch.current())
            )
