"""距離型の2入力を加算する。"""

from .._core.flags import flag_aliases
from ..common._fast import fast_edit
from ..decorator import undoChunk
from ._calculation import _Calculation
from .node import Node


class AddDoubleLinear(Node):
    """距離型の2入力を加算する。"""

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
    @fast_edit
    @undoChunk("mlibCalculationEdit")
    def setInput(self, index, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            value (float): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            AddDoubleLinear: 自身。

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
            AddDoubleLinear: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getInputPlug, index, force=force)
        return self
