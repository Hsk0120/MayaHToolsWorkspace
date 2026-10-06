"""Mayaの単位変換係数を扱う。"""

from .._core.flags import flag_aliases
from .._core.registry import node_wrapper
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from ._calculation import _Calculation
from .node import Node


@node_wrapper("unitConversion")
class UnitConversion(Node):
    """Mayaの単位変換係数を扱う。"""

    def getInputPlug(self):
        """入力のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("input")

    def getInput(self):
        """入力の評価値を取得する。
        Returns:
            float: 現在の値。
        """
        return self.getInputPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
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
        _Calculation.set_value(value, _Calculation.scalar, self.getInputPlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectInput(self, source, force=False):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            UnitConversion: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getInputPlug, force=force)
        return self

    def getFactorPlug(self):
        """変換係数のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("conversionFactor")

    def getFactor(self):
        """変換係数の評価値を取得する。
        Returns:
            float: 現在の値。
        """
        return self.getFactorPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
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
        _Calculation.set_value(value, _Calculation.scalar, self.getFactorPlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectFactor(self, source, force=False):
        """変換係数へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            UnitConversion: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getFactorPlug, force=force)
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
            float: 計算結果。
        """
        return self.getOutputPlug().get()
