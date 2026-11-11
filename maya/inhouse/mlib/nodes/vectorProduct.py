"""ベクトルの内積・外積・マトリクスとの積を計算する。"""

from . import _calculation
from .node import Node

#: 演算の種類の名前(Mayaの ``operation`` の番号順)。
_OPERATIONS = ("noOperation", "dotProduct", "crossProduct", "vectorMatrixProduct", "pointMatrixProduct")


class VectorProduct(Node):
    """ベクトルの内積・外積・マトリクスとの積を計算する。"""

    def setInput(self, input1=None, input2=None, matrix=None, normalizeOutput=None):
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            input1 (Iterable[float] | Plug | str | None): 1つ目のベクトル(マトリクスとの積では変換するベクトル・点)。
            input2 (Iterable[float] | Plug | str | None): 2つ目のベクトル。
            matrix (Matrix | Iterable[float] | Plug | str | None): マトリクスとの積で使うマトリクス。
            normalizeOutput (bool | Plug | str | None): 出力を正規化するか。

        Returns:
            VectorProduct: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        return _calculation.set_inputs(self, "setInput", {
            "input1": input1,
            "input2": input2,
            "matrix": matrix,
            "normalizeOutput": normalizeOutput,
        })

    def getOperation(self):
        """演算の種類を名前で取得する(``operation``)。

        Returns:
            str: ``"noOperation"``・``"dotProduct"``・``"crossProduct"``・``"vectorMatrixProduct"``・
                ``"pointMatrixProduct"`` のいずれか。
        """
        return _calculation.get_enum(self, "operation", _OPERATIONS)

    def setOperation(self, operation):
        """演算の種類を名前または番号で設定する(``operation``)。1回のUndoで戻せる。

        Args:
            operation (str | int): ``"noOperation"``・``"dotProduct"``・``"crossProduct"``・``"vectorMatrixProduct"``・
                ``"pointMatrixProduct"`` のいずれか、またはMayaの番号(0から)。

        Returns:
            VectorProduct: 自身。

        Raises:
            TypeError: operationが文字列・int以外の場合。
            ValueError: 未対応の名前・範囲外の番号の場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込みを拒否した場合。
        """
        return _calculation.set_enum(self, "setOperation", "operation", operation, _OPERATIONS, "operation")

    def getResult(self):
        """出力 ``output`` の現在の値を取得する。

        Returns:
            tuple[float, float, float]: 演算の結果(内積はX成分)。
        """
        return self.getOutputPlug().get()

    def getOutputPlug(self):
        """出力のアトリビュート ``output`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        return self.getPlug("output")
