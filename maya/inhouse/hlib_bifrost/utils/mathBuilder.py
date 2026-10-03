"""Bifrostの定数・接続・基本数値演算を組み立てる。"""

from ..plugs.port import Port
from .._binding import coreModule
undoTransaction = coreModule('decorators.undo').undoTransaction


class MathBuilder:
    """Compoundへ再利用可能なscalar演算を追加する。"""

    def __init__(self, compound):
        """演算の追加先を保持する。

        Args:
            compound (Compound): 追加先。
        """
        self.compound = compound

    @staticmethod
    def feed(value, port):
        """定数またはポートを演算入力へ割り当てる。

        Args:
            value (float | Port): 入力する値または接続元。
            port (Port): 接続先のポート。
        """
        if isinstance(value, Port):
            value.connect(port)
        else:
            port.set_default(value)

    @undoTransaction("hlib_bifrost.MathBuilder.operation")
    def operation(self, kind, values, output="output"):
        """同型の可変数入力演算を追加する。

        Args:
            kind (str): Core::Mathの演算名。
            values (Sequence[float | Port]): 入力する定数またはポート。
            output (str): 結果ポート名。既定はoutput。


        Returns:
            Port: 生成した演算の結果ポート。
        """
        node = self.compound.add_node("BifrostGraph,Core::Math," + kind)
        for index, value in enumerate(values):
            self.feed(value, node.add_port("v" + str(index), "float"))
        return node.port(output)

    @undoTransaction("hlib_bifrost.MathBuilder.clamp")
    def clamp(self, value, low, high):
        """既存clamp Compoundへ固定ポートで接続する。

        Args:
            value (float | Port): 制限対象。
            low (float | Port): 下限。
            high (float | Port): 上限。


        Returns:
            Port: 制限後の結果ポート。
        """
        node = self.compound.add_node("BifrostGraph,Core::Math,clamp")
        for key, val in (("value", value), ("min", low), ("max", high)):
            self.feed(val, node.port(key))
        return node.port("clamped")

    @undoTransaction("hlib_bifrost.MathBuilder.matrix_multiply")
    def matrix_multiply(self, values):
        """列ベクトル規約の順序で倍精度行列を乗算する。

        Args:
            values (Sequence[Port]): 左から右の乗算順。Mayaの行列積とは逆順。

        Returns:
            Port: double4x4の積。
        """
        values = tuple(values)
        if not values or any(not isinstance(value, Port) for value in values):
            raise ValueError("matrix_multiply requires one or more Port inputs")
        node = self.compound.add_node("BifrostGraph,Core::Math,matrix_multiply")
        for index, value in enumerate(values):
            value.connect(node.add_port("v" + str(index), "Math::double4x4"))
        return node.port("matrix")
