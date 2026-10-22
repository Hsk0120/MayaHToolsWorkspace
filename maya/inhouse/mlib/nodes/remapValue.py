"""ランプで値を再マッピングする。色ランプも操作できる。"""

from .._core.flags import flag_aliases
from ..common._fast import fast_edit
from ..decorator import undoChunk
from ._calculation import _Calculation
from .node import Node


class RemapValue(Node):
    """ランプで値を再マッピングする。色ランプも操作できる。"""

    @fast_edit
    @undoChunk("mlibCalculationEdit")
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
        _Calculation.set_value(value, _Calculation.scalar, self.getPlug, 'inputValue')
        return self

    def getRange(self):
        """入出力範囲を取得する。
        Returns:
            dict[str, float]: 入出力の上下限。
        """
        return {key: self.getPlug(attr).get() for key, attr in (("input_min", "inputMin"), ("input_max", "inputMax"), ("output_min", "outputMin"), ("output_max", "outputMax"))}

    @fast_edit
    @undoChunk("mlibCalculationEdit")
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
            self.getPlug(attr).set(value)
        return self

    def getRampPoints(self, kind="value"):
        """ランプの既存点を取得する。

        Args:
            kind (str): value/color。
        Returns:
            dict[int, dict]: 論理番号ごとのposition/value/interpolation。
        """
        array = self._ramp_array(kind)
        result = {}
        for index in array.mplug().getExistingArrayAttributeIndices():
            point = array[index]
            result[index] = {"position": point[0].get(), "value": point[1].get(), "interpolation": point[2].get()}
        return result

    @flag_aliases(idx="index")
    @undoChunk("mlibCalculationEdit")
    def setRampPoint(self, index, position, value, interpolation="linear", kind="value"):
        """指定番号のランプ点を追加または編集する。

        Args:
            index (int): 非負の論理番号。 別名 ``idx`` も使用可能。
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
        point = array[index]
        point[0].set(position)
        point[1].set(value)
        point[2].set(mode)
        return self

    @flag_aliases(idx="index")
    @undoChunk("mlibCalculationEdit")
    def removeRampPoint(self, index, kind="value"):
        """指定したランプ点を削除する。

        Args:
            index (int): 既存の論理番号。 別名 ``idx`` も使用可能。
            kind (str): value/color。
        Returns:
            RemapValue: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        self._ramp_array(kind).removeElement(_Calculation.index(index))
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
        return self.getPlug(kind)
