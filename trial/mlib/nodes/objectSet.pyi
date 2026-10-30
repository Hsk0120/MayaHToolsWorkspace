# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の objectSet(セット)を扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..core.nodeEdit import require_editable
from ..core.object import Object
from ..decorator import _edit_context
from .node import Node
from typing import Iterable



class ObjectSet(Node):
    """objectSetノードの参照を保持し、ノード・アトリビュート・コンポーネントの所属を扱う。

    セットへの登録はDAGの親子付けやContainerの所属とは別の関係として扱う。
    照会はMFnSet、通常編集はcmds.sets、対応するfast編集はMFnSetを使う。
    """
    def getMembers(self) -> list[Node | str]:
        """objectSetの直接メンバーを、入れ子のセットを展開せず取得する。

        MFnSet.getMembers(False)の選択文字列を使う。名前にドットがある
        アトリビュート/コンポーネント表記は文字列、それ以外はNode参照へ変換する。
        Maya APIの列挙順と圧縮された範囲表記を使い、独自のソートや全要素展開は行わない。

        Returns:
            list[Node | str]: 新しいリスト。空セットは空。文字列をPlug/Componentへ自動変換しない。
        """
        ...
    def addMembers(self, *members: Node | str, fast: bool = ...) -> ObjectSet:
        """ノードやコンポーネント等を、このobjectSetへ追加する。

        通常は共通の入力解決からcmds.setsへ渡す。fastはセットのロック/参照を検査し、
        DAGパスとコンポーネント範囲を保つ選択リストをMFnSetへ渡す。
        空引数は変更せず自身を返す。ノードの複製や親子付けは行わない。

        Args:
            members (Node | str): 追加するノードやコンポーネント表記などの入力。
            fast (bool): TrueはMFnSet更新でUndoへ記録しない。Undo設定は変更しない。
                Falseは通常更新をUndo有効時にまとめる。

        Returns:
            ObjectSet: 自身。

        Raises:
            RuntimeError: fastでセットがロックまたは参照されている場合、またはMayaが追加を拒否した場合。
        """
        ...
    def removeMembers(self, *members: Node | str, fast: bool = ...) -> ObjectSet:
        """objectSetから指定メンバーの所属だけを外す。ノード自体は削除しない。

        空引数は変更しない。入力解決とfastの編集制限は :meth:`addMembers` と同じ。

        Args:
            *members (Node | str): 除外するノードやコンポーネント表記などの入力。
            fast (bool): TrueはUndo設定を変えないMFnSet更新(Undoなし)。
                Falseはcmds.setsによる通常更新をUndo有効時にまとめる。

        Returns:
            ObjectSet: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            RuntimeError: fastでセットがロック/参照されている、またはMayaが除外を拒否した場合。
        """
        ...
    def isMember(self, member: Node | str) -> bool:
        """指定入力の全要素が、このセットの直接メンバーに含まれるか調べる。

        入力を選択リストへ解決し、各要素をアトリビュート(MPlug)、DAG/コンポーネント
        (DAGパスとコンポーネント)、DGノード(MObject)の順に取り出してhasItem()で照合する。
        DGノード・DGノードのアトリビュート・DAGノードのアトリビュートも
        ``cmds.sets(member, isMember=set)`` と同じ結果になる。
        入れ子セットを展開した集合を使わず、名前文字列だけで同一性を判定しない。

        Args:
            member (Node | str): 判定対象。コンポーネント範囲表記も指定できる。

        Returns:
            bool: 解決した全要素が含まれる場合はTrue。一部でも未登録ならFalse。
        """
        ...
    @staticmethod
    def _member_selection(members: Iterable) -> om2.MSelectionList:
        """入力を圧縮コンポーネントとDAGパスを保つ選択リストへ解決する。

        Args:
            members (Iterable): 追加・除外する入力。

        Returns:
            om2.MSelectionList: 解決した対象。
        """
        ...
    def _editable_set(self) -> om2.MFnSet:
        """高速更新がロック・参照を迂回しないように確認する。

        Returns:
            om2.MFnSet: 更新可能なセット。

        Raises:
            RuntimeError: セットがロックまたは参照されている場合。
        """
        ...
