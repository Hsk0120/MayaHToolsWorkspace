"""接続したcurveの形状情報をMayaで評価する。"""

from .._core.flags import flag_aliases
from .._core.registry import node_wrapper
from ..decorators.undo import undoChunk
from ._calculation import _Calculation
from .abstractBaseCreate import AbstractBaseCreate


@node_wrapper("curveInfo")
class CurveInfo(AbstractBaseCreate):
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
            CurveInfo: 自身。

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
            CurveInfo: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        source = _Calculation.geometryOutput(curve, "nurbsCurve", worldSpace)
        source.connectTo(self.getInputPlug(), force=force)
        return self

    def getOutputPlug(self):
        """計算結果の接続用Plugを取得する。
        Returns:
            Plug: 出力参照。
        """
        return self.getPlug("arcLength")

    def getResult(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            float: 計算結果。
        """
        return self.getOutputPlug().get()

    def getArcLength(self):
        """接続された空間でのカーブ長を取得する。
        Returns:
            float: カーブ長。
        """
        return self.getOutputPlug().get()
