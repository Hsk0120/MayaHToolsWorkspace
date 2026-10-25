"""マトリクスアトリビュートの値を読み書きする。ノードの変換はTransformで扱う。"""

from contextlib import nullcontext

import maya.api.OpenMaya as om2

from ..core.fastWrite import set_attr, set_plug
from ..decorator import undoChunk
from ..maths import Matrix
from .plug import Plug


class MatrixPlug(Plug):
    """matrixアトリビュート用のPlug。対象アトリビュートの値だけを扱う。"""

    def get(self, *, uiUnits=False):
        """対象アトリビュートのマトリクス値を取得する。

        Args:
            uiUnits (bool): Plug共通の単位指定。マトリクス成分の単位変換は行わない。

        Returns:
            Matrix: 対象アトリビュートのマトリクスの複製。uiUnitsにかかわらず内部単位を維持する。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        self._validate_ui_units(uiUnits)
        self._require_valid()
        return Matrix.fromMMatrix(om2.MFnMatrixData(self._mplug.asMObject()).matrix())

    def set(self, value, safe=False, *, uiUnits=False, fast=False):
        """マトリクスアトリビュートへ直接設定する。TransformのTRSは操作しない。

        worldMatrixは計算出力のため拒否する。ロック解除・入力切断は行わない。
        通常処理はUndo有効時に記録し、fastはUndo設定を変えず直接更新する。

        Args:
            value (Matrix | Transformation | om2.MMatrix | sequence): Matrix(value)で変換するマトリクス値。
            safe (bool): Trueは対応する書込み失敗を0/1で返す。既定Falseは例外を送出する。
            uiUnits (bool): 共通フラグとして受理するが、マトリクス成分は換算しない。
            fast (bool): 既定Falseはcmds.setAttr。TrueはOpenMaya直接更新でUndoなし。

        Returns:
            MatrixPlug | int: 通常は自身。safe=Trueは成功0、参照検査・マトリクスへの変換・UI指定・
                書込みのRuntimeError/TypeError/ValueErrorを1にする。成分別の部分更新はしない。

        Raises:
            TypeError: fastがbool以外、または配列全体を指定した場合。safe=Trueでも拒否する。
                safe=FalseではworldMatrixや不正なUI指定・入力型も拒否する。
            ValueError: safe=Falseでマトリクス値を変換できない場合。
            RuntimeError: safe=Falseで参照が無効、またはMayaが書込みを拒否した場合。
            NotImplementedError: fastで未対応の条件。safe=Trueでも抑制しない。

        Note:
            完了済みの変更は自動では戻さない。
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
