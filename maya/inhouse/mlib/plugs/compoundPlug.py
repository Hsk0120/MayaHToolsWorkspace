"""複合アトリビュートとその子プラグを扱う。"""

from contextlib import nullcontext

import maya.api.OpenMaya as om2

from ..core.attributeType import _convert_units, attributeType, value_reader
from ..core.fastWrite import _require_supported_type, set_attr, set_plug
from ..decorator import undoChunk
from .plug import Plug


class CompoundPlug(Plug):
    """複合アトリビュートを参照し、直接の子Plugと値を扱う。

    子は定義順の0始まりの連続番号かロング名・ショート名で取得する。
    番号はArrayPlugの論理番号とは異なる。基底のget()は子の値を定義順tupleで返す。
    maya.cmdsへは ``str(plug)`` で渡す。mlib.selectにはそのまま渡せる。
    """

    _child_readers = None  #: 子の値を直接読む関数の列。初回の内部単位get()で子の定義から選ぶ。
    _bulk_children = None  #: 子を1回のsetAttrでまとめて書けるか。初回のset()で子の定義から判定する。

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

    def __getitem__(self, nameOrIndex):
        """複合アトリビュートの直接の子を、定義順の番号または子名で参照する。

        整数は0始まりの子番号で、multi要素の論理番号ではない。負数・sliceは使えない。
        文字列は直接の子のロング名・ショート名と照合し、孫へのパスやaliasは解決しない。
        子の値は読み出さない。

        Args:
            nameOrIndex (str | int): 子のロング名、ショート名、または定義順の子番号。

        Returns:
            Plug: 同じ所有Nodeを共有する新しい子ラッパー。値やノードの複製ではない。

        Raises:
            AttributeError: 名前に一致する直接の子がない場合。
            IndexError: 整数番号が子の範囲外の場合。
            TypeError: 整数または文字列以外を指定した場合。boolも拒否する。
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        self._require_valid()
        if isinstance(nameOrIndex, bool) or not isinstance(nameOrIndex, (int, str)):
            raise TypeError("Child index must be an integer or attribute name")
        if isinstance(nameOrIndex, int):
            if not 0 <= nameOrIndex < self._mplug.numChildren():
                raise IndexError("Child index out of range")
            return self._child_at(nameOrIndex)
        for index in range(self._mplug.numChildren()):
            child = self._mplug.child(index)
            attribute = om2.MFnAttribute(child.attribute())
            if nameOrIndex in (attribute.name, attribute.shortName):
                return Plug(self._node, child)
        raise AttributeError(f"No child named {nameOrIndex!r} on {self.getFullName()}")

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
        if not uiUnits:
            return tuple(self._child_values())
        return tuple(self._child_at(index).get(uiUnits=uiUnits) for index in range(self._mplug.numChildren()))

    def set(self, value, safe=False, *, uiUnits=False, fast=False):
        """子数と同じ長さの値を、アトリビュート定義順に設定する。

        通常はUndo有効時に一括記録し、固定長数値型は型付き設定、それ以外は子ごとに更新する。
        どの経路も書き込む前に自身と全子の書込み可否(ロック・入力接続・書込み禁止)を検査し、
        書けない子が1つでもあれば何も書かずに例外にする(safe=Falseの場合)。子の値の型の誤りは
        子ごとに書く時点で検出するため、先行する子の更新が残る場合がある(1回のUndoで戻る)。
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
                elif self.getType() in {"float2", "float3", "long2", "long3", "short2", "short3"}:
                    self._require_writable()
                    Plug.set(self, values, safe=False, uiUnits=uiUnits, fast=fast)
                else:
                    # 子ごとに書く経路でも、先に全子の書込み可否を検査する。ロック・入力接続の
                    # ある子より前の子だけが書かれて残ることを防ぐ(Double3Plugと同じ)。
                    self._require_writable()
                    if not uiUnits:
                        self._set_child_values(values, writable_checked=True)
                        return 0 if safe else self
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

    def _child_values(self):
        """有効性を確かめ済みの前提で、直接の子の内部単位の値を定義順に読む。

        子のPlugラッパーを作らず、子の ``get()`` と同じ読取関数をMPlugへ直接適用する。
        読取関数はアトリビュート定義から一度だけ選んで保持し、値は毎回読み直す。
        複合・配列の子と、読取関数を持たない型(generic・message・マトリクス等)の子は、
        従来どおり子Plugの ``get()`` へ委譲する。

        Returns:
            list: 子の値。型・単位は各子の ``get()`` と同じ(距離cm・角度rad・時間秒)。
        """
        mplug = self._mplug
        readers = self._child_readers
        if readers is None:
            selected = []
            for index in range(mplug.numChildren()):
                child = mplug.child(index)
                if child.isCompound or child.isArray:
                    selected.append(False)
                else:
                    selected.append(value_reader(child.attribute()))
            readers = self._child_readers = tuple(selected)
        return [
            reader(mplug.child(index)) if reader is not False else self._child_at(index).get()
            for index, reader in enumerate(readers)
        ]

    def _set_child_values(self, values, *, writable_checked=False):
        """内部単位の値を、cmdsの経路で定義順に子へ書き込む。

        double2・double3の数値の子だけを持ち、値がすべてint・floatで、全子が書込み可能なら、
        親へ1回の ``cmds.setAttr`` でまとめて書く。それ以外、またはまとめた書込みが失敗した
        場合は、従来どおり子ごとに ``set()`` するため、例外の種類・文言と部分更新の順序は
        子ごとの書込みと同じになる。Undoチャンクは呼出し元で開く。

        Args:
            values (tuple): 子数と同じ長さの内部単位の値(距離cm・角度rad・時間秒)。
            writable_checked (bool): Trueは呼出し元が ``_require_writable()`` を確認済み。

        Raises:
            RuntimeError: 子の書込みに失敗した場合。
            TypeError: 子の値の型が不正な場合。
            ValueError: 子の値を変換できない場合。
        """
        mplug = self._mplug
        if self._can_set_at_once(values):
            try:
                if not writable_checked:
                    self._require_writable()
            except RuntimeError:
                pass  # 書けない子は、子ごとの書込みで従来の例外にする。
            else:
                try:
                    set_attr(self.getFullName(), *_convert_units(mplug, values), fast=False)
                    return
                except (RuntimeError, TypeError, ValueError):
                    pass  # 子ごとに書き直し、従来の例外と更新順にする。
        for index, child_value in enumerate(values):
            self._child_at(index).set(child_value, safe=False, fast=False)

    def _can_set_at_once(self, values):
        """子を1回のsetAttrでまとめて書けるか判定する。シーンは変更しない。

        子の構成はアトリビュート定義から一度だけ判定して保持し、値の型は毎回確かめる。

        Args:
            values (tuple): 書き込む値。

        Returns:
            bool: double2・double3で、子が数値・単位付きの単純なアトリビュートで、
                値がすべてint・float(boolを除く)の場合はTrue。
        """
        bulk = self._bulk_children
        if bulk is None:
            mplug = self._mplug
            bulk = attributeType(mplug) in ("double2", "double3")
            if bulk:
                for index in range(mplug.numChildren()):
                    child = mplug.child(index)
                    attribute = child.attribute()
                    if (child.isCompound or child.isArray
                            or not (attribute.hasFn(om2.MFn.kNumericAttribute)
                                    or attribute.hasFn(om2.MFn.kUnitAttribute))):
                        bulk = False
                        break
            self._bulk_children = bulk
        if not bulk:
            return False
        for item in values:
            if type(item) is not float and type(item) is not int:
                return False
        return True

    def _child_at(self, index):
        """有効性を確かめ済みの前提で、子インデックスの子 Plug を作る。

        Args:
            index (int): 子インデックス。

        Returns:
            Plug: 子プラグ。
        """
        return Plug(self._node, self._mplug.child(index))
