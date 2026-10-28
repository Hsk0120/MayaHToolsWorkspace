"""指定の生成先へ標準scalar演算を構築する。"""

from ..decorator import _edit_context
from ..nodes.container import Container
from ..plugs.plug import Plug


class ScalarGraph:
    """定数とPlugを組み合わせる単位なし数値グラフのビルダー。

    各構築メソッドの通常経路は一つのUndoチャンクにまとめ、例外時は巻戻しを試みる。
    ``fast=True`` は生成関数へ ``fast=True`` を渡して作成し、値の設定と接続をOpenMayaで
    直接行う(Undoなし・途中失敗の巻戻しなし)。containerを所有先にした場合は
    Container.createNodeがfastを持たないため、fast=Trueは変更前にNotImplementedErrorとする。
    """

    def __init__(self, container=None, *, createNode=None):
        """containerまたは生成関数のどちらか一方を保持する。

        Args:
            container (str | Container | None): 演算ノードの所有先。
            createNode (Callable | None): (node_type, name=...)を受け取りNodeを返す生成関数。
                構築メソッドへfast=Trueを渡す場合は、キーワード ``fast=True`` も受け取る必要がある
                (例: ``mlib.createNode``)。

        Raises:
            TypeError: createNodeが呼び出せない値の場合。
            ValueError: containerとcreateNodeを両方指定した、またはどちらも指定しない場合。
        """
        if (container is None) == (createNode is None):
            raise ValueError("Specify exactly one of 'container' and 'createNode'")
        if createNode is not None and not callable(createNode):
            raise TypeError("createNode must be callable")
        self.container = Container(container) if container is not None else None
        self._createNode = self.container.createNode if self.container is not None else createNode

    def sum(self, role, left, right, subtract=False, *, fast=False):
        """加減算を構築する。

        Args:
            role (str): 演算名。
            left (float | str | Plug): 左辺。
            right (float | str | Plug): 右辺。
            subtract (bool): Trueなら減算。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug: 改名に追従する出力プラグ。

        Raises:
            TypeError: fastがbool以外の場合。
            NotImplementedError: containerを所有先にしてfast=Trueを指定した場合。
        """
        with self._edit("mlibScalarGraphSum", fast):
            node = self._node("plusMinusAverage", role, fast)
            node.getPlug("operation").set(2 if subtract else 1, fast=fast)
            self._feed(left, node.getPlug("input1D")[0], fast)
            self._feed(right, node.getPlug("input1D")[1], fast)
            return node.getPlug("output1D")

    def multiply(self, role, left, right, operation=1, *, fast=False):
        """乗除算・累乗を構築する。

        Args:
            role (str): 演算名。
            left (float | str | Plug): 左辺。
            right (float | str | Plug): 右辺。
            operation (int): 1は乗算、2は除算、3は累乗。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug: 改名に追従する出力プラグ。

        Raises:
            TypeError: fastがbool以外の場合。
            NotImplementedError: containerを所有先にしてfast=Trueを指定した場合。
        """
        with self._edit("mlibScalarGraphMultiply", fast):
            node = self._node("multiplyDivide", role, fast)
            node.getPlug("operation").set(operation, fast=fast)
            self._feed(left, node.getPlug("input1X"), fast)
            self._feed(right, node.getPlug("input2X"), fast)
            return node.getPlug("outputX")

    def condition(self, role, left, right, yes, no, *, fast=False):
        """大小比較によって値を選択する。

        Args:
            role (str): 演算名。
            left (float | str | Plug): 比較の左辺。
            right (float | str | Plug): 比較の右辺。
            yes (float | str | Plug): 左辺が右辺より大きい場合の値。
            no (float | str | Plug): それ以外の値。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Plug: 改名に追従する出力プラグ。

        Raises:
            TypeError: fastがbool以外の場合。
            NotImplementedError: containerを所有先にしてfast=Trueを指定した場合。
        """
        with self._edit("mlibScalarGraphCondition", fast):
            node = self._node("condition", role, fast)
            node.getPlug("operation").set(2, fast=fast)
            for value, attr in (
                (left, "firstTerm"),
                (right, "secondTerm"),
                (yes, "colorIfTrueR"),
                (no, "colorIfFalseR"),
            ):
                self._feed(value, node.getPlug(attr), fast)
            return node.getPlug("outColorR")

    def _edit(self, name, fast):
        """fastを検証し、構築全体のUndo範囲を返す。

        Args:
            name (str): 通常経路のUndoチャンク名。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            contextlib.AbstractContextManager: 通常はundoTransaction、fastはnullcontext。

        Raises:
            TypeError: fastがbool以外の場合。
            NotImplementedError: containerを所有先にしてfast=Trueを指定した場合。
        """
        # 構築途中の失敗を巻き戻すため、通常経路はUndo無効時に拒否するundoTransactionを使う。
        context = _edit_context(name, fast, transaction=True)
        if fast and self.container is not None:
            raise NotImplementedError("fast=True is not supported when the owner is a container")
        return context

    def _node(self, kind, role, fast=False):
        """設定した生成先へ演算ノードを作成する。

        Args:
            kind (str): 標準ノード型。
            role (str): 演算の識別名。
            fast (bool): Trueは生成関数へ ``fast=True`` を渡す。Falseは従来どおり渡さない。

        Returns:
            Node: 作成したノード。
        """
        prefix = self.container.getName() + "_" if self.container is not None else ""
        if fast:
            return self._createNode(kind, name=prefix + role, fast=True)
        return self._createNode(kind, name=prefix + role)

    @staticmethod
    def _feed(value, destination, fast=False):
        """入力へ定数を設定するかプラグを接続する。

        Args:
            value (float | str | Plug): 定数または入力プラグ名。
            destination (Plug | str): 接続先アトリビュート。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            None: 値を返さない。
        """
        destination = Plug._resolve_input(destination)
        if isinstance(value, (str, Plug)):
            Plug._resolve_input(value).connectTo(destination, fast=fast)
        else:
            destination.set(value, fast=fast)
