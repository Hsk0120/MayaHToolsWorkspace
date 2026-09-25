"""行列を配列の順番で乗算するmultMatrixを扱う。"""

from ..decorators._fast import fast_edit

from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
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
        return index

    @fast_edit
    @undo_chunk("hlibMultMatrixSetInput")
    def set_input(self, index, value, *, fast=False):
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
        """
        index = self._index(index)
        value = Matrix(value)
        self.plug("matrixIn").element(index, create=True).set(value)
        return self

    @undo_chunk("hlibMultMatrixConnectInput")
    def connect_input(self, index, source, force=False):
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
        source.connect(self.plug("matrixIn").element(index, create=True), force=force)
        return self

    def output(self):
        """MatrixPlug: matrixSum出力。別ノードへの接続に使用する。"""
        return self.plug("matrixSum")

    def result(self):
        """Matrix: 現在の入力を乗算した評価済み行列。"""
        return self.output().get()
