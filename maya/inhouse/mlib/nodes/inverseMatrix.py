"""逆行列を計算する。Maya付属matrixNodesの明示的なロードが必要。"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..maths import Matrix
from ..util import _ArgumentError, _UNSET
from .THdependNode import THDependNode


class InverseMatrix(THDependNode):
    """逆行列を計算する。Maya付属matrixNodesの明示的なロードが必要。"""

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
            InverseMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            value = Matrix(value)
            self.getInputPlug().set(value, fast=fast)
            return self

    def connectInput(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            InverseMatrix: 自身。

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
            from ..plugs.plug import Plug as _InputPlug
            _InputPlug._resolve_input(source).connectTo(self.getInputPlug(), force=force)
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
