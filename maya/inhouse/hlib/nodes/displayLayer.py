"""Maya の displayLayer を扱う。"""

import maya.cmds as cmds

from .._core.getterAlias import _getter_alias
from ..decorator import undoChunk
from .node import Node


class DisplayLayer(Node):
    """Maya の displayLayer ラッパー。メンバー管理とカレントレイヤー操作を提供する。"""

    def getMembers(self):
        """レイヤーのメンバーを取得する。

        Returns:
            list[Node]: メンバーのラッパー。メンバーが無ければ空リスト。
        """
        # 既定の問い合わせは葉の名前だけを返し、短い名前が重複するノードを解決できないため
        # 完全パスで受け取る。
        names = cmds.editDisplayLayerMembers(self.getName(), query=True, fullNames=True) or []
        return [Node(name) for name in names]

    @undoChunk("hlibDisplayLayerAddMembers")
    def addMembers(self, *members):
        """メンバーを追加する。

        displayLayer のメンバーシップは常に単一のレイヤーに限られるため、
        既に他のレイヤーに属しているノードはこのレイヤーへ排他的に移動する。

        Args:
            members (Node | str): 追加するノード。

        Returns:
            DisplayLayer: 自身。
        """
        from .._core.object import Object as _InputObject
        if members:
            cmds.editDisplayLayerMembers(self.getName(), _InputObject._input_names(members))
        return self

    @undoChunk("hlibDisplayLayerRemoveMembers")
    def removeMembers(self, *members):
        """メンバーを既定の defaultLayer へ戻して除外する。

        ``editDisplayLayerMembers`` に明示的な削除フラグは無く、Maya の
        レイヤー機構では既定レイヤーへ移すことが除外に相当する。

        Args:
            members (Node | str): 除外するノード。

        Returns:
            DisplayLayer: 自身。
        """
        from .._core.object import Object as _InputObject
        if members:
            cmds.editDisplayLayerMembers("defaultLayer", _InputObject._input_names(members))
        return self

    @undoChunk("hlibDisplayLayerSetCurrent")
    def setCurrent(self):
        """このレイヤーを現在のレイヤー(新規作成ノードの追加先)にする。

        Returns:
            DisplayLayer: 自身。
        """
        cmds.editDisplayLayerGlobals(currentDisplayLayer=self.getName())
        return self

    @_getter_alias(getMembers)
    def members(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getMembers(*args, **kwargs)
