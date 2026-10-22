"""XYZ各成分を旧範囲から新範囲へ線形変換する。"""

from .._core.flags import flag_aliases
from ..common._fast import fast_edit
from ..decorator import undoChunk
from ..maths import Vector
from ._calculation import _Calculation
from .node import Node


class SetRange(Node):
    """XYZ各成分を旧範囲から新範囲へ線形変換する。"""

    @fast_edit
    @undoChunk("mlibCalculationEdit")
    def setInput(self, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            SetRange: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.getPlug, 'value')
        return self

    def getRange(self):
        """現在の範囲を取得する。
        Returns:
            dict[str, tuple]: 各成分の上下限。
        """
        return {key: tuple(self.getPlug(attr).get()) for key, attr in (('input_min', 'oldMin'), ('input_max', 'oldMax'), ('output_min', 'min'), ('output_max', 'max'))}

    @fast_edit
    @undoChunk("mlibCalculationEdit")
    def setRange(self, input_min, input_max, output_min, output_max, *, fast=False):
        """各成分の範囲をまとめて設定する。

        Args:
            input_min (Iterable[float]): XYZ/RGB順の有限な3要素。
            input_max (Iterable[float]): XYZ/RGB順の有限な3要素。
            output_min (Iterable[float]): XYZ/RGB順の有限な3要素。
            output_max (Iterable[float]): XYZ/RGB順の有限な3要素。
            fast (bool): TrueはUndoなし。
        Returns:
            SetRange: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        values = [_Calculation.vector(value) for value in (input_min, input_max, output_min, output_max)]
        for attr, value in zip(('oldMin', 'oldMax', 'min', 'max'), values):
            self.getPlug(attr).set(value)
        return self

    def getResult(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            Vector: 計算結果。
        """
        return Vector(self.getPlug('outValue').get())
