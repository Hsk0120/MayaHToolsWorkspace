# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""複数のマトリクスを順に掛け合わせる。"""

from ..decorator import _edit_context
from . import _calculation
from .node import Node
from typing import Iterable
from mlib.maths.matrix import Matrix
from mlib.plugs.plug import Plug



class MultMatrix(Node):
    """``matrixIn`` のマトリクスを論理番号の順に掛け合わせ(先頭が最初に適用される)、``matrixSum`` へ出力する。"""
    def setInput(self, matrices: Iterable[Matrix | Iterable[float] | Plug | str]) -> MultMatrix:
        """入力のマトリクスを、既存の入力をすべて置き換えて設定する。1回のUndoで戻せる。

        渡した順に論理番号0から設定する。マトリクスは値として書き込み、Plug・MPlug・``"node.attr"`` の
        文字列は接続元として接続する。

        Args:
            matrices (Iterable[Matrix | Iterable[float] | Plug | str]): 掛け合わせるマトリクスの並び。

        Returns:
            MultMatrix: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        ...
    def addInput(self, matrix: Matrix | Iterable[float] | Plug | str) -> int:
        """マトリクスを末尾(既存の最大の番号+1)へ足し、その番号を返す。1回のUndoで戻せる。

        Args:
            matrix (Matrix | Iterable[float] | Plug | str): マトリクスの値、または接続元。

        Returns:
            int: 足した入力の論理番号。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合。
        """
        ...
    def removeInput(self, index: int) -> MultMatrix:
        """入力のマトリクスを接続ごと削除する。1回のUndoで戻せる。

        Args:
            index (int): 入力の論理番号。

        Returns:
            MultMatrix: 自身。

        Raises:
            TypeError: indexがint以外の場合。
            ValueError: index の入力が無い場合。
            RuntimeError: ノードが無効な場合、またはMayaが削除を拒否した場合。
        """
        ...
    def getInputIndices(self) -> list[int]:
        """既存の入力の論理番号を昇順で取得する。

        Returns:
            list[int]: 論理番号。
        """
        ...
    def getResult(self) -> Matrix:
        """出力 ``matrixSum`` の現在の値を取得する。

        Returns:
            Matrix: 掛け合わせたマトリクス。
        """
        ...
    def getOutputPlug(self) -> Plug:
        """出力のアトリビュート ``matrixSum`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        ...
