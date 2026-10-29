# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の aimConstraint を扱う。"""

import math
from ..core.nodeEdit import require_editable
from ..decorator import _edit_context
from ..maths import EulerRotate
from .constraint import Constraint
from typing import Sequence
from mlib.plugs.plug import Plug



class AimConstraint(Constraint):
    """指定ターゲットへ向ける aimConstraint ラッパー。"""
    def getRotateConnections(self) -> list[tuple[Plug, Plug]]:
        """回転出力の直接接続を取得する。下流の探索や対象の選別は行わない。

        Returns:
            list[tuple[Plug, Plug]]: 接続元と接続先。コンパウンドアトリビュートの接続は親のペアのみ。
        """
        ...
    def getRestRotate(self) -> tuple[float, float, float]:
        """Rest RotateのXYZ設定値をラジアン3値で返す。

        Returns:
            tuple[float, float, float]: 評価済みの設定値。対象の回転ではない。
        """
        ...
    def setRestRotate(self, value: Sequence[float], *, fast: bool = ...) -> AimConstraint:
        """Rest Rotateだけを設定する。追従状態や対象の回転は直接変更しない。

        Args:
            value (Sequence[float]): XYZの有限なラジアン3値。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AimConstraint: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 値が不正な場合。
            RuntimeError: ノードが参照・ロックされている、またはアトリビュートがロック・入力接続されている場合。
        """
        ...
    def getOffset(self) -> tuple[float, float, float]:
        """OffsetのXYZ設定値をラジアン3値で返す。

        Returns:
            tuple[float, float, float]: 評価済みのOffset。
        """
        ...
    def setOffset(self, value: Sequence[float], *, fast: bool = ...) -> AimConstraint:
        """Offsetだけを設定する。Maintain Offsetの再計算は行わない。

        Args:
            value (Sequence[float]): XYZの有限なラジアン3値。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AimConstraint: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 値が不正な場合。
            RuntimeError: ノードが参照・ロックされている、またはアトリビュートがロック・入力接続されている場合。
        """
        ...
    def getOutputRotate(self) -> EulerRotate:
        """constraintRotateをその回転順序で取得する。

        Returns:
            EulerRotate: ラジアンの評価出力。自身のTransform回転やワールド回転ではない。
        """
        ...
    def _set_angles(self, attribute: str, value: Sequence[float], fast: bool = ...) -> AimConstraint:
        """入力・ロックを事前検証し、角度3値を一括更新する。

        検証はすべて書込み前に行う。通常はUndo 1回で戻せるチャンクにまとめ、
        fast=TrueはOpenMayaで直接更新する(Undoなし)。

        Args:
            attribute (str): 更新するコンパウンドアトリビュート。
            value (Sequence[float]): ラジアン3値。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AimConstraint: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 値が不正な場合。
            RuntimeError: ノードが参照・ロックされている、またはアトリビュートがロック・入力接続されている場合。
        """
        ...
