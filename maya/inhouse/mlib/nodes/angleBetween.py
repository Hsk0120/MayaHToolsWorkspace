"""2本のベクトルのなす角と回転。"""

from ..decorator import _pick_alias
from ..maths import Vector
from ..util import _ArgumentError, _UNSET
from ._calculation import _Calculation
from .node import Node


class AngleBetween(Node):
    """angleBetweenノードを参照し、二本の入力ベクトルのなす角・回転軸・Euler回転を扱う。

    値設定では入力接続を切らない。通常編集はUndo有効時にまとめ、fast=TrueはUndo設定を変えないOM2直接更新(Undoなし)。途中の変更は自動で戻さない。
    """

    def getInputPlug(self, index=_UNSET, *, idx=_UNSET):
        """入力のPlugを取得する。

        Args:
            index (int): 入力番号1または2。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        index = _pick_alias(index, idx, "index", "idx")
        return self.getPlug(f"vector{_Calculation.index(index, (1, 2))}")

    def getInput(self, index=_UNSET, *, idx=_UNSET):
        """入力の評価値を取得する。

        Args:
            index (int): 入力番号1または2。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            tuple[float, float, float]: 現在の値。
        """
        index = _pick_alias(index, idx, "index", "idx")
        return self.getInputPlug(index).get()

    def setInput(self, index=_UNSET, value=_UNSET, *, fast=False, idx=_UNSET):
        """入力へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。
            value (Iterable[float]): 設定値。数値は有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            AngleBetween: 自身。
        """
        index = _pick_alias(index, idx, "index", "idx")
        if value is _UNSET:
            raise _ArgumentError("Missing required argument: 'value'")
        with _Calculation.edit_context(self, "setInput", fast):
            _Calculation.set_value(value, _Calculation.vector, self.getInputPlug, index, fast=fast)
            return self

    def connectInput(self, index=_UNSET, source=_UNSET, force=_UNSET, *, fast=False, idx=_UNSET, src=_UNSET, f=_UNSET):
        """入力へ接続する。

        Args:
            index (int): 入力番号1または2。
            source (Plug | str | MPlug): 接続元。別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。別名 ``f`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            idx (int): indexの別名。同時指定は不可。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            AngleBetween: 自身。
        """
        index = _pick_alias(index, idx, "index", "idx")
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectInput", fast):
            _Calculation.connect(source, self.getInputPlug, index, force=force, fast=fast)
            return self

    def getResult(self):
        """入力ベクトル間の角度をradで評価して返す。

        Returns:
            float: angleアトリビュートの値。内部角度単位rad。
        """
        return self.getPlug("angle").get()

    def getAxis(self):
        """評価済みの回転軸を取得する。

        Returns:
            Vector: 入力ベクトル1から2への回転軸(単位ベクトル)。

        Note:
            axisは複合axisAngleの子で、angleBetweenはaxisAngle全体を要求されたときに軸を
            計算する。子のaxisだけをOpenMayaで読むと再計算されず既定値(0, 0, 1)が返るため、
            親のaxisAngleをデータハンドルで評価してから子の値を読む。
        """
        parent = self.getPlug("axisAngle").mplug()
        child = self.getPlug("axis").mplug().attribute()
        handle = parent.asMDataHandle()
        try:
            value = handle.child(child).asDouble3()
        finally:
            parent.destructHandle(handle)
        return Vector(value)

    def getRotate(self):
        """Euler回転を取得する。

        Returns:
            tuple[float, float, float]: XYZ順、rad。
        """
        return tuple(self.getPlug("euler").get())
