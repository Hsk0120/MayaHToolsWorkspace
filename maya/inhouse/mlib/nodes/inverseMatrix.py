"""マトリクスの逆マトリクスを計算する。"""

from . import _calculation
from .node import Node


class InverseMatrix(Node):
    """入力マトリクスの逆マトリクスを出力する。

    Mayaの ``matrixNodes`` プラグインのノード。作成する前にプラグインを読み込む
    (``mlib.Plugin("matrixNodes").load()`` または ``cmds.loadPlugin("matrixNodes")``)。
    """

    def setInput(self, inputMatrix=None):
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            inputMatrix (Matrix | Iterable[float] | Plug | str | None): 元のマトリクス。

        Returns:
            InverseMatrix: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        return _calculation.set_inputs(self, "setInput", {
            "inputMatrix": inputMatrix,
        })

    def getResult(self):
        """出力 ``outputMatrix`` の現在の値を取得する。

        Returns:
            Matrix: 逆マトリクス。
        """
        return self.getOutputPlug().get()

    def getOutputPlug(self):
        """出力のアトリビュート ``outputMatrix`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        return self.getPlug("outputMatrix")
