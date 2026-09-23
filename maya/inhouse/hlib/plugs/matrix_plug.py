"""行列属性と所有ノードの変換行列を扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .._core.registry import plug_wrapper
from ..maths import Matrix
from .plug import Plug


@plug_wrapper("matrix")
class MatrixPlug(Plug):
    """matrix 属性用の Plug。値は hlib.maths.Matrix として扱う。"""

    def get(self, ws=False):
        """行列値を Matrix として取得する。

        Args:
            ws (bool): True ならプラグ自身の値ではなく所有ノードの get_matrix(ws=True) を呼ぶ。

        Returns:
            Matrix: 属性行列、または所有ノードのワールド行列。

        Raises:
            AttributeError: ws=True で所有ノードに get_matrix がない場合。
        """
        if ws:
            return self.node.get_matrix(ws=True)
        return Matrix(om2.MFnMatrixData(self._mplug.asMObject()).matrix())

    def set(self, value, ws=False):
        """行列値を設定する。

        所有ノードに set_matrix があれば、対象属性名にかかわらずノードの変換を更新する。なければ対象プラグへ type="matrix" で直接書き込む。この直接書き込み経路は独自の Undo チャンクを作らない。

        Args:
            value (Matrix | Iterable[float] | Iterable[Iterable[float]]): 設定する行列。ノードへ委譲できない場合は16要素の平坦な入力を指定する。
            ws (bool): 所有ノードの set_matrix へ渡す空間指定。直接 setAttr する場合は無視する。

        Returns:
            MatrixPlug: 自身。

        Raises:
            TypeError: worldMatrix 属性への書き込みの場合。
        """
        if self.attribute in ("worldMatrix", "wm"):
            raise TypeError("worldMatrix is a computed output and cannot be set")
        if hasattr(self.node, "set_matrix"):
            self.node.set_matrix(Matrix(value), ws=ws)
            return self
        cmds.setAttr(self.full_name, *tuple(value), type="matrix")
        return self
