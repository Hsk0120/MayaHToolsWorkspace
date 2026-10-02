"""内積・外積・行列による点/ベクトル変換。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ..maths import Matrix, Vector
from ._calculation import _Calculation
from .shadingDependNode import ShadingDependNode


@node_wrapper("vectorProduct")
class VectorProduct(ShadingDependNode):
    """内積・外積・行列による点/ベクトル変換。"""

    def input_plug(self, index):
        """入力のPlugを取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug(f"input{_Calculation.index(index, (1, 2))}")

    def get_input(self, index):
        """入力の評価値を取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.input_plug(index).get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_input(self, index, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            VectorProduct: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.input_plug, index)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_input(self, index, source, force=False):
        """入力へ接続する。

        Args:
            index (int): 入力番号1または2。
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            VectorProduct: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.input_plug, index, force=force)
        return self

    def get_operation(self):
        """現在のモード名を取得する。
        Returns:
            str: none, dot, cross, vector_matrix, point_matrix。
        """
        return _Calculation.enum_name(self.plug("operation"), ('none', 'dot', 'cross', 'vector_matrix', 'point_matrix'))

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_operation(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): none, dot, cross, vector_matrix, point_matrix、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            VectorProduct: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enum_value(mode, ('none', 'dot', 'cross', 'vector_matrix', 'point_matrix'))
        self.plug("operation").set(value)
        return self

    def matrix_plug(self):
        """変換行列のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("matrix")

    def get_matrix(self):
        """変換行列の評価値を取得する。
        Returns:
            Matrix: 現在の値。
        """
        return self.matrix_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_matrix(self, value, *, fast=False):
        """変換行列へ定数値を設定する。

        Args:
            value (Matrix): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            VectorProduct: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, Matrix, self.matrix_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_matrix(self, source, force=False):
        """変換行列へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            VectorProduct: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.matrix_plug, force=force)
        return self

    def normalize_output_plug(self):
        """出力正規化のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("normalizeOutput")

    def get_normalize_output(self):
        """出力正規化の評価値を取得する。
        Returns:
            bool: 現在の値。
        """
        return self.normalize_output_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_normalize_output(self, value, *, fast=False):
        """出力正規化へ定数値を設定する。

        Args:
            value (bool): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            VectorProduct: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.boolean, self.normalize_output_plug)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_normalize_output(self, source, force=False):
        """出力正規化へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            VectorProduct: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.normalize_output_plug, force=force)
        return self

    def output_plug(self):
        """計算結果の接続用Plugを取得する。
        Returns:
            Plug: 出力参照。
        """
        return self.plug("output")

    def result(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            Vector: 計算結果。
        """
        return Vector(self.output_plug().get())
