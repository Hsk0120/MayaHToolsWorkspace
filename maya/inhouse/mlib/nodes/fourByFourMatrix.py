"""16個の値からマトリクスを作る。"""

from . import _calculation
from .node import Node

#: マトリクスの成分のアトリビュート名(行優先。``in00`` が1行1列)。
_ELEMENTS = tuple(f"in{row}{column}" for row in range(4) for column in range(4))


class FourByFourMatrix(Node):
    """``in00``〜``in33`` の16個の値(行優先)からマトリクスを作り、``output`` へ出力する。"""

    def setInput(self, matrix=None, **elements):
        """成分をまとめて設定する。値は書き込み、Plug は接続する。1回のUndoで戻せる。

        Args:
            matrix (Matrix | Iterable[float] | None): 16個の値(行優先)。Noneは変更しない。
            **elements (float | Plug | str): 個別の成分(``in03=5.0`` や ``in30=node.tx`` など)。
                matrix の後に適用する。

        Returns:
            FourByFourMatrix: 自身。

        Raises:
            TypeError: elements に ``in00``〜``in33`` 以外の名前がある場合、または接続元の型が不正な場合。
            ValueError: matrix の値が16個でない場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        unknown = sorted(set(elements) - set(_ELEMENTS))
        if unknown:
            raise TypeError(f"Unknown matrix elements: {', '.join(unknown)} (expected in00 to in33)")
        values = {}
        if matrix is not None:
            numbers = [float(value) for value in matrix]
            if len(numbers) != 16:
                raise ValueError(f"matrix must have 16 values, got {len(numbers)}")
            values.update(zip(_ELEMENTS, numbers))
        values.update(elements)
        return _calculation.set_inputs(self, "setInput", values)

    def getResult(self):
        """出力 ``output`` の現在の値を取得する。

        Returns:
            Matrix: 作ったマトリクス。
        """
        return self.getOutputPlug().get()

    def getOutputPlug(self):
        """出力のアトリビュート ``output`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        return self.getPlug("output")
