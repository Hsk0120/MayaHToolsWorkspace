"""Maya containerによる計算ノードの所有管理。"""

from maya import cmds
from .._core.registry import node_wrapper
from ..decorators.undo import undoTransaction, undoChunk
from .node import Node


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

    @undoChunk("hlib.Container.add")
    def addMembers(self, *members):
        """指定ノードを所有下へ追加する。別containerからは強制移動しない。

        Args:
            *members (str | Node | Iterable[Node | str]): 所有するノード。

        Returns:
            Container: 自身。
        """
        from hlib.object import Object as _InputObject
        nodes = [Node(name) for name in _InputObject._input_names(members, allow_plugs=False)]
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
