"""接続したcurveの形状情報をMayaで評価する。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ._calculation import _Calculation
from .abstractBaseCreate import AbstractBaseCreate


@node_wrapper("curveInfo")
class CurveInfo(AbstractBaseCreate):
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
            CurveInfo: 自身。

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
            CurveInfo: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        source = _Calculation.geometryOutput(curve, "nurbsCurve", world_space)
        source.connect(self.inputPlug(), force=force)
        return self

    def outputPlug(self):
        """計算結果の接続用Plugを取得する。
        Returns:
            Plug: 出力参照。
        """
        return self.plug("arcLength")

    def result(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            float: 計算結果。
        """
        return self.outputPlug().get()

    def arcLength(self):
        """接続された空間でのカーブ長を取得する。
        Returns:
            float: カーブ長。
        """
        return self.outputPlug().get()
