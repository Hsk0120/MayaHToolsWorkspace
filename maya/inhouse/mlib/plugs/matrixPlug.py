"""行列アトリビュートの値を読み書きする。ノードの変換はTransformで扱う。"""

from contextlib import nullcontext

import maya.api.OpenMaya as om2

from ..core.fastWrite import set_attr, set_plug
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

    def set(self, value, safe=False, *, uiUnits=False, fast=False):
        """対象の行列アトリビュートへ直接書き込む。所有ノードのTRSへ委譲しない。

        Matrixへ変換した値を通常はcmds.setAttrへ、fastではOpenMayaへ渡す。
        通常はUndoが有効ならチャンクへ記録し、fastはUndo設定を変更せず記録しない。
        ロック解除や接続の切断は行わない。

        Args:
            value (Matrix | Transformation | Iterable[float]): 設定する4x4行列または変換情報。
                行列の成分順と入力の解釈はMatrixのコンストラクターに従う。
            safe (bool): Trueで書込み失敗を抑制し、失敗数を返す。
            uiUnits (bool): Plug共通の単位指定。入力行列の成分単位は変換しない。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。

        Returns:
            MatrixPlug | int: safe=Falseでは自身。safe=Trueでは成功なら0、対応する失敗なら1。
                setter本体のRuntimeError/TypeError/ValueErrorが対象。行列成分へ分けた部分更新は行わない。
                非対応fastのNotImplementedErrorと、fastがbool以外のTypeErrorは抑制しない。

        Raises:
            TypeError: safe=FalseでworldMatrixを指定した場合など、入力を受け付けられない場合。
            RuntimeError: safe=Falseで所有ノード・アトリビュートが無効、またはMayaが更新を拒否した場合。

        ノード自体の変換にはTransform.setMatrixを使う。更新後の自動ロールバックは行わない。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibMatrixPlugSet"):
            if self.isArray():
                raise TypeError("Set an array element instead of the array plug")
            try:
                self._validate_ui_units(uiUnits)
                self._require_valid()
                if self.getLongName() in ("worldMatrix", "wm"):
                    raise TypeError("worldMatrix is a computed output and cannot be set")
                matrix = Matrix(value)
                if fast:
                    set_plug(self._mplug, matrix)
                else:
                    set_attr(self.getFullName(), *tuple(matrix), type="matrix", fast=False)
            except NotImplementedError:
                raise
            except (RuntimeError, TypeError, ValueError):
                if not safe:
                    raise
                return 1
            return 0 if safe else self
