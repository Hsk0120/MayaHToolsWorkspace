"""指定した軸をターゲットへ向ける行列を生成する。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ..maths import Matrix
from ._calculation import _Calculation
from .node import Node


@node_wrapper("aimMatrix")
class AimMatrix(Node):
    """指定した軸をターゲットへ向ける行列を生成する。"""

    def inputPlug(self):
        """入力のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("inputMatrix")

    def getInput(self):
        """入力の評価値を取得する。
        Returns:
            Matrix: 現在の値。
        """
        return self.inputPlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
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
        _Calculation.set_value(value, Matrix, self.inputPlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectInput(self, source, force=False):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.inputPlug, force=force)
        return self

    def envelopePlug(self):
        """全体ウェイトのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("envelope")

    def getEnvelope(self):
        """全体ウェイトの評価値を取得する。
        Returns:
            float: 現在の値。
        """
        return self.envelopePlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
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
        _Calculation.set_value(value, _Calculation.scalar, self.envelopePlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectEnvelope(self, source, force=False):
        """全体ウェイトへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.envelopePlug, force=force)
        return self

    def primaryMatrixPlug(self):
        """primaryターゲット行列のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('primaryTargetMatrix')

    def getPrimaryMatrix(self):
        """primaryターゲット行列の評価値を取得する。
        Returns:
            Matrix: 現在の値。
        """
        return self.primaryMatrixPlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
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
        _Calculation.set_value(value, Matrix, self.primaryMatrixPlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectPrimaryMatrix(self, source, force=False):
        """primaryターゲット行列へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.primaryMatrixPlug, force=force)
        return self

    def primaryAxisPlug(self):
        """primary入力軸のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('primaryInputAxis')

    def getPrimaryAxis(self):
        """primary入力軸の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.primaryAxisPlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
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
        _Calculation.set_value(value, _Calculation.vector, self.primaryAxisPlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectPrimaryAxis(self, source, force=False):
        """primary入力軸へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.primaryAxisPlug, force=force)
        return self

    def primaryVectorPlug(self):
        """primaryターゲットベクトルのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('primaryTargetVector')

    def getPrimaryVector(self):
        """primaryターゲットベクトルの評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.primaryVectorPlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
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
        _Calculation.set_value(value, _Calculation.vector, self.primaryVectorPlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectPrimaryVector(self, source, force=False):
        """primaryターゲットベクトルへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.primaryVectorPlug, force=force)
        return self

    def getPrimaryMode(self):
        """現在のモード名を取得する。
        Returns:
            str: lock, aim, align。
        """
        return _Calculation.enumName(self.plug("primaryMode"), ('lock', 'aim', 'align'))

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
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
        self.plug("primaryMode").set(value)
        return self

    def secondaryMatrixPlug(self):
        """secondaryターゲット行列のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('secondaryTargetMatrix')

    def getSecondaryMatrix(self):
        """secondaryターゲット行列の評価値を取得する。
        Returns:
            Matrix: 現在の値。
        """
        return self.secondaryMatrixPlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
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
        _Calculation.set_value(value, Matrix, self.secondaryMatrixPlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectSecondaryMatrix(self, source, force=False):
        """secondaryターゲット行列へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.secondaryMatrixPlug, force=force)
        return self

    def secondaryAxisPlug(self):
        """secondary入力軸のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('secondaryInputAxis')

    def getSecondaryAxis(self):
        """secondary入力軸の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.secondaryAxisPlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
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
        _Calculation.set_value(value, _Calculation.vector, self.secondaryAxisPlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectSecondaryAxis(self, source, force=False):
        """secondary入力軸へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.secondaryAxisPlug, force=force)
        return self

    def secondaryVectorPlug(self):
        """secondaryターゲットベクトルのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('secondaryTargetVector')

    def getSecondaryVector(self):
        """secondaryターゲットベクトルの評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.secondaryVectorPlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
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
        _Calculation.set_value(value, _Calculation.vector, self.secondaryVectorPlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectSecondaryVector(self, source, force=False):
        """secondaryターゲットベクトルへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.secondaryVectorPlug, force=force)
        return self

    def getSecondaryMode(self):
        """現在のモード名を取得する。
        Returns:
            str: none, aim, align。
        """
        return _Calculation.enumName(self.plug("secondaryMode"), ('none', 'aim', 'align'))

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
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
        self.plug("secondaryMode").set(value)
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
