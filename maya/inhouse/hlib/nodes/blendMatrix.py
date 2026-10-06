"""論理番号順に行列をブレンドする。加重平均ではない。"""

from .._core.flags import flag_aliases
from .._core.registry import node_wrapper
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from ..maths import Matrix
from ._calculation import _Calculation
from .node import Node


@node_wrapper("blendMatrix")
class BlendMatrix(Node):
    """論理番号順に行列をブレンドする。加重平均ではない。"""

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
            BlendMatrix: 自身。

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
            BlendMatrix: 自身。

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
            BlendMatrix: 自身。

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
            BlendMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getEnvelopePlug, force=force)
        return self

    def getTargetIndices(self):
        """既存ターゲットの論理番号を取得する。
        Returns:
            list[int]: 疎な論理番号。
        """
        return list(self.getPlug("target").mplug().getExistingArrayAttributeIndices())

    @flag_aliases(idx="index")
    def getTargetPlug(self, index):
        """既存ターゲットを参照する。

        Args:
            index (int): 既存の論理番号。 別名 ``idx`` も使用可能。
        Returns:
            CompoundPlug: ターゲット。
        """
        plug = self.getPlug("target")[_Calculation.index(index)]
        if index not in self.getTargetIndices():
            raise IndexError(f"No target at logical index {index}")
        return plug

    @flag_aliases(idx="index", src="source", f="force")
    @undoChunk("hlibCalculationEdit")
    def connectTarget(self, index, source, weight=1.0, force=False):
        """行列Plugをターゲットへ接続する。

        Args:
            index (int): 非負の論理番号。 別名 ``idx`` も使用可能。
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            weight (float): 有限なウェイト。
            force (bool): 接続を置き換えるか。 別名 ``f`` も使用可能。
        Returns:
            BlendMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        from ..plugs.plug import Plug as _InputPlug
        index = _Calculation.index(index)
        source, weight = _InputPlug._resolve_input(source), _Calculation.scalar(weight)
        target = self.getPlug("target")[index]
        source.connectTo(target["targetMatrix"], force=force)
        target["weight"].set(weight)
        return self

    @flag_aliases(idx="index")
    @undoChunk("hlibCalculationEdit")
    def removeTarget(self, index):
        """ターゲットとその接続を削除する。

        Args:
            index (int): 既存の論理番号。 別名 ``idx`` も使用可能。
        Returns:
            BlendMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        self.getPlug("target").removeElement(_Calculation.index(index))
        return self

    @flag_aliases(idx="index")
    def getTarget(self, index):
        """ターゲットの評価値を取得する。

        Args:
            index (int): 既存の論理番号。 別名 ``idx`` も使用可能。
        Returns:
            dict: matrix/weight。
        """
        target = self.getTargetPlug(index)
        return {"matrix": Matrix(target["targetMatrix"].get()), "weight": target["weight"].get()}

    @flag_aliases(idx="index")
    @undoChunk("hlibCalculationEdit")
    def setTarget(self, index, matrix, weight=1.0):
        """ターゲットの行列とウェイトを設定する。

        Args:
            index (int): 非負の論理番号。 別名 ``idx`` も使用可能。
            matrix (Matrix | Iterable[float]): 行列。
            weight (float): 有限なウェイト。
        Returns:
            BlendMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        index = _Calculation.index(index)
        matrix, weight = Matrix(matrix), _Calculation.scalar(weight)
        target = self.getPlug("target")[index]
        target["targetMatrix"].set(matrix)
        target["weight"].set(weight)
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
