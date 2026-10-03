"""接続したsurfaceの形状情報をMayaで評価する。"""

from .._core.registry import node_wrapper
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from ..maths import Vector
from ._calculation import _Calculation
from .abstractBaseCreate import AbstractBaseCreate


@node_wrapper("pointOnSurfaceInfo")
class PointOnSurfaceInfo(AbstractBaseCreate):
    """接続したsurfaceの形状情報をMayaで評価する。"""

    def inputPlug(self):
        """形状データの入力を取得する。
        Returns:
            Plug: 入力参照。
        """
        return self.plug("inputSurface")

    @undoChunk("hlibCalculationEdit")
    def connectInput(self, source, force=False):
        """形状データPlugを入力へ接続する。

        Args:
            source (Plug | str | MPlug): local/worldSpace等の接続元。
            force (bool): 接続を置き換えるか。
        Returns:
            PointOnSurfaceInfo: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.inputPlug, force=force)
        return self

    @undoChunk("hlibCalculationEdit")
    def connectSurface(self, surface, world_space=True, force=False):
        """形状またはTransformを解決して接続する。

        Args:
            surface (Node | str | MObject | MDagPath): 対象形状。
            world_space (bool): Trueはワールド空間、Falseはオブジェクト空間。
            force (bool): 接続を置き換えるか。
        Returns:
            PointOnSurfaceInfo: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        source = _Calculation.geometryOutput(surface, "nurbsSurface", world_space)
        source.connect(self.inputPlug(), force=force)
        return self

    def getParameters(self):
        """現在のUVパラメーターを取得する。
        Returns:
            tuple[float, float]: U/V。
        """
        return self.plug("parameterU").get(), self.plug("parameterV").get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
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
        self.plug("turnOnPercentage").set(percentage)
        self.plug("parameterU").set(u)
        self.plug("parameterV").set(v)
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
        return Vector(self.plug(("normalizedTangent" if normalized else "tangent") + direction.upper()).get())
