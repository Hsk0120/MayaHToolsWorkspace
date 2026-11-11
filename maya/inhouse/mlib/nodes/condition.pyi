# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""2値の比較により出力を切り替える。"""

from . import _calculation
from .node import Node
from typing import Iterable
from mlib.plugs.plug import Plug

_OPERATIONS: tuple


class Condition(Node):
    """2値の比較により出力を切り替える。"""
    def setInput(self, firstTerm: float | Plug | str | None = ..., secondTerm: float | Plug | str | None = ..., colorIfTrue: Iterable[float] | Plug | str | None = ..., colorIfFalse: Iterable[float] | Plug | str | None = ...) -> Condition:
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            firstTerm (float | Plug | str | None): 比較する1つ目の値。
            secondTerm (float | Plug | str | None): 比較する2つ目の値。
            colorIfTrue (Iterable[float] | Plug | str | None): 比較が成り立つときの出力(RGB)。
            colorIfFalse (Iterable[float] | Plug | str | None): 比較が成り立たないときの出力(RGB)。

        Returns:
            Condition: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        ...
    def getOperation(self) -> str:
        """比較の種類を名前で取得する(``operation``)。

        Returns:
            str: ``"equal"``・``"notEqual"``・``"greaterThan"``・``"greaterOrEqual"``・``"lessThan"``・
                ``"lessOrEqual"`` のいずれか。
        """
        ...
    def setOperation(self, operation: str | int) -> Condition:
        """比較の種類を名前または番号で設定する(``operation``)。1回のUndoで戻せる。

        Args:
            operation (str | int): ``"equal"``・``"notEqual"``・``"greaterThan"``・``"greaterOrEqual"``・``"lessThan"``・
                ``"lessOrEqual"`` のいずれか、またはMayaの番号(0から)。

        Returns:
            Condition: 自身。

        Raises:
            TypeError: operationが文字列・int以外の場合。
            ValueError: 未対応の名前・範囲外の番号の場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込みを拒否した場合。
        """
        ...
    def getResult(self) -> tuple[float, float, float]:
        """出力 ``outColor`` の現在の値を取得する。

        Returns:
            tuple[float, float, float]: 比較の結果の色(RGB)。
        """
        ...
    def getOutputPlug(self) -> Plug:
        """出力のアトリビュート ``outColor`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        ...
