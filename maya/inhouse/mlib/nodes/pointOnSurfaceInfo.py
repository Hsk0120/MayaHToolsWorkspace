"""接続したsurfaceの形状情報をMayaで評価する。"""

from .._core.flags import flag_aliases
from ..common._fast import fast_edit
from ..decorator import undoChunk
from ..maths import Vector
from ._calculation import _Calculation
from .abstractBaseCreate import AbstractBaseCreate


class PointOnSurfaceInfo(AbstractBaseCreate):
    """接続したsurfaceの形状情報をMayaで評価する。"""

    @flag_aliases(ws="worldSpace", f="force")
    @undoChunk("mlibCalculationEdit")
    def connectSurface(self, surface, worldSpace=True, force=False):
        """形状またはTransformを解決して接続する。

        Args:
            surface (Node | str | MObject | MDagPath): 対象形状。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            force (bool): 接続を置き換えるか。 別名 ``f`` も使用可能。

        Returns:
            PointOnSurfaceInfo: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        source = _Calculation.geometry_output(surface, "nurbsSurface", worldSpace)
        source.connectTo(self.getPlug("inputSurface"), force=force)
        return self

    def getParameters(self):
        """現在のUVパラメーターを取得する。

        Returns:
            tuple[float, float]: U/V。
        """
        return self.getPlug("parameterU").get(), self.getPlug("parameterV").get()

    @fast_edit
    @undoChunk("mlibCalculationEdit")
    def setParameters(self, u, v, percentage=False, *, fast=False):
        """UVと百分率モードを設定する。

        Args:
            u (float): Uパラメーター。
            v (float): Vパラメーター。
            percentage (bool): 0～1の範囲を使用するか。
            fast (bool): TrueはUndoなし。

        Returns:
            PointOnSurfaceInfo: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        u, v = _Calculation.scalar(u), _Calculation.scalar(v)
        percentage = _Calculation.boolean(percentage)
        if percentage and not (0 <= u <= 1 and 0 <= v <= 1):
            raise ValueError("percentage parameters must be in 0..1")
        self.getPlug("turnOnPercentage").set(percentage)
        self.getPlug("parameterU").set(u)
        self.getPlug("parameterV").set(v)
        return self

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

    def getTangent(self, direction="u", normalized=True):
        """UまたはV方向の接線を取得する。

        Args:
            direction (str): u/v。
            normalized (bool): 単位ベクトルにするか。

        Returns:
            Vector: 接線。
        """
        if direction not in ("u", "v"):
            raise ValueError("direction must be u or v")
        _Calculation.boolean(normalized)
        return Vector(self.getPlug(("normalizedTangent" if normalized else "tangent") + direction.upper()).get())
