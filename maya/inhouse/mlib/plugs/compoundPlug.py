"""複合アトリビュートとその子プラグを扱う。"""

from contextlib import nullcontext

import maya.api.OpenMaya as om2

from ..core.fastWrite import _require_supported_type, set_plug
from ..decorator import undoChunk
from .plug import Plug


class CompoundPlug(Plug):
    """複合アトリビュートを参照し、直接の子Plugと値を扱う。

    子は定義順の0始まりの連続番号かロング名・ショート名で取得する。
    番号はArrayPlugの論理番号とは異なる。基底のget()は子の値を定義順tupleで返す。
    maya.cmdsへは ``str(plug)`` で渡す。mlib.selectにはそのまま渡せる。
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
        """複合アトリビュートの直接の子を、定義順の番号または子名で参照する。

        整数は0始まりの子番号で、multi要素の論理番号ではない。負数・sliceは使えない。
        文字列は直接の子のロング名・ショート名と照合し、孫へのパスやaliasは解決しない。
        子の値は読み出さない。

        Args:
            name_or_index (str | int): 子のロング名、ショート名、または定義順の子番号。

        Returns:
            Plug: 同じ所有Nodeを共有する新しい子ラッパー。値やノードの複製ではない。

        Raises:
            AttributeError: 名前に一致する直接の子がない場合。
            IndexError: 整数番号が子の範囲外の場合。
            TypeError: 整数または文字列以外を指定した場合。boolも拒否する。
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
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
        """直接の子の参照一覧を取得し、アトリビュート定義順に反復する。

        反復子を作る時点のgetChildren()を使い、子の値は読み出さない。

        Returns:
            Iterator[Plug]: 作成時に集めた直接の子参照の反復子。
        """
        return iter(self.getChildren())

    def get(self, *, uiUnits=False):
        """直接の子の値を、アトリビュート定義順のtupleで取得する。

        各子でget()を呼ぶため、値取得に伴うDG評価が発生し得る。
        入れ子の複合型や配列型の値は平坦化せず、各子の返却型を保つ。

        Args:
            uiUnits (bool): 各子のgetへ渡す。TrueはUI単位、既定Falseは内部単位。

        Returns:
            tuple: 子数と同じ長さの新しいtuple。値の型・単位は各子のgetに従う。

        Raises:
            TypeError: uiUnitsがbool以外の場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効、または子の値を取得できない場合。
        """
        self._require_valid()
        self._validate_ui_units(uiUnits)
        return tuple(self._child_at(index).get(uiUnits=uiUnits) for index in range(self._mplug.numChildren()))

    def set(self, value, safe=False, *, uiUnits=False, fast=False):
        """子数と同じ長さの値を、アトリビュート定義順に設定する。

        通常はUndo有効時に一括記録し、固定長数値型は型付き設定、それ以外は子ごとに更新する。
        fastは全成分を事前検証して直接更新するが、書込み途中の失敗を自動で戻すものではない。
        safe=Trueは対応する失敗後に子を再試行し、書ける子を更新する。先行変更は戻さない。

        Args:
            value (Iterable[object]): 子数と同じ数の値。
            safe (bool): Trueは対応する書込み失敗を抑制し、失敗数を返す。
            uiUnits (bool): TrueはUI単位。既定Falseは内部単位（角度rad・距離cm・時間秒）。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。既定Falseはcmds。

        Returns:
            CompoundPlug | int: safe=Falseは自身。safe=Trueは子の失敗数、成功は0。
                要素数不一致等で子へ分けられない場合や再試行を完了できない場合は1。
                厳密な未更新成分数とは限らない。

        Raises:
            TypeError: 配列全体への設定、fastがbool以外、またはsafe=Falseで入力型が不正な場合。
            ValueError: safe=Falseで要素数が子数と一致しない場合。
            RuntimeError: safe=Falseで参照が無効、または書込みに失敗した場合。
            NotImplementedError: fastで未対応の型。safe=Trueでも部分更新前に拒否する。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibCompoundPlugSet"):
            if self.isArray():
                raise TypeError("Set an array element instead of the array plug")
            if safe and fast and self.isValid() and self.mplug().isCompound:
                _require_supported_type(self.mplug())
            try:
                self._require_valid()
                self._validate_ui_units(uiUnits)
                values = tuple(value)
                if len(values) != self._mplug.numChildren():
                    raise ValueError("Compound plug value length does not match its child count")
                if fast:
                    if uiUnits:
                        from ..core.attributeType import _convert_units
                        values = _convert_units(self._mplug, values, to_ui=False)
                    set_plug(self._mplug, values)
                elif self.getDataType() in {"float2", "float3", "long2", "long3", "short2", "short3"}:
                    self._require_writable()
                    Plug.set(self, values, safe=False, uiUnits=uiUnits, fast=fast)
                else:
                    for index, child_value in enumerate(values):
                        self._child_at(index).set(child_value, safe=False, uiUnits=uiUnits, fast=fast)
            except NotImplementedError:
                raise
            except (RuntimeError, TypeError, ValueError):
                if not safe:
                    raise
                return self._set_children_safely(value, uiUnits=uiUnits, fast=fast)
            return 0 if safe else self

    def getChildren(self):
        """複合アトリビュートの直接の子Plugを、定義順で取得する。

        孫は再帰的に列挙せず、子の値も読み出さない。

        Returns:
            list[Plug]: 新しいリストと子ラッパー。所有Nodeは共有し、シーンを複製しない。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
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
