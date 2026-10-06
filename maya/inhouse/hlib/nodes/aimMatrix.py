"""指定した軸をターゲットへ向ける行列を生成する。"""

from .._core.flags import flag_aliases
from .._core.registry import node_wrapper
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from ..maths import Matrix
from ._calculation import _Calculation
from .node import Node


@node_wrapper("aimMatrix")
class AimMatrix(Node):
    """指定した軸をターゲットへ向ける行列を生成する。"""

    def getInputPlug(self):
        """入力のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("inputMatrix")

    def getInput(self):
        """入力の評価値を取得する。
        Returns:
            Matrix: 現在の値。
        """
        return self.getInputPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setInput(self, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            value (Matrix): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, Matrix, self.getInputPlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectInput(self, source, force=False):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            AimMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getInputPlug, force=force)
        return self

    def getEnvelopePlug(self):
        """全体ウェイトのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("envelope")

    def getEnvelope(self):
        """全体ウェイトの評価値を取得する。
        Returns:
            float: 現在の値。
        """
        return self.getEnvelopePlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setEnvelope(self, value, *, fast=False):
        """全体ウェイトへ定数値を設定する。

        Args:
            value (float): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.scalar, self.getEnvelopePlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectEnvelope(self, source, force=False):
        """全体ウェイトへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            AimMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getEnvelopePlug, force=force)
        return self

    def getPrimaryMatrixPlug(self):
        """primaryターゲット行列のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug('primaryTargetMatrix')

    def getPrimaryMatrix(self):
        """primaryターゲット行列の評価値を取得する。
        Returns:
            Matrix: 現在の値。
        """
        return self.getPrimaryMatrixPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setPrimaryMatrix(self, value, *, fast=False):
        """primaryターゲット行列へ定数値を設定する。

        Args:
            value (Matrix): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, Matrix, self.getPrimaryMatrixPlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectPrimaryMatrix(self, source, force=False):
        """primaryターゲット行列へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            AimMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getPrimaryMatrixPlug, force=force)
        return self

    def getPrimaryAxisPlug(self):
        """primary入力軸のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug('primaryInputAxis')

    def getPrimaryAxis(self):
        """primary入力軸の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getPrimaryAxisPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setPrimaryAxis(self, value, *, fast=False):
        """primary入力軸へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.getPrimaryAxisPlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectPrimaryAxis(self, source, force=False):
        """primary入力軸へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            AimMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getPrimaryAxisPlug, force=force)
        return self

    def getPrimaryVectorPlug(self):
        """primaryターゲットベクトルのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug('primaryTargetVector')

    def getPrimaryVector(self):
        """primaryターゲットベクトルの評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getPrimaryVectorPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setPrimaryVector(self, value, *, fast=False):
        """primaryターゲットベクトルへ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.getPrimaryVectorPlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectPrimaryVector(self, source, force=False):
        """primaryターゲットベクトルへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            AimMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getPrimaryVectorPlug, force=force)
        return self

    def getPrimaryMode(self):
        """現在のモード名を取得する。
        Returns:
            str: lock, aim, align。
        """
        return _Calculation.enumName(self.getPlug("primaryMode"), ('lock', 'aim', 'align'))

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setPrimaryMode(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): lock, aim, align、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enumValue(mode, ('lock', 'aim', 'align'))
        self.getPlug("primaryMode").set(value)
        return self

    def getSecondaryMatrixPlug(self):
        """secondaryターゲット行列のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug('secondaryTargetMatrix')

    def getSecondaryMatrix(self):
        """secondaryターゲット行列の評価値を取得する。
        Returns:
            Matrix: 現在の値。
        """
        return self.getSecondaryMatrixPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setSecondaryMatrix(self, value, *, fast=False):
        """secondaryターゲット行列へ定数値を設定する。

        Args:
            value (Matrix): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, Matrix, self.getSecondaryMatrixPlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectSecondaryMatrix(self, source, force=False):
        """secondaryターゲット行列へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            AimMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getSecondaryMatrixPlug, force=force)
        return self

    def getSecondaryAxisPlug(self):
        """secondary入力軸のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug('secondaryInputAxis')

    def getSecondaryAxis(self):
        """secondary入力軸の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getSecondaryAxisPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setSecondaryAxis(self, value, *, fast=False):
        """secondary入力軸へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.getSecondaryAxisPlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectSecondaryAxis(self, source, force=False):
        """secondary入力軸へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            AimMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getSecondaryAxisPlug, force=force)
        return self

    def getSecondaryVectorPlug(self):
        """secondaryターゲットベクトルのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug('secondaryTargetVector')

    def getSecondaryVector(self):
        """secondaryターゲットベクトルの評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getSecondaryVectorPlug().get()

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setSecondaryVector(self, value, *, fast=False):
        """secondaryターゲットベクトルへ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.getSecondaryVectorPlug)
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectSecondaryVector(self, source, force=False):
        """secondaryターゲットベクトルへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            AimMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getSecondaryVectorPlug, force=force)
        return self

    def getSecondaryMode(self):
        """現在のモード名を取得する。
        Returns:
            str: none, aim, align。
        """
        return _Calculation.enumName(self.getPlug("secondaryMode"), ('none', 'aim', 'align'))

    @fast_edit
    @undoChunk("hlibCalculationEdit")
    def setSecondaryMode(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): none, aim, align、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enumValue(mode, ('none', 'aim', 'align'))
        self.getPlug("secondaryMode").set(value)
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
