"""ウェイト付き加算ノード。ウェイトの正規化はしない。"""

from . import _calculation
from .node import Node


class BlendWeighted(Node):
    """input[i] * weight[i]を合計する。weightの既定値は1。"""

    def addInput(self, value, weight=1.0):
        """入力とウェイトを末尾(既存の最大の番号+1)へ足し、その番号を返す。1回のUndoで戻せる。

        Args:
            value (float | Plug | str): 入力の値、または接続元(``input[i]``)。
            weight (float | Plug | str): ウェイトの値、または接続元(``weight[i]``)。

        Returns:
            int: 足した入力の論理番号。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合。
        """
        return _calculation.add_element(self, "addInput", "input", {"input[{index}]": value, "weight[{index}]": weight})

    def removeInput(self, index):
        """入力と同じ番号のウェイトを、接続ごと削除する。1回のUndoで戻せる。

        Args:
            index (int): 入力の論理番号。

        Returns:
            BlendWeighted: 自身。

        Raises:
            TypeError: indexがint以外の場合。
            ValueError: index の入力が無い場合。
            RuntimeError: ノードが無効な場合、またはMayaが削除を拒否した場合。
        """
        return _calculation.remove_elements(self, "removeInput", ("input", "weight"), index)

    def getInputIndices(self):
        """既存の入力の論理番号を昇順で取得する。

        Returns:
            list[int]: 論理番号。
        """
        return _calculation.element_indices(self, "input")

    def getResult(self):
        """出力 ``output`` の現在の値を取得する。

        Returns:
            float: input[i] * weight[i] の合計。
        """
        return self.getOutputPlug().get()

    def getOutputPlug(self):
        """出力のアトリビュート ``output`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        return self.getPlug("output")
