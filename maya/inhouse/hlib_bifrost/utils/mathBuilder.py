"""Bifrostの定数・接続・基本数値演算を組み立てる。"""

from hlib_bifrost.plugs.port import Port
from hlib.decorators.undo import undo_transaction


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

    @undo_transaction("hlib_bifrost.MathBuilder.operation")
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

    @undo_transaction("hlib_bifrost.MathBuilder.clamp")
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
