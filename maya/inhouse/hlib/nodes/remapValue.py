"""ランプで値を再マッピングする。色ランプも操作できる。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ._calculation import _Calculation
from .node import Node


@node_wrapper("remapValue")
class RemapValue(Node):
    """ランプで値を再マッピングする。色ランプも操作できる。"""

    def inputPlug(self):
        """入力のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("inputValue")

    def getInput(self):
        """入力の評価値を取得する。
        Returns:
            float: 現在の値。
        """
        return self.inputPlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def setInput(self, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            value (float): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            RemapValue: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.scalar, self.inputPlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectInput(self, source, force=False):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            RemapValue: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.inputPlug, force=force)
        return self

    def getRange(self):
        """入出力範囲を取得する。
        Returns:
            dict[str, float]: 入出力の上下限。
        """
        return {key: self.plug(attr).get() for key, attr in (("input_min", "inputMin"), ("input_max", "inputMax"), ("output_min", "outputMin"), ("output_max", "outputMax"))}

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def setRange(self, input_min, input_max, output_min, output_max, *, fast=False):
        """入出力範囲を設定する。

        Args:
            input_min (float): 有限な境界値。
            input_max (float): 有限な境界値。
            output_min (float): 有限な境界値。
            output_max (float): 有限な境界値。
            fast (bool): TrueはUndoなし。
        Returns:
            RemapValue: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        values = [_Calculation.scalar(v) for v in (input_min, input_max, output_min, output_max)]
        for attr, value in zip(("inputMin", "inputMax", "outputMin", "outputMax"), values):
            self.plug(attr).set(value)
        return self

    def _ramp_array(self, kind):
        """ランプ配列を取得する。

        Args:
            kind (str): value/color。
        Returns:
            ArrayPlug: ランプの参照。
        """
        if kind not in ("value", "color"):
            raise ValueError("kind must be value or color")
        return self.plug(kind)

    def rampPoints(self, kind="value"):
        """ランプの既存点を取得する。

        Args:
            kind (str): value/color。
        Returns:
            dict[int, dict]: 論理番号ごとのposition/value/interpolation。
        """
        array = self._ramp_array(kind)
        result = {}
        for index in array.mplug().getExistingArrayAttributeIndices():
            point = array.element(index)
            result[index] = {"position": point.child(0).get(), "value": point.child(1).get(), "interpolation": point.child(2).get()}
        return result

    @undo_chunk("hlibCalculationEdit")
    def setRampPoint(self, index, position, value, interpolation="linear", kind="value"):
        """指定番号のランプ点を追加または編集する。

        Args:
            index (int): 非負の論理番号。
            position (float): 0～1。
            value (float | Iterable[float]): 値またはRGB。
            interpolation (str | int): none/linear/smooth/splineまたは0～3。
            kind (str): value/color。
        Returns:
            RemapValue: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        index = _Calculation.index(index)
        array = self._ramp_array(kind)
        position = _Calculation.scalar(position)
        if not 0 <= position <= 1:
            raise ValueError("position must be in 0..1")
        value = _Calculation.scalar(value) if kind == "value" else _Calculation.vector(value)
        mode = _Calculation.enumValue(interpolation, ("none", "linear", "smooth", "spline"))
        point = array.element(index, create=True)
        point.child(0).set(position)
        point.child(1).set(value)
        point.child(2).set(mode)
        return self

    @undo_chunk("hlibCalculationEdit")
    def removeRampPoint(self, index, kind="value"):
        """指定したランプ点を削除する。

        Args:
            index (int): 既存の論理番号。
            kind (str): value/color。
        Returns:
            RemapValue: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        self._ramp_array(kind).removeElement(_Calculation.index(index))
        return self

    def outputPlug(self):
        """計算結果の接続用Plugを取得する。
        Returns:
            Plug: 出力参照。
        """
        return self.plug("outValue")

    def result(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            float: 計算結果。
        """
        return self.outputPlug().get()
