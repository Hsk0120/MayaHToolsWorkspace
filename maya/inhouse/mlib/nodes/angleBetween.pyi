# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""2つのベクトルのなす角を計算する。"""

from . import _calculation
from .node import Node
from typing import Iterable
from mlib.maths.vector import Vector
from mlib.plugs.plug import Plug

_OUTPUTS: dict


class AngleBetween(Node):
    """2つのベクトルのなす角・回転軸・オイラー角を計算する。"""
    def setInput(self, vector1: Iterable[float] | Plug | str | None = ..., vector2: Iterable[float] | Plug | str | None = ...) -> AngleBetween:
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            vector1 (Iterable[float] | Plug | str | None): 1つ目のベクトル。
            vector2 (Iterable[float] | Plug | str | None): 2つ目のベクトル。

        Returns:
            AngleBetween: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        ...
    def getResult(self, kind: str = ...) -> float | Vector:
        """出力の現在の値を取得する。

        Args:
            kind (str): 出力の種類。``"angle"`` は ``angle``、``"axis"`` は ``axis``、``"euler"`` は ``euler``。

        Returns:
            float | Vector: なす角(度)・回転軸・オイラー角(度)。

        Raises:
            ValueError: kindが未対応の名前の場合。
        """
        ...
    def getOutputPlug(self, kind: str = ...) -> Plug:
        """出力のアトリビュートを取得する(接続元に使う)。

        Args:
            kind (str): 出力の種類。:meth:`getResult` と同じ。

        Returns:
            Plug: 出力のアトリビュート。

        Raises:
            ValueError: kindが未対応の名前の場合。
        """
        ...
