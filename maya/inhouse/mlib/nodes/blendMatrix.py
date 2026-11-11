"""入力マトリクスへ、ターゲットのマトリクスをウェイトで順に混ぜる。"""

from . import _calculation
from .node import Node


class BlendMatrix(Node):
    """``inputMatrix`` へ ``target[i].targetMatrix`` を ``weight`` で順に混ぜたマトリクスを出力する。"""

    def setInput(self, inputMatrix=None):
        """元のマトリクスを設定する。値は書き込み、Plug は接続する。1回のUndoで戻せる。

        Args:
            inputMatrix (Matrix | Iterable[float] | Plug | str | None): 元のマトリクス。Noneは変更しない。

        Returns:
            BlendMatrix: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合。
        """
        return _calculation.set_inputs(self, "setInput", {"inputMatrix": inputMatrix})

    def addTarget(self, matrix, weight=1.0):
        """ターゲットのマトリクスとウェイトを末尾(既存の最大の番号+1)へ足し、その番号を返す。1回のUndoで戻せる。

        Args:
            matrix (Matrix | Iterable[float] | Plug | str): ``targetMatrix`` の値、または接続元。
            weight (float | Plug | str): ``weight`` の値(0〜1)、または接続元。

        Returns:
            int: 足したターゲットの論理番号。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合。
        """
        return _calculation.add_element(self, "addTarget", "target", {
            "target[{index}].targetMatrix": matrix,
            "target[{index}].weight": weight,
        })

    def removeTarget(self, index):
        """ターゲットを接続ごと削除する。1回のUndoで戻せる。

        Args:
            index (int): ターゲットの論理番号。

        Returns:
            BlendMatrix: 自身。

        Raises:
            TypeError: indexがint以外の場合。
            ValueError: index のターゲットが無い場合。
            RuntimeError: ノードが無効な場合、またはMayaが削除を拒否した場合。
        """
        return _calculation.remove_elements(self, "removeTarget", ("target",), index)

    def getTargetIndices(self):
        """既存のターゲットの論理番号を昇順で取得する。

        Returns:
            list[int]: 論理番号。
        """
        return _calculation.element_indices(self, "target")

    def getResult(self):
        """出力 ``outputMatrix`` の現在の値を取得する。

        Returns:
            Matrix: 混ぜたマトリクス。
        """
        return self.getOutputPlug().get()

    def getOutputPlug(self):
        """出力のアトリビュート ``outputMatrix`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        return self.getPlug("outputMatrix")
