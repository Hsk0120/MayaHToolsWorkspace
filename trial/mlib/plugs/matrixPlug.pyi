# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""マトリクスアトリビュートの値を読み書きする。ノードの変換はTransformで扱う。"""

import maya.api.OpenMaya as om2
from ..core.attributeType import _plain_angle_unit, typed_data
from ..core.fastWrite import set_attr, set_plug
from ..decorator import _require_bool
from ..maths import Matrix
from .plug import Plug
from typing import Any, Sequence



class MatrixPlug(Plug):
    """matrixアトリビュート用のPlug。対象アトリビュートの値だけを扱う。"""
    def get(self, *, unit: str | None = ..., uiUnits: bool = ...) -> Matrix | None:
        """対象アトリビュートのマトリクス値を取得する。

        Args:
            unit (str | None): Plug共通の角度の単位指定。検証だけ行い、マトリクス成分は換算しない。
            uiUnits (bool): Plug共通の単位指定。マトリクス成分の単位変換は行わない。

        Returns:
            Matrix | None: 対象アトリビュートのマトリクスの複製。uiUnitsにかかわらず内部単位を維持する。
                値を一度も設定していない ``dataType="matrix"`` (型付きデータ)はNone。
                ``attributeType="matrix"`` は未設定でも既定の単位マトリクスを返す。

        Raises:
            TypeError: uiUnitsがbool以外、またはunitが文字列・None以外の場合。
            ValueError: unitが未対応の単位名、またはunitとuiUnits=Trueを同時に指定した場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効、または値を読み取れない場合。
        """
        ...
    def _set_value(self, value: Matrix | om2.MMatrix | Sequence[Any], *, uiUnits: bool = ..., fast: bool = ...) -> None:
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
        ...
