"""XYZ成分ごとの乗算・除算・累乗。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ..maths import Vector
from ._calculation import _Calculation
from .shadingDependNode import ShadingDependNode


@node_wrapper("multiplyDivide")
class MultiplyDivide(ShadingDependNode):
    """XYZ成分ごとの乗算・除算・累乗。"""

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
            Iterable[float]: 現在の値。
        """
        return self.inputPlug(index).get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def setInput(self, index, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            MultiplyDivide: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.inputPlug, index)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectInput(self, index, source, force=False):
        """入力へ接続する。

        Args:
            index (int): 入力番号1または2。
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            MultiplyDivide: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.inputPlug, index, force=force)
        return self

    def getOperation(self):
        """現在のモード名を取得する。
        Returns:
            str: none, multiply, divide, power。
        """
        return _Calculation.enumName(self.plug("operation"), ('none', 'multiply', 'divide', 'power'))

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def setOperation(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): none, multiply, divide, power、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            MultiplyDivide: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enumValue(mode, ('none', 'multiply', 'divide', 'power'))
        self.plug("operation").set(value)
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
