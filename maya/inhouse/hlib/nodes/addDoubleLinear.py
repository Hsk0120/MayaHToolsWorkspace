"""距離型の2入力を加算する。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ._calculation import _Calculation
from .node import Node


@node_wrapper("addDoubleLinear")
class AddDoubleLinear(Node):
    """距離型の2入力を加算する。"""

    def inputPlug(self, index):
        """入力のPlugを取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug(f"input{_Calculation.index(index, (1, 2))}")

    def getInput(self, index):
        """入力の評価値を取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            float: 現在の値。
        """
        return self.inputPlug(index).get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def setInput(self, index, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。
            value (float): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AddDoubleLinear: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.scalar, self.inputPlug, index)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectInput(self, index, source, force=False):
        """入力へ接続する。

        Args:
            index (int): 入力番号1または2。
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AddDoubleLinear: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.inputPlug, index, force=force)
        return self

    def outputPlug(self):
        """計算結果の接続用Plugを取得する。
        Returns:
            Plug: 出力参照。
        """
        return self.plug("output")

    def result(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            float: 計算結果。
        """
        return self.outputPlug().get()
