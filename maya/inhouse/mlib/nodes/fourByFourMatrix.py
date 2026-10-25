"""個別の16要素からマトリクスを構築する。"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..maths import Matrix
from .node import Node


class FourByFourMatrix(Node):
    """fourByFourMatrixノードを参照し、16入力からマトリクスを評価する。

    値設定は入力接続を切断しない。通常設定はUndo有効時に一つのチャンクへ記録する。
    fast=TrueはUndoなしのOM2直接更新で、Undo設定は変えない。途中失敗の変更は自動で戻さない。
    """

    def getMatrix(self):
        """16要素の入力マトリクスを取得する。

        Returns:
            Matrix: 入力値。
        """
        return Matrix([self.getPlug("in%d%d" % (r, c)).get() for r in range(4) for c in range(4)])

    def setMatrix(self, value, *, fast=False):
        """マトリクスの16要素を、行優先で各入力Plugへ順に設定する。

        Args:
            value (Matrix | Iterable[float]): マトリクス。
            fast (bool): TrueはUndoなし。

        Returns:
            FourByFourMatrix: 自身。途中の失敗でも先に設定した要素は残る。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            value = Matrix(value)
            for r in range(4):
                for c in range(4):
                    self.getPlug("in%d%d" % (r, c)).set(value[r * 4 + c], fast=fast)
            return self

    def getOutputPlug(self):
        """計算結果の接続用Plugを取得する。

        Returns:
            Plug: 出力参照。
        """
        return self.getPlug("output")

    def getResult(self):
        """現在の入力をMayaで評価した結果を取得する。

        Returns:
            Matrix: 計算結果。
        """
        return Matrix(self.getOutputPlug().get())
