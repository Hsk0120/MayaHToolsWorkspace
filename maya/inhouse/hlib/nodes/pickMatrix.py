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

    def input_plug(self):
        """入力のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("inputMatrix")

    def get_input(self):
        """入力の評価値を取得する。
        Returns:
            Matrix: 現在の値。
        """
        return self.input_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_input(self, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            value (Matrix): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, Matrix, self.input_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_input(self, source, force=False):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.input_plug, force=force)
        return self

    def use_translate_plug(self):
        """translate成分を使用するかのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('useTranslate')

    def get_use_translate(self):
        """translate成分を使用するかの評価値を取得する。
        Returns:
            bool: 現在の値。
        """
        return self.use_translate_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_use_translate(self, value, *, fast=False):
        """translate成分を使用するかへ定数値を設定する。

        Args:
            value (bool): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.boolean, self.use_translate_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_use_translate(self, source, force=False):
        """translate成分を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.use_translate_plug, force=force)
        return self

    def use_rotate_plug(self):
        """rotate成分を使用するかのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('useRotate')

    def get_use_rotate(self):
        """rotate成分を使用するかの評価値を取得する。
        Returns:
            bool: 現在の値。
        """
        return self.use_rotate_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_use_rotate(self, value, *, fast=False):
        """rotate成分を使用するかへ定数値を設定する。

        Args:
            value (bool): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.boolean, self.use_rotate_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_use_rotate(self, source, force=False):
        """rotate成分を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.use_rotate_plug, force=force)
        return self

    def use_scale_plug(self):
        """scale成分を使用するかのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('useScale')

    def get_use_scale(self):
        """scale成分を使用するかの評価値を取得する。
        Returns:
            bool: 現在の値。
        """
        return self.use_scale_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_use_scale(self, value, *, fast=False):
        """scale成分を使用するかへ定数値を設定する。

        Args:
            value (bool): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.boolean, self.use_scale_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_use_scale(self, source, force=False):
        """scale成分を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.use_scale_plug, force=force)
        return self

    def use_shear_plug(self):
        """shear成分を使用するかのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('useShear')

    def get_use_shear(self):
        """shear成分を使用するかの評価値を取得する。
        Returns:
            bool: 現在の値。
        """
        return self.use_shear_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_use_shear(self, value, *, fast=False):
        """shear成分を使用するかへ定数値を設定する。

        Args:
            value (bool): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.boolean, self.use_shear_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_use_shear(self, source, force=False):
        """shear成分を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            PickMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.use_shear_plug, force=force)
        return self

    def output_plug(self):
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
        return Matrix(self.output_plug().get())
