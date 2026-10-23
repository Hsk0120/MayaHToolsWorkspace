"""複合アトリビュートとその子プラグを扱う。"""

import maya.api.OpenMaya as om2

from ..core.fastWrite import set_plug
from ..decorator import _fast_edit, _is_fast, _safe_edit, undoChunk
from .plug import Plug


class CompoundPlug(Plug):
    """番号・子名の角括弧アクセスに対応する複合Plug。

    maya.cmdsへ渡す場合はstrまたはfullNameで文字列化する。
    mlibのコマンドにはそのまま渡せる。
    """

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
            return self[name]
        except (AttributeError, TypeError, RuntimeError) as error:
            raise AttributeError(f"No plug member named {name!r}") from error

    def __getitem__(self, name_or_index):
        """子 Plug を取得する。

        整数は定義順の子番号。負数・範囲外はIndexError。

        Args:
            name_or_index (str | int): 子のロング名、ショート名、または子インデックス。

        Returns:
            Plug: 子プラグ。

        Raises:
            AttributeError: 名前に一致する子アトリビュートがない場合。
            IndexError: 整数番号が子の範囲外の場合。
            TypeError: 整数または文字列以外を指定した場合。boolも拒否する。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        if isinstance(name_or_index, bool) or not isinstance(name_or_index, (int, str)):
            raise TypeError("Child index must be an integer or attribute name")
        if isinstance(name_or_index, int):
            if not 0 <= name_or_index < self._mplug.numChildren():
                raise IndexError("Child index out of range")
            return self._child_at(name_or_index)
        for index in range(self._mplug.numChildren()):
            child = self._mplug.child(index)
            attribute = om2.MFnAttribute(child.attribute())
            if name_or_index in (attribute.name, attribute.shortName):
                return Plug(self._node, child)
        raise AttributeError(f"No child named {name_or_index!r} on {self.getFullName()}")

    def __iter__(self):
        """子を定義順で反復する。

        Returns:
            Iterator[Plug]: 子を定義順で反復する。
        """
        return iter(self.getChildren())

    def get(self, *, uiUnits=False):
        """子プラグの値を集めた tuple を返す。

        Args:
            uiUnits (bool): TrueはUI単位の数値。既定Falseは内部単位。

        Returns:
            tuple: 子の数と同じ長さの値。

        Raises:
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。
        """
        self._require_valid()
        self._validate_ui_units(uiUnits)
        return tuple(self._child_at(index).get(uiUnits=uiUnits) for index in range(self._mplug.numChildren()))

    @_fast_edit
    @undoChunk("mlibCompoundPlugSet")
    @_safe_edit
    def set(self, value, safe=False, *, uiUnits=False, fast=False):
        """子数と同数のシーケンスを各子プラグへ設定する。

        子の変更を一回のUndoにまとめる。要素数は先に検査する。
        float/long/shortの固定長数値型は全子の書込み可否を確認し型付きで一括設定する。
        その他の複合型は子ごとの設定を使う。途中の失敗時に完了済みの値は自動で戻さない。

        Args:
            value (Iterable[object]): 子プラグと同じ数の値。先頭から順に設定する。
            safe (bool): Trueで書込み失敗を抑制し、失敗数を返す。
            uiUnits (bool): TrueはUI単位の数値。既定Falseは内部単位。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            CompoundPlug | int: safe=Falseでは自身。safe=Trueでは書けなかった成分数、全て成功なら0。
                子数と値の件数が不一致など、成分へ分けられない失敗は1を返す。

        Raises:
            ValueError: 要素数が子数と一致しない場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        self._require_valid()
        self._validate_ui_units(uiUnits)
        values = tuple(value)
        if len(values) != self._mplug.numChildren():
            raise ValueError("Compound plug value length does not match its child count")
        if _is_fast():
            if uiUnits:
                from ..core.attributeType import _convert_units
                values = _convert_units(self._mplug, values, to_ui=False)
            set_plug(self._mplug, values)
        elif self.getDataType() in {"float2", "float3", "long2", "long3", "short2", "short3"}:
            self._require_writable()
            Plug.set(self, values, uiUnits=uiUnits)
        else:
            for index, child_value in enumerate(values):
                self._child_at(index).set(child_value, uiUnits=uiUnits)
        return self

    def getChildren(self):
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
