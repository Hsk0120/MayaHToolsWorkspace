"""移動・回転・スケール・シアーからマトリクスを構築する。"""

from ..decorator import _pick_alias
from ..maths import Matrix
from ..util import _UNSET
from ._calculation import _Calculation
from .node import Node


class ComposeMatrix(Node):
    """composeMatrixノードを参照し、移動(cm)・回転(rad)・スケール・シアー入力からマトリクスを評価する。

    値設定は入力接続を切断しない。通常の設定・接続はUndo有効時にチャンクへ記録する。
    設定・接続のfast=TrueはUndoなしのOM2直接更新で、Undo設定は変えない。途中失敗の変更は自動で戻さない。
    """

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
            value (Iterable[float]): XYZ順の有限な3成分(cm)。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            ComposeMatrix: 自身。
        """
        with _Calculation.edit_context(self, "setTranslate", fast):
            _Calculation.set_value(value, _Calculation.vector, self.getTranslatePlug, fast=fast)
            return self

    def connectTranslate(self, source=_UNSET, force=_UNSET, *, fast=False, src=_UNSET, f=_UNSET):
        """translate入力（移動はcm）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): Trueで既存の入力接続を置き換える。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            ComposeMatrix: 自身。
        """
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectTranslate", fast):
            _Calculation.connect(source, self.getTranslatePlug, force=force, fast=fast)
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
            value (Iterable[float]): XYZ順の有限な3成分(rad)。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            ComposeMatrix: 自身。
        """
        with _Calculation.edit_context(self, "setRotate", fast):
            _Calculation.set_value(value, _Calculation.vector, self.getRotatePlug, fast=fast)
            return self

    def connectRotate(self, source=_UNSET, force=_UNSET, *, fast=False, src=_UNSET, f=_UNSET):
        """rotate入力（回転はrad）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): Trueで既存の入力接続を置き換える。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            ComposeMatrix: 自身。
        """
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectRotate", fast):
            _Calculation.connect(source, self.getRotatePlug, force=force, fast=fast)
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
            value (Iterable[float]): XYZ順の有限な3成分。無次元。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            ComposeMatrix: 自身。
        """
        with _Calculation.edit_context(self, "setScale", fast):
            _Calculation.set_value(value, _Calculation.vector, self.getScalePlug, fast=fast)
            return self

    def connectScale(self, source=_UNSET, force=_UNSET, *, fast=False, src=_UNSET, f=_UNSET):
        """scale入力（無次元）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): Trueで既存の入力接続を置き換える。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            ComposeMatrix: 自身。
        """
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectScale", fast):
            _Calculation.connect(source, self.getScalePlug, force=force, fast=fast)
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
            value (Iterable[float]): XY・XZ・YZ順の有限な3成分。無次元。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            ComposeMatrix: 自身。
        """
        with _Calculation.edit_context(self, "setShear", fast):
            _Calculation.set_value(value, _Calculation.vector, self.getShearPlug, fast=fast)
            return self

    def connectShear(self, source=_UNSET, force=_UNSET, *, fast=False, src=_UNSET, f=_UNSET):
        """shear入力（無次元）へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): Trueで既存の入力接続を置き換える。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            ComposeMatrix: 自身。
        """
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectShear", fast):
            _Calculation.connect(source, self.getShearPlug, force=force, fast=fast)
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
            value (Iterable[float]): XYZW順の有限な4成分。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            ComposeMatrix: 自身。
        """
        with _Calculation.edit_context(self, "setQuaternion", fast):
            value = _Calculation.vector(value, 4)
            self.getQuaternionPlug().set(value, fast=fast)
            return self

    def connectQuaternion(self, source=_UNSET, force=_UNSET, *, fast=False, src=_UNSET, f=_UNSET):
        """XYZW順のQuaternion入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): Trueで既存の入力接続を置き換える。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            ComposeMatrix: 自身。
        """
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectQuaternion", fast):
            _Calculation.connect(source, self.getQuaternionPlug, force=force, fast=fast)
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
        """Euler入力とQuaternion入力を切り替える。

        Args:
            value (bool): TrueはEuler入力、FalseはQuaternion入力を使う。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            ComposeMatrix: 自身。
        """
        with _Calculation.edit_context(self, "setUseEulerRotation", fast):
            _Calculation.set_value(value, _Calculation.boolean, self.getUseEulerRotationPlug, fast=fast)
            return self

    def connectUseEulerRotation(self, source=_UNSET, force=_UNSET, *, fast=False, src=_UNSET, f=_UNSET):
        """Euler入力を使用するかへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): Trueで既存の入力接続を置き換える。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            ComposeMatrix: 自身。
        """
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectUseEulerRotation", fast):
            _Calculation.connect(source, self.getUseEulerRotationPlug, force=force, fast=fast)
            return self

    def getRotateOrder(self):
        """現在のモード名を取得する。

        Returns:
            str: xyz, yzx, zxy, xzy, yxz, zyx。
        """
        return _Calculation.enum_name(self.getPlug("inputRotateOrder"), ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx"))

    def setRotateOrder(self, mode, *, fast=False):
        """Euler入力の回転順を設定する。

        Args:
            mode (str | int): xyz, yzx, zxy, xzy, yxz, zyx、またはMayaの番号。
            fast (bool): TrueはUndoなし。

        Returns:
            ComposeMatrix: 自身。
        """
        with _Calculation.edit_context(self, "setRotateOrder", fast):
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
