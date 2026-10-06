"""2値の比較により出力を切り替える。"""

from .._core.flags import flag_aliases
from .._core.registry import node_wrapper
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from ..maths import Vector
from ._calculation import _Calculation
from .node import Node


@node_wrapper("condition")
class Condition(Node):
    """2値の比較により出力を切り替える。"""

    def getOperation(self):
        """現在のモード名を取得する。
        Returns:
            str: equal, not_equal, greater, greater_equal, less, less_equal。
        """
        return _Calculation.enumName(self.getPlug("operation"), ('equal', 'not_equal', 'greater', 'greater_equal', 'less', 'less_equal'))

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setOperation(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): equal, not_equal, greater, greater_equal, less, less_equal、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            Condition: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enumValue(mode, ('equal', 'not_equal', 'greater', 'greater_equal', 'less', 'less_equal'))
        self.getPlug("operation").set(value)
        return self

    @flag_aliases(idx="index")
    def getInputPlug(self, index):
        """入力のPlugを取得する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("firstTerm" if _Calculation.index(index, (1, 2)) == 1 else "secondTerm")

    @flag_aliases(idx="index")
    def getInput(self, index):
        """入力の評価値を取得する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
        Returns:
            float: 現在の値。
        """
        return self.getInputPlug(index).get()

    @flag_aliases(idx="index")
    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setInput(self, index, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            value (float): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            Condition: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.scalar, self.getInputPlug, index)
        return self

    @flag_aliases(idx="index", src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectInput(self, index, source, force=False):
        """入力へ接続する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            Condition: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getInputPlug, index, force=force)
        return self

    def getTrueValuePlug(self):
        """条件成立時のRGB値のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("colorIfTrue")

    def getTrueValue(self):
        """条件成立時のRGB値の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getTrueValuePlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setTrueValue(self, value, *, fast=False):
        """条件成立時のRGB値へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            Condition: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.getTrueValuePlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectTrueValue(self, source, force=False):
        """条件成立時のRGB値へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            Condition: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getTrueValuePlug, force=force)
        return self

    def getFalseValuePlug(self):
        """条件不成立時のRGB値のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("colorIfFalse")

    def getFalseValue(self):
        """条件不成立時のRGB値の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getFalseValuePlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setFalseValue(self, value, *, fast=False):
        """条件不成立時のRGB値へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            Condition: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.getFalseValuePlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectFalseValue(self, source, force=False):
        """条件不成立時のRGB値へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            Condition: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getFalseValuePlug, force=force)
        return self

    def getOutputPlug(self):
        """計算結果の接続用Plugを取得する。
        Returns:
            Plug: 出力参照。
        """
        return self.getPlug("outColor")

    def getResult(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            Vector: 計算結果。
        """
        return Vector(self.getOutputPlug().get())
