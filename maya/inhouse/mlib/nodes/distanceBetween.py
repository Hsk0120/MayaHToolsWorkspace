"""2点の距離を計算する。"""

from . import _calculation
from .node import Node


class DistanceBetween(Node):
    """2点(それぞれのマトリクスで変換した点)の距離を計算する。"""

    def setInput(self, point1=None, point2=None, inMatrix1=None, inMatrix2=None):
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            point1 (Iterable[float] | Plug | str | None): 1つ目の点(cm)。
            point2 (Iterable[float] | Plug | str | None): 2つ目の点(cm)。
            inMatrix1 (Matrix | Iterable[float] | Plug | str | None): point1を変換するマトリクス。
            inMatrix2 (Matrix | Iterable[float] | Plug | str | None): point2を変換するマトリクス。

        Returns:
            DistanceBetween: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        return _calculation.set_inputs(self, "setInput", {
            "point1": point1,
            "point2": point2,
            "inMatrix1": inMatrix1,
            "inMatrix2": inMatrix2,
        })

    def getResult(self):
        """出力 ``distance`` の現在の値を取得する。

        Returns:
            float: 距離(cm)。
        """
        return self.getOutputPlug().get()

    def getOutputPlug(self):
        """出力のアトリビュート ``distance`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        return self.getPlug("distance")
