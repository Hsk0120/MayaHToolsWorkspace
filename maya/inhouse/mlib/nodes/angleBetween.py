"""2本のベクトルのなす角と回転。"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..maths import Vector
from ..util import _ArgumentError, _UNSET
from ._calculation import _Calculation
from .node import Node


class AngleBetween(Node):
    """angleBetweenノードを参照し、二本の入力ベクトルのなす角・回転軸・Euler回転を扱う。

    値設定では入力接続を切らない。通常編集はUndo有効時にまとめ、fast=TrueはUndo設定を変えないOM2直接更新（Undoなし）。途中の変更は自動で戻さない。
    """

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
        return self.getPlug(f"vector{_Calculation.index(index, (1, 2))}")

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
            AngleBetween: 自身。
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
            AngleBetween: 自身。
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

    def getResult(self):
        """入力ベクトル間の角度をradで評価して返す。

        Returns:
            float: angleアトリビュートの値。内部角度単位rad。
        """
        return self.getPlug("angle").get()

    def getAxis(self):
        """回転軸を取得する。

        Returns:
            Vector: 回転軸。
        """
        return Vector(self.getPlug("axis").get())

    def getRotate(self):
        """Euler回転を取得する。

        Returns:
            tuple[float, float, float]: XYZ順、rad。
        """
        return tuple(self.getPlug("euler").get())
