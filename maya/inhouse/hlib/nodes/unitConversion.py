"""Mayaの単位変換係数を扱う。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ._calculation import _Calculation
from .node import Node


@node_wrapper("unitConversion")
class UnitConversion(Node):
    """Mayaの単位変換係数を扱う。"""

    def inputPlug(self):
        """入力のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("input")

    def getInput(self):
        """入力の評価値を取得する。
        Returns:
            float: 現在の値。
        """
        return self.inputPlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def setInput(self, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            value (float): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            UnitConversion: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.scalar, self.inputPlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectInput(self, source, force=False):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            UnitConversion: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.inputPlug, force=force)
        return self

    def factorPlug(self):
        """変換係数のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("conversionFactor")

    def getFactor(self):
        """変換係数の評価値を取得する。
        Returns:
            float: 現在の値。
        """
        return self.factorPlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def setFactor(self, value, *, fast=False):
        """変換係数へ定数値を設定する。

        Args:
            value (float): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            UnitConversion: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.scalar, self.factorPlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectFactor(self, source, force=False):
        """変換係数へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            UnitConversion: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.factorPlug, force=force)
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
