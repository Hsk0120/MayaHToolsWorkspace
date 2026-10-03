"""移動・回転をブレンドする。Euler/Quaternion補間を選択できる。"""

from .._core.registry import node_wrapper
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from ._calculation import _Calculation
from .node import Node


@node_wrapper("pairBlend")
class PairBlend(Node):
    """移動・回転をブレンドする。Euler/Quaternion補間を選択できる。"""

    def weightPlug(self):
        """ブレンドウェイトのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("weight")

    def getWeight(self):
        """ブレンドウェイトの評価値を取得する。
        Returns:
            float: 現在の値。
        """
        return self.weightPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setWeight(self, value, *, fast=False):
        """ブレンドウェイトへ定数値を設定する。

        Args:
            value (float): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.scalar, self.weightPlug)
        return self

    @undoChunk("hlibCalculationEdit")
    def connectWeight(self, source, force=False):
        """ブレンドウェイトへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PairBlend: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.weightPlug, force=force)
        return self

    def getRotationInterpolation(self):
        """現在のモード名を取得する。
        Returns:
            str: euler, quaternion。
        """
        return _Calculation.enumName(self.plug("rotInterpolation"), ('euler', 'quaternion'))

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setRotationInterpolation(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): euler, quaternion、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enumValue(mode, ('euler', 'quaternion'))
        self.plug("rotInterpolation").set(value)
        return self

    def getRotateOrder(self):
        """現在のモード名を取得する。
        Returns:
            str: xyz, yzx, zxy, xzy, yxz, zyx。
        """
        return _Calculation.enumName(self.plug("rotateOrder"), ('xyz', 'yzx', 'zxy', 'xzy', 'yxz', 'zyx'))

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setRotateOrder(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): xyz, yzx, zxy, xzy, yxz, zyx、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enumValue(mode, ('xyz', 'yzx', 'zxy', 'xzy', 'yxz', 'zyx'))
        self.plug("rotateOrder").set(value)
        return self

    def translatePlug(self, index):
        """translate入力（cm）のPlugを取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug(f"inTranslate{_Calculation.index(index, (1, 2))}")

    def getTranslation(self, index):
        """translate入力（cm）の評価値を取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.translatePlug(index).get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setTranslation(self, index, value, *, fast=False):
        """translate入力（cm）へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.translatePlug, index)
        return self

    @undoChunk("hlibCalculationEdit")
    def connectTranslate(self, index, source, force=False):
        """translate入力（cm）へ接続する。

        Args:
            index (int): 入力番号1または2。
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PairBlend: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.translatePlug, index, force=force)
        return self

    def rotatePlug(self, index):
        """rotate入力（rad）のPlugを取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug(f"inRotate{_Calculation.index(index, (1, 2))}")

    def getRotation(self, index):
        """rotate入力（rad）の評価値を取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.rotatePlug(index).get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setRotation(self, index, value, *, fast=False):
        """rotate入力（rad）へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.rotatePlug, index)
        return self

    @undoChunk("hlibCalculationEdit")
    def connectRotate(self, index, source, force=False):
        """rotate入力（rad）へ接続する。

        Args:
            index (int): 入力番号1または2。
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PairBlend: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.rotatePlug, index, force=force)
        return self

    def outputPlug(self, kind="translate"):
        """移動または回転の出力を取得する。

        Args:
            kind (str): translate/rotate。
        Returns:
            Plug: 出力参照。
        """
        if kind not in ("translate", "rotate"):
            raise ValueError("kind must be translate or rotate")
        return self.plug("out" + kind.title())

    def result(self, kind="translate"):
        """移動または回転の評価値を取得する。

        Args:
            kind (str): translate/rotate。
        Returns:
            tuple[float, float, float]: 移動はcm、回転はrad。
        """
        return tuple(self.outputPlug(kind).get())
