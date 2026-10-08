"""接続したcurveの形状情報をMayaで評価する。"""

from .._core.flags import flag_aliases
from .._core.getterAlias import _getter_alias
from ..common._fast import fast_edit
from ..decorator import undoChunk
from ..maths import Vector
from ._calculation import _Calculation
from .abstractBaseCreate import AbstractBaseCreate


class PointOnCurveInfo(AbstractBaseCreate):
    """接続したcurveの形状情報をMayaで評価する。"""

    def getInputPlug(self):
        """形状データの入力を取得する。
        Returns:
            Plug: 入力参照。
        """
        return self.getPlug("inputCurve")

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectInput(self, source, force=False):
        """形状データPlugを入力へ接続する。

        Args:
            source (Plug | str | MPlug): local/worldSpace等の接続元。 別名 ``src`` も使用可能。
            force (bool): 接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            PointOnCurveInfo: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getInputPlug, force=force)
        return self

    @flag_aliases(ws="worldSpace", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectCurve(self, curve, worldSpace=True, force=False):
        """形状またはTransformを解決して接続する。

        Args:
            curve (Node | str | MObject | MDagPath): 対象形状。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            force (bool): 接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            PointOnCurveInfo: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        source = _Calculation.geometryOutput(curve, "nurbsCurve", worldSpace)
        source.connectTo(self.getInputPlug(), force=force)
        return self

    def getParameter(self):
        """現在のパラメーターを取得する。
        Returns:
            float: 現在値。
        """
        return self.getPlug("parameter").get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
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
        self.getPlug("turnOnPercentage").set(percentage)
        self.getPlug("parameter").set(value)
        return self

    def getPercentage(self):
        """百分率モードを取得する。
        Returns:
            bool: 0～1のパラメーターを使うか。
        """
        return self.getPlug("turnOnPercentage").get()

    def getPosition(self):
        """接続された空間での位置を取得する。
        Returns:
            Vector: XYZ位置。
        """
        return Vector(self.getPlug("position").get())

    def getNormal(self, normalized=True):
        """法線を取得する。

        Args:
            normalized (bool): 単位ベクトルにするか。
        Returns:
            Vector: 法線。
        """
        _Calculation.boolean(normalized)
        return Vector(self.getPlug("normalizedNormal" if normalized else "normal").get())

    def getTangent(self, normalized=True):
        """接線を取得する。

        Args:
            normalized (bool): 単位ベクトルにするか。
        Returns:
            Vector: 接線。
        """
        _Calculation.boolean(normalized)
        return Vector(self.getPlug("normalizedTangent" if normalized else "tangent").get())

    @_getter_alias(getInputPlug)
    def inputPlug(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getInputPlug(*args, **kwargs)

    @_getter_alias(getParameter)
    def parameter(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getParameter(*args, **kwargs)

    @_getter_alias(getPercentage)
    def percentage(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPercentage(*args, **kwargs)

    @_getter_alias(getPosition)
    def position(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPosition(*args, **kwargs)

    @_getter_alias(getNormal)
    def normal(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNormal(*args, **kwargs)

    @_getter_alias(getTangent)
    def tangent(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getTangent(*args, **kwargs)
