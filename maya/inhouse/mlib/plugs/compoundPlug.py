"""複合アトリビュートとその子プラグを扱う。"""

from contextlib import nullcontext

import maya.api.OpenMaya as om2

from ..core.fastWrite import _require_supported_type, set_plug
from ..decorator import undoChunk
from .plug import Plug


class CompoundPlug(Plug):
    """複合アトリビュート全体の参照を保持し、直接の子Plugと値を扱う。

    子はアトリビュート定義順の番号、ロング名、ショート名で取得する。
    ArrayPlugの疎な論理番号とは異なり、子番号は0から子数-1までの連続した番号。
    子の参照取得と値取得を分け、基底のget()は子の値を定義順のtupleで返す。

    maya.cmdsへ渡す場合は ``str(plug)`` または ``plug.getFullName()`` で文字列化する。
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
        """子数と同数のシーケンスを各子プラグへ設定する。

        要素数は先に検査する。通常はUndoが有効なら子の変更を同じチャンクへ記録する。
        float/long/shortの固定長数値型は全子の書込み可否を確認し型付きで一括設定する。
        その他の複合型は子ごとの設定を使う。途中の失敗時に完了済みの値は自動で戻さない。
        fastは全成分の型・書込み可否・制限を確認してから直接更新する。
        safe=Trueでは対応する失敗後に子を定義順で再試行するため、書ける子は更新される。
        fastの事前検証も、実際の書込み中の失敗に対する原子性を保証するものではない。

        Args:
            value (Iterable[object]): 子プラグと同じ数の値。先頭から順に設定する。
            safe (bool): Trueで書込み失敗を抑制し、失敗数を返す。
            uiUnits (bool): TrueはUI単位の数値。既定Falseは内部単位。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            CompoundPlug | int: safe=Falseでは自身。safe=Trueでは書けなかった成分数、全て成功なら0。
                子数と値の件数が不一致など、成分へ分けられない失敗は1を返す。
                子の再試行を完了できない失敗も1で、厳密な未更新成分の総数は保証しない。
                fastで未対応の子の型があれば、safe=Trueでも部分更新前にNotImplementedErrorを送出する。
                fastがbool以外のTypeErrorは抑制しない。

        Raises:
            ValueError: 要素数が子数と一致しない場合。
            RuntimeError: 所有ノードが無効(削除済み)、またはアトリビュートが削除済みの場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
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
