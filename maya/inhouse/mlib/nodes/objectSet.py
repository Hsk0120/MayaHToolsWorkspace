"""Maya の objectSet(セット)を扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..common._fast import fast_edit, is_fast
from ..decorator import undoChunk
from .node import Node


class ObjectSet(Node):
    """Maya の objectSet ラッパー。コントロールセット・表示セット等の基本操作を提供する。"""

    def getMembers(self):
        """セットのメンバーを取得する。

        コンポーネント(例: ``mesh1.vtx[0:2]``)を含む場合、そのメンバーは
        ノードラッパーではなく文字列のまま返す。

        Returns:
            list[Node | str]: メンバー。ノードは Node ラッパー、コンポーネントは
                文字列。メンバーが無ければ空リスト。
        """
        names = om2.MFnSet(self.mnode()).getMembers(False).getSelectionStrings()
        return [name if "." in name else Node(name) for name in names]

    @fast_edit
    @undoChunk("mlibObjectSetAdd")
    def addMembers(self, *members, fast=False):
        """メンバーを追加する。

        Args:
            members (Node | str): 追加するノードまたはコンポーネント文字列
                (例: ``"mesh1.vtx[0:2]"``)。
            fast (bool): TrueはMFnSet直接更新でUndoなし。

        Returns:
            ObjectSet: 自身。
        """
        from .._core.object import Object as _InputObject
        if members:
            if is_fast():
                self._editable_set().addMembers(self._member_selection(members))
            else:
                cmds.sets(_InputObject._input_names(members), add=self.getName())
        return self

    @fast_edit
    @undoChunk("mlibObjectSetRemove")
    def removeMembers(self, *members, fast=False):
        """メンバーを除外する。

        Args:
            members (Node | str): 除外するノードまたはコンポーネント文字列。
            fast (bool): TrueはMFnSet直接更新でUndoなし。

        Returns:
            ObjectSet: 自身。
        """
        from .._core.object import Object as _InputObject
        if members:
            if is_fast():
                self._editable_set().removeMembers(self._member_selection(members))
            else:
                cmds.sets(_InputObject._input_names(members), remove=self.getName())
        return self

    def isMember(self, member):
        """指定した要素がメンバーか判定する。

        Args:
            member (Node | str): 判定対象のノードまたはコンポーネント文字列。

        Returns:
            bool: メンバーの場合は True。
        """
        from .._core.object import Object as _InputObject
        query = om2.MSelectionList()
        query.add(_InputObject._input_name(member))
        members = om2.MFnSet(self.mnode()).getMembers(False)
        for index in range(query.length()):
            try:
                item = query.getComponent(index)
            except RuntimeError:
                try:
                    item = query.getPlug(index)
                except RuntimeError:
                    item = query.getDependNode(index)
            if not members.hasItem(item):
                return False
        return True

    @staticmethod
    def _member_selection(members):
        """入力を圧縮コンポーネントとDAGパスを保つ選択リストへ解決する。

        Args:
            members (Iterable): 追加・除外する入力。

        Returns:
            om2.MSelectionList: 解決した対象。
        """
        from .._core.object import Object
        selection = om2.MSelectionList()
        for name in Object._input_names(members):
            selection.add(name)
        return selection

    def _editable_set(self):
        """高速更新がロック・参照を迂回しないように確認する。

        Returns:
            om2.MFnSet: 更新可能なセット。

        Raises:
            RuntimeError: セットがロックまたは参照されている場合。
        """
        fn = om2.MFnSet(self.mnode())
        if fn.isLocked or fn.isFromReferencedFile:
            raise RuntimeError("Cannot edit a locked or referenced set")
        return fn
