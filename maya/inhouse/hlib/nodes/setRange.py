"""XYZ各成分を旧範囲から新範囲へ線形変換する。"""

from .._core.flags import flag_aliases
from .._core.registry import node_wrapper
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from ..maths import Vector
from ._calculation import _Calculation
from .node import Node


@node_wrapper("setRange")
class SetRange(Node):
    """XYZ各成分を旧範囲から新範囲へ線形変換する。"""

    def getInputPlug(self):
        """入力のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug('value')

    def getInput(self):
        """入力の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getInputPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
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
        _Calculation.set_value(value, _Calculation.vector, self.getInputPlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectInput(self, source, force=False):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            SetRange: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getInputPlug, force=force)
        return self

    def getRange(self):
        """現在の範囲を取得する。
        Returns:
            dict[str, tuple]: 各成分の上下限。
        """
        return {key: tuple(self.getPlug(attr).get()) for key, attr in (('input_min', 'oldMin'), ('input_max', 'oldMax'), ('output_min', 'min'), ('output_max', 'max'))}

    @fast_edit
    @undoChunk("hlibCalculationEdit")
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

    def getOutputPlug(self):
        """計算結果の接続用Plugを取得する。
        Returns:
            Plug: 出力参照。
        """
        return self.getPlug("outValue")

    def getResult(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            Vector: 計算結果。
        """
        return Vector(self.getOutputPlug().get())
