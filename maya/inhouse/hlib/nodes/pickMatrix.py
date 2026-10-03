"""行列の使用成分を選択する。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ..maths import Matrix
from ._calculation import _Calculation
from .node import Node


@node_wrapper("pickMatrix")
class PickMatrix(Node):
    """行列の使用成分を選択する。"""

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
            PickMatrix: 自身。

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
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.inputPlug, force=force)
        return self

    def useTranslatePlug(self):
        """translate成分を使用するかのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('useTranslate')

    def getUseTranslate(self):
        """translate成分を使用するかの評価値を取得する。
        Returns:
            bool: 現在の値。
        """
        return self.useTranslatePlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def setUseTranslate(self, value, *, fast=False):
        """translate成分を使用するかへ定数値を設定する。

        Args:
            value (bool): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.boolean, self.useTranslatePlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectUseTranslate(self, source, force=False):
        """translate成分を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.useTranslatePlug, force=force)
        return self

    def useRotatePlug(self):
        """rotate成分を使用するかのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('useRotate')

    def getUseRotate(self):
        """rotate成分を使用するかの評価値を取得する。
        Returns:
            bool: 現在の値。
        """
        return self.useRotatePlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def setUseRotate(self, value, *, fast=False):
        """rotate成分を使用するかへ定数値を設定する。

        Args:
            value (bool): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.boolean, self.useRotatePlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectUseRotate(self, source, force=False):
        """rotate成分を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.useRotatePlug, force=force)
        return self

    def useScalePlug(self):
        """scale成分を使用するかのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('useScale')

    def getUseScale(self):
        """scale成分を使用するかの評価値を取得する。
        Returns:
            bool: 現在の値。
        """
        return self.useScalePlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def setUseScale(self, value, *, fast=False):
        """scale成分を使用するかへ定数値を設定する。

        Args:
            value (bool): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.boolean, self.useScalePlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectUseScale(self, source, force=False):
        """scale成分を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.useScalePlug, force=force)
        return self

    def useShearPlug(self):
        """shear成分を使用するかのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('useShear')

    def getUseShear(self):
        """shear成分を使用するかの評価値を取得する。
        Returns:
            bool: 現在の値。
        """
        return self.useShearPlug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def setUseShear(self, value, *, fast=False):
        """shear成分を使用するかへ定数値を設定する。

        Args:
            value (bool): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.boolean, self.useShearPlug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connectUseShear(self, source, force=False):
        """shear成分を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.useShearPlug, force=force)
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
