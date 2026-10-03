"""逆行列を計算する。Maya付属matrixNodesの明示的なロードが必要。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undoChunk
from ..decorators._fast import fast_edit
from ..maths import Matrix
from .THdependNode import THDependNode


@node_wrapper("inverseMatrix")
class InverseMatrix(THDependNode):
    """逆行列を計算する。Maya付属matrixNodesの明示的なロードが必要。"""

    def inputPlug(self):
        """入力のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("inputMatrix")

    def getInput(self):
        """入力の評価値を取得する。
        Returns:
            Matrix: 現在の値。
        """
        return self.inputPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setInput(self, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            value (Matrix): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            InverseMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = Matrix(value)
        self.inputPlug().set(value)
        return self

    @undoChunk("hlibCalculationEdit")
    def connectInput(self, source, force=False):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            InverseMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        from ..plugs.plug import Plug as _InputPlug
        _InputPlug._resolve_input(source).connect(self.inputPlug(), force=force)
        return self

    def outputPlug(self):
        """計算結果の接続用Plugを取得する。
        Returns:
            Plug: 出力参照。
        """
        return self.plug("outputMatrix")

    def result(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            Matrix: 計算結果。
        """
        return Matrix(self.outputPlug().get())
