"""指定した軸をターゲットへ向ける行列を生成する。"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..maths import Matrix
from ..util import _ArgumentError, _UNSET
from ._calculation import _Calculation
from .node import Node


class AimMatrix(Node):
    """aimMatrixノードを参照し、入力軸・ターゲットと出力行列を扱う。

    値設定では入力接続を切らない。通常編集はUndo有効時にまとめ、fast=TrueはUndo設定を変えないOM2直接更新（Undoなし）。途中の変更は自動で戻さない。
    """

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
            value (Matrix | Iterable[float]): Matrix(value)で解釈する行列。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            AimMatrix: 自身。
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
            AimMatrix: 自身。
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
            AimMatrix: 自身。
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
            AimMatrix: 自身。
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

    def getPrimaryMatrixPlug(self):
        """primaryターゲット行列のPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("primaryTargetMatrix")

    def getPrimaryMatrix(self):
        """primaryターゲット行列の評価値を取得する。

        Returns:
            Matrix: 現在の値。
        """
        return self.getPrimaryMatrixPlug().get()

    def setPrimaryMatrix(self, value, *, fast=False):
        """primaryターゲット行列へ定数値を設定する。

        Args:
            value (Matrix | Iterable[float]): Matrix(value)で解釈する行列。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            AimMatrix: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, Matrix, self.getPrimaryMatrixPlug, fast=fast)
            return self

    def connectPrimaryMatrix(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """primaryターゲット行列へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            AimMatrix: 自身。
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
            _Calculation.connect(source, self.getPrimaryMatrixPlug, force=force)
            return self

    def getPrimaryAxisPlug(self):
        """primary入力軸のPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("primaryInputAxis")

    def getPrimaryAxis(self):
        """primary入力軸の評価値を取得する。

        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getPrimaryAxisPlug().get()

    def setPrimaryAxis(self, value, *, fast=False):
        """primary入力軸へ定数値を設定する。

        Args:
            value (Iterable[float]): XYZ順の有限な3成分。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            AimMatrix: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.vector, self.getPrimaryAxisPlug, fast=fast)
            return self

    def connectPrimaryAxis(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """primary入力軸へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            AimMatrix: 自身。
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
            _Calculation.connect(source, self.getPrimaryAxisPlug, force=force)
            return self

    def getPrimaryVectorPlug(self):
        """primaryターゲットベクトルのPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("primaryTargetVector")

    def getPrimaryVector(self):
        """primaryターゲットベクトルの評価値を取得する。

        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getPrimaryVectorPlug().get()

    def setPrimaryVector(self, value, *, fast=False):
        """primaryターゲットベクトルへ定数値を設定する。

        Args:
            value (Iterable[float]): XYZ順の有限な3成分。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            AimMatrix: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.vector, self.getPrimaryVectorPlug, fast=fast)
            return self

    def connectPrimaryVector(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """primaryターゲットベクトルへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            AimMatrix: 自身。
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
            _Calculation.connect(source, self.getPrimaryVectorPlug, force=force)
            return self

    def getPrimaryMode(self):
        """現在のモード名を取得する。

        Returns:
            str: lock, aim, align。
        """
        return _Calculation.enum_name(self.getPlug("primaryMode"), ("lock", "aim", "align"))

    def setPrimaryMode(self, mode, *, fast=False):
        """primary側の軸合わせモードを設定する。

        Args:
            mode (str | int): lock, aim, align、またはMayaの番号。
            fast (bool): TrueはUndoなし。

        Returns:
            AimMatrix: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            value = _Calculation.enum_value(mode, ("lock", "aim", "align"))
            self.getPlug("primaryMode").set(value, fast=fast)
            return self

    def getSecondaryMatrixPlug(self):
        """secondaryターゲット行列のPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("secondaryTargetMatrix")

    def getSecondaryMatrix(self):
        """secondaryターゲット行列の評価値を取得する。

        Returns:
            Matrix: 現在の値。
        """
        return self.getSecondaryMatrixPlug().get()

    def setSecondaryMatrix(self, value, *, fast=False):
        """secondaryターゲット行列へ定数値を設定する。

        Args:
            value (Matrix | Iterable[float]): Matrix(value)で解釈する行列。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            AimMatrix: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, Matrix, self.getSecondaryMatrixPlug, fast=fast)
            return self

    def connectSecondaryMatrix(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """secondaryターゲット行列へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            AimMatrix: 自身。
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
            _Calculation.connect(source, self.getSecondaryMatrixPlug, force=force)
            return self

    def getSecondaryAxisPlug(self):
        """secondary入力軸のPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("secondaryInputAxis")

    def getSecondaryAxis(self):
        """secondary入力軸の評価値を取得する。

        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getSecondaryAxisPlug().get()

    def setSecondaryAxis(self, value, *, fast=False):
        """secondary入力軸へ定数値を設定する。

        Args:
            value (Iterable[float]): XYZ順の有限な3成分。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            AimMatrix: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.vector, self.getSecondaryAxisPlug, fast=fast)
            return self

    def connectSecondaryAxis(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """secondary入力軸へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            AimMatrix: 自身。
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
            _Calculation.connect(source, self.getSecondaryAxisPlug, force=force)
            return self

    def getSecondaryVectorPlug(self):
        """secondaryターゲットベクトルのPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("secondaryTargetVector")

    def getSecondaryVector(self):
        """secondaryターゲットベクトルの評価値を取得する。

        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getSecondaryVectorPlug().get()

    def setSecondaryVector(self, value, *, fast=False):
        """secondaryターゲットベクトルへ定数値を設定する。

        Args:
            value (Iterable[float]): XYZ順の有限な3成分。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            AimMatrix: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.vector, self.getSecondaryVectorPlug, fast=fast)
            return self

    def connectSecondaryVector(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """secondaryターゲットベクトルへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            AimMatrix: 自身。
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
            _Calculation.connect(source, self.getSecondaryVectorPlug, force=force)
            return self

    def getSecondaryMode(self):
        """現在のモード名を取得する。

        Returns:
            str: none, aim, align。
        """
        return _Calculation.enum_name(self.getPlug("secondaryMode"), ("none", "aim", "align"))

    def setSecondaryMode(self, mode, *, fast=False):
        """secondary側の軸合わせモードを設定する。

        Args:
            mode (str | int): none, aim, align、またはMayaの番号。
            fast (bool): TrueはUndoなし。

        Returns:
            AimMatrix: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            value = _Calculation.enum_value(mode, ("none", "aim", "align"))
            self.getPlug("secondaryMode").set(value, fast=fast)
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
