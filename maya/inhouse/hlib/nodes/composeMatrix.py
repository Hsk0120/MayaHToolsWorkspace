"""移動・回転・スケール・シアーから行列を構築する。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ..maths import Matrix
from ._calculation import _Calculation
from .node import Node


@node_wrapper("composeMatrix")
class ComposeMatrix(Node):
    """移動・回転・スケール・シアーから行列を構築する。"""

    def translate_plug(self):
        """translate入力（回転は度）のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('inputTranslate')

    def get_translate(self):
        """translate入力（回転は度）の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.translate_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_translate(self, value, *, fast=False):
        """translate入力（回転は度）へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.translate_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_translate(self, source, force=False):
        """translate入力（回転は度）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.translate_plug, force=force)
        return self

    def rotate_plug(self):
        """rotate入力（回転は度）のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('inputRotate')

    def get_rotate(self):
        """rotate入力（回転は度）の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.rotate_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_rotate(self, value, *, fast=False):
        """rotate入力（回転は度）へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.rotate_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_rotate(self, source, force=False):
        """rotate入力（回転は度）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.rotate_plug, force=force)
        return self

    def scale_plug(self):
        """scale入力（回転は度）のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('inputScale')

    def get_scale(self):
        """scale入力（回転は度）の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.scale_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_scale(self, value, *, fast=False):
        """scale入力（回転は度）へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.scale_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_scale(self, source, force=False):
        """scale入力（回転は度）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.scale_plug, force=force)
        return self

    def shear_plug(self):
        """shear入力（回転は度）のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('inputShear')

    def get_shear(self):
        """shear入力（回転は度）の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.shear_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_shear(self, value, *, fast=False):
        """shear入力（回転は度）へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.shear_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_shear(self, source, force=False):
        """shear入力（回転は度）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.shear_plug, force=force)
        return self

    def quaternion_plug(self):
        """XYZW順のQuaternion入力のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("inputQuat")

    def get_quaternion(self):
        """XYZW順のQuaternion入力の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.quaternion_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_quaternion(self, value, *, fast=False):
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
        self.quaternion_plug().set(value)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_quaternion(self, source, force=False):
        """XYZW順のQuaternion入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.quaternion_plug, force=force)
        return self

    def use_euler_rotation_plug(self):
        """Euler入力を使用するかのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("useEulerRotation")

    def get_use_euler_rotation(self):
        """Euler入力を使用するかの評価値を取得する。
        Returns:
            bool: 現在の値。
        """
        return self.use_euler_rotation_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_use_euler_rotation(self, value, *, fast=False):
        """Euler入力を使用するかへ定数値を設定する。

        Args:
            value (bool): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.boolean, self.use_euler_rotation_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_use_euler_rotation(self, source, force=False):
        """Euler入力を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.use_euler_rotation_plug, force=force)
        return self

    def get_rotate_order(self):
        """現在のモード名を取得する。
        Returns:
            str: xyz, yzx, zxy, xzy, yxz, zyx。
        """
        return _Calculation.enum_name(self.plug("inputRotateOrder"), ('xyz', 'yzx', 'zxy', 'xzy', 'yxz', 'zyx'))

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_rotate_order(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): xyz, yzx, zxy, xzy, yxz, zyx、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enum_value(mode, ('xyz', 'yzx', 'zxy', 'xzy', 'yxz', 'zyx'))
        self.plug("inputRotateOrder").set(value)
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
