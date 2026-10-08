"""Bifrostで単一入力の親空間追従をカプセル化する。"""

from maya import cmds
from hlib_bifrost.nodes.graph import Graph
from hlib_bifrost.common.mathBuilder import MathBuilder
from hlib.common.undo import isEnabled


class BifrostMatrixFollow:
    """offset/sourceWorld/parentInverse入力からoutputMatrixを返す。"""

    @staticmethod
    def create(name):
        """倍精度行列積グラフを作成する。

        Args:
            name (str): グラフshape名。

        Returns:
            Graph: 入出力がMayaのmatrix属性として公開されたグラフ。
        """
        if isEnabled() or not cmds.about(batch=True):
            raise RuntimeError(
                "Bifrost matrix graph is experimental; use an isolated process with Undo disabled"
            )
        graph = Graph.create(name)
        try:
            root = graph.root
            for port in ("offset", "sourceWorld", "parentInverse"):
                root.add_port(port, "Math::double4x4")
            root.add_port("outputMatrix", "Math::double4x4", output=True)
            # Maya境界で転置されるため、列ベクトルのBifrostでは積を逆順にする。
            MathBuilder(root).matrix_multiply(
                [root.io_port(key) for key in ("parentInverse", "sourceWorld", "offset")]
            ).connect(root.io_port("outputMatrix", output=True))
            return graph
        except Exception:
            graph.delete()
            raise
