"""Maya の objectSet(セット)を扱う。"""

import maya.cmds as cmds

from .._core.getterAlias import _getter_alias, _is_alias
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
        names = cmds.sets(self.getName(), query=True) or []
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
        from .._core.object import Object as _InputObject
        if members:
            cmds.sets(_InputObject._input_names(members), add=self.getName())
        return self

    @undoChunk("hlibObjectSetRemove")
    def removeMembers(self, *members):
        """メンバーを除外する。

        Args:
            members (Node | str): 除外するノードまたはコンポーネント文字列。

        Returns:
            ObjectSet: 自身。
        """
        from .._core.object import Object as _InputObject
        if members:
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
        return bool(cmds.sets(_InputObject._input_name(member), isMember=self.getName()))

    @_is_alias(isMember)
    def member(self, *args, **kwargs):
        """isMemberへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isMember(*args, **kwargs)

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
