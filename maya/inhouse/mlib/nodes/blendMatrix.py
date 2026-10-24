"""論理番号順に行列をブレンドする。加重平均ではない。"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..maths import Matrix
from ..util import _ArgumentError, _UNSET
from ._calculation import _Calculation
from .node import Node


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
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, Matrix, self.getInputPlug, fast=fast)
            return self

    def connectInput(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            BlendMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if src is not _UNSET:
            if source is not _UNSET:
                raise _ArgumentError("Specify only one of 'source' and 'src'")
            source = src
        if f is not _UNSET:
            if force is not _UNSET:
                raise _ArgumentError("Specify only one of 'force' and 'f'")
            force = f
        if source is _UNSET:
            raise _ArgumentError("Missing required argument: 'source'")
        if force is _UNSET:
            force = False
        with undoChunk("mlibCalculationEdit"):
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
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.scalar, self.getEnvelopePlug, fast=fast)
            return self

    def connectEnvelope(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """全体ウェイトへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            BlendMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if src is not _UNSET:
            if source is not _UNSET:
                raise _ArgumentError("Specify only one of 'source' and 'src'")
            source = src
        if f is not _UNSET:
            if force is not _UNSET:
                raise _ArgumentError("Specify only one of 'force' and 'f'")
            force = f
        if source is _UNSET:
            raise _ArgumentError("Missing required argument: 'source'")
        if force is _UNSET:
            force = False
        with undoChunk("mlibCalculationEdit"):
            _Calculation.connect(source, self.getEnvelopePlug, force=force)
            return self

    def getTargetIndices(self):
        """既存ターゲットの論理番号を取得する。

        Returns:
            list[int]: 疎な論理番号。
        """
        return list(self.getPlug("target").mplug().getExistingArrayAttributeIndices())

    def getTargetPlug(self, index=_UNSET, *, idx=_UNSET):
        """既存ターゲットを参照する。

        Args:
            index (int): 既存の論理番号。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            CompoundPlug: ターゲット。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        plug = self.getPlug("target")[_Calculation.index(index)]
        if index not in self.getTargetIndices():
            raise IndexError(f"No target at logical index {index}")
        return plug

    def connectTarget(self, index=_UNSET, source=_UNSET, weight=1.0, force=_UNSET, *, idx=_UNSET, src=_UNSET,
        f=_UNSET):
        """行列Plugをターゲットへ接続する。

        Args:
            index (int): 非負の論理番号。 別名 ``idx`` も使用可能。
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            weight (float): 有限なウェイト。
            force (bool): 接続を置き換えるか。 別名 ``f`` も使用可能。
            idx (int): indexの別名。同時指定は不可。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            BlendMatrix: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if src is not _UNSET:
            if source is not _UNSET:
                raise _ArgumentError("Specify only one of 'source' and 'src'")
            source = src
        if f is not _UNSET:
            if force is not _UNSET:
                raise _ArgumentError("Specify only one of 'force' and 'f'")
            force = f
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        if source is _UNSET:
            raise _ArgumentError("Missing required argument: 'source'")
        if force is _UNSET:
            force = False
        with undoChunk("mlibCalculationEdit"):
            from ..plugs.plug import Plug as _InputPlug
            index = _Calculation.index(index)
            source, weight = _InputPlug._resolve_input(source), _Calculation.scalar(weight)
            target = self.getPlug("target")[index]
            source.connectTo(target["targetMatrix"], force=force)
            target["weight"].set(weight)
            return self

    def removeTarget(self, index=_UNSET, *, idx=_UNSET):
        """ターゲットとその接続を削除する。

        Args:
            index (int): 既存の論理番号。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            BlendMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        with undoChunk("mlibCalculationEdit"):
            self.getPlug("target").removeElement(_Calculation.index(index))
            return self

    def getTarget(self, index=_UNSET, *, idx=_UNSET):
        """ターゲットの評価値を取得する。

        Args:
            index (int): 既存の論理番号。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            dict: matrix/weight。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        target = self.getTargetPlug(index)
        return {"matrix": Matrix(target["targetMatrix"].get()), "weight": target["weight"].get()}

    def setTarget(self, index=_UNSET, matrix=_UNSET, weight=1.0, *, idx=_UNSET):
        """ターゲットの行列とウェイトを設定する。

        Args:
            index (int): 非負の論理番号。 別名 ``idx`` も使用可能。
            matrix (Matrix | Iterable[float]): 行列。
            weight (float): 有限なウェイト。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            BlendMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        if matrix is _UNSET:
            raise _ArgumentError("Missing required argument: 'matrix'")
        with undoChunk("mlibCalculationEdit"):
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
