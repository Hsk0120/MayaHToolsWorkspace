"""Maya の displayLayer を扱う。"""

import maya.cmds as cmds

from .._core.coerce import to_names
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from .node import Node


@node_wrapper("displayLayer")
class DisplayLayer(Node):
    """Maya の displayLayer ラッパー。メンバー管理とカレントレイヤー操作を提供する。"""

    def members(self):
        """レイヤーのメンバーを取得する。

        Returns:
            list[Node]: メンバーのラッパー。メンバーが無ければ空リスト。
        """
        names = cmds.editDisplayLayerMembers(self.name(), query=True) or []
        return [Node(name) for name in names]

    @undo_chunk("hlibDisplayLayerAddMembers")
    def add_members(self, *members):
        """メンバーを追加する。

        displayLayer のメンバーシップは常に単一のレイヤーに限られるため、
        既に他のレイヤーに属しているノードはこのレイヤーへ排他的に移動する。

        Args:
            members (Node | str): 追加するノード。

        Returns:
            DisplayLayer: 自身。
        """
        if members:
            cmds.editDisplayLayerMembers(self.name(), to_names(members))
        return self

    @undo_chunk("hlibDisplayLayerRemoveMembers")
    def remove_members(self, *members):
        """メンバーを既定の defaultLayer へ戻して除外する。

        ``editDisplayLayerMembers`` に明示的な削除フラグは無く、Maya の
        レイヤー機構では既定レイヤーへ移すことが除外に相当する。

        Args:
            members (Node | str): 除外するノード。

        Returns:
            DisplayLayer: 自身。
        """
        if members:
            cmds.editDisplayLayerMembers("defaultLayer", to_names(members))
        return self

    @undo_chunk("hlibDisplayLayerSetCurrent")
    def set_current(self):
        """このレイヤーを現在のレイヤー(新規作成ノードの追加先)にする。

        Returns:
            DisplayLayer: 自身。
        """
        cmds.editDisplayLayerGlobals(currentDisplayLayer=self.name())
        return self
