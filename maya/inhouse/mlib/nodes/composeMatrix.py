"""移動・回転・スケール・シアーから行列を構築する。"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..maths import Matrix
from ..util import _ArgumentError, _UNSET
from ._calculation import _Calculation
from .node import Node


class ComposeMatrix(Node):
    """移動・回転・スケール・シアーから行列を構築する。"""

    def getTranslatePlug(self):
        """translate入力（移動はcm）のPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("inputTranslate")

    def getTranslate(self):
        """translate入力（移動はcm）の評価値を取得する。

        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getTranslatePlug().get()

    def setTranslate(self, value, *, fast=False):
        """translate入力（移動はcm）へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.vector, self.getTranslatePlug, fast=fast)
            return self

    def connectTranslate(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """translate入力（移動はcm）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            ComposeMatrix: 自身。

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
            _Calculation.connect(source, self.getTranslatePlug, force=force)
            return self

    def getRotatePlug(self):
        """rotate入力（回転はrad）のPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("inputRotate")

    def getRotate(self):
        """rotate入力（回転はrad）の評価値を取得する。

        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getRotatePlug().get()

    def setRotate(self, value, *, fast=False):
        """rotate入力（回転はrad）へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.vector, self.getRotatePlug, fast=fast)
            return self

    def connectRotate(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """rotate入力（回転はrad）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            ComposeMatrix: 自身。

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
            _Calculation.connect(source, self.getRotatePlug, force=force)
            return self

    def getScalePlug(self):
        """scale入力（無次元）のPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("inputScale")

    def getScale(self):
        """scale入力（無次元）の評価値を取得する。

        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getScalePlug().get()

    def setScale(self, value, *, fast=False):
        """scale入力（無次元）へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.vector, self.getScalePlug, fast=fast)
            return self

    def connectScale(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """scale入力（無次元）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            ComposeMatrix: 自身。

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
            _Calculation.connect(source, self.getScalePlug, force=force)
            return self

    def getShearPlug(self):
        """shear入力（無次元）のPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("inputShear")

    def getShear(self):
        """shear入力（無次元）の評価値を取得する。

        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getShearPlug().get()

    def setShear(self, value, *, fast=False):
        """shear入力（無次元）へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.vector, self.getShearPlug, fast=fast)
            return self

    def connectShear(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """shear入力（無次元）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            ComposeMatrix: 自身。

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
            _Calculation.connect(source, self.getShearPlug, force=force)
            return self

    def getQuaternionPlug(self):
        """XYZW順のQuaternion入力のPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("inputQuat")

    def getQuaternion(self):
        """XYZW順のQuaternion入力の評価値を取得する。

        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getQuaternionPlug().get()

    def setQuaternion(self, value, *, fast=False):
        """XYZW順のQuaternion入力へ定数値を設定する。

        Args:
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            value = _Calculation.vector(value, 4)
            self.getQuaternionPlug().set(value, fast=fast)
            return self

    def connectQuaternion(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """XYZW順のQuaternion入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            ComposeMatrix: 自身。

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
            _Calculation.connect(source, self.getQuaternionPlug, force=force)
            return self

    def getUseEulerRotationPlug(self):
        """Euler入力を使用するかのPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("useEulerRotation")

    def getUseEulerRotation(self):
        """Euler入力を使用するかの評価値を取得する。

        Returns:
            bool: 現在の値。
        """
        return self.getUseEulerRotationPlug().get()

    def setUseEulerRotation(self, value, *, fast=False):
        """Euler入力を使用するかへ定数値を設定する。

        Args:
            value (bool): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.boolean, self.getUseEulerRotationPlug, fast=fast)
            return self

    def connectUseEulerRotation(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """Euler入力を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            ComposeMatrix: 自身。

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
            _Calculation.connect(source, self.getUseEulerRotationPlug, force=force)
            return self

    def getRotateOrder(self):
        """現在のモード名を取得する。

        Returns:
            str: xyz, yzx, zxy, xzy, yxz, zyx。
        """
        return _Calculation.enum_name(self.getPlug("inputRotateOrder"), ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx"))

    def setRotateOrder(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): xyz, yzx, zxy, xzy, yxz, zyx、またはMayaの番号。
            fast (bool): TrueはUndoなし。

        Returns:
            ComposeMatrix: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            value = _Calculation.enum_value(mode, ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx"))
            self.getPlug("inputRotateOrder").set(value, fast=fast)
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
