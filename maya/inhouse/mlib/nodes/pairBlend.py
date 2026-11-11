"""2組の移動・回転をweightで補間する。"""

from . import _calculation
from .node import Node

#: 回転の補間の方法の名前(Mayaの ``rotInterpolation`` の番号順)。
_ROTATE_INTERPOLATIONS = ("euler", "quaternion")
#: 出力の種類からMayaの出力アトリビュート名。
_OUTPUTS = {
    "translate": "outTranslate",
    "rotate": "outRotate",
}


class PairBlend(Node):
    """2組の移動・回転をweightで補間する(weight=0で入力1、1で入力2)。"""

    def setInput(self, inTranslate1=None, inRotate1=None, inTranslate2=None, inRotate2=None, weight=None):
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            inTranslate1 (Iterable[float] | Plug | str | None): 入力1の移動(cm)。
            inRotate1 (Iterable[float] | Plug | str | None): 入力1の回転(度)。
            inTranslate2 (Iterable[float] | Plug | str | None): 入力2の移動(cm)。
            inRotate2 (Iterable[float] | Plug | str | None): 入力2の回転(度)。
            weight (float | Plug | str | None): 補間の割合(0〜1)。

        Returns:
            PairBlend: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        return _calculation.set_inputs(self, "setInput", {
            "inTranslate1": inTranslate1,
            "inRotate1": inRotate1,
            "inTranslate2": inTranslate2,
            "inRotate2": inRotate2,
            "weight": weight,
        })

    def getRotateInterpolation(self):
        """回転の補間の方法を名前で取得する(``rotInterpolation``)。

        Returns:
            str: ``"euler"``・``"quaternion"`` のいずれか。
        """
        return _calculation.get_enum(self, "rotInterpolation", _ROTATE_INTERPOLATIONS)

    def setRotateInterpolation(self, interpolation):
        """回転の補間の方法を名前または番号で設定する(``rotInterpolation``)。1回のUndoで戻せる。

        Args:
            interpolation (str | int): ``"euler"``・``"quaternion"`` のいずれか、またはMayaの番号(0から)。

        Returns:
            PairBlend: 自身。

        Raises:
            TypeError: interpolationが文字列・int以外の場合。
            ValueError: 未対応の名前・範囲外の番号の場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込みを拒否した場合。
        """
        return _calculation.set_enum(self, "setRotateInterpolation", "rotInterpolation", interpolation, _ROTATE_INTERPOLATIONS, "interpolation")

    def getResult(self, kind="translate"):
        """出力の現在の値を取得する。

        Args:
            kind (str): 出力の種類。``"translate"`` は ``outTranslate``、``"rotate"`` は ``outRotate``。

        Returns:
            Vector: 補間した値。移動はcm、回転は度。

        Raises:
            ValueError: kindが未対応の名前の場合。
        """
        return self.getOutputPlug(kind).get()

    def getOutputPlug(self, kind="translate"):
        """出力のアトリビュートを取得する(接続元に使う)。

        Args:
            kind (str): 出力の種類。:meth:`getResult` と同じ。

        Returns:
            Plug: 出力のアトリビュート。

        Raises:
            ValueError: kindが未対応の名前の場合。
        """
        return self.getPlug(_OUTPUTS[_calculation.choice(kind, _OUTPUTS, "kind")])
