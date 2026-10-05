"""複合アトリビュートとその子プラグを扱う。"""

import maya.api.OpenMaya as om2

from ..decorators._safe import safe_edit
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from .plug import Plug


class CompoundPlug(Plug):
    """compound アトリビュート用の Plug。"""

    def __getattr__(self, name):
        """子を Python アトリビュート形式で取得する。

        Args:
            name (str): 子アトリビュート名。

        Returns:
            Plug: 解決した子プラグ。

        Raises:
            AttributeError: private 名または存在しない子を指定した場合。所有ノード・アトリビュートが
                削除済みの(無効な)Plug の場合も、``hasattr``/``getattr(..., default)`` が
                使えるよう AttributeError にする(原因の RuntimeError を ``__cause__`` に持つ)。
        """
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self.child(name)
        except (AttributeError, TypeError, RuntimeError) as error:
            raise AttributeError(f"No plug member named {name!r}") from error

    def get(self):
        """子プラグの値を集めた tuple を返す。

        Returns:
            tuple: 子の数と同じ長さの値。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return tuple(self._child_at(index).get() for index in range(self._mplug.numChildren()))

    @fast_edit
    @undoChunk("hlibCompoundPlugSet")
    @safe_edit
    def set(self, value, safe=False, *, fast=False):
        """子数と同数のシーケンスを各子プラグへ設定する。

        子の変更を一回のUndoにまとめる。要素数は先に検査する。
        float/long/shortの固定長数値型は全子の書込み可否を確認し型付きで一括設定する。
        その他の複合型は子ごとの設定を使う。途中の失敗時に完了済みの値は自動で戻さない。

        Args:
            safe (bool): Trueで書込み失敗を抑制し、失敗数を返す。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Iterable[object]): 子プラグと同じ数の値。先頭から順に設定する。

        Returns:
            CompoundPlug | int: 自身。safe=Trueでは失敗した成分数。

        Raises:
            ValueError: 要素数が子数と一致しない場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        self._require_valid()
        values = tuple(value)
        if len(values) != self._mplug.numChildren():
            raise ValueError("Compound plug value length does not match its child count")
        if self.dataType() in {"float2", "float3", "long2", "long3", "short2", "short3"}:
            self._require_writable()
            Plug.set(self, values)
        else:
            for index, child_value in enumerate(values):
                self._child_at(index).set(child_value)
        return self

    def child(self, name_or_index):
        """子 Plug を取得する。

        整数の場合は MPlug.child に直接渡す。範囲外の添字による例外は Maya API から伝播する。

        Args:
            name_or_index (str | int): 子のロング名、ショート名、または子インデックス。

        Returns:
            Plug: 子プラグ。

        Raises:
            AttributeError: 名前に一致する子アトリビュートがない場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        if isinstance(name_or_index, int):
            return self._child_at(name_or_index)
        for index in range(self._mplug.numChildren()):
            child = self._mplug.child(index)
            attribute = om2.MFnAttribute(child.attribute())
            if name_or_index in (attribute.name, attribute.shortName):
                return Plug(self._node, child)
        raise AttributeError(f"No child named {name_or_index!r} on {self.fullName()}")

    def children(self):
        """直接の子 Plug をすべて取得する。

        Returns:
            list[Plug]: 子プラグ。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        return [self._child_at(index) for index in range(self._mplug.numChildren())]

    def _child_at(self, index):
        """有効性を確かめ済みの前提で、子インデックスの子 Plug を作る。

        Args:
            index (int): 子インデックス。

        Returns:
            Plug: 子プラグ。
        """
        return Plug(self._node, self._mplug.child(index))
