"""Maya の objectSet(セット)を扱う。"""

import maya.cmds as cmds

from .._core.registry import node_wrapper
from ..decorators.undo import undoChunk
from .node import Node


@node_wrapper("objectSet")
class ObjectSet(Node):
    """Maya の objectSet ラッパー。コントロールセット・表示セット等の基本操作を提供する。"""

    def members(self):
        """セットのメンバーを取得する。

        コンポーネント(例: ``mesh1.vtx[0:2]``)を含む場合、そのメンバーは
        ノードラッパーではなく文字列のまま返す。

        Returns:
            list[Node | str]: メンバー。ノードは Node ラッパー、コンポーネントは
                文字列。メンバーが無ければ空リスト。
        """
        names = cmds.sets(self.name(), query=True) or []
        return [name if "." in name else Node(name) for name in names]

    @undoChunk("hlibObjectSetAdd")
    def addMembers(self, *members):
        """メンバーを追加する。

        Args:
            members (Node | str): 追加するノードまたはコンポーネント文字列
                (例: ``"mesh1.vtx[0:2]"``)。

        Returns:
            ObjectSet: 自身。
        """
        from hlib.object import Object as _InputObject
        if members:
            cmds.sets(_InputObject._input_names(members), add=self.name())
        return self

    @undoChunk("hlibObjectSetRemove")
    def removeMembers(self, *members):
        """メンバーを除外する。

        Args:
            members (Node | str): 除外するノードまたはコンポーネント文字列。

        Returns:
            ObjectSet: 自身。
        """
        from hlib.object import Object as _InputObject
        if members:
            cmds.sets(_InputObject._input_names(members), remove=self.name())
        return self

    def isMember(self, member):
        """指定した要素がメンバーか判定する。

        Args:
            member (Node | str): 判定対象のノードまたはコンポーネント文字列。

        Returns:
            bool: メンバーの場合は True。
        """
        from hlib.object import Object as _InputObject
        return bool(cmds.sets(_InputObject._input_name(member), isMember=self.name()))
