"""XYZ各成分の1-inputを計算する。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ..maths import Vector
from ._calculation import _Calculation
from .node import Node


@node_wrapper("reverse")
class Reverse(Node):
    """XYZ各成分の1-inputを計算する。"""

    def inputPlug(self):
        """入力のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('input')

    def getInput(self):
        """入力の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.inputPlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def setInput(self, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            Reverse: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.inputPlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectInput(self, source, force=False):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            Reverse: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.inputPlug, force=force)
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
            Vector: 計算結果。
        """
        return Vector(self.outputPlug().get())
