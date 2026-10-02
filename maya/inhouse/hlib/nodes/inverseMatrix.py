"""逆行列を計算する。Maya付属matrixNodesの明示的なロードが必要。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ..maths import Matrix
from .THdependNode import THDependNode


@node_wrapper("inverseMatrix")
class InverseMatrix(THDependNode):
    """逆行列を計算する。Maya付属matrixNodesの明示的なロードが必要。"""

    def input_plug(self):
        """入力のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("inputMatrix")

    def get_input(self):
        """入力の評価値を取得する。
        Returns:
            Matrix: 現在の値。
        """
        return self.input_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_input(self, value, *, fast=False):
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
        self.input_plug().set(value)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_input(self, source, force=False):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            InverseMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        from hlib.plugs.plug import Plug as _InputPlug
        _InputPlug._resolve_input(source).connect(self.input_plug(), force=force)
        return self

    def output_plug(self):
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
        return Matrix(self.output_plug().get())
