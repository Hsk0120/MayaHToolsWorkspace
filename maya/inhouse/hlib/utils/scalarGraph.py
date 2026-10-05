"""指定の生成先へ標準scalar演算を構築する。"""

from ..decorators.undo import undoTransaction
from ..nodes.container import Container
from ..plugs.plug import Plug


class ScalarGraph:
    """定数とPlugを組み合わせる単位なし数値グラフのビルダー。"""

    def __init__(self, container=None, *, create_node=None):
        """containerまたは生成関数のどちらか一方を保持する。

        Args:
            container (str | Container | None): 演算ノードの所有先。
            create_node (Callable | None): (node_type, name=...)を受け取りNodeを返す生成関数。
        """
        if (container is None) == (create_node is None):
            raise ValueError("containerかcreate_nodeのどちらか一方を指定してください。")
        if create_node is not None and not callable(create_node):
            raise TypeError("create_nodeは呼出可能な生成関数を指定してください。")
        self.container = Container(container) if container is not None else None
        self._createNode = self.container.createNode if self.container is not None else create_node

    @undoTransaction("hlib.ScalarGraph.sum")
    def sum(self, role, left, right, subtract=False):
        """加減算を構築する。

        Args:
            role (str): 演算名。
            left (float | str | Plug): 左辺。
            right (float | str | Plug): 右辺。
            subtract (bool): Trueなら減算。

        Returns:
            Plug: 改名に追従する出力プラグ。
        """
        node = self._node("plusMinusAverage", role)
        node.plug("operation").set(2 if subtract else 1)
        self._feed(left, node.plug("input1D[0]"))
        self._feed(right, node.plug("input1D[1]"))
        return node.plug("output1D")

    @undoTransaction("hlib.ScalarGraph.multiply")
    def multiply(self, role, left, right, operation=1):
        """乗除算・累乗を構築する。

        Args:
            role (str): 演算名。
            left (float | str | Plug): 左辺。
            right (float | str | Plug): 右辺。
            operation (int): 1は乗算、2は除算、3は累乗。

        Returns:
            Plug: 改名に追従する出力プラグ。
        """
        node = self._node("multiplyDivide", role)
        node.plug("operation").set(operation)
        self._feed(left, node.plug("input1X"))
        self._feed(right, node.plug("input2X"))
        return node.plug("outputX")

    @undoTransaction("hlib.ScalarGraph.condition")
    def condition(self, role, left, right, yes, no):
        """大小比較によって値を選択する。

        Args:
            role (str): 演算名。
            left (float | str | Plug): 比較の左辺。
            right (float | str | Plug): 比較の右辺。
            yes (float | str | Plug): 左辺が右辺より大きい場合の値。
            no (float | str | Plug): それ以外の値。

        Returns:
            Plug: 改名に追従する出力プラグ。
        """
        node = self._node("condition", role)
        node.plug("operation").set(2)
        for value, attr in (
            (left, "firstTerm"),
            (right, "secondTerm"),
            (yes, "colorIfTrueR"),
            (no, "colorIfFalseR"),
        ):
            self._feed(value, node.plug(attr))
        return node.plug("outColorR")

    def _node(self, kind, role):
        """設定した生成先へ演算ノードを作成する。

        Args:
            kind (str): 標準ノード型。
            role (str): 演算の識別名。

        Returns:
            Node: 作成したノード。
        """
        prefix = self.container.name() + "_" if self.container is not None else ""
        return self._createNode(kind, name=prefix + role)

    @staticmethod
    def _feed(value, destination):
        """入力へ定数を設定するかプラグを接続する。

        Args:
            value (float | str | Plug): 定数または入力プラグ名。
            destination (Plug | str): 接続先アトリビュート。
        """
        destination = Plug._resolve_input(destination)
        if isinstance(value, (str, Plug)):
            Plug._resolve_input(value).connectTo(destination)
        else:
            destination.set(value)
