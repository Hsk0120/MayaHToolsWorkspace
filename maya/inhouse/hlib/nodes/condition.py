"""2値の比較により出力を切り替える。"""
from .._core.registry import node_wrapper
from .._core.coerce import to_plug
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ..maths import Vector
from ._calculation import _Calculation
from .node import Node


@node_wrapper("condition")
class Condition(Node):
    """2値の比較により出力を切り替える。"""

    def get_operation(self):
        """現在のモード名を取得する。
        Returns:
            str: equal, not_equal, greater, greater_equal, less, less_equal。
        """
        return _Calculation.enum_name(self.plug("operation"), ('equal', 'not_equal', 'greater', 'greater_equal', 'less', 'less_equal'))

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_operation(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): equal, not_equal, greater, greater_equal, less, less_equal、またはMayaの番号。
            fast (bool): TrueはUndoなし。
        Returns:
            Condition: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enum_value(mode, ('equal', 'not_equal', 'greater', 'greater_equal', 'less', 'less_equal'))
        self.plug("operation").set(value)
        return self

    def input_plug(self, index):
        """入力のPlugを取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("firstTerm" if _Calculation.index(index, (1, 2)) == 1 else "secondTerm")

    def get_input(self, index):
        """入力の評価値を取得する。

        Args:
            index (int): 入力番号1または2。
        Returns:
            float: 現在の値。
        """
        return self.input_plug(index).get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_input(self, index, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。
            value (float): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            Condition: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.scalar(value)
        self.input_plug(index).set(value)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_input(self, index, source, force=False):
        """入力へ接続する。

        Args:
            index (int): 入力番号1または2。
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            Condition: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        to_plug(source).connect(self.input_plug(index), force=force)
        return self

    def true_value_plug(self):
        """条件成立時のRGB値のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("colorIfTrue")

    def get_true_value(self):
        """条件成立時のRGB値の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.true_value_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_true_value(self, value, *, fast=False):
        """条件成立時のRGB値へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            Condition: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.vector(value)
        self.true_value_plug().set(value)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_true_value(self, source, force=False):
        """条件成立時のRGB値へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            Condition: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        to_plug(source).connect(self.true_value_plug(), force=force)
        return self

    def false_value_plug(self):
        """条件不成立時のRGB値のPlugを取得する。
        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.plug("colorIfFalse")

    def get_false_value(self):
        """条件不成立時のRGB値の評価値を取得する。
        Returns:
            Iterable[float]: 現在の値。
        """
        return self.false_value_plug().get()

    @fast_edit
    @undo_chunk("hlibCalculationEdit")
    def set_false_value(self, value, *, fast=False):
        """条件不成立時のRGB値へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
        Returns:
            Condition: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.vector(value)
        self.false_value_plug().set(value)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_false_value(self, source, force=False):
        """条件不成立時のRGB値へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): 既存接続を置き換えるか。
        Returns:
            Condition: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        to_plug(source).connect(self.false_value_plug(), force=force)
        return self

    def output_plug(self):
        """計算結果の接続用Plugを取得する。
        Returns:
            Plug: 出力参照。
        """
        return self.plug("outColor")

    def result(self):
        """現在の入力をMayaで評価した結果を取得する。
        Returns:
            Vector: 計算結果。
        """
        return Vector(self.output_plug().get())
