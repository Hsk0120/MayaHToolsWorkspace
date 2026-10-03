"""行列を配列の順番で乗算するmultMatrixを扱う。"""

from ..decorators._fast import fast_edit

from .._core.registry import node_wrapper
from ..decorators.undo import undoChunk
from ..maths import Matrix
from .node import Node


@node_wrapper("multMatrix")
class MultMatrix(Node):
    """matrixInの論理インデックス順に行列を乗算する。"""

    @staticmethod
    def _index(index):
        """非負の整数インデックスを検証する。不正値はValueError。"""
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("Matrix index must be a non-negative integer")
        from ..plugs.arrayPlug import ArrayPlug
        return ArrayPlug._validate_index(index)

    def inputPlug(self, index):
        """既存入力のPlugを取得する。未存在要素は作成しない。

        Args:
            index (int): 非負の論理インデックス。
        Returns:
            Plug: 入力アトリビュートの参照。
        Raises:
            ValueError: indexが非負整数でない場合。
            IndexError: 指定した入力要素が存在しない、または番号が範囲外の場合。
        """
        return self.plug("matrixIn").element(self._index(index))

    def getInput(self, index):
        """既存入力の評価値を取得する。接続済みなら接続元を評価する。

        Args:
            index (int): 入力の論理インデックス。
        Returns:
            Matrix: 現在の入力値。
        Raises:
            IndexError: 入力要素が存在しない場合。
        """
        return self.inputPlug(index).get()

    @fast_edit
    @undoChunk("hlibMultMatrixSetInput")
    def setInput(self, index, value, *, fast=False):
        """指定スロットに定数行列を設定する。入力接続は切断しない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            index (int): 非負の論理インデックス。
            value (Matrix | Iterable[float]): Maya規約の行列。

        Returns:
            MultMatrix: 自身。

        Raises:
            ValueError: インデックスや行列が不正な場合。
            RuntimeError: ロックや入力接続により設定できない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        index = self._index(index)
        value = Matrix(value)
        self.plug("matrixIn")._element_reference(index).set(value)
        return self

    @undoChunk("hlibMultMatrixConnectInput")
    def connectInput(self, index, source, force=False):
        """行列Plugを指定スロットへ接続する。

        Args:
            index (int): 非負の論理インデックス。
            source (Plug): 接続元の行列Plug。
            force (bool): 既存入力を置き換えるか。

        Returns:
            MultMatrix: 自身。

        Raises:
            ValueError: インデックスが不正な場合。
            RuntimeError: 型不一致などでMayaが接続を拒否した場合。
        """
        index = self._index(index)
        from ..plugs.plug import Plug
        source = Plug._resolve_input(source)
        source.connect(self.plug("matrixIn")._element_reference(index), force=force)
        return self

    def outputPlug(self):
        """MatrixPlug: matrixSum出力。別ノードへの接続に使用する。"""
        return self.plug("matrixSum")

    def result(self):
        """Matrix: 現在の入力を乗算した評価済み行列。"""
        return self.outputPlug().get()
