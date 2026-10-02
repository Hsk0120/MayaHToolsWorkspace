"""論理番号順に行列をブレンドする。加重平均ではない。"""
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..decorators._fast import fast_edit
from ..maths import Matrix
from ._calculation import _Calculation
from .node import Node


@node_wrapper("blendMatrix")
class BlendMatrix(Node):
    """論理番号順に行列をブレンドする。加重平均ではない。"""

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
            BlendMatrix: 自身。

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
            BlendMatrix: 自身。

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
            BlendMatrix: 自身。

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
            BlendMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.envelope_plug, force=force)
        return self

    def target_indices(self):
        """既存ターゲットの論理番号を取得する。
        Returns:
            list[int]: 疎な論理番号。
        """
        return list(self.plug("target").mplug().getExistingArrayAttributeIndices())

    def target_plug(self, index):
        """既存ターゲットを参照する。

        Args:
            index (int): 既存の論理番号。
        Returns:
            CompoundPlug: ターゲット。
        """
        return self.plug("target").element(_Calculation.index(index))

    @undo_chunk("hlibCalculationEdit")
    def set_target(self, index, matrix, weight=1.0):
        """ターゲットの行列とウェイトを設定する。

        Args:
            index (int): 非負の論理番号。
            matrix (Matrix | Iterable[float]): 行列。
            weight (float): 有限なウェイト。
        Returns:
            BlendMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        index = _Calculation.index(index)
        matrix, weight = Matrix(matrix), _Calculation.scalar(weight)
        target = self.plug("target").element(index, create=True)
        target.child("targetMatrix").set(matrix)
        target.child("weight").set(weight)
        return self

    @undo_chunk("hlibCalculationEdit")
    def connect_target(self, index, source, weight=1.0, force=False):
        """行列Plugをターゲットへ接続する。

        Args:
            index (int): 非負の論理番号。
            source (Plug | str | MPlug): 接続元。
            weight (float): 有限なウェイト。
            force (bool): 接続を置き換えるか。
        Returns:
            BlendMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        from hlib.plugs.plug import Plug as _InputPlug
        index = _Calculation.index(index)
        source, weight = _InputPlug._resolve_input(source), _Calculation.scalar(weight)
        target = self.plug("target").element(index, create=True)
        source.connect(target.child("targetMatrix"), force=force)
        target.child("weight").set(weight)
        return self

    @undo_chunk("hlibCalculationEdit")
    def remove_target(self, index):
        """ターゲットとその接続を削除する。

        Args:
            index (int): 既存の論理番号。
        Returns:
            BlendMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        self.plug("target").remove_element(_Calculation.index(index))
        return self

    def get_target(self, index):
        """ターゲットの評価値を取得する。

        Args:
            index (int): 既存の論理番号。
        Returns:
            dict: matrix/weight。
        """
        target = self.target_plug(index)
        return {"matrix": Matrix(target.child("targetMatrix").get()), "weight": target.child("weight").get()}

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
