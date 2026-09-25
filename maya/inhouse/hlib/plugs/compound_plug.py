"""複合属性とその子プラグを扱う。"""

from ..decorators._fast import fast_edit

import maya.api.OpenMaya as om2

from ..decorators.undo import undo_chunk
from .plug import Plug


class CompoundPlug(Plug):
    """compound 属性用の Plug。"""

    def get(self, ws=False):
        """子プラグの値を集めた tuple を返す。

        Args:
            ws (bool): 汎用 compound 属性では無視される。

        Returns:
            tuple: 子の数と同じ長さの値。
        """
        return tuple(self.child(index).get() for index in range(self._mplug.numChildren()))

    @fast_edit
    @undo_chunk("hlibCompoundPlugSet")
    def set(self, value, *, fast=False):
        """子数と同数のシーケンスを各子プラグへ設定する。

        子の変更を一回のUndoにまとめる。要素数は先に検査する。
        設定途中の失敗時に、先に設定した子の値を自動で戻す処理はない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Iterable[object]): 子プラグと同じ数の値。先頭から順に設定する。

        Returns:
            CompoundPlug: 自身。

        Raises:
            ValueError: 要素数が子数と一致しない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        values = tuple(value)
        if len(values) != self._mplug.numChildren():
            raise ValueError("Compound plug value length does not match its child count")
        for index, child_value in enumerate(values):
            self.child(index).set(child_value)
        return self

    def child(self, name_or_index):
        """子 Plug を取得する。

        整数の場合は MPlug.child に直接渡す。範囲外の添字による例外は Maya API から伝播する。

        Args:
            name_or_index (str | int): 子のロング名、ショート名、または子インデックス。

        Returns:
            Plug: 子プラグ。

        Raises:
            AttributeError: 名前に一致する子属性がない場合。
        """
        if isinstance(name_or_index, int):
            return Plug(self._node, self._mplug.child(name_or_index))
        for index in range(self._mplug.numChildren()):
            child = self._mplug.child(index)
            attribute = om2.MFnAttribute(child.attribute())
            if name_or_index in (attribute.name, attribute.shortName):
                return Plug(self._node, child)
        raise AttributeError(f"No child named {name_or_index!r} on {self.full_name()}")

    def children(self):
        """直接の子 Plug をすべて取得する。

        Returns:
            list[Plug]: 子プラグ。
        """
        return [self.child(index) for index in range(self._mplug.numChildren())]

    def __getattr__(self, name):
        """子を Python 属性形式で取得する。

        Args:
            name (str): 子属性名。

        Returns:
            Plug: 解決した子プラグ。

        Raises:
            AttributeError: private 名または存在しない子を指定した場合。
        """
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self.child(name)
        except (AttributeError, TypeError) as error:
            raise AttributeError(f"No plug member named {name!r}") from error
