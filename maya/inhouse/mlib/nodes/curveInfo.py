"""接続したcurveの形状情報をMayaで評価する。"""

from .._core.flags import flag_aliases
from ..decorator import undoChunk
from ._calculation import _Calculation
from .abstractBaseCreate import AbstractBaseCreate


class CurveInfo(AbstractBaseCreate):
    """接続したcurveの形状情報をMayaで評価する。"""

    @flag_aliases(ws="worldSpace", f="force")
    @undoChunk("mlibCalculationEdit")
    def connectCurve(self, curve, worldSpace=True, force=False):
        """形状またはTransformを解決して接続する。

        Args:
            curve (Node | str | MObject | MDagPath): 対象形状。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            force (bool): 接続を置き換えるか。 別名 ``f`` も使用可能。

        Returns:
            CurveInfo: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        source = _Calculation.geometry_output(curve, "nurbsCurve", worldSpace)
        source.connectTo(self.getPlug("inputCurve"), force=force)
        return self
