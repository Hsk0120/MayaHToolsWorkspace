# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""ランプのアトリビュート(位置・値・補間の点を持つマルチアトリビュート)を扱う。"""

import math
import numbers
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..decorator import undoChunk
from .multiPlug import MultiPlug

_INTERPOLATION_NAMES: tuple

def _require_number(value: float, name: str) -> float:
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
    ...


class RampPlug(MultiPlug):
    """ランプのアトリビュート(remapValueの ``value``・``color`` など)を、位置・値・補間の点の並びとして扱う。

    ``om2.MRampAttribute`` で扱えるマルチアトリビュートを取得するとこの型になる。値は、float のランプ
    (カーブのランプ)は float、色のランプは ``(r, g, b)`` の tuple。補間は ``"none"``・``"linear"``・
    ``"smooth"``・``"spline"`` の名前で扱う。要素の番号・値の直接の編集は :class:`MultiPlug` の機能で行える。

    Note:
        ``ramp`` テクスチャノードの ``colorEntryList`` は MRampAttribute で扱えない形のため、この型にならない
        (:class:`MultiPlug`)。
    """
    def isColorRamp(self) -> bool:
        """色のランプか判定する。

        Returns:
            bool: 色のランプなら ``True``。float のランプ(カーブのランプ)は ``False``。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        ...
    def getEntries(self) -> list[tuple[float, float | tuple[float, float, float], str]]:
        """ランプの点を、位置の昇順で取得する。

        Returns:
            list[tuple[float, float | tuple[float, float, float], str]]: (位置, 値, 補間の名前)の新しいリスト。
                値は float のランプが float、色のランプが ``(r, g, b)``。位置が同じ点は論理番号の順。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        ...
    def setEntries(self, entries: list[tuple[float, float | tuple[float, float, float], str]]) -> RampPlug:
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
        ...
    def getValueAt(self, position: float) -> float | tuple[float, float, float]:
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
        ...
    def _ramp(self) -> om2.MRampAttribute:
        """有効性を確かめ、このプラグの ``om2.MRampAttribute`` を作る。

        Returns:
            om2.MRampAttribute: このランプのアトリビュート。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        ...
    @staticmethod
    def _validated_entries(entries: list[tuple[float, float | tuple[float, float, float], str]], color: bool) -> list[tuple[float, float | tuple[float, float, float], int]]:
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
        ...
