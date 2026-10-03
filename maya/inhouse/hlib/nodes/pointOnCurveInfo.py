"""接続したcurveの形状情報をMayaで評価する。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ..maths import Vector
from ._calculation import _Calculation
from .abstractBaseCreate import AbstractBaseCreate


@node_wrapper("pointOnCurveInfo")
class PointOnCurveInfo(AbstractBaseCreate):
    """接続したcurveの形状情報をMayaで評価する。"""

    def inputPlug(self):
        """形状データの入力を取得する。
        Returns:
            Plug: 入力参照。
        """
        return self.plug("inputCurve")

    @undo_chunk("hlibCalculationEdit")
    def connectInput(self, source, force=False):
        """形状データPlugを入力へ接続する。

        Args:
            source (Plug | str | MPlug): local/worldSpace等の接続元。
            force (bool): 接続を置き換えるか。
        Returns:
            PointOnCurveInfo: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.inputPlug, force=force)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectCurve(self, curve, world_space=True, force=False):
        """形状またはTransformを解決して接続する。

        Args:
            curve (Node | str | MObject | MDagPath): 対象形状。
            world_space (bool): Trueはワールド空間、Falseはオブジェクト空間。
            force (bool): 接続を置き換えるか。
        Returns:
            PointOnCurveInfo: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        source = _Calculation.geometryOutput(curve, "nurbsCurve", world_space)
        source.connect(self.inputPlug(), force=force)
        return self

    def getParameter(self):
        """現在のパラメーターを取得する。
        Returns:
            float: 現在値。
        """
        return self.plug("parameter").get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def setParameter(self, value, percentage=False, *, fast=False):
        """パラメーターと百分率モードを設定する。

        Args:
            value (float): パラメーター。percentage=Trueなら0～1。
            percentage (bool): 0～1の範囲を使用するか。
            fast (bool): TrueはUndoなし。
        Returns:
            PointOnCurveInfo: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.scalar(value)
        percentage = _Calculation.boolean(percentage)
        if percentage and not 0 <= value <= 1:
            raise ValueError("percentage parameter must be in 0..1")
        self.plug("turnOnPercentage").set(percentage)
        self.plug("parameter").set(value)
        return self

    def getPercentage(self):
        """百分率モードを取得する。
        Returns:
            bool: 0～1のパラメーターを使うか。
        """
        return self.plug("turnOnPercentage").get()

    def getPosition(self):
        """接続された空間での位置を取得する。
        Returns:
            Vector: XYZ位置。
        """
        return Vector(self.plug("position").get())

    def getNormal(self, normalized=True):
        """法線を取得する。

        Args:
            normalized (bool): 単位ベクトルにするか。
        Returns:
            Vector: 法線。
        """
        _Calculation.boolean(normalized)
        return Vector(self.plug("normalizedNormal" if normalized else "normal").get())

    def getTangent(self, normalized=True):
        """接線を取得する。

        Args:
            normalized (bool): 単位ベクトルにするか。
        Returns:
            Vector: 接線。
        """
        _Calculation.boolean(normalized)
        return Vector(self.plug("normalizedTangent" if normalized else "tangent").get())
