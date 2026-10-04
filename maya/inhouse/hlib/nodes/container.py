"""Maya containerによる計算ノードの所有管理。"""

import maya.cmds as cmds

from .._core.registry import node_wrapper
from ..decorators.undo import undoTransaction
from ..plugs.plug import Plug
from .node import Node, Nodes


@node_wrapper("container")
class Container(Node):
    """削除・保存を一括管理するDGノードの所有単位。"""

    @classmethod
    @undoTransaction("hlib.Container.create")
    def create(cls, name="container"):
        """空の所有containerを作成する。

        Args:
            name (str): 希望名。衝突時はMayaが一意名にする。

        Returns:
            Container: 新しい所有ノード。
        """
        return cls(cmds.container(name=name))

    def members(self):
        """直接所属するノードを取得する。

        Returns:
            list[Node]: メンバー。入出力の接続先は自動で含めない。
        """
        return [
            Node(n) for n in (cmds.container(self.fullName(), query=True, nodeList=True) or [])
        ]

    @undoTransaction("hlib.Container.add")
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
                self.fullName(), edit=True, addNode=[Node(n).fullName() for n in nodes]
            )
        return self

    @undoTransaction("hlib.Container.createNode")
    def createNode(self, type, name=None):
        """標準ノードを生成し所有下へまとめる。

        Args:
            type (str): Maya nodeType。
            name (str | None): 希望名。省略時はcontainer名に型名を付加。

        Returns:
            Node: 作成したノード。
        """
        node = Node.create(type, name=name or self.name() + "_" + type, skipSelect=True)
        self.addMembers(node)
        return node

    @undoTransaction("hlib.Container.removeMembers")
    def removeMembers(self, *members, force=False):
        """所属だけを解除する。ネスト時は通常、親containerの所属へ移る。

        Args:
            *members (Node | str | Iterable[Node]): 解除するメンバー。
            force (bool): Trueなら全containerから解除する。ロック解除ではない。

        Returns:
            Container: 自身。
        """
        nodes = [Node(node) for node in Nodes._resolve_inputs(members)]
        current = self.members()
        if any(node not in current for node in nodes):
            raise ValueError("このcontainerに所属していないノードが含まれています。")
        if nodes:
            cmds.container(self.fullName(), edit=True,
                           removeNode=[node.fullName() for node in nodes], force=force)
        return self

    @undoTransaction("hlib.Container.removeContainer")
    def removeContainer(self):
        """メンバーを残して自身を解除する。自身のアトリビュートの接続は失われる。

        出力の迂回接続や設定の移送は行わない。通常のdeleteとは異なる。
        """
        # removeContainer単独では未接続のDGメンバーも削除される版がある。
        # 所属を先に外し、メンバーの生存を保証してから空の箱を除去する。
        members = self.members()
        if members:
            cmds.container(self.fullName(), edit=True,
                           removeNode=[node.fullName() for node in members])
        cmds.container(self.fullName(), edit=True, removeContainer=True)

    @undoTransaction("hlib.Container.publishName")
    def publishName(self, name):
        """未Bindの公開名を作る。

        Args:
            name (str): 希望する公開名。

        Returns:
            str: 作成した公開名。
        """
        if name in self.publishedAttributes():
            raise ValueError("既に公開されている名前です: " + name)
        result = cmds.container(self.fullName(), edit=True, publishName=name)
        return result[0] if isinstance(result, (list, tuple)) else result

    def publishedAttributes(self):
        """公開名と対応する内部アトリビュートを取得する。

        Returns:
            dict[str, Plug | None]: 未Bind名はNone。公開ノードのアンカーは対象外。
        """
        names = cmds.container(self.fullName(), query=True, publishName=True) or []
        result = dict.fromkeys(names)
        pairs = cmds.container(self.fullName(), query=True, bindAttr=True) or []
        for attribute, name in zip(pairs[::2], pairs[1::2]):
            result[name] = Plug._resolve_input(attribute)
        return result

    @undoTransaction("hlib.Container.bindAttribute")
    def bindAttribute(self, name, plug):
        """未Bindの公開名を内部アトリビュートへ対応付ける。

        Args:
            name (str): 既存の未Bind公開名。
            plug (Plug | str): 内部アトリビュート。

        Returns:
            Plug: 対応付けた内部アトリビュート。
        """
        published = self.publishedAttributes()
        if name not in published or published[name] is not None:
            raise ValueError("未Bindの公開名を指定してください: " + name)
        plug = Plug._resolve_input(plug)
        if plug.node not in self.members():
            raise ValueError("所属ノードのアトリビュートを指定してください。")
        cmds.container(self.fullName(), edit=True, bindAttr=(plug.fullName(), name))
        return plug

    @undoTransaction("hlib.Container.publishAndBind")
    def publishAndBind(self, name, plug):
        """公開名の作成とBindを一括で行う。

        Args:
            name (str): 新しい公開名。
            plug (Plug | str): 内部アトリビュート。

        Returns:
            Plug: 対応付けた内部アトリビュート。
        """
        if name in self.publishedAttributes():
            raise ValueError("既に公開されている名前です: " + name)
        plug = Plug._resolve_input(plug)
        if plug.node not in self.members():
            raise ValueError("所属ノードのアトリビュートを指定してください。")
        cmds.container(self.fullName(), edit=True, publishAndBind=(plug.fullName(), name))
        return plug

    @undoTransaction("hlib.Container.unbindAttribute")
    def unbindAttribute(self, name):
        """対応付けだけを解除し、公開名を残す。

        Args:
            name (str): Bind済みの公開名。
        """
        plug = self.publishedAttributes().get(name)
        if plug is None:
            raise ValueError("Bind済みの公開名を指定してください: " + name)
        cmds.container(self.fullName(), edit=True, unbindAttr=(plug.fullName(), name))

    @undoTransaction("hlib.Container.unpublishName")
    def unpublishName(self, name):
        """未Bindの公開名を削除する。

        Args:
            name (str): 未Bindの公開名。
        """
        published = self.publishedAttributes()
        if name not in published or published[name] is not None:
            raise ValueError("未Bindの公開名を指定してください: " + name)
        cmds.container(self.fullName(), edit=True, unpublishName=name)
