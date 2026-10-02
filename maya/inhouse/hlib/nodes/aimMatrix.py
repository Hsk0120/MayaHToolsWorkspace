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
            AimMatrix: 自身。

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
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.input_plug, force=force)
        return self

    def envelope_plug(self):
        """全体ウェイトのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("envelope")

    def get_envelope(self):
        """全体ウェイトの評価値を取得する。
        Returns:
            float: 現在の値。
        """
        return self.envelope_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_envelope(self, value, *, fast=False):
        """全体ウェイトへ定数値を設定する。

        Args:
            value (float): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.scalar, self.envelope_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_envelope(self, source, force=False):
        """全体ウェイトへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.envelope_plug, force=force)
        return self

    def primary_matrix_plug(self):
        """primaryターゲット行列のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('primaryTargetMatrix')

    def get_primary_matrix(self):
        """primaryターゲット行列の評価値を取得する。
        Returns:
            Matrix: 現在の値。
        """
        return self.primary_matrix_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_primary_matrix(self, value, *, fast=False):
        """primaryターゲット行列へ定数値を設定する。

        Args:
            value (Matrix): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, Matrix, self.primary_matrix_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_primary_matrix(self, source, force=False):
        """primaryターゲット行列へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.primary_matrix_plug, force=force)
        return self

    def primary_axis_plug(self):
        """primary入力軸のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('primaryInputAxis')

    def get_primary_axis(self):
        """primary入力軸の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.primary_axis_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_primary_axis(self, value, *, fast=False):
        """primary入力軸へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.primary_axis_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_primary_axis(self, source, force=False):
        """primary入力軸へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.primary_axis_plug, force=force)
        return self

    def primary_vector_plug(self):
        """primaryターゲットベクトルのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('primaryTargetVector')

    def get_primary_vector(self):
        """primaryターゲットベクトルの評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.primary_vector_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_primary_vector(self, value, *, fast=False):
        """primaryターゲットベクトルへ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.primary_vector_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_primary_vector(self, source, force=False):
        """primaryターゲットベクトルへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.primary_vector_plug, force=force)
        return self

    def get_primary_mode(self):
        """現在のモード名を取得する。
        Returns:
            str: lock, aim, align。
        """
        return _Calculation.enum_name(self.plug("primaryMode"), ('lock', 'aim', 'align'))

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_primary_mode(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): lock, aim, align、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enum_value(mode, ('lock', 'aim', 'align'))
        self.plug("primaryMode").set(value)
        return self

    def secondary_matrix_plug(self):
        """secondaryターゲット行列のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('secondaryTargetMatrix')

    def get_secondary_matrix(self):
        """secondaryターゲット行列の評価値を取得する。
        Returns:
            Matrix: 現在の値。
        """
        return self.secondary_matrix_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_secondary_matrix(self, value, *, fast=False):
        """secondaryターゲット行列へ定数値を設定する。

        Args:
            value (Matrix): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, Matrix, self.secondary_matrix_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_secondary_matrix(self, source, force=False):
        """secondaryターゲット行列へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.secondary_matrix_plug, force=force)
        return self

    def secondary_axis_plug(self):
        """secondary入力軸のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('secondaryInputAxis')

    def get_secondary_axis(self):
        """secondary入力軸の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.secondary_axis_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_secondary_axis(self, value, *, fast=False):
        """secondary入力軸へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.secondary_axis_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_secondary_axis(self, source, force=False):
        """secondary入力軸へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.secondary_axis_plug, force=force)
        return self

    def secondary_vector_plug(self):
        """secondaryターゲットベクトルのPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug('secondaryTargetVector')

    def get_secondary_vector(self):
        """secondaryターゲットベクトルの評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.secondary_vector_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_secondary_vector(self, value, *, fast=False):
        """secondaryターゲットベクトルへ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.secondary_vector_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_secondary_vector(self, source, force=False):
        """secondaryターゲットベクトルへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.secondary_vector_plug, force=force)
        return self

    def get_secondary_mode(self):
        """現在のモード名を取得する。
        Returns:
            str: none, aim, align。
        """
        return _Calculation.enum_name(self.plug("secondaryMode"), ('none', 'aim', 'align'))

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_secondary_mode(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): none, aim, align、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            AimMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enum_value(mode, ('none', 'aim', 'align'))
        self.plug("secondaryMode").set(value)
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
