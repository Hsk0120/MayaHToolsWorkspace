"""接続したcurveの形状情報をMayaで評価する。"""

from ..decorator import _pick_alias
from ..util import _UNSET
from ._calculation import _Calculation
from .abstractBaseCreate import AbstractBaseCreate


class CurveInfo(AbstractBaseCreate):
    """接続したcurveの形状情報をMayaで評価する。"""

    def connectCurve(self, curve, worldSpace=_UNSET, force=_UNSET, *, fast=False, ws=_UNSET, f=_UNSET):
        """形状またはTransformを解決して接続する。

        Args:
            curve (Node | str | MObject | MDagPath): 対象形状。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。短縮名ws。
            force (bool): 接続を置き換えるか。別名 ``f`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            ws (bool): worldSpaceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            CurveInfo: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=True)
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectCurve", fast):
            source = _Calculation.geometry_output(curve, "nurbsCurve", worldSpace)
            source.connectTo(self.getPlug("inputCurve"), force=force, fast=fast)
            return self
