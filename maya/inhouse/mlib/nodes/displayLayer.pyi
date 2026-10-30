# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の displayLayer を扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..core.object import Object
from ..decorator import undoChunk
from .node import Node



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
    def addMembers(self, *members: Node | str) -> DisplayLayer:
        """子階層を含めてメンバーを排他的にこのレイヤーへ移動する。

        fast引数は持たない(OpenMayaで接続を移す処理はcmdsより遅いため)。

        Args:
            members (Node | str): 追加するDAGノード。

        Returns:
            DisplayLayer: 自身。
        """
        ...
    def removeMembers(self, *members: Node | str) -> DisplayLayer:
        """子階層を含めてdefaultLayerへ移す。

        Args:
            members (Node | str): 除外するDAGノード。

        Returns:
            DisplayLayer: 自身。
        """
        ...
    def setCurrent(self) -> DisplayLayer:
        """このレイヤーを新規作成ノードの追加先にする。

        Returns:
            DisplayLayer: 自身。
        """
        ...
