# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""RGB各成分を指定範囲に制限する。"""

from . import _calculation
from .node import Node
from typing import Iterable
from mlib.plugs.plug import Plug



class Clamp(Node):
    """RGB各成分を指定範囲に制限する。"""
    def setInput(self, input: Iterable[float] | Plug | str | None = ..., min: Iterable[float] | Plug | str | None = ..., max: Iterable[float] | Plug | str | None = ...) -> Clamp:
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            input (Iterable[float] | Plug | str | None): 制限する値(RGB)。
            min (Iterable[float] | Plug | str | None): 下限(RGB)。
            max (Iterable[float] | Plug | str | None): 上限(RGB)。

        Returns:
            Clamp: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        ...
    def getResult(self) -> tuple[float, float, float]:
        """出力 ``output`` の現在の値を取得する。

        Returns:
            tuple[float, float, float]: 制限した値(RGB)。
        """
        ...
    def getOutputPlug(self) -> Plug:
        """出力のアトリビュート ``output`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        ...
