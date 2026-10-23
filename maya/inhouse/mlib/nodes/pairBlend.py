"""移動・回転をブレンドする。Euler/Quaternion補間を選択できる。"""

from ..decorator import _flag_aliases, _fast_edit, undoChunk
from ._calculation import _Calculation
from .node import Node


class PairBlend(Node):
    """移動・回転をブレンドする。Euler/Quaternion補間を選択できる。"""

    def getWeightPlug(self):
        """ブレンドウェイトのPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("weight")

    def getWeight(self):
        """ブレンドウェイトの評価値を取得する。

        Returns:
            float: 現在の値。
        """
        return self.getWeightPlug().get()

    @_fast_edit
    @undoChunk("mlibCalculationEdit")
    def setWeight(self, value, *, fast=False):
        """ブレンドウェイトへ定数値を設定する。

        Args:
            value (float): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.scalar, self.getWeightPlug)
        return self

    @_flag_aliases(src="source", f="force")
    @undoChunk("mlibCalculationEdit")
    def connectWeight(self, source, force=False):
        """ブレンドウェイトへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。

        Returns:
            PairBlend: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getWeightPlug, force=force)
        return self

    def getRotateInterpolation(self):
        """現在のモード名を取得する。

        Returns:
            str: euler, quaternion。
        """
        return _Calculation.enum_name(self.getPlug("rotInterpolation"), ("euler", "quaternion"))

    @_fast_edit
    @undoChunk("mlibCalculationEdit")
    def setRotateInterpolation(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): euler, quaternion、またはMayaの番号。
            fast (bool): TrueはUndoなし。

        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enum_value(mode, ("euler", "quaternion"))
        self.getPlug("rotInterpolation").set(value)
        return self

    def getRotateOrder(self):
        """現在のモード名を取得する。

        Returns:
            str: xyz, yzx, zxy, xzy, yxz, zyx。
        """
        return _Calculation.enum_name(self.getPlug("rotateOrder"), ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx"))

    @_fast_edit
    @undoChunk("mlibCalculationEdit")
    def setRotateOrder(self, mode, *, fast=False):
        """モードを設定する。

        Args:
            mode (str | int): xyz, yzx, zxy, xzy, yxz, zyx、またはMayaの番号。
            fast (bool): TrueはUndoなし。

        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        value = _Calculation.enum_value(mode, ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx"))
        self.getPlug("rotateOrder").set(value)
        return self

    @_flag_aliases(idx="index")
    def getTranslatePlug(self, index):
        """translate入力（cm）のPlugを取得する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug(f"inTranslate{_Calculation.index(index, (1, 2))}")

    @_flag_aliases(idx="index")
    def getTranslate(self, index):
        """translate入力（cm）の評価値を取得する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。

        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getTranslatePlug(index).get()

    @_flag_aliases(idx="index")
    @_fast_edit
    @undoChunk("mlibCalculationEdit")
    def setTranslate(self, index, value, *, fast=False):
        """translate入力（cm）へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.getTranslatePlug, index)
        return self

    @_flag_aliases(idx="index", src="source", f="force")
    @undoChunk("mlibCalculationEdit")
    def connectTranslate(self, index, source, force=False):
        """translate入力（cm）へ接続する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。

        Returns:
            PairBlend: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getTranslatePlug, index, force=force)
        return self

    @_flag_aliases(idx="index")
    def getRotatePlug(self, index):
        """rotate入力（rad）のPlugを取得する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug(f"inRotate{_Calculation.index(index, (1, 2))}")

    @_flag_aliases(idx="index")
    def getRotate(self, index):
        """rotate入力（rad）の評価値を取得する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。

        Returns:
            Iterable[float]: 現在の値。
        """
        return self.getRotatePlug(index).get()

    @_flag_aliases(idx="index")
    @_fast_edit
    @undoChunk("mlibCalculationEdit")
    def setRotate(self, index, value, *, fast=False):
        """rotate入力（rad）へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            PairBlend: 自身。

        Note:
            接続済み入力は値設定で切断しません。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.set_value(value, _Calculation.vector, self.getRotatePlug, index)
        return self

    @_flag_aliases(idx="index", src="source", f="force")
    @undoChunk("mlibCalculationEdit")
    def connectRotate(self, index, source, force=False):
        """rotate入力（rad）へ接続する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。

        Returns:
            PairBlend: 自身。

        Note:
            force=True では既存接続を置き換えます。通常モードでは失敗前の変更もUndoで戻せます。
        """
        _Calculation.connect(source, self.getRotatePlug, index, force=force)
        return self

    def getOutputPlug(self, kind="translate"):
        """移動または回転の出力を取得する。

        Args:
            kind (str): translate/rotate。

        Returns:
            Plug: 出力参照。
        """
        if kind not in ("translate", "rotate"):
            raise ValueError("kind must be translate or rotate")
        return self.getPlug("out" + kind.title())

    def getResult(self, kind="translate"):
        """移動または回転の評価値を取得する。

        Args:
            kind (str): translate/rotate。

        Returns:
            tuple[float, float, float]: 移動はcm、回転はrad。
        """
        return tuple(self.getOutputPlug(kind).get())
