"""接続したcurveの形状情報をMayaで評価する。"""

from ..decorator import _pick_alias
from ..maths import Vector
from ..util import _UNSET
from ._calculation import _Calculation
from .abstractBaseCreate import AbstractBaseCreate


class PointOnCurveInfo(AbstractBaseCreate):
    """pointOnCurveInfoノードを参照し、接続したカーブの位置・法線・接線を評価する。

    値設定では入力接続を切らない。通常編集はUndo有効時にまとめ、fast=TrueはUndo設定を変えないOM2直接更新(Undoなし)。途中の変更は自動で戻さない。
    """

    def connectCurve(self, curve, worldSpace=_UNSET, force=_UNSET, *, fast=False, ws=_UNSET, f=_UNSET):
        """nurbsCurveのlocal/worldSpaceをinputCurveへ接続する。

        Args:
            curve (Node | str | MObject | MDagPath): nurbsCurveシェイプ、または対応シェイプが1個のTransform。
            worldSpace (bool): Trueは解決したDAGインスタンスのワールド空間、Falseはローカル空間。既定True。
            force (bool): 接続を置き換えるか。別名 ``f`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            ws (bool): worldSpaceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            PointOnCurveInfo: 自身。

        Raises:
            TypeError: fastがbool以外、または対象のシェイプ型またはworldSpaceの型が不正な場合。
            ValueError: Transformの対応シェイプが1個に定まらない場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=True)
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectCurve", fast):
            source = _Calculation.geometry_output(curve, "nurbsCurve", worldSpace)
            source.connectTo(self.getPlug("inputCurve"), force=force, fast=fast)
            return self

    def setParameter(self, value, percentage=False, *, fast=False):
        """カーブのパラメーターと0～1モードを設定する。

        入力をすべて検証してから、turnOnPercentage、parameterの順に書く。途中の書込み失敗で先行変更は戻さない。

        Args:
            value (float): 有限なパラメーター。percentage=Trueなら0～1。
            percentage (bool): 0～1の範囲を使用するか。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            PointOnCurveInfo: 自身。
        """
        with _Calculation.edit_context(self, "setParameter", fast):
            value = _Calculation.scalar(value)
            percentage = _Calculation.boolean(percentage)
            if percentage and not 0 <= value <= 1:
                raise ValueError("percentage parameter must be in 0..1")
            self.getPlug("turnOnPercentage").set(percentage, fast=fast)
            self.getPlug("parameter").set(value, fast=fast)
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

    def getTangent(self, normalized=True):
        """接線を取得する。

        Args:
            normalized (bool): 単位ベクトルにするか。

        Returns:
            Vector: 接線。
        """
        _Calculation.boolean(normalized)
        return Vector(self.getPlug("normalizedTangent" if normalized else "tangent").get())
