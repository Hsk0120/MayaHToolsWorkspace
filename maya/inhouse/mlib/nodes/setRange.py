"""XYZ各成分を旧範囲から新範囲へ線形変換する。"""

from . import _calculation
from .node import Node


class SetRange(Node):
    """XYZ各成分を旧範囲から新範囲へ線形変換する。"""

    def setInput(self, value=None, min=None, max=None, oldMin=None, oldMax=None):
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            value (Iterable[float] | Plug | str | None): 変換する値(XYZ)。
            min (Iterable[float] | Plug | str | None): 新しい範囲の下限(XYZ)。
            max (Iterable[float] | Plug | str | None): 新しい範囲の上限(XYZ)。
            oldMin (Iterable[float] | Plug | str | None): 元の範囲の下限(XYZ)。
            oldMax (Iterable[float] | Plug | str | None): 元の範囲の上限(XYZ)。

        Returns:
            SetRange: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        return _calculation.set_inputs(self, "setInput", {
            "value": value,
            "min": min,
            "max": max,
            "oldMin": oldMin,
            "oldMax": oldMax,
        })

    def getResult(self):
        """出力 ``outValue`` の現在の値を取得する。

        Returns:
            tuple[float, float, float]: 変換した値(XYZ)。
        """
        return self.getOutputPlug().get()

    def getOutputPlug(self):
        """出力のアトリビュート ``outValue`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        return self.getPlug("outValue")
