"""Maya containerによる計算ノードの所有管理。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorator import _flag_aliases, undoTransaction
from ..plugs.plug import Plug
from .node import Node, Nodes


class Container(Node):
    """削除・保存を一括管理するDGノードの所有単位。"""

    @classmethod
    @undoTransaction("mlib.Container.create")
    def create(cls, name="container"):
        """空の所有containerを作成する。

        Args:
            name (str): 希望名。衝突時はMayaが一意名にする。

        Returns:
            Container: 新しい所有ノード。
        """
        return cls(cmds.container(name=name))

    def getMembers(self):
        """直接所属するノードを取得する。

        Returns:
            list[Node]: メンバー。入出力の接続先は自動で含めない。
        """
        return [Node(obj) for obj in om2.MFnContainerNode(self.mnode()).getMembers()]

    @undoTransaction("mlib.Container.add")
    def addMembers(self, *members):
        """指定ノードを所有下へ追加する。別containerからは強制移動しない。

        Args:
            *members (str | Node | Iterable[Node | str]): 所有するノード。

        Returns:
            Container: 自身。
        """
        nodes = Nodes._resolve_inputs(members)
        if nodes:
            cmds.container(
                self.getFullName(), edit=True, addNode=[Node(n).getFullName() for n in nodes]
            )
        return self

    @_flag_aliases(f="force")
    @undoTransaction("mlib.Container.removeMembers")
    def removeMembers(self, *members, force=False):
        """所属だけを解除する。ネスト時は通常、親containerの所属へ移る。

        Args:
            *members (Node | str | Iterable[Node]): 解除するメンバー。
            force (bool): Trueなら全containerから解除する。ロック解除ではない。 別名 ``f`` も使用可能。

        Returns:
            Container: 自身。
        """
        nodes = [Node(node) for node in Nodes._resolve_inputs(members)]
        current = self.getMembers()
        if any(node not in current for node in nodes):
            raise ValueError("このcontainerに所属していないノードが含まれています。")
        if nodes:
            cmds.container(self.getFullName(), edit=True,
                           removeNode=[node.getFullName() for node in nodes], force=force)
        return self

    @undoTransaction("mlib.Container.createNode")
    def createNode(self, type, name=None):
        """標準ノードを生成し所有下へまとめる。

        Args:
            type (str): Maya nodeType。
            name (str | None): 希望名。省略時はcontainer名に型名を付加。

        Returns:
            Node: 作成したノード。
        """
        node = Node.create(type, name=name or self.getName() + "_" + type, skipSelect=True)
        self.addMembers(node)
        return node

    @undoTransaction("mlib.Container.removeContainer")
    def removeContainer(self):
        """メンバーを残して自身を解除する。自身のアトリビュートの接続は失われる。

        出力の迂回接続や設定の移送は行わない。通常のdeleteとは異なる。
        """
        # removeContainer単独では未接続のDGメンバーも削除される版がある。
        # 所属を先に外し、メンバーの生存を保証してから空の箱を除去する。
        members = self.getMembers()
        if members:
            cmds.container(self.getFullName(), edit=True,
                           removeNode=[node.getFullName() for node in members])
        cmds.container(self.getFullName(), edit=True, removeContainer=True)

    @undoTransaction("mlib.Container.publishName")
    def publishName(self, name):
        """未Bindの公開名を作る。

        Args:
            name (str): 希望する公開名。

        Returns:
            str: 作成した公開名。
        """
        if name in self.getPublishedAttrs():
            raise ValueError("既に公開されている名前です: " + name)
        result = cmds.container(self.getFullName(), edit=True, publishName=name)
        return result[0] if isinstance(result, (list, tuple)) else result

    def getPublishedAttrs(self):
        """公開名と対応する内部アトリビュートを取得する。

        Returns:
            dict[str, Plug | None]: 未Bind名はNone。公開ノードのアンカーは対象外。
        """
        fn = om2.MFnContainerNode(self.mnode())
        result = dict.fromkeys(fn.getPublishedNames(False))
        plugs, names = fn.getPublishedPlugs()
        for plug, name in zip(plugs, names):
            result[name] = Plug._resolve_input(plug)
        return result

    @undoTransaction("mlib.Container.bindAttribute")
    def bindAttr(self, name, plug):
        """未Bindの公開名を内部アトリビュートへ対応付ける。

        Args:
            name (str): 既存の未Bind公開名。
            plug (Plug | str): 内部アトリビュート。

        Returns:
            Plug: 対応付けた内部アトリビュート。
        """
        published = self.getPublishedAttrs()
        if name not in published or published[name] is not None:
            raise ValueError("未Bindの公開名を指定してください: " + name)
        plug = Plug._resolve_input(plug)
        if plug.getNode() not in self.getMembers():
            raise ValueError("所属ノードのアトリビュートを指定してください。")
        cmds.container(self.getFullName(), edit=True, bindAttr=(plug.getFullName(), name))
        return plug

    @undoTransaction("mlib.Container.publishAndBind")
    def publishAndBind(self, name, plug):
        """公開名の作成とBindを一括で行う。

        Args:
            name (str): 新しい公開名。
            plug (Plug | str): 内部アトリビュート。

        Returns:
            Plug: 対応付けた内部アトリビュート。
        """
        if name in self.getPublishedAttrs():
            raise ValueError("既に公開されている名前です: " + name)
        plug = Plug._resolve_input(plug)
        if plug.getNode() not in self.getMembers():
            raise ValueError("所属ノードのアトリビュートを指定してください。")
        cmds.container(self.getFullName(), edit=True, publishAndBind=(plug.getFullName(), name))
        return plug

    @undoTransaction("mlib.Container.unbindAttribute")
    def unbindAttr(self, name):
        """対応付けだけを解除し、公開名を残す。

        Args:
            name (str): Bind済みの公開名。
        """
        plug = self.getPublishedAttrs().get(name)
        if plug is None:
            raise ValueError("Bind済みの公開名を指定してください: " + name)
        cmds.container(self.getFullName(), edit=True, unbindAttr=(plug.getFullName(), name))

    @undoTransaction("mlib.Container.unpublishName")
    def unpublishName(self, name):
        """未Bindの公開名を削除する。

        Args:
            name (str): 未Bindの公開名。
        """
        published = self.getPublishedAttrs()
        if name not in published or published[name] is not None:
            raise ValueError("未Bindの公開名を指定してください: " + name)
        cmds.container(self.getFullName(), edit=True, unpublishName=name)
