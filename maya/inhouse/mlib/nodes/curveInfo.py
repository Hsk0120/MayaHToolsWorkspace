"""カーブの長さ等を取得する。"""

from . import _calculation
from .node import Node

#: ジオメトリの入力のアトリビュート名からシェイプのMaya型名。
_GEOMETRY = {"inputCurve": "nurbsCurve"}


class CurveInfo(Node):
    """カーブの長さ・CVの位置・ノット等を出力する。"""

    def setInput(self, inputCurve=None):
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            inputCurve (NurbsCurve | Transform | Plug | str | None): 対象のカーブ。シェイプ(またはそれを1つだけ持つTransform)はworldSpaceを接続する。

        Returns:
            CurveInfo: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            ValueError: ジオメトリの入力のTransformに、対応するシェイプが1つだけでない場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        return _calculation.set_inputs(self, "setInput", {
            "inputCurve": inputCurve,
        }, _GEOMETRY)

    def getResult(self):
        """出力 ``arcLength`` の現在の値を取得する。

        Returns:
            float: カーブの長さ(cm)。
        """
        return self.getOutputPlug().get()

    def getOutputPlug(self):
        """出力のアトリビュート ``arcLength`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        return self.getPlug("arcLength")
