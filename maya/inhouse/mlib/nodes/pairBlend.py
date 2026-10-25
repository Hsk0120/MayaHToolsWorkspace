"""移動・回転をブレンドする。Euler/Quaternion補間を選択できる。"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..util import _ArgumentError, _UNSET
from ._calculation import _Calculation
from .node import Node


class PairBlend(Node):
    """pairBlendノードを参照し、二組の移動・回転入力とブレンド結果を扱う。

    値設定では入力接続を切らない。通常編集はUndo有効時にまとめ、fast=TrueはUndo設定を変えないOM2直接更新（Undoなし）。途中の変更は自動で戻さない。
    """

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

    def setWeight(self, value, *, fast=False):
        """ブレンドウェイトへ定数値を設定する。

        Args:
            value (float): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            PairBlend: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            _Calculation.set_value(value, _Calculation.scalar, self.getWeightPlug, fast=fast)
            return self

    def connectWeight(self, source=_UNSET, force=_UNSET, *, src=_UNSET, f=_UNSET):
        """ブレンドウェイトへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            PairBlend: 自身。
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
            _Calculation.connect(source, self.getWeightPlug, force=force)
            return self

    def getRotateInterpolation(self):
        """現在のモード名を取得する。

        Returns:
            str: euler, quaternion。
        """
        return _Calculation.enum_name(self.getPlug("rotInterpolation"), ("euler", "quaternion"))

    def setRotateInterpolation(self, mode, *, fast=False):
        """回転のEuler/Quaternion補間方式を設定する。

        Args:
            mode (str | int): euler, quaternion、またはMayaの番号。
            fast (bool): TrueはUndoなし。

        Returns:
            PairBlend: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            value = _Calculation.enum_value(mode, ("euler", "quaternion"))
            self.getPlug("rotInterpolation").set(value, fast=fast)
            return self

    def getRotateOrder(self):
        """現在のモード名を取得する。

        Returns:
            str: xyz, yzx, zxy, xzy, yxz, zyx。
        """
        return _Calculation.enum_name(self.getPlug("rotateOrder"), ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx"))

    def setRotateOrder(self, mode, *, fast=False):
        """pairBlendのEuler回転順を設定する。

        Args:
            mode (str | int): xyz, yzx, zxy, xzy, yxz, zyx、またはMayaの番号。
            fast (bool): TrueはUndoなし。

        Returns:
            PairBlend: 自身。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCalculationEdit"):
            value = _Calculation.enum_value(mode, ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx"))
            self.getPlug("rotateOrder").set(value, fast=fast)
            return self

    def getTranslatePlug(self, index=_UNSET, *, idx=_UNSET):
        """translate入力（cm）のPlugを取得する。

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
        return self.getPlug(f"inTranslate{_Calculation.index(index, (1, 2))}")

    def getTranslate(self, index=_UNSET, *, idx=_UNSET):
        """translate入力（cm）の評価値を取得する。

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
        return self.getTranslatePlug(index).get()

    def setTranslate(self, index=_UNSET, value=_UNSET, *, fast=False, idx=_UNSET):
        """指定入力のXYZ移動をcmで設定する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            value (Iterable[float]): XYZ順の3成分。有限値のみ。
            fast (bool): TrueはUndoなしのOpenMaya更新。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            PairBlend: 自身。
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
            _Calculation.set_value(value, _Calculation.vector, self.getTranslatePlug, index, fast=fast)
            return self

    def connectTranslate(self, index=_UNSET, source=_UNSET, force=_UNSET, *, idx=_UNSET, src=_UNSET, f=_UNSET):
        """translate入力（cm）へ接続する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            idx (int): indexの別名。同時指定は不可。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            PairBlend: 自身。
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
            _Calculation.connect(source, self.getTranslatePlug, index, force=force)
            return self

    def getRotatePlug(self, index=_UNSET, *, idx=_UNSET):
        """rotate入力（rad）のPlugを取得する。

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
        return self.getPlug(f"inRotate{_Calculation.index(index, (1, 2))}")

    def getRotate(self, index=_UNSET, *, idx=_UNSET):
        """rotate入力（rad）の評価値を取得する。

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
        return self.getRotatePlug(index).get()

    def setRotate(self, index=_UNSET, value=_UNSET, *, fast=False, idx=_UNSET):
        """指定入力のXYZ回転をradで設定する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            value (Iterable[float]): XYZ順の3成分。有限値のみ。
            fast (bool): TrueはUndoなしのOpenMaya更新。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            PairBlend: 自身。
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
            _Calculation.set_value(value, _Calculation.vector, self.getRotatePlug, index, fast=fast)
            return self

    def connectRotate(self, index=_UNSET, source=_UNSET, force=_UNSET, *, idx=_UNSET, src=_UNSET, f=_UNSET):
        """rotate入力（rad）へ接続する。

        Args:
            index (int): 入力番号1または2。 別名 ``idx`` も使用可能。
            source (Plug | str | MPlug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。 別名 ``f`` も使用可能。
            idx (int): indexの別名。同時指定は不可。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            PairBlend: 自身。
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
