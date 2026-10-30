"""Maya の objectSet(セット)を扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.object import Object
from ..decorator import undoChunk
from .node import Node


class ObjectSet(Node):
    """objectSetノードの参照を保持し、ノード・アトリビュート・コンポーネントの所属を扱う。

    セットへの登録はDAGの親子付けやContainerの所属とは別の関係として扱う。
    照会はMFnSet、編集はcmds.setsを使う。
    """

    def getMembers(self):
        """objectSetの直接メンバーを、入れ子のセットを展開せず取得する。

        MFnSet.getMembers(False)の選択文字列を使う。名前にドットがある
        アトリビュート/コンポーネント表記は文字列、それ以外はNode参照へ変換する。
        Maya APIの列挙順と圧縮された範囲表記を使い、独自のソートや全要素展開は行わない。

        Returns:
            list[Node | str]: 新しいリスト。空セットは空。文字列をPlug/Componentへ自動変換しない。
        """
        names = om2.MFnSet(self.mnode()).getMembers(False).getSelectionStrings()
        return [name if "." in name else Node(name) for name in names]

    def addMembers(self, *members):
        """ノードやコンポーネント等を、このobjectSetへ追加する。

        共通の入力解決からcmds.setsへ渡す。空引数は変更せず自身を返す。ノードの複製や
        親子付けは行わない。fast引数は持たない(MFnSetの更新はcmds.setsより遅いため)。

        Args:
            members (Node | str): 追加するノードやコンポーネント表記などの入力。

        Returns:
            ObjectSet: 自身。

        Raises:
            RuntimeError: Mayaが追加を拒否した場合。
        """
        with undoChunk("mlibObjectSetAddMembers"):
            if members:
                cmds.sets(Object._input_names(members), add=self.getName())
            return self

    def removeMembers(self, *members):
        """objectSetから指定メンバーの所属だけを外す。ノード自体は削除しない。

        空引数は変更しない。入力解決は :meth:`addMembers` と同じ。

        Args:
            *members (Node | str): 除外するノードやコンポーネント表記などの入力。

        Returns:
            ObjectSet: 自身。

        Raises:
            RuntimeError: Mayaが除外を拒否した場合。
        """
        with undoChunk("mlibObjectSetRemoveMembers"):
            if members:
                cmds.sets(Object._input_names(members), remove=self.getName())
            return self

    def isMember(self, member):
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
        query = om2.MSelectionList()
        query.add(Object._input_name(member))
        members = om2.MFnSet(self.mnode()).getMembers(False)
        for index in range(query.length()):
            # getComponent は DG ノードやアトリビュートの要素で RuntimeError ではなく TypeError を出し、
            # getPlug はノードの要素で空の MPlug を返す。両方を判定して要素の種類を選ぶ。
            try:
                item = query.getPlug(index)
            except (RuntimeError, TypeError):
                item = None
            if item is None or item.isNull:
                try:
                    item = query.getComponent(index)
                except (RuntimeError, TypeError):
                    item = query.getDependNode(index)
            if not members.hasItem(item):
                return False
        return True
