"""RGB各成分を指定範囲に制限する。"""

from .._core.flags import flag_aliases
from ..common._fast import fast_edit
from ..decorator import undoChunk
from ..maths import Vector
from ._calculation import _Calculation
from .node import Node


class Clamp(Node):
    """RGB各成分を指定範囲に制限する。"""

    @fast_edit
    @undoChunk("mlibCalculationEdit")
    def setInput(self, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            Clamp: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.getPlug, 'input')
        return self

    def getRange(self):
        """現在の範囲を取得する。
        Returns:
            dict[str, tuple]: 各成分の上下限。
        """
        return {key: tuple(self.getPlug(attr).get()) for key, attr in (('min', 'min'), ('max', 'max'))}

    @fast_edit
    @undoChunk("mlibCalculationEdit")
    def setRange(self, min, max, *, fast=False):
        """各成分の範囲をまとめて設定する。

        Args:
            min (Iterable[float]): XYZ/RGB順の有限な3要素。
            max (Iterable[float]): XYZ/RGB順の有限な3要素。
            fast (bool): TrueはUndoなし。
        Returns:
            Clamp: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        values = [_Calculation.vector(value) for value in (min, max)]
        for attr, value in zip(('min', 'max'), values):
            self.getPlug(attr).set(value)
        return self

    def getResult(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            Vector: 計算結果。
        """
        return Vector(self.getPlug('output').get())
