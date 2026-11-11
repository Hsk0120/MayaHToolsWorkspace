"""二つのRGB入力をblenderで補間する。"""

from . import _calculation
from .node import Node


class BlendColors(Node):
    """color1 * blender + color2 * (1 - blender)を評価するノード。"""

    def setInput(self, color1=None, color2=None, blender=None):
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            color1 (Iterable[float] | Plug | str | None): blender=1のときの色(RGB)。
            color2 (Iterable[float] | Plug | str | None): blender=0のときの色(RGB)。
            blender (float | Plug | str | None): 補間の割合(0〜1)。

        Returns:
            BlendColors: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        return _calculation.set_inputs(self, "setInput", {
            "color1": color1,
            "color2": color2,
            "blender": blender,
        })

    def getResult(self):
        """出力 ``output`` の現在の値を取得する。

        Returns:
            tuple[float, float, float]: 補間した色(RGB)。
        """
        return self.getOutputPlug().get()

    def getOutputPlug(self):
        """出力のアトリビュート ``output`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        return self.getPlug("output")
