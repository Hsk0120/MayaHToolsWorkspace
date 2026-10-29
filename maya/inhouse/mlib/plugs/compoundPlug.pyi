# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""コンパウンドアトリビュートとその子プラグを扱う。"""

import maya.api.OpenMaya as om2
from ..core.attributeType import _convert_angles, _convert_units, _plain_angle_unit, attributeType, value_reader
from ..core.fastWrite import set_attr, set_plug
from ..core.object import _missing_member_message
from ..decorator import _require_bool
from .plug import Plug
from typing import Iterable, Iterator



class CompoundPlug(Plug):
    """コンパウンドアトリビュートを参照し、直接の子Plugと値を扱う。

    子は定義順の0始まりの連続番号かロング名・ショート名で取得する。
    番号はMultiPlugの論理番号とは異なる。基底のget()は子の値を定義順tupleで返す。
    maya.cmdsへは ``str(plug)`` で渡す。mlib.selectにはそのまま渡せる。
    """
    _child_readers: None
    _bulk_children: None
    def __getattr__(self, name: str) -> Plug:
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
        ...
    def __getitem__(self, nameOrIndex: str | int) -> Plug:
        """コンパウンドアトリビュートの直接の子を、定義順の番号または子名で参照する。

        整数は0始まりの子番号で、マルチアトリビュートの要素の論理番号ではない。負数・sliceは使えない。
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
        ...
    def __iter__(self) -> Iterator[Plug]:
        """直接の子の参照一覧を取得し、アトリビュート定義順に反復する。

        反復子を作る時点のgetChildren()を使い、子の値は読み出さない。

        Returns:
            Iterator[Plug]: 作成時に集めた直接の子参照の反復子。
        """
        ...
    def get(self, *, unit: str | None = ..., uiUnits: bool = ...) -> tuple:
        """直接の子の値を、アトリビュート定義順のtupleで取得する。

        各子でget()を呼ぶため、値取得に伴うDG評価が発生し得る。
        入れ子のコンパウンドアトリビュートや配列型の値は平坦化せず、各子の返却型を保つ。

        Args:
            unit (str | None): 角度の子の数値の単位。None(既定)は度、``"rad"`` はラジアン。
                :meth:`Plug.get` と同じ名前を受け付け、uiUnits=Trueとは同時に指定できない。
            uiUnits (bool): 各子のgetへ渡す。TrueはUI単位、既定Falseは角度が度、距離cm、時間秒。

        Returns:
            tuple: 子数と同じ長さの新しいtuple。値の型・単位は各子のgetに従う。

        Raises:
            TypeError: uiUnitsがbool以外、またはunitが文字列・None以外の場合。
            ValueError: unitが未対応の単位名、またはunitとuiUnits=Trueを同時に指定した場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効、または子の値を取得できない場合。
        """
        ...
    def getChildren(self) -> list[Plug]:
        """コンパウンドアトリビュートの直接の子Plugを、定義順で取得する。

        孫は再帰的に列挙せず、子の値も読み出さない。

        Returns:
            list[Plug]: 新しいリストと子ラッパー。所有Nodeは共有し、シーンを複製しない。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        ...
    def _child_values(self) -> list:
        """有効性を確かめ済みの前提で、直接の子の内部単位の値を定義順に読む。

        子のPlugラッパーを作らず、子の ``get()`` と同じ読取関数をMPlugへ直接適用する。
        読取関数はアトリビュート定義から一度だけ選んで保持し、値は毎回読み直す。
        コンパウンドアトリビュート・マルチアトリビュートの子と、読取関数を持たない型(generic・message・マトリクス等)の子は、
        従来どおり子Plugの ``get()`` へ委譲する。

        Returns:
            list: 子の値。型は各子の ``get()`` と同じで、単位は内部単位(距離cm・角度rad・時間秒)。
        """
        ...
    def _set_value(self, value: Iterable[object], *, uiUnits: bool = ..., fast: bool = ...) -> None:
        """子数と同じ数の値を、全子の書込み可否を確認してから書き込む。

        骨格は :meth:`Plug.set`。書けない子が1つでもあれば何も書かずに例外にする。子の値の型の誤りは
        子ごとに書く時点で検出するため、先行する子の更新が残る場合がある(1回のUndoで戻る)。

        Args:
            value (Iterable[object]): 子数と同じ数の値。
            uiUnits (bool): TrueはUI単位。既定Falseは内部単位(角度rad・距離cm・時間秒)。
                角度の数値は :meth:`Plug.set` の骨格で度からradへ換算済み。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 入力型が不正な場合。
            ValueError: 要素数が子数と一致しない場合。
            RuntimeError: 参照が無効、または書込みに失敗した場合。
        """
        ...
    def _set_child_values(self, values: tuple, *, writable_checked: bool = ...) -> None:
        """内部単位の値を、cmdsの経路で定義順に子へ書き込む。

        double2・double3の数値の子だけを持ち、値がすべてint・floatで、全子が書込み可能なら、
        親へ1回の ``cmds.setAttr`` でまとめて書く。それ以外、またはまとめた書込みが失敗した
        場合は、従来どおり子ごとに ``set()`` するため、例外の種類・文言と部分更新の順序は
        子ごとの書込みと同じになる。Undoチャンクは呼出し元で開く。

        Args:
            values (tuple): 子数と同じ長さの内部単位の値(距離cm・角度rad・時間秒)。
            writable_checked (bool): Trueは呼出し元が ``_require_writable()`` を確認済み。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 子の値の型が不正な場合。
            ValueError: 子の値を変換できない場合。
            RuntimeError: 子の書込みに失敗した場合。
        """
        ...
    def _can_set_at_once(self, values: tuple) -> bool:
        """子を1回のsetAttrでまとめて書けるか判定する。シーンは変更しない。

        子の構成はアトリビュート定義から一度だけ判定して保持し、値の型は毎回確かめる。

        Args:
            values (tuple): 書き込む値。

        Returns:
            bool: double2・double3で、子が数値・単位付きの単純なアトリビュートで、
                値がすべてint・float(boolを除く)の場合はTrue。
        """
        ...
    def _child_at(self, index: int) -> Plug:
        """有効性を確かめ済みの前提で、子番号の子 Plug を作る。

        Args:
            index (int): 子番号。

        Returns:
            Plug: 子プラグ。
        """
        ...
