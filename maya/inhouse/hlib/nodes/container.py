"""Maya containerによる計算ノードの所有管理。"""

from maya import cmds
from .._core.registry import node_wrapper
from ..decorators.undo import undo_transaction, undo_chunk
from .node import Node


@node_wrapper("container")
class Container(Node):
    """削除・保存を一括管理するDGノードの所有単位。"""

    @classmethod
    @undo_transaction("hlib.Container.create")
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
            Node(n) for n in (cmds.container(self.full_name(), query=True, nodeList=True) or [])
        ]

    @undo_chunk("hlib.Container.add")
    def add(self, *nodes):
        """指定ノードを所有下へ追加する。別containerからは強制移動しない。

        Args:
            *nodes (str | Node): 所有するノード。

        Returns:
            Container: 自身。
        """
        if nodes:
            cmds.container(
                self.full_name(), edit=True, addNode=[Node(n).full_name() for n in nodes]
            )
        return self

    @undo_transaction("hlib.Container.create_node")
    def create_node(self, kind, name=None):
        """標準ノードを生成し所有下へまとめる。

        Args:
            kind (str): Maya nodeType。
            name (str | None): 希望名。省略時はcontainer名に型名を付加。

        Returns:
            Node: 作成したノード。
        """
        node = Node.create(kind, name=name or self.name() + "_" + kind, skipSelect=True)
        self.add(node)
        return node
