"""行列アトリビュートの値を読み書きする。ノードの変換はTransformで扱う。"""

import maya.api.OpenMaya as om2

from .._core.fastWrite import set_attr, set_plug
from .._core.registry import plug_wrapper
from ..decorators._fast import fast_edit, is_fast
from ..decorators._safe import safe_edit
from ..decorators.undo import undoChunk
from ..maths import Matrix
from .plug import Plug


@plug_wrapper("matrix")
class MatrixPlug(Plug):
    """matrixアトリビュート用のPlug。対象アトリビュートの値だけを扱う。"""

    def get(self):
        """対象アトリビュートの行列値を取得する。

        Returns:
            Matrix: 対象アトリビュートの行列の複製。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        self._require_valid()
        return Matrix.fromMMatrix(om2.MFnMatrixData(self._mplug.asMObject()).matrix())

    @fast_edit
    @undoChunk("hlibMatrixPlugSet")
    @safe_edit
    def set(self, value, safe=False, *, fast=False):
        """対象の行列アトリビュートへ直接書き込む。所有ノードのTRSへ委譲しない。

        Args:
            safe (bool): Trueで書込み失敗を抑制し、失敗数を返す。
            value (Matrix | Transformation | Iterable[float]): 設定する4x4行列または変換情報。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。

        Returns:
            MatrixPlug | int: 自身。safe=Trueでは失敗した成分数。

        Raises:
            TypeError: worldMatrixなどの書込み不可アトリビュートを指定した場合。
            RuntimeError: 所有ノード・アトリビュートが無効、またはMayaが更新を拒否した場合。

        ノード自体の変換にはTransform.setMatrixを使う。
        """
        self._require_valid()
        if self.getLongName() in ("worldMatrix", "wm"):
            raise TypeError("worldMatrix is a computed output and cannot be set")
        matrix = Matrix(value)
        if is_fast():
            set_plug(self._mplug, matrix)
        else:
            set_attr(self.getFullName(), *tuple(matrix), type="matrix")
        return self
