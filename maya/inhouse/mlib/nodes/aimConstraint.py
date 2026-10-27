"""Maya の aimConstraint を扱う。"""

import math
from contextlib import nullcontext

from ..decorator import undoChunk
from ..maths import EulerRotate
from .constraint import Constraint


class AimConstraint(Constraint):
    """指定ターゲットへ向ける aimConstraint ラッパー。"""

    def getRotateConnections(self):
        """回転出力の直接接続を取得する。下流の探索や対象の選別は行わない。

        Returns:
            list[tuple[Plug, Plug]]: 接続元と接続先。複合接続は親のペアのみ。
        """
        root = self.getPlug("constraintRotate")
        destinations = root.getDestinations(skipConversionNodes=False)
        result = [(root, destination) for destination in destinations]
        for axis in "XYZ":
            source = self.getPlug("constraintRotate" + axis)
            for destination in source.getDestinations(skipConversionNodes=False):
                if destination.isChild() and destination.getParent() in destinations:
                    continue
                result.append((source, destination))
        return result

    def getRestRotate(self):
        """Rest RotateのXYZ設定値をラジアン3値で返す。

        Returns:
            tuple[float, float, float]: 評価済みの設定値。対象の回転ではない。
        """
        return tuple(self.getPlug("restRotate" + axis).get() for axis in "XYZ")

    def setRestRotate(self, value, *, fast=False):
        """Rest Rotateだけを設定する。追従状態や対象の回転は直接変更しない。

        Args:
            value (Sequence[float]): XYZの有限なラジアン3値。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AimConstraint: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 値が不正、参照・ロック・入力接続がある場合。
        """
        return self._set_angles("restRotate", value, fast=fast)

    def getOffset(self):
        """OffsetのXYZ設定値をラジアン3値で返す。

        Returns:
            tuple[float, float, float]: 評価済みのOffset。
        """
        return tuple(self.getPlug("offset" + axis).get() for axis in "XYZ")

    def setOffset(self, value, *, fast=False):
        """Offsetだけを設定する。Maintain Offsetの再計算は行わない。

        Args:
            value (Sequence[float]): XYZの有限なラジアン3値。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AimConstraint: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 値が不正、参照・ロック・入力接続がある場合。
        """
        return self._set_angles("offset", value, fast=fast)

    def getOutputRotate(self):
        """constraintRotateをその回転順序で取得する。

        Returns:
            EulerRotate: ラジアンの評価出力。自身のTransform回転やワールド回転ではない。
        """
        values = [self.getPlug("constraintRotate" + axis).get() for axis in "XYZ"]
        return EulerRotate(*values, order=int(self.getPlug("constraintRotateOrder").get()))

    def _set_angles(self, attribute, value, fast=False):
        """入力・ロックを事前検証し、角度3値を一括更新する。

        検証はすべて書込み前に行う。通常はUndo 1回で戻せるチャンクにまとめ、
        fast=TrueはOpenMayaで直接更新する(Undoなし)。

        Args:
            attribute (str): 更新する複合アトリビュート。
            value (Sequence[float]): ラジアン3値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            AimConstraint: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 値が不正、参照・ロック・入力接続がある場合。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibAimConstraintSetAngles"):
            values = tuple(float(component) for component in value)
            if len(values) != 3 or not all(math.isfinite(component) for component in values):
                raise ValueError("角度は有限のラジアン3値を指定してください。")
            parent = self.getPlug(attribute)
            children = [self.getPlug(attribute + axis) for axis in "XYZ"]
            if (self.isLocked() or self.isFromReferencedFile()
                    or any((plug.isLocked() or plug.getSource(skipConversionNodes=False) is not None
                            for plug in [parent] + children))):
                raise ValueError("参照・ロック・入力接続のある設定は変更できません: " + parent.getFullName())
            for plug, component in zip(children, values):
                plug.set(component, fast=fast)
            return self
