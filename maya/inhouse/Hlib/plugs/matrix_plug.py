"""matrix attribute plug wrapper."""

import maya.cmds as cmds

from ..core.registry import plug_wrapper
from ..maths import Matrix
from .plug import Plug


@plug_wrapper("matrix")
class MatrixPlug(Plug):
    """matrix 属性用の Plug。値は Hlib.maths.Matrix として扱う。"""

    def get(self, ws=False):
        """行列値を Matrix として取得する。

        Args:
            ws (bool): ``True`` でワールド空間の行列を取得する。

        Returns:
            Matrix: 属性値。
        """
        if ws:
            return self.node.get_matrix(ws=True)
        return Matrix(cmds.getAttr(self.full_name))

    def set(self, value, ws=False):
        """行列値を設定する。

        Args:
            value (Matrix | Iterable[float]): 16要素の行列値。

        Returns:
            Plug: 自身。
        """
        if self.attribute in ("worldMatrix", "wm"):
            raise TypeError("worldMatrix is a computed output and cannot be set")
        if hasattr(self.node, "set_matrix"):
            self.node.set_matrix(Matrix(value), ws=ws)
            return self
        cmds.setAttr(self.full_name, *tuple(value), type="matrix")
        return self
