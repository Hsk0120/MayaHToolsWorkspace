"""移動・回転・スケール・シアーから行列を構築する。"""

from .._core.flags import flag_aliases
from .._core.registry import node_wrapper
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from ..maths import Matrix
from ._calculation import _Calculation
from .node import Node


@node_wrapper("composeMatrix")
class ComposeMatrix(Node):
    """移動・回転・スケール・シアーから行列を構築する。"""

    def getTranslatePlug(self):
        """translate入力（移動はcm）のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug('inputTranslate')

    def getTranslation(self):
        """translate入力（移動はcm）の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getTranslatePlug().get()

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
        _Calculation.set_value(value, _Calculation.vector, self.getTranslatePlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectTranslate(self, source, force=False):
        """translate入力（移動はcm）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            ComposeMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getTranslatePlug, force=force)
        return self

    def getRotatePlug(self):
        """rotate入力（回転はrad）のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug('inputRotate')

    def getRotation(self):
        """rotate入力（回転はrad）の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getRotatePlug().get()

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
        _Calculation.set_value(value, _Calculation.vector, self.getRotatePlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectRotate(self, source, force=False):
        """rotate入力（回転はrad）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            ComposeMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getRotatePlug, force=force)
        return self

    def getScalePlug(self):
        """scale入力（無次元）のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug('inputScale')

    def getScale(self):
        """scale入力（無次元）の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getScalePlug().get()

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
        _Calculation.set_value(value, _Calculation.vector, self.getScalePlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectScale(self, source, force=False):
        """scale入力（無次元）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            ComposeMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getScalePlug, force=force)
        return self

    def getShearPlug(self):
        """shear入力（無次元）のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug('inputShear')

    def getShear(self):
        """shear入力（無次元）の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getShearPlug().get()

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
        _Calculation.set_value(value, _Calculation.vector, self.getShearPlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectShear(self, source, force=False):
        """shear入力（無次元）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            ComposeMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getShearPlug, force=force)
        return self

    def getQuaternionPlug(self):
        """XYZW順のQuaternion入力のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("inputQuat")

    def getQuaternion(self):
        """XYZW順のQuaternion入力の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getQuaternionPlug().get()

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
        self.getQuaternionPlug().set(value)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectQuaternion(self, source, force=False):
        """XYZW順のQuaternion入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            ComposeMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getQuaternionPlug, force=force)
        return self

    def getUseEulerRotationPlug(self):
        """Euler入力を使用するかのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("useEulerRotation")

    def getUseEulerRotation(self):
        """Euler入力を使用するかの評価値を取得する。
        Returns:
            bool: 現在の値。
        """
        return self.getUseEulerRotationPlug().get()

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
        _Calculation.set_value(value, _Calculation.boolean, self.getUseEulerRotationPlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectUseEulerRotation(self, source, force=False):
        """Euler入力を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            ComposeMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getUseEulerRotationPlug, force=force)
        return self

    def getRotateOrder(self):
        """現在のモード名を取得する。
        Returns:
            str: xyz, yzx, zxy, xzy, yxz, zyx。
        """
        return _Calculation.enumName(self.getPlug("inputRotateOrder"), ('xyz', 'yzx', 'zxy', 'xzy', 'yxz', 'zyx'))

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
        self.getPlug("inputRotateOrder").set(value)
        return self

    def getOutputPlug(self):
        """計算結果の接続用Plugを取得する。
        Returns:
            Plug: 出力参照。
        """
        return self.getPlug("outputMatrix")

    def getResult(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            Matrix: 計算結果。
        """
        return Matrix(self.getOutputPlug().get())
