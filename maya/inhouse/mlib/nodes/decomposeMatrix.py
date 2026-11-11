"""マトリクスを移動・回転・スケール・せん断へ分解する。"""

from . import _calculation
from .node import Node

#: 出力する回転の回転順の名前(Mayaの ``inputRotateOrder`` の番号順)。
_ROTATE_ORDERS = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")
#: 出力の種類からMayaの出力アトリビュート名。
_OUTPUTS = {
    "translate": "outputTranslate",
    "rotate": "outputRotate",
    "scale": "outputScale",
    "shear": "outputShear",
    "quaternion": "outputQuat",
}


class DecomposeMatrix(Node):
    """マトリクスを移動・回転・スケール・せん断・クォータニオンへ分解する。親空間やjointOrientの補正は行わない。"""

    def setInput(self, inputMatrix=None):
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            inputMatrix (Matrix | Iterable[float] | Plug | str | None): 分解するマトリクス。

        Returns:
            DecomposeMatrix: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        return _calculation.set_inputs(self, "setInput", {
            "inputMatrix": inputMatrix,
        })

    def getRotateOrder(self):
        """出力する回転の回転順を名前で取得する(``inputRotateOrder``)。

        Returns:
            str: ``"xyz"``・``"yzx"``・``"zxy"``・``"xzy"``・``"yxz"``・``"zyx"`` のいずれか。
        """
        return _calculation.get_enum(self, "inputRotateOrder", _ROTATE_ORDERS)

    def setRotateOrder(self, order):
        """出力する回転の回転順を名前または番号で設定する(``inputRotateOrder``)。1回のUndoで戻せる。

        Args:
            order (str | int): ``"xyz"``・``"yzx"``・``"zxy"``・``"xzy"``・``"yxz"``・``"zyx"`` のいずれか、またはMayaの番号(0から)。

        Returns:
            DecomposeMatrix: 自身。

        Raises:
            TypeError: orderが文字列・int以外の場合。
            ValueError: 未対応の名前・範囲外の番号の場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込みを拒否した場合。
        """
        return _calculation.set_enum(self, "setRotateOrder", "inputRotateOrder", order, _ROTATE_ORDERS, "order")

    def getResult(self, kind="translate"):
        """出力の現在の値を取得する。

        Args:
            kind (str): 出力の種類。``"translate"`` は ``outputTranslate``、``"rotate"`` は ``outputRotate``、
                ``"scale"`` は ``outputScale``、``"shear"`` は ``outputShear``、
                ``"quaternion"`` は ``outputQuat``。

        Returns:
            Vector | tuple[float, float, float, float]: 分解した値。回転は度の ``Vector``
                (``inputRotateOrder`` の回転順)、クォータニオンは ``(x, y, z, w)``。

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
