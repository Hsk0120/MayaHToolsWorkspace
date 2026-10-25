"""行列の使用成分を選択する。"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..maths import Matrix
from ..util import _ArgumentError, _UNSET
from ._calculation import _Calculation
from .node import Node


class PickMatrix(Node):
    """pickMatrixノードを参照し、入力行列の使用成分を選択する。

    値設定は入力接続を切断しない。通常の設定・接続はUndo有効時にチャンクへ記録する。
    fast=Trueの設定はUndoなしのOM2直接更新で、Undo設定は変えない。途中失敗の変更は自動で戻さない。
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
            PickMatrix: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, Matrix, self.getInputPlug, fast=fast)
            return self

    def connectInput(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): Trueで既存の入力接続を置き換える。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            PickMatrix: 自身。
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

    def getUseTranslatePlug(self):
        """translate成分を使用するかのPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("useTranslate")

    def getUseTranslate(self):
        """translate成分を使用するかの評価値を取得する。

        Returns:
            bool: 現在の値。
        """
        return self.getUseTranslatePlug().get()

    def setUseTranslate(self, value, *, fast=False):
        """translate成分を使用するかへ定数値を設定する。

        Args:
            value (bool): Trueで移動成分を出力へ含める。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            PickMatrix: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.boolean, self.getUseTranslatePlug, fast=fast)
            return self

    def connectUseTranslate(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """translate成分を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): Trueで既存の入力接続を置き換える。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            PickMatrix: 自身。
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
            _Calculation.connect(source, self.getUseTranslatePlug, force=force)
            return self

    def getUseRotatePlug(self):
        """rotate成分を使用するかのPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("useRotate")

    def getUseRotate(self):
        """rotate成分を使用するかの評価値を取得する。

        Returns:
            bool: 現在の値。
        """
        return self.getUseRotatePlug().get()

    def setUseRotate(self, value, *, fast=False):
        """rotate成分を使用するかへ定数値を設定する。

        Args:
            value (bool): Trueで回転成分を出力へ含める。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            PickMatrix: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.boolean, self.getUseRotatePlug, fast=fast)
            return self

    def connectUseRotate(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """rotate成分を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): Trueで既存の入力接続を置き換える。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            PickMatrix: 自身。
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
            _Calculation.connect(source, self.getUseRotatePlug, force=force)
            return self

    def getUseScalePlug(self):
        """scale成分を使用するかのPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("useScale")

    def getUseScale(self):
        """scale成分を使用するかの評価値を取得する。

        Returns:
            bool: 現在の値。
        """
        return self.getUseScalePlug().get()

    def setUseScale(self, value, *, fast=False):
        """scale成分を使用するかへ定数値を設定する。

        Args:
            value (bool): Trueでスケール成分を出力へ含める。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            PickMatrix: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.boolean, self.getUseScalePlug, fast=fast)
            return self

    def connectUseScale(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """scale成分を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): Trueで既存の入力接続を置き換える。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            PickMatrix: 自身。
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
            _Calculation.connect(source, self.getUseScalePlug, force=force)
            return self

    def getUseShearPlug(self):
        """shear成分を使用するかのPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("useShear")

    def getUseShear(self):
        """shear成分を使用するかの評価値を取得する。

        Returns:
            bool: 現在の値。
        """
        return self.getUseShearPlug().get()

    def setUseShear(self, value, *, fast=False):
        """shear成分を使用するかへ定数値を設定する。

        Args:
            value (bool): Trueでシアー成分を出力へ含める。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            PickMatrix: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.boolean, self.getUseShearPlug, fast=fast)
            return self

    def connectUseShear(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """shear成分を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): Trueで既存の入力接続を置き換える。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            PickMatrix: 自身。
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
            _Calculation.connect(source, self.getUseShearPlug, force=force)
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
