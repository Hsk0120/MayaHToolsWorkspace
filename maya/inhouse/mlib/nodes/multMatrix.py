"""複数のマトリクスを順に掛け合わせる。"""

from ..decorator import _edit_context
from . import _calculation
from .node import Node


class MultMatrix(Node):
    """``matrixIn`` のマトリクスを論理番号の順に掛け合わせ(先頭が最初に適用される)、``matrixSum`` へ出力する。"""

    def setInput(self, matrices):
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
        matrices = list(matrices)
        self._require_valid("setInput")
        with _edit_context(_calculation.chunk_name(self, "setInput"), False, transaction=True):
            for index in reversed(_calculation.element_indices(self, "matrixIn")):
                _calculation.remove_elements(self, "setInput", ("matrixIn",), index)
            _calculation.set_inputs(self, "setInput", {f"matrixIn[{index}]": matrix
                                                       for index, matrix in enumerate(matrices)})
        return self

    def addInput(self, matrix):
        """マトリクスを末尾(既存の最大の番号+1)へ足し、その番号を返す。1回のUndoで戻せる。

        Args:
            matrix (Matrix | Iterable[float] | Plug | str): マトリクスの値、または接続元。

        Returns:
            int: 足した入力の論理番号。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合。
        """
        return _calculation.add_element(self, "addInput", "matrixIn", {"matrixIn[{index}]": matrix})

    def removeInput(self, index):
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
        return _calculation.remove_elements(self, "removeInput", ("matrixIn",), index)

    def getInputIndices(self):
        """既存の入力の論理番号を昇順で取得する。

        Returns:
            list[int]: 論理番号。
        """
        return _calculation.element_indices(self, "matrixIn")

    def getResult(self):
        """出力 ``matrixSum`` の現在の値を取得する。

        Returns:
            Matrix: 掛け合わせたマトリクス。
        """
        return self.getOutputPlug().get()

    def getOutputPlug(self):
        """出力のアトリビュート ``matrixSum`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        return self.getPlug("matrixSum")
