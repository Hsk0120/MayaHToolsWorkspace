"""配列入力の加算・減算・平均を計算する。"""

from .._core.flags import flag_aliases
from .._core.registry import node_wrapper
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from ._calculation import _Calculation
from .shadingDependNode import ShadingDependNode


@node_wrapper("plusMinusAverage")
class PlusMinusAverage(ShadingDependNode):
    """配列入力の加算・減算・平均を計算する。"""

    def getOperation(self):
        """現在のモード名を取得する。
        Returns:
            str: none, sum, subtract, average。
        """
        return _Calculation.enumName(self.getPlug("operation"), ('none', 'sum', 'subtract', 'average'))

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setOperation(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): none, sum, subtract, average、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            PlusMinusAverage: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enumValue(mode, ('none', 'sum', 'subtract', 'average'))
        self.getPlug("operation").set(value)
        return self

    def getInputIndices(self, dimension=1):
        """既存の入力番号を取得する。

        Args:
            dimension (int): 1/2/3。
        Returns:
            list[int]: 疎な論理番号。
        """
        return list(self._input_array(dimension).mplug().getExistingArrayAttributeIndices())

    @flag_aliases(idx="index")
    def getInputPlug(self, index, dimension=1):
        """既存の入力を参照する。

        Args:
            index (int): 非負の論理番号。 別名 ``idx`` も使用可能。
            dimension (int): 1/2/3。
        Returns:
            Plug: 未作成要素はIndexError。
        """
        plug = self._input_array(dimension)[_Calculation.index(index)]
        if index not in self.getInputIndices(dimension):
            raise IndexError(f"No input at logical index {index}")
        return plug

    @flag_aliases(idx="index")
    def getInput(self, index, dimension=1):
        """入力の評価値を取得する。

        Args:
            index (int): 既存の論理番号。 別名 ``idx`` も使用可能。
            dimension (int): 1/2/3。
        Returns:
            float | tuple: 入力値。
        """
        return self.getInputPlug(index, dimension).get()

    @flag_aliases(idx="index")
    @undoChunk("hlibCalculationEdit")
    def setInput(self, index, value, dimension=1):
        """指定番号に入力値を設定する。

        Args:
            index (int): 非負の論理番号。 別名 ``idx`` も使用可能。
            value (float | Iterable[float]): 入力値。
            dimension (int): 1/2/3。
        Returns:
            PlusMinusAverage: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        index = _Calculation.index(index)
        array = self._input_array(dimension)
        value = _Calculation.scalar(value) if dimension == 1 else _Calculation.vector(value, dimension)
        array[index].set(value)
        return self

    @flag_aliases(idx="index", src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectInput(self, index, source, dimension=1, force=False):
        """指定番号に接続する。

        Args:
            index (int): 非負の論理番号。 別名 ``idx`` も使用可能。
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            dimension (int): 1/2/3。
            force (bool): 既存入力を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            PlusMinusAverage: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        from ..plugs.plug import Plug as _InputPlug
        source = _InputPlug._resolve_input(source)
        target = self._input_array(dimension)[_Calculation.index(index)]
        source.connectTo(target, force=force)
        return self

    @flag_aliases(idx="index")
    @undoChunk("hlibCalculationEdit")
    def removeInput(self, index, dimension=1):
        """入力要素とその接続を削除する。

        Args:
            index (int): 既存番号。 別名 ``idx`` も使用可能。
            dimension (int): 1/2/3。
        Returns:
            PlusMinusAverage: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        self._input_array(dimension).removeElement(_Calculation.index(index))
        return self

    def getOutputPlug(self, dimension=1):
        """出力Plugを取得する。

        Args:
            dimension (int): 1/2/3。
        Returns:
            Plug: 出力参照。
        """
        return self.getPlug("output%dD" % _Calculation.index(dimension, (1, 2, 3)))

    def getResult(self, dimension=1):
        """演算結果を取得する。

        Args:
            dimension (int): 1/2/3。
        Returns:
            float | tuple: 評価済み出力。
        """
        return self.getOutputPlug(dimension).get()

    def _input_array(self, dimension):
        """入力配列を取得する。

        Args:
            dimension (int): 1/2/3。
        Returns:
            ArrayPlug: 入力配列。
        """
        return self.getPlug("input%dD" % _Calculation.index(dimension, (1, 2, 3)))
