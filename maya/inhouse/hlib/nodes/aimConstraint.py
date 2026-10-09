"""Maya の aimConstraint を扱う。"""

import math

from .._core.getterAlias import _getter_alias
from ..decorator import undoTransaction
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
        destinations = root.getDestinationsWithConversions()
        result = [(root, destination) for destination in destinations]
        for axis in "XYZ":
            source = self.getPlug("constraintRotate" + axis)
            for destination in source.getDestinationsWithConversions():
                if destination.isChild() and destination.getParent() in destinations:
                    continue
                result.append((source, destination))
        return result

    def settingPlugs(self):
        """値として保存する標準設定候補を取得する。接続の有無で除外しない。

        Rest Rotate、Offset、Aim/Up/World Up Vector、World Up Type、
        enableRestPosition、useOldOffsetCalculationを対象とする。
        worldUpMatrix等の行列入力やウェイトは含めない。ウェイトはweightPlugsを使う。

        Returns:
            list[Plug]: ベクトル・角度はXYZの子アトリビュートで返す。
        """
        attrs = [prefix + axis for prefix in (
            "restRotate", "offset", "aimVector", "upVector", "worldUpVector") for axis in "XYZ"]
        attrs.extend(("worldUpType", "enableRestPosition", "useOldOffsetCalculation"))
        return [self.getPlug(attr) for attr in attrs]

    def getRestRotate(self):
        """Rest RotateのXYZ設定値をラジアン3値で返す。

        Returns:
            tuple[float, float, float]: 評価済みの設定値。対象の回転ではない。
        """
        return tuple(self.getPlug("restRotate" + axis).get() for axis in "XYZ")

    def setRestRotate(self, value):
        """Rest Rotateだけを設定する。追従状態や対象の回転は直接変更しない。

        Args:
            value (Sequence[float]): XYZの有限なラジアン3値。

        Returns:
            AimConstraint: 自身。
        """
        return self._setAngles("restRotate", value)

    def getOffset(self):
        """OffsetのXYZ設定値をラジアン3値で返す。

        Returns:
            tuple[float, float, float]: 評価済みのOffset。
        """
        return tuple(self.getPlug("offset" + axis).get() for axis in "XYZ")

    def setOffset(self, value):
        """Offsetだけを設定する。Maintain Offsetの再計算は行わない。

        Args:
            value (Sequence[float]): XYZの有限なラジアン3値。

        Returns:
            AimConstraint: 自身。
        """
        return self._setAngles("offset", value)

    def getOutputRotate(self):
        """constraintRotateをその回転順序で取得する。

        Returns:
            EulerRotate: ラジアンの評価出力。自身のTransform回転やワールド回転ではない。
        """
        values = [self.getPlug("constraintRotate" + axis).get() for axis in "XYZ"]
        return EulerRotate(*values, order=int(self.getPlug("constraintRotateOrder").get()))

    @_getter_alias(getRotateConnections)
    def rotateConnections(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getRotateConnections(*args, **kwargs)

    @_getter_alias(getRestRotate)
    def restRotate(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getRestRotate(*args, **kwargs)

    @_getter_alias(getOffset)
    def offset(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOffset(*args, **kwargs)

    @_getter_alias(getOutputRotate)
    def outputRotate(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOutputRotate(*args, **kwargs)

    @undoTransaction("hlib.AimConstraint.setAngles")
    def _setAngles(self, attribute, value):
        """入力・ロックを事前検証し、角度3値を一括更新する。

        Args:
            attribute (str): 更新する複合アトリビュート。
            value (Sequence[float]): ラジアン3値。

        Returns:
            AimConstraint: 自身。

        Raises:
            ValueError: 値が不正、参照・ロック・入力接続がある場合。
        """
        values = tuple(float(component) for component in value)
        if len(values) != 3 or not all(math.isfinite(component) for component in values):
            raise ValueError("角度は有限のラジアン3値を指定してください。")
        parent = self.getPlug(attribute)
        children = [self.getPlug(attribute + axis) for axis in "XYZ"]
        if (self.isLocked() or self.isFromReferencedFile()
                or any(plug.isLocked() or plug.getSourceWithConversion() is not None for plug in [parent] + children)):
            raise ValueError("参照・ロック・入力接続のある設定は変更できません: " + parent.getFullName())
        for plug, component in zip(children, values):
            plug.set(component)
        return self
