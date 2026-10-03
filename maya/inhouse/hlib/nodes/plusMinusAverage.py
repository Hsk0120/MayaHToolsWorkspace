"""配列入力の加算・減算・平均を計算する。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
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
        return _Calculation.enumName(self.plug("operation"), ('none', 'sum', 'subtract', 'average'))

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
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
        self.plug("operation").set(value)
        return self

    def _input_array(self, dimension):
        """入力配列を取得する。

        Args:
            dimension (int): 1/2/3。
        Returns:
            ArrayPlug: 入力配列。
        """
        return self.plug("input%dD" % _Calculation.index(dimension, (1, 2, 3)))

    def inputIndices(self, dimension=1):
        """既存の入力番号を取得する。

        Args:
            dimension (int): 1/2/3。
        Returns:
            list[int]: 疎な論理番号。
        """
        return list(self._input_array(dimension).mplug().getExistingArrayAttributeIndices())

    def inputPlug(self, index, dimension=1):
        """既存の入力を参照する。

        Args:
            index (int): 非負の論理番号。
            dimension (int): 1/2/3。
        Returns:
            Plug: 未作成要素はIndexError。
        """
        return self._input_array(dimension).element(_Calculation.index(index))

    def getInput(self, index, dimension=1):
        """入力の評価値を取得する。

        Args:
            index (int): 既存の論理番号。
            dimension (int): 1/2/3。
        Returns:
            float | tuple: 入力値。
        """
        return self.inputPlug(index, dimension).get()

    @undo_chunk("hlibCalculationEdit")
    def setInput(self, index, value, dimension=1):
        """指定番号に入力値を設定する。

        Args:
            index (int): 非負の論理番号。
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
        array.element(index, create=True).set(value)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectInput(self, index, source, dimension=1, force=False):
        """指定番号に接続する。

        Args:
            index (int): 非負の論理番号。
            source (Plug | str | MPlug): 接続元。
            dimension (int): 1/2/3。
            force (bool): 既存入力を置き換えるか。
        Returns:
            PlusMinusAverage: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        from hlib.plugs.plug import Plug as _InputPlug
        source = _InputPlug._resolve_input(source)
        target = self._input_array(dimension).element(_Calculation.index(index), create=True)
        source.connect(target, force=force)
        return self

    @undo_chunk("hlibCalculationEdit")
    def removeInput(self, index, dimension=1):
        """入力要素とその接続を削除する。

        Args:
            index (int): 既存番号。
            dimension (int): 1/2/3。
        Returns:
            PlusMinusAverage: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        self._input_array(dimension).removeElement(_Calculation.index(index))
        return self

    def outputPlug(self, dimension=1):
        """出力Plugを取得する。

        Args:
            dimension (int): 1/2/3。
        Returns:
            Plug: 出力参照。
        """
        return self.plug("output%dD" % _Calculation.index(dimension, (1, 2, 3)))

    def result(self, dimension=1):
        """演算結果を取得する。

        Args:
            dimension (int): 1/2/3。
        Returns:
            float | tuple: 評価済み出力。
        """
        return self.outputPlug(dimension).get()
