"""内積・外積・行列による点/ベクトル変換。"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..maths import Matrix, Vector
from ..util import _ArgumentError, _UNSET
from ._calculation import _Calculation
from .shadingDependNode import ShadingDependNode


class VectorProduct(ShadingDependNode):
    """内積・外積・行列による点/ベクトル変換。"""

    def getInputPlug(self, index=_UNSET, *, idx=_UNSET):
        """入力のPlugを取得する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        return self.getPlug(f"input{_Calculation.index(index, (1, 2))}")

    def getInput(self, index=_UNSET, *, idx=_UNSET):
        """入力の評価値を取得する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            Iterable[float]: 現在の値。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        return self.getInputPlug(index).get()

    def setInput(self, index=_UNSET, value=_UNSET, *, fast=False, idx=_UNSET):
        """入力へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            VectorProduct: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        if value is _UNSET:
            raise _ArgumentError("Missing required argument: 'value'")
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.vector, self.getInputPlug, index, fast=fast)
            return self

    def connectInput(self, index=_UNSET, source=_UNSET, force=_UNSET, *, idx=_UNSET, src=_UNSET, f=_UNSET):
        """入力へ接続する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            idx (int): indexの別名。同時指定は不可。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            VectorProduct: 自身。

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
            _Calculation.connect(source, self.getInputPlug, index, force=force)
            return self

    def getOperation(self):
        """現在のモード名を取得する。

        Returns:
            str: none, dot, cross, vector_matrix, point_matrix。
        """
        return _Calculation.enum_name(self.getPlug("operation"), ("none", "dot", "cross", "vector_matrix", "point_matrix"))

    def setOperation(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): none, dot, cross, vector_matrix, point_matrix、またはMayaの番号。
            fast (bool): TrueはUndoなし。

        Returns:
            VectorProduct: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            value = _Calculation.enum_value(mode, ("none", "dot", "cross", "vector_matrix", "point_matrix"))
            self.getPlug("operation").set(value, fast=fast)
            return self

    def getMatrixPlug(self):
        """変換行列のPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("matrix")

    def getMatrix(self):
        """変換行列の評価値を取得する。

        Returns:
            Matrix: 現在の値。
        """
        return self.getMatrixPlug().get()

    def setMatrix(self, value, *, fast=False):
        """変換行列へ定数値を設定する。

        Args:
            value (Matrix): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            VectorProduct: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, Matrix, self.getMatrixPlug, fast=fast)
            return self

    def connectMatrix(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """変換行列へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            VectorProduct: 自身。

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
            _Calculation.connect(source, self.getMatrixPlug, force=force)
            return self

    def getNormalizeOutput(self):
        """出力正規化の評価値を取得する。

        Returns:
            bool: 現在の値。
        """
        return self.getPlug("normalizeOutput").get()

    def setNormalizeOutput(self, value, *, fast=False):
        """出力正規化へ定数値を設定する。

        Args:
            value (bool): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            VectorProduct: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.boolean, self.getPlug, "normalizeOutput", fast=fast)
            return self

    def connectNormalizeOutput(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """出力正規化へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            VectorProduct: 自身。

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
            _Calculation.connect(source, self.getPlug, "normalizeOutput", force=force)
            return self

    def getResult(self):
        """現在の入力をMayaで評価した結果を取得する。

        Returns:
            Vector: 計算結果。
        """
        return Vector(self.getPlug("output").get())
