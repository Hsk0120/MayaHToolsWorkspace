"""行列属性の値を読み書きする。ノードの変換はTransformで扱う。"""

import maya.api.OpenMaya as om2

from ..decorators._fast import fast_edit
from ..decorators.undo import undo_chunk
from .._core.fastWrite import set_attr
from .._core.registry import plug_wrapper
from ..maths import Matrix
from .plug import Plug


@plug_wrapper("matrix")
class MatrixPlug(Plug):
    """matrix属性用のPlug。対象属性の値だけを扱う。"""

    def get(self):
        """対象属性の行列値を取得する。

        Returns:
            Matrix: 対象属性の行列の複製。

        Raises:
            RuntimeError: 所有ノードまたは属性が無効の場合。
        """
        self._require_valid()
        return Matrix.from_mmatrix(om2.MFnMatrixData(self._mplug.asMObject()).matrix())

    @fast_edit
    @undo_chunk("hlibMatrixPlugSet")
    def set(self, value, *, fast=False):
        """対象の行列属性へ直接書き込む。所有ノードのTRSへ委譲しない。

        Args:
            value (Matrix | Iterable[float]): 設定する4x4行列。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。

        Returns:
            MatrixPlug: 自身。

        Raises:
            TypeError: worldMatrixなどの書込み不可属性を指定した場合。
            RuntimeError: 所有ノード・属性が無効、またはMayaが更新を拒否した場合。

        ノード自体の変換にはTransform.set_matrixを使う。
        """
        self._require_valid()
        if self.attribute() in ("worldMatrix", "wm"):
            raise TypeError("worldMatrix is a computed output and cannot be set")
        set_attr(self.full_name(), *tuple(Matrix(value)), type="matrix")
        return self
