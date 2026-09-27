"""所有containerへ標準scalar演算を構築する。"""

from hlib.nodes.container import Container
from hlib.plugs.plug import Plug
from hlib._core.coerce import to_plug
from hlib.decorators.undo import undo_transaction


class ScalarGraph:
    """定数とPlugを組み合わせる単位なし数値グラフのビルダー。"""

    def __init__(self, container):
        """既存containerを保持する。

        Args:
            container (str | Container): 演算ノードの所有先。
        """
        self.container = Container(container)

    def _node(self, kind, role):
        """演算ノードを作成し、削除・保存用のcontainerへ登録する。

        Args:
            kind (str): 標準ノード型。
            role (str): 演算の識別名。

        Returns:
            str: 作成したノード名。
        """
        node = self.container.create_node(kind, name=self.container.name() + "_" + role).full_name()
        return node

    @staticmethod
    def _feed(value, destination):
        """入力へ定数を設定するかプラグを接続する。

        Args:
            value (float | str | Plug): 定数または入力プラグ名。
            destination (str): 接続先プラグ名。
        """
        if isinstance(value, (str, Plug)):
            to_plug(value).connect(destination)
        else:
            to_plug(destination).set(value)

    @undo_transaction("hlib.ScalarGraph.sum")
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
        to_plug(node + ".operation").set(2 if subtract else 1)
        self._feed(left, node + ".input1D[0]")
        self._feed(right, node + ".input1D[1]")
        return to_plug(node + ".output1D")

    @undo_transaction("hlib.ScalarGraph.multiply")
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
        to_plug(node + ".operation").set(operation)
        self._feed(left, node + ".input1X")
        self._feed(right, node + ".input2X")
        return to_plug(node + ".outputX")

    @undo_transaction("hlib.ScalarGraph.condition")
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
        to_plug(node + ".operation").set(2)
        for value, attr in (
            (left, "firstTerm"),
            (right, "secondTerm"),
            (yes, "colorIfTrueR"),
            (no, "colorIfFalseR"),
        ):
            self._feed(value, node + "." + attr)
        return to_plug(node + ".outColorR")
