"""個別の16要素から行列を構築する。"""

from .._core.getterAlias import _getter_alias
from ..common._fast import fast_edit
from ..decorator import undoChunk
from ..maths import Matrix
from .node import Node


class FourByFourMatrix(Node):
    """個別の16要素から行列を構築する。"""

    def getMatrix(self):
        """16要素の入力行列を取得する。
        Returns:
            Matrix: 入力値。
        """
        return Matrix([self.getPlug("in%d%d" % (r, c)).get() for r in range(4) for c in range(4)])

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setMatrix(self, value, *, fast=False):
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
                self.getPlug("in%d%d" % (r, c)).set(value[r * 4 + c])
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

    @_getter_alias(getMatrix)
    def matrix(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getMatrix(*args, **kwargs)

    @_getter_alias(getOutputPlug)
    def outputPlug(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOutputPlug(*args, **kwargs)

    @_getter_alias(getResult)
    def result(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getResult(*args, **kwargs)
