"""接続したsurfaceの形状情報をMayaで評価する。"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..maths import Vector
from ..util import _ArgumentError, _UNSET
from ._calculation import _Calculation
from .abstractBaseCreate import AbstractBaseCreate


class PointOnSurfaceInfo(AbstractBaseCreate):
    """pointOnSurfaceInfoノードを参照し、接続したサーフェスの位置・法線・接線を評価する。

    値設定では入力接続を切らない。通常編集はUndo有効時にまとめ、fast=TrueはUndo設定を変えないOM2直接更新（Undoなし）。途中の変更は自動で戻さない。
    """

    def connectSurface(self, surface, worldSpace=_UNSET, force=_UNSET, *, fast=False, ws=_UNSET, f=_UNSET):
        """nurbsSurfaceのlocal/worldSpaceをinputSurfaceへ接続する。

        Args:
            surface (Node | str | MObject | MDagPath): nurbsSurfaceシェイプ、または対応シェイプが1個のTransform。
            worldSpace (bool): 既定Trueは解決したDAGインスタンスのworldSpace、Falseはlocal。
            force (bool): 接続を置き換えるか。 別名 ``f`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            ws (bool): worldSpaceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            PointOnSurfaceInfo: 自身。

        Raises:
            TypeError: fastがbool以外、または対象のシェイプ型またはworldSpaceの型が不正な場合。
            ValueError: Transformの対応シェイプが1個に定まらない場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if f is not _UNSET:
            if force is not _UNSET:
                raise _ArgumentError("Specify only one of 'force' and 'f'")
            force = f
        if worldSpace is _UNSET:
            worldSpace = True
        if force is _UNSET:
            force = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            source = _Calculation.geometry_output(surface, "nurbsSurface", worldSpace)
            source.connectTo(self.getPlug("inputSurface"), force=force, fast=fast)
            return self

    def getParameters(self):
        """現在のUVパラメーターを取得する。

        Returns:
            tuple[float, float]: U/V。
        """
        return self.getPlug("parameterU").get(), self.getPlug("parameterV").get()

    def setParameters(self, u, v, percentage=False, *, fast=False):
        """サーフェスのU/Vパラメーターと0～1モードを設定する。

        入力をすべて検証してから、turnOnPercentage、parameterU、parameterVの順に書く。先行変更は自動で戻さない。

        Args:
            u (float): 有限なU値。percentage=Trueなら0～1。
            v (float): 有限なV値。percentage=Trueなら0～1。
            percentage (bool): 0～1の範囲を使用するか。
            fast (bool): TrueはUndoなし。

        Returns:
            PointOnSurfaceInfo: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            u, v = _Calculation.scalar(u), _Calculation.scalar(v)
            percentage = _Calculation.boolean(percentage)
            if percentage and not (0 <= u <= 1 and 0 <= v <= 1):
                raise ValueError("percentage parameters must be in 0..1")
            self.getPlug("turnOnPercentage").set(percentage, fast=fast)
            self.getPlug("parameterU").set(u, fast=fast)
            self.getPlug("parameterV").set(v, fast=fast)
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
