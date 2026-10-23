"""行列アトリビュートの値を読み書きする。ノードの変換はTransformで扱う。"""

import maya.api.OpenMaya as om2

from .._core.fastWrite import set_attr, set_plug
from ..common._fast import fast_edit, is_fast
from ..common._safe import safe_edit
from ..decorator import undoChunk
from ..maths import Matrix
from .plug import Plug


class MatrixPlug(Plug):
    """matrixアトリビュート用のPlug。対象アトリビュートの値だけを扱う。"""

    def get(self, *, uiUnits=False):
        """対象アトリビュートの行列値を取得する。

        Args:
            uiUnits (bool): Plug共通の単位指定。行列成分の単位変換は行わない。

        Returns:
            Matrix: 対象アトリビュートの行列の複製。uiUnitsにかかわらず内部単位を維持する。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        self._validate_ui_units(uiUnits)
        self._require_valid()
        return Matrix.fromMMatrix(om2.MFnMatrixData(self._mplug.asMObject()).matrix())

    @fast_edit
    @undoChunk("mlibMatrixPlugSet")
    @safe_edit
    def set(self, value, safe=False, *, uiUnits=False, fast=False):
        """対象の行列アトリビュートへ直接書き込む。所有ノードのTRSへ委譲しない。

        Args:
            value (Matrix | Transformation | Iterable[float]): 設定する4x4行列または変換情報。
            safe (bool): Trueで書込み失敗を抑制し、失敗数を返す。
            uiUnits (bool): Plug共通の単位指定。入力行列の成分単位は変換しない。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。

        Returns:
            MatrixPlug | int: safe=Falseでは自身。safe=Trueでは成功なら0、設定失敗なら1。
                通常/fastとも同じ規則で、非対応fastのNotImplementedErrorは抑制しない。

        Raises:
            TypeError: worldMatrixなどの書込み不可アトリビュートを指定した場合。
            RuntimeError: 所有ノード・アトリビュートが無効、またはMayaが更新を拒否した場合。

        ノード自体の変換にはTransform.setMatrixを使う。
        """
        self._validate_ui_units(uiUnits)
        self._require_valid()
        if self.getLongName() in ("worldMatrix", "wm"):
            raise TypeError("worldMatrix is a computed output and cannot be set")
        matrix = Matrix(value)
        if is_fast():
            set_plug(self._mplug, matrix)
        else:
            set_attr(self.getFullName(), *tuple(matrix), type="matrix")
        return self
