"""2値の比較により出力を切り替える。"""

from .._core.flags import flag_aliases
from ..common._fast import fast_edit
from ..decorator import undoChunk
from ..maths import Vector
from ._calculation import _Calculation
from .node import Node


class Condition(Node):
    """2値の比較により出力を切り替える。"""

    def getOperation(self):
        """現在のモード名を取得する。

        Returns:
            str: equal, not_equal, greater, greater_equal, less, less_equal。
        """
        return _Calculation.enum_name(self.getPlug("operation"), ("equal", "not_equal", "greater", "greater_equal", "less", "less_equal"))

    @fast_edit
    @undoChunk("mlibCalculationEdit")
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
        value = _Calculation.enum_value(mode, ("equal", "not_equal", "greater", "greater_equal", "less", "less_equal"))
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
    @fast_edit
    @undoChunk("mlibCalculationEdit")
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
    @undoChunk("mlibCalculationEdit")
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

    @fast_edit
    @undoChunk("mlibCalculationEdit")
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
        _Calculation.set_value(value, _Calculation.vector, self.getPlug, "colorIfTrue")
        return self

    @fast_edit
    @undoChunk("mlibCalculationEdit")
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
        _Calculation.set_value(value, _Calculation.vector, self.getPlug, "colorIfFalse")
        return self

    def getResult(self):
        """現在の入力をMayaで評価した結果を取得する。

        Returns:
            Vector: 計算結果。
        """
        return Vector(self.getPlug("outColor").get())
