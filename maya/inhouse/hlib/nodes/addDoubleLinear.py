"""距離型の2入力を加算する。"""
from .._core.registry import node_wrapper
from .._core.coerce import to_plug
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ._calculation import _Calculation
from .node import Node


@node_wrapper("addDoubleLinear")
class AddDoubleLinear(Node):
    """距離型の2入力を加算する。"""

    def input_plug(self, index):
        """入力のPlugを取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug(f"input{_Calculation.index(index, (1, 2))}")

    def get_input(self, index):
        """入力の評価値を取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            float: 現在の値。
        """
        return self.input_plug(index).get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_input(self, index, value, *, fast=False):
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
        value = _Calculation.scalar(value)
        self.input_plug(index).set(value)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_input(self, index, source, force=False):
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
        to_plug(source).connect(self.input_plug(index), force=force)
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
            float: 計算結果。
        """
        return self.output_plug().get()
