"""ブラシで塗るウェイトの操作(1ストロークの計算)。Maya のペイントの仕組みからは :mod:`skinWeightKit.ui.paint` が呼ぶ。

ストロークの始めに全頂点のウェイトを1回だけ読み、塗った頂点だけを計算して Undo なしで書く(塗っている間の表示用)。
ストロークの終わりに、塗った頂点を元の値へ戻してから、最後の値を1回の Undo で書く。

- ``smooth``: 隣の頂点の(重み付き)平均へ、ブラシの強さだけ近づける。
- ``sharpen``: 隣の頂点の平均から遠ざけ、ウェイトの境目をくっきりさせる。
- ``remove``: アクティブなインフルエンスを減らし、他のインフルエンスへ配る。
- ``add``: アクティブなインフルエンスを増やす(他から比率を保って取る)。
- ``transfer``: 指定したインフルエンス(source)のウェイトを、アクティブなインフルエンスへ移す。
"""

from mlib.decorator import undoChunk

from . import influences as influences_module
from . import smoothing
from . import weights as weights_module

#: ブラシの種類。
MODES = ("smooth", "sharpen", "remove", "add", "transfer")


class PaintSession(object):
    """1ストロークの間の状態。

    Args:
        target (Target): 塗るメッシュ(頂点の選択は使わない)。
        mode (str): :data:`MODES` の名前。
        influence (mlib.nodes.Node | str | None): アクティブなインフルエンス(remove・add・transfer で使う)。
        source (mlib.nodes.Node | str | None): transfer で移す元のインフルエンス。
        method (str): スムーズの重みの付け方(:data:`skinWeightKit.core.smoothing.METHODS`)。
        radius (float): スムーズで、辺でつながっていない半径内の頂点も含める(cm)。0は含めない。
        keepMax (bool): Trueは skinCluster の最大インフルエンス数を超えないようにする。
        neighbors (list | None): 計算済みの :func:`smoothing.neighborWeights` の結果(ストロークごとに作り直さない)。

    Raises:
        ValueError: mode が不正、必要なインフルエンスが無い・ロックされている場合。
    """

    def __init__(self, target, mode="smooth", influence=None, source=None, method="uniform", radius=0.0,
                 keepMax=False, neighbors=None):
        if mode not in MODES:
            raise ValueError("mode must be one of " + ", ".join(MODES))
        self.skin = target.requireSkin()
        self.mesh = target.mesh
        self.mode = mode
        self.influences = self.skin.getInfluences()
        self.locked = [influences_module.isLocked(node) for node in self.influences]
        self.column = None
        self.source = None
        if mode in ("remove", "add", "transfer"):
            if influence is None:
                raise ValueError("Click an influence in the list first")
            node = influences_module.find(self.skin, influence)
            if influences_module.isLocked(node):
                raise ValueError("{} is locked".format(node.getNodeName()))
            self.column = self.influences.index(node)
        if mode == "transfer":
            if source is None:
                raise ValueError("Choose the influence to transfer from")
            other = influences_module.find(self.skin, source)
            if other == self.influences[self.column]:
                raise ValueError("Choose two different influences")
            if influences_module.isLocked(other):
                raise ValueError("{} is locked".format(other.getNodeName()))
            self.source = self.influences.index(other)
        self.limit = self.skin.getMaxInfluences() if keepMax else None
        if mode in ("smooth", "sharpen"):
            if neighbors is None:
                neighbors = smoothing.neighborWeights(self.mesh, method, radius)
            self.neighbors = neighbors
        else:
            self.neighbors = None
        count = self.mesh.getNumVertices()
        width = len(self.influences)
        flat = self.skin.getWeights(self.influences)
        self.rows = [[flat[vertex * width + column] for column in range(width)] for vertex in range(count)]
        self.original = {}

    def newRow(self, vertex, value):
        """頂点にブラシの強さ value を当てたときの新しい行を返す(シーンは変えない)。

        Args:
            vertex (int): 頂点の番号。
            value (float): ブラシの強さ(0〜1。ブラシの不透明度と減衰を掛けた値)。

        Returns:
            list[float]: 新しい行(合計1)。
        """
        row = self.rows[vertex]
        value = max(0.0, min(1.0, float(value)))
        if self.mode in ("smooth", "sharpen"):
            strength = value if self.mode == "smooth" else -value
            neighbor_rows = [(self.rows[other], weight) for other, weight in self.neighbors[vertex]]
            return smoothing.smoothRow(row, neighbor_rows, strength, self.locked, self.limit)
        if self.mode == "remove":
            return weights_module.fitColumn(row, self.column, row[self.column] * (1.0 - value), self.locked)
        if self.mode == "add":
            return weights_module.fitColumn(row, self.column, row[self.column] + value * (1.0 - row[self.column]),
                                            self.locked)
        moved = row[self.source] * value
        new = list(row)
        new[self.source] -= moved
        new[self.column] += moved
        return new

    def dab(self, vertex, value):
        """頂点を塗る(Undo なしで書く)。

        Args:
            vertex (int): 頂点の番号。
            value (float): ブラシの強さ。

        Returns:
            None: 値を返さない。
        """
        vertex = int(vertex)
        if vertex not in self.original:
            self.original[vertex] = list(self.rows[vertex])
        self.rows[vertex] = self.newRow(vertex, value)
        weights_module.writeRows(self.skin, self.influences, [vertex], [self.rows[vertex]], fast=True)

    def finish(self):
        """塗った頂点を元へ戻してから、最後の値を1回の Undo で書く。

        Returns:
            int: 塗った頂点の数。
        """
        if not self.original:
            return 0
        vertices = sorted(self.original)
        weights_module.writeRows(self.skin, self.influences, vertices, [self.original[vertex] for vertex in vertices],
                                 fast=True)
        with undoChunk("skinWeightKitPaint"):
            weights_module.writeRows(self.skin, self.influences, vertices, [self.rows[vertex] for vertex in vertices])
        self.original = {}
        return len(vertices)

    def cancel(self):
        """塗った頂点を元へ戻す(Undo に残さない)。

        Returns:
            None: 値を返さない。
        """
        if self.original:
            vertices = sorted(self.original)
            for vertex in vertices:
                self.rows[vertex] = self.original[vertex]
            weights_module.writeRows(self.skin, self.influences, vertices, [self.rows[vertex] for vertex in vertices],
                                     fast=True)
        self.original = {}
