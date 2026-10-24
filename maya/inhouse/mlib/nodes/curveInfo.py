"""接続したcurveの形状情報をMayaで評価する。"""

from ..decorator import undoChunk
from ..util import _ArgumentError, _UNSET
from ._calculation import _Calculation
from .abstractBaseCreate import AbstractBaseCreate


class CurveInfo(AbstractBaseCreate):
    """接続したcurveの形状情報をMayaで評価する。"""

    def connectCurve(self, curve, worldSpace=_UNSET, force=_UNSET, *, ws=_UNSET, f=_UNSET):
        """形状またはTransformを解決して接続する。

        Args:
            curve (Node | str | MObject | MDagPath): 対象形状。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            force (bool): 接続を置き換えるか。 別名 ``f`` も使用可能。
            ws (bool): worldSpaceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            CurveInfo: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
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
        with undoChunk("mlibCalculationEdit"):
            source = _Calculation.geometry_output(curve, "nurbsCurve", worldSpace)
            source.connectTo(self.getPlug("inputCurve"), force=force)
            return self
