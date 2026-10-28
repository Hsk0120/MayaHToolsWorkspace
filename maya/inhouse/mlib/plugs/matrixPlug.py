"""マトリクスアトリビュートの値を読み書きする。ノードの変換はTransformで扱う。"""

import maya.api.OpenMaya as om2

from ..core.attributeType import typed_data
from ..core.fastWrite import set_attr, set_plug
from ..decorator import _require_bool
from ..maths import Matrix
from .plug import Plug


class MatrixPlug(Plug):
    """matrixアトリビュート用のPlug。対象アトリビュートの値だけを扱う。"""

    def get(self, *, uiUnits=False):
        """対象アトリビュートのマトリクス値を取得する。

        Args:
            uiUnits (bool): Plug共通の単位指定。マトリクス成分の単位変換は行わない。

        Returns:
            Matrix | None: 対象アトリビュートのマトリクスの複製。uiUnitsにかかわらず内部単位を維持する。
                値を一度も設定していない ``dataType="matrix"`` (型付きデータ)はNone。
                ``attributeType="matrix"`` は未設定でも既定の単位マトリクスを返す。

        Raises:
            TypeError: uiUnitsがbool以外の場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効、または値を読み取れない場合。
        """
        _require_bool(uiUnits, "uiUnits")
        self._require_valid()
        # 未初期化の型付きデータはasMObjectがkFailureになるため、nullだけをNoneにする。
        data = typed_data(self._mplug)
        if data.isNull():
            return None
        return Matrix.fromMMatrix(om2.MFnMatrixData(data).matrix())

    def _set_value(self, value, *, uiUnits=False, fast=False):
        """マトリクスアトリビュートへ直接設定する。TransformのTRSは操作しない。

        骨格は :meth:`Plug.set`。worldMatrixは計算出力のため拒否する。ロック解除・入力切断は行わない。
        safe=Trueの失敗は成分別に再試行せず1を返す。

        Args:
            value (Matrix | om2.MMatrix | sequence): Matrix(value)で変換するマトリクス値。
            uiUnits (bool): 共通フラグとして受理するが、マトリクス成分は換算しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: worldMatrixや不正なUI指定・入力型の場合。
            ValueError: マトリクス値を変換できない場合。
            RuntimeError: 参照が無効、またはMayaが書込みを拒否した場合。
        """
        _require_bool(uiUnits, "uiUnits")
        self._require_valid()
        if self.getLongName() in ("worldMatrix", "wm"):
            raise TypeError("worldMatrix is a computed output and cannot be set")
        matrix = Matrix(value)
        if fast:
            set_plug(self._mplug, matrix)
        else:
            set_attr(self.getFullName(), *tuple(matrix), type="matrix", fast=False)
