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
            TypeError: 未対応型の入力、または名前とNode等の参照を混在させた場合。
            ValueError: 名前に一致するものが無い場合。
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

    def clear(self):
        """objectSetの直接メンバーをすべて外す(``cmds.sets(clear=set)``)。ノード自体は削除しない。

        fast引数は持たない(:meth:`addMembers` と同じ理由)。Undo有効時は1回で戻せる。

        Returns:
            ObjectSet: 自身。

        Raises:
            RuntimeError: ノードが無効(削除済み)、またはMayaが処理を拒否した場合。
        """
        self._require_valid("clear")
        with undoChunk("mlibObjectSetClear"):
            cmds.sets(clear=self.getName())
            return self

    def getUnion(self, other):
        """このセットと別のセットの、どちらかの直接メンバーであるものを取得する。

        入れ子のセットは展開しない。戻り値の形は :meth:`getMembers` と同じで、コンポーネントの範囲は
        Mayaの選択リストの規則でまとめる。シーンは変更しない。

        Args:
            other (ObjectSet | str): 比べるobjectSet。

        Returns:
            list[Node | str]: 新しいリスト。

        Raises:
            TypeError: otherがobjectSetでない場合。
            RuntimeError: どちらかのノードが無効(削除済み)の場合。
        """
        members = self._member_list()
        members.merge(self._other_member_list(other))
        return self._member_names(members)

    def getIntersection(self, other):
        """このセットと別のセットの、両方の直接メンバーであるものを取得する。

        コンポーネントは要素単位で比べる(``cube.vtx[0:3]`` と ``cube.vtx[2:5]`` の共通は ``cube.vtx[2:3]``)。
        入れ子のセットは展開しない。シーンは変更しない。

        Args:
            other (ObjectSet | str): 比べるobjectSet。

        Returns:
            list[Node | str]: 新しいリスト。形は :meth:`getMembers` と同じ。

        Raises:
            TypeError: otherがobjectSetでない場合。
            RuntimeError: どちらかのノードが無効(削除済み)の場合。
        """
        members = self._member_list()
        only_self = om2.MSelectionList(members)
        only_self.merge(self._other_member_list(other), om2.MSelectionList.kRemoveFromList)
        members.merge(only_self, om2.MSelectionList.kRemoveFromList)
        return self._member_names(members)

    def getDifference(self, other):
        """このセットの直接メンバーのうち、別のセットの直接メンバーでないものを取得する。

        コンポーネントは要素単位で除く。入れ子のセットは展開しない。シーンは変更しない。

        Args:
            other (ObjectSet | str): 除くメンバーを持つobjectSet。

        Returns:
            list[Node | str]: 新しいリスト。形は :meth:`getMembers` と同じ。

        Raises:
            TypeError: otherがobjectSetでない場合。
            RuntimeError: どちらかのノードが無効(削除済み)の場合。
        """
        members = self._member_list()
        members.merge(self._other_member_list(other), om2.MSelectionList.kRemoveFromList)
        return self._member_names(members)

    def isSubSet(self, other):
        """このセットの直接メンバーがすべて、別のセットの直接メンバーに含まれるか判定する。

        空のセットはどのセットにも含まれる(True)。入れ子のセットは展開しない。

        Args:
            other (ObjectSet | str): 含む側のobjectSet。

        Returns:
            bool: すべて含まれる場合はTrue。

        Raises:
            TypeError: otherがobjectSetでない場合。
            RuntimeError: どちらかのノードが無効(削除済み)の場合。
        """
        members = self._member_list()
        members.merge(self._other_member_list(other), om2.MSelectionList.kRemoveFromList)
        return members.isEmpty()

    def _member_list(self):
        """直接メンバーの選択リストを返す。

        Returns:
            om2.MSelectionList: 新しい選択リスト。

        Raises:
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        self._require_valid("access members of")
        return om2.MFnSet(self.mnode()).getMembers(False)

    @staticmethod
    def _other_member_list(other):
        """比べる相手のobjectSetを解決し、直接メンバーの選択リストを返す。

        Args:
            other (ObjectSet | str): 比べるobjectSet。

        Returns:
            om2.MSelectionList: 新しい選択リスト。

        Raises:
            TypeError: otherがobjectSetでない場合。
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        node = other if isinstance(other, Node) else Node(Object._input_name(other))
        node._require_valid("access members of")
        if not node.isType("objectSet"):
            raise TypeError(f"Expected an objectSet, got {node.getType()}: {node.getName()}")
        return om2.MFnSet(node.mnode()).getMembers(False)

    @staticmethod
    def _member_names(members):
        """選択リストを :meth:`getMembers` と同じ形のリストへ変換する。

        Args:
            members (om2.MSelectionList): 変換する選択リスト。

        Returns:
            list[Node | str]: 名前にドットがあるものは文字列、それ以外はNode。
        """
        return [name if "." in name else Node(name) for name in members.getSelectionStrings()]
