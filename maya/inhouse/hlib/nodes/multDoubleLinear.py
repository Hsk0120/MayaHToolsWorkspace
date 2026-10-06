"""距離型の2入力を乗算する。"""

from .._core.flags import flag_aliases
from .._core.registry import node_wrapper
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from ._calculation import _Calculation
from .node import Node


@node_wrapper("multDoubleLinear")
class MultDoubleLinear(Node):
    """距離型の2入力を乗算する。"""

    @flag_aliases(idx="index")
    def getInputPlug(self, index):
        """入力のPlugを取得する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug(f"input{_Calculation.index(index, (1, 2))}")

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
            MultDoubleLinear: 自身。

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
            MultDoubleLinear: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getInputPlug, index, force=force)
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
