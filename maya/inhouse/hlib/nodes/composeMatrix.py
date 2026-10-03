"""移動・回転・スケール・シアーから行列を構築する。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undoChunk
from ..decorators._fast import fast_edit
from ..maths import Matrix
from ._calculation import _Calculation
from .node import Node


@node_wrapper("composeMatrix")
class ComposeMatrix(Node):
    """移動・回転・スケール・シアーから行列を構築する。"""

    def translatePlug(self):
        """translate入力（移動はcm）のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('inputTranslate')

    def getTranslation(self):
        """translate入力（移動はcm）の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.translatePlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setTranslation(self, value, *, fast=False):
        """translate入力（移動はcm）へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.translatePlug)
        return self

    @undoChunk("hlibCalculationEdit")
    def connectTranslate(self, source, force=False):
        """translate入力（移動はcm）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            ComposeMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.translatePlug, force=force)
        return self

    def rotatePlug(self):
        """rotate入力（回転はrad）のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('inputRotate')

    def getRotation(self):
        """rotate入力（回転はrad）の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.rotatePlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setRotation(self, value, *, fast=False):
        """rotate入力（回転はrad）へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.rotatePlug)
        return self

    @undoChunk("hlibCalculationEdit")
    def connectRotate(self, source, force=False):
        """rotate入力（回転はrad）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            ComposeMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.rotatePlug, force=force)
        return self

    def scalePlug(self):
        """scale入力（無次元）のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('inputScale')

    def getScale(self):
        """scale入力（無次元）の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.scalePlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setScale(self, value, *, fast=False):
        """scale入力（無次元）へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.scalePlug)
        return self

    @undoChunk("hlibCalculationEdit")
    def connectScale(self, source, force=False):
        """scale入力（無次元）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            ComposeMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.scalePlug, force=force)
        return self

    def shearPlug(self):
        """shear入力（無次元）のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('inputShear')

    def getShear(self):
        """shear入力（無次元）の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.shearPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setShear(self, value, *, fast=False):
        """shear入力（無次元）へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.shearPlug)
        return self

    @undoChunk("hlibCalculationEdit")
    def connectShear(self, source, force=False):
        """shear入力（無次元）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            ComposeMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.shearPlug, force=force)
        return self

    def quaternionPlug(self):
        """XYZW順のQuaternion入力のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("inputQuat")

    def getQuaternion(self):
        """XYZW順のQuaternion入力の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.quaternionPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setQuaternion(self, value, *, fast=False):
        """XYZW順のQuaternion入力へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.vector(value, 4)
        self.quaternionPlug().set(value)
        return self

    @undoChunk("hlibCalculationEdit")
    def connectQuaternion(self, source, force=False):
        """XYZW順のQuaternion入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            ComposeMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.quaternionPlug, force=force)
        return self

    def useEulerRotationPlug(self):
        """Euler入力を使用するかのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("useEulerRotation")

    def getUseEulerRotation(self):
        """Euler入力を使用するかの評価値を取得する。
        Returns:
            bool: 現在の値。
        """
        return self.useEulerRotationPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setUseEulerRotation(self, value, *, fast=False):
        """Euler入力を使用するかへ定数値を設定する。

        Args:
            value (bool): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.boolean, self.useEulerRotationPlug)
        return self

    @undoChunk("hlibCalculationEdit")
    def connectUseEulerRotation(self, source, force=False):
        """Euler入力を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            ComposeMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.useEulerRotationPlug, force=force)
        return self

    def getRotateOrder(self):
        """現在のモード名を取得する。
        Returns:
            str: xyz, yzx, zxy, xzy, yxz, zyx。
        """
        return _Calculation.enumName(self.plug("inputRotateOrder"), ('xyz', 'yzx', 'zxy', 'xzy', 'yxz', 'zyx'))

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setRotateOrder(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): xyz, yzx, zxy, xzy, yxz, zyx、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enumValue(mode, ('xyz', 'yzx', 'zxy', 'xzy', 'yxz', 'zyx'))
        self.plug("inputRotateOrder").set(value)
        return self

    def outputPlug(self):
        """計算結果の接続用Plugを取得する。
        Returns:
            Plug: 出力参照。
        """
        return self.plug("outputMatrix")

    def result(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            Matrix: 計算結果。
        """
        return Matrix(self.outputPlug().get())
