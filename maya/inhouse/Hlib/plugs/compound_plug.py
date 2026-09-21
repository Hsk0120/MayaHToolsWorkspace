"""compound attribute plug wrapper."""

import maya.api.OpenMaya as om2

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

    def set(self, value):
        """子数と同数のシーケンスを各子プラグへ設定する。

        Args:
            value (object): 子数と同数のシーケンス。

        Returns:
            Plug: 自身。

        Raises:
            ValueError: 要素数が子数と一致しない場合。
        """
        values = tuple(value)
        if len(values) != self._mplug.numChildren():
            raise ValueError("Compound plug value length does not match its child count")
        for index, child_value in enumerate(values):
            self.child(index).set(child_value)
        return self

    def child(self, name_or_index):
        """子 Plug を取得する。

        Args:
            name_or_index (str | int): 子のロング名、ショート名、または子インデックス。

        Returns:
            Plug: 子プラグ。

        Raises:
            AttributeError: 指定した子が存在しない場合。
        """
        if isinstance(name_or_index, int):
            return Plug(self._node, self._mplug.child(name_or_index))
        for index in range(self._mplug.numChildren()):
            child = self._mplug.child(index)
            attribute = om2.MFnAttribute(child.attribute())
            if name_or_index in (attribute.name, attribute.shortName):
                return Plug(self._node, child)
        raise AttributeError(f"No child named {name_or_index!r} on {self.full_name}")

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
