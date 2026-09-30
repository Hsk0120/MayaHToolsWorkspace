"""個別の16要素から行列を構築する。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ..maths import Matrix
from .node import Node


@node_wrapper("fourByFourMatrix")
class FourByFourMatrix(Node):
    """個別の16要素から行列を構築する。"""

    def get_matrix(self):
        """16要素の入力行列を取得する。
        Returns:
            Matrix: 入力値。
        """
        return Matrix([self.plug("in%d%d" % (r, c)).get() for r in range(4) for c in range(4)])

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_matrix(self, value, *, fast=False):
        """16要素をまとめて設定する。

        Args:
            value (Matrix | Iterable[float]): 行列。
            fast (bool): TrueはUndoなし。
        Returns:
            FourByFourMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = Matrix(value)
        for r in range(4):
            for c in range(4):
                self.plug("in%d%d" % (r, c)).set(value[r * 4 + c])
        return self

    def output_plug(self):
        """計算結果の接続用Plugを取得する。
        Returns:
            Plug: 出力参照。
        """
        return self.plug("output")

    def result(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            Matrix: 計算結果。
        """
        return Matrix(self.output_plug().get())
