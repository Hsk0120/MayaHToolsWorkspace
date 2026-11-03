"""ランプのアトリビュート(位置・値・補間の点を持つマルチアトリビュート)を扱う。"""

import math
import numbers

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorator import undoChunk
from .multiPlug import MultiPlug

#: 補間の番号(``MRampAttribute.kNone`` 等と同じ)に対応する名前。
_INTERPOLATION_NAMES = ("none", "linear", "smooth", "spline")


def _require_number(value, name):
    """有限の実数を検証し、floatで返す。

    Args:
        value (float): 検証する値。
        name (str): 例外の文言に使う引数名。

    Returns:
        float: 検証済みの値。

    Raises:
        TypeError: boolまたは実数以外の場合。
        ValueError: 有限でない場合。
    """
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise TypeError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return value


class RampPlug(MultiPlug):
    """ランプのアトリビュート(remapValueの ``value``・``color`` など)を、位置・値・補間の点の並びとして扱う。

    ``om2.MRampAttribute`` で扱えるマルチアトリビュートを取得するとこの型になる。値は、float のランプ
    (カーブのランプ)は float、色のランプは ``(r, g, b)`` の tuple。補間は ``"none"``・``"linear"``・
    ``"smooth"``・``"spline"`` の名前で扱う。要素の番号・値の直接の編集は :class:`MultiPlug` の機能で行える。

    Note:
        ``ramp`` テクスチャノードの ``colorEntryList`` は MRampAttribute で扱えない形のため、この型にならない
        (:class:`MultiPlug`)。
    """

    def isColorRamp(self):
        """色のランプか判定する。

        Returns:
            bool: 色のランプなら ``True``。float のランプ(カーブのランプ)は ``False``。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        return self._ramp().isColorRamp

    def getEntries(self):
        """ランプの点を、位置の昇順で取得する。

        Returns:
            list[tuple[float, float | tuple[float, float, float], str]]: (位置, 値, 補間の名前)の新しいリスト。
                値は float のランプが float、色のランプが ``(r, g, b)``。位置が同じ点は論理番号の順。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        ramp = self._ramp()
        indices, positions, values, interpolations = ramp.getEntries()
        color = ramp.isColorRamp
        entries = []
        for index, position, value, interpolation in zip(indices, positions, values, interpolations):
            value = (value.r, value.g, value.b) if color else float(value)
            entries.append((float(position), index, value, _INTERPOLATION_NAMES[interpolation]))
        entries.sort(key=lambda entry: (entry[0], entry[1]))
        return [(position, value, interpolation) for position, _, value, interpolation in entries]

    def setEntries(self, entries):
        """ランプの点を、既存の点をすべて置き換えて設定する。

        既存の要素を ``cmds.removeMultiInstance`` で外し、渡した順に論理番号0から設定する。Undo 1回で戻る。

        Args:
            entries (list[tuple[float, float | tuple[float, float, float], str]]): (位置, 値, 補間の名前)の並び。
                値は float のランプが実数、色のランプが3つの実数。補間は ``"none"``・``"linear"``・
                ``"smooth"``・``"spline"``。:meth:`getEntries` の結果をそのまま渡せる。

        Returns:
            RampPlug: 自身。

        Raises:
            TypeError: entriesや各点が3つの組でない、位置・値が実数(色は3つの実数)でない、補間が文字列でない場合。
            ValueError: entriesが空、数値が有限でない、または補間が未対応の名前の場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効、ロック・入力接続でMayaが設定を拒否した場合。
        """
        with undoChunk("mlibRampPlugSetEntries"):
            ramp = self._ramp()
            points = self._validated_entries(entries, ramp.isColorRamp)
            if self._mplug.isLocked:
                raise RuntimeError(f"Ramp attribute is locked: {self.getFullName()}")
            name = self.getFullName()
            for index in self._mplug.getExistingArrayAttributeIndices():
                cmds.removeMultiInstance(f"{name}[{index}]", b=True)
            element = self._mplug.elementByLogicalIndex(0)
            children = [om2.MFnAttribute(element.child(number).attribute()).name for number in range(3)]
            for index, (position, value, interpolation) in enumerate(points):
                prefix = f"{name}[{index}]."
                cmds.setAttr(prefix + children[0], position)
                if isinstance(value, tuple):
                    cmds.setAttr(prefix + children[1], *value, type="double3")
                else:
                    cmds.setAttr(prefix + children[1], value)
                cmds.setAttr(prefix + children[2], interpolation)
            return self

    def getValueAt(self, position):
        """ランプの位置での値を、補間した値で取得する。

        Args:
            position (float): ランプ上の位置。

        Returns:
            float | tuple[float, float, float]: float のランプは float、色のランプは ``(r, g, b)``。

        Raises:
            TypeError: positionが実数以外の場合。
            ValueError: positionが有限でない場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        position = _require_number(position, "position")
        ramp = self._ramp()
        value = ramp.getValueAtPosition(position)
        if ramp.isColorRamp:
            return (value.r, value.g, value.b)
        return float(value)

    def _ramp(self):
        """有効性を確かめ、このプラグの ``om2.MRampAttribute`` を作る。

        Returns:
            om2.MRampAttribute: このランプのアトリビュート。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        self._require_valid()
        return om2.MRampAttribute(self._mplug)

    @staticmethod
    def _validated_entries(entries, color):
        """setEntriesの点を検証し、(位置, 値, 補間の番号)のリストで返す。

        Args:
            entries (list[tuple[float, float | tuple[float, float, float], str]]): 検証する点の並び。
            color (bool): 色のランプならTrue。

        Returns:
            list[tuple[float, float | tuple[float, float, float], int]]: 検証済みの点。

        Raises:
            TypeError: 並び・点・値・補間の型が違う場合。
            ValueError: 空、有限でない数値、または未対応の補間の名前の場合。
        """
        if isinstance(entries, (str, bytes)):
            raise TypeError("entries must be a sequence of (position, value, interpolation)")
        try:
            entries = list(entries)
        except TypeError:
            raise TypeError("entries must be a sequence of (position, value, interpolation)") from None
        if not entries:
            raise ValueError("entries must not be empty")
        points = []
        for entry in entries:
            if isinstance(entry, (str, bytes)) or not isinstance(entry, (tuple, list)) or len(entry) != 3:
                raise TypeError("Each entry must be a (position, value, interpolation) tuple")
            position, value, interpolation = entry
            position = _require_number(position, "position")
            if color:
                if isinstance(value, (str, bytes)) or not isinstance(value, (tuple, list)) or len(value) != 3:
                    raise TypeError("value must be three numbers (r, g, b) for a color ramp")
                value = tuple(_require_number(item, "value") for item in value)
            else:
                value = _require_number(value, "value")
            if not isinstance(interpolation, str):
                raise TypeError("interpolation must be a string")
            if interpolation not in _INTERPOLATION_NAMES:
                raise ValueError("interpolation must be one of: " + ", ".join(_INTERPOLATION_NAMES))
            points.append((position, value, _INTERPOLATION_NAMES.index(interpolation)))
        return points
