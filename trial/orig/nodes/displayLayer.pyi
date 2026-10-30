# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の displayLayer を扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..core.nodeEdit import require_editable
from ..core.object import Object
from ..decorator import _edit_context
from .dagNode import DagNode
from .node import Node
from typing import Iterable



class DisplayLayer(Node):
    """Maya の displayLayer ラッパー。メンバー管理とカレントレイヤー操作を提供する。"""
    def getMembers(self) -> list[Node]:
        """レイヤーのメンバーを取得する。

        Returns:
            list[Node]: メンバーのラッパー。メンバーが無ければ空リスト。

        Note:
            2024以降はMFnDisplayLayerを使用する。2022/2023のdefaultLayerは
            同APIがないため、既存のカメラ除外規則を標準コマンドで維持する。
        """
        ...
    def addMembers(self, *members: Node | str, fast: bool = ...) -> DisplayLayer:
        """子階層を含めてメンバーを排他的にこのレイヤーへ移動する。

        Args:
            members (Node | str): 追加するDAGノード。
            fast (bool): TrueはdrawInfo接続をOpenMayaで直接移動し、Undoなし。
                コンポーネントとUFEパスは未対応。

        Returns:
            DisplayLayer: 自身。
        """
        ...
    def removeMembers(self, *members: Node | str, fast: bool = ...) -> DisplayLayer:
        """子階層を含めてdefaultLayerへ移す。

        Args:
            members (Node | str): 除外するDAGノード。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            DisplayLayer: 自身。
        """
        ...
    def setCurrent(self, *, fast: bool = ...) -> DisplayLayer:
        """このレイヤーを新規作成ノードの追加先にする。

        Args:
            fast (bool): TrueはlayerManagerをOpenMayaで直接更新し、Undoなし。

        Returns:
            DisplayLayer: 自身。
        """
        ...
    def _move_members(self, members: Iterable) -> None:
        """標準DAGの排他レイヤー接続を事前確認して直接移動する。

        Args:
            members (Iterable): 子階層も含めて移動するノード。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: ノード・レイヤーの参照やロックにより編集できない場合。
            NotImplementedError: コンポーネント・UFE・標準外接続の場合。
        """
        ...
