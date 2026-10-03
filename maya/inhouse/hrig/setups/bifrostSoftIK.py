"""BifrostでSoft IKの距離減衰を構成する。"""

import math
from hlib.decorators.undo import undoTransaction
from hlib_bifrost.nodes.graph import Graph
from hlib_bifrost.utils.mathBuilder import MathBuilder


class SoftIK:
    """モジュール階層に依存しない距離・softness・ratioグラフ。"""

    @classmethod
    @undoTransaction("hlib_bifrost.SoftIK.create")
    def create(cls, name, length):
        """同一距離単位の入力から位置倍率を計算する。

        Args:
            name (str): 希望するshape名。
            length (float): 正の固定チェーン長。

        Returns:
            Graph: distance/softness入力とratio出力。

        Note:
            ゼロ除算を避けるためdistance/softnessを1e-6以上へ制限する。
            この微小領域は標準DG版と厳密一致しない。
        """
        if not math.isfinite(length) or length <= 0:
            raise ValueError("length must be positive and finite")
        graph = Graph.create(name)
        try:
            return cls._populate(graph, length)
        except Exception:
            graph.delete()
            raise

    @staticmethod
    def _populate(graph, length):
        """検証済みパラメータを演算へ展開する。

        Args:
            graph (Graph): 追加先グラフ。
            length (float): 骨長。

        Returns:
            Graph: 構築済みグラフ。
        """
        root = graph.root
        root.add_port("distance", "float")
        root.add_port("softness", "float")
        root.add_port("ratio", "float", output=True)
        builder = MathBuilder(root)
        distance = builder.operation("max", (root.io_port("distance"), 0.000001), "maximum")
        soft = builder.clamp(root.io_port("softness"), 0.000001, length)
        threshold = builder.operation("subtract", (length, soft))
        excess = builder.operation(
            "max", (builder.operation("subtract", (distance, threshold)), 0), "maximum"
        )
        exponent = builder.operation("divide", (builder.operation("multiply", (-1, excess)), soft))
        power = root.add_node("BifrostGraph,Core::Math,power")
        builder.feed(math.e, power.port("base"))
        builder.feed(exponent, power.port("exponent"))
        softened = builder.operation(
            "add",
            (
                threshold,
                builder.operation(
                    "multiply", (soft, builder.operation("subtract", (1, power.port("power"))))
                ),
            ),
        )
        limited = builder.operation("min", (distance, softened), "minimum")
        builder.operation("divide", (limited, distance)).connect(root.io_port("ratio", output=True))
        return graph
