"""Mayaの単位変換係数を扱う。"""

from .._core.flags import flag_aliases
from ..common._fast import fast_edit
from ..decorator import undoChunk
from ._calculation import _Calculation
from .node import Node


class UnitConversion(Node):
    """Mayaの単位変換係数を扱う。"""

    @fast_edit
    @undoChunk("mlibCalculationEdit")
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
        _Calculation.set_value(value, _Calculation.scalar, self.getPlug, "input")
        return self

    @fast_edit
    @undoChunk("mlibCalculationEdit")
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
        _Calculation.set_value(value, _Calculation.scalar, self.getPlug, "conversionFactor")
        return self
