"""二点間、またはTransformの原点間の距離を扱う。"""

from .._core.registry import node_wrapper
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from .node import Node
from .transform import Transform


@node_wrapper("distanceBetween")
class DistanceBetween(Node):
    """inMatrix1/2で変換したpoint1/2間の距離を評価する。"""

    @fast_edit
    @undoChunk("hlibDistanceBetweenSetPoints")
    def setPoints(self, point1, point2, *, fast=False):
        """各入力行列の空間における二点を設定する。行列は変更しない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            point1 (Iterable[float]): 第一の点。内部距離単位cm。
            point2 (Iterable[float]): 第二の点。同じ単位。

        Returns:
            DistanceBetween: 自身。

        Raises:
            ValueError: 座標が3要素でない、または非有限値の場合。
            RuntimeError: アトリビュートロックなどで設定できない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        import math

        points = [tuple(float(v) for v in point) for point in (point1, point2)]
        if any(len(point) != 3 or not all(math.isfinite(v) for v in point) for point in points):
            raise ValueError("Points must contain three finite coordinates")
        for name, point in zip(("point1", "point2"), points):
            self.plug(name).set(point)
        return self

    @undoChunk("hlibDistanceBetweenConnectTransforms")
    def connectTransforms(self, first, second, force=False):
        """二つのTransform原点のワールド距離を測る接続を設定する。

        Args:
            first (Transform | str): 第一のTransform。ラッパーが解決したDAGパスを使う。
            second (Transform | str): 第二のTransform。
            force (bool): 既存の行列入力接続を置き換えるか。

        Returns:
            DistanceBetween: 自身。point1/2は原点にリセットする。

        Raises:
            TypeError: Transform以外を指定した場合。
            RuntimeError: ロックや既存接続により変更できない場合。
                途中の変更は自動では戻さず、一回のUndoで戻せる。
        """
        from ..nodes.node import Node as _InputNode
        nodes = [_InputNode._resolve_input(first), _InputNode._resolve_input(second)]
        if not all(isinstance(node, Transform) for node in nodes):
            raise TypeError("Both inputs must be transforms")
        self.setPoints((0, 0, 0), (0, 0, 0))
        for number, node in enumerate(nodes, 1):
            index = node.dagPath().instanceNumber()
            node.plug("worldMatrix").element(index, create=True).connect(
                self.plug(f"inMatrix{number}"), force=force)
        return self

    def outputPlug(self):
        """Plug: distance出力。別アトリビュートへの接続に使用する。"""
        return self.plug("distance")

    def distance(self):
        """float: 評価済み距離。内部距離単位cm。"""
        return self.outputPlug().get()
