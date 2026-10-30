"""Maya の displayLayer を扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.object import Object
from ..decorator import undoChunk
from .node import Node


class DisplayLayer(Node):
    """Maya の displayLayer ラッパー。メンバー管理とカレントレイヤー操作を提供する。"""

    def getMembers(self):
        """レイヤーのメンバーを取得する。

        Returns:
            list[Node]: メンバーのラッパー。メンバーが無ければ空リスト。

        Note:
            2024以降はMFnDisplayLayerを使用する。2022/2023のdefaultLayerは
            同APIがないため、既存のカメラ除外規則を標準コマンドで維持する。
        """
        if hasattr(om2, "MFnDisplayLayer"):
            members = om2.MFnDisplayLayer(self.mnode()).getMembers()
            # 選択リストから取得したばかりのパスなので、入力の再解決を省いてラッパーにする。
            return [Node._wrap_dag_path(members.getDagPath(index)) for index in range(members.length())]
        if not self.getPlug("identification").get():
            # 2022/2023にはMFnDisplayLayerがない。defaultLayer固有の除外規則を
            # 単なる未接続DAG走査で再現せず、既存コマンドの意味を維持する。
            names = cmds.editDisplayLayerMembers(self.getName(), query=True, fullNames=True) or []
            return [Node(name) for name in names]
        output = self.getPlug("drawInfo").mplug()
        return [Node._wrap_dag_path(om2.MDagPath.getAPathTo(plug.node()))
                for plug in output.connectedTo(False, True)
                if plug.node().hasFn(om2.MFn.kDagNode)]

    def addMembers(self, *members):
        """子階層を含めてメンバーを排他的にこのレイヤーへ移動する。

        fast引数は持たない(OpenMayaで接続を移す処理はcmdsより遅いため)。

        Args:
            members (Node | str): 追加するDAGノード。

        Returns:
            DisplayLayer: 自身。
        """
        with undoChunk("mlibDisplayLayerAddMembers"):
            if members:
                cmds.editDisplayLayerMembers(self.getName(), Object._input_names(members))
            return self

    def removeMembers(self, *members):
        """子階層を含めてdefaultLayerへ移す。

        Args:
            members (Node | str): 除外するDAGノード。

        Returns:
            DisplayLayer: 自身。
        """
        with undoChunk("mlibDisplayLayerRemoveMembers"):
            if members:
                cmds.editDisplayLayerMembers("defaultLayer", Object._input_names(members))
            return self

    def setCurrent(self):
        """このレイヤーを新規作成ノードの追加先にする。

        Returns:
            DisplayLayer: 自身。
        """
        with undoChunk("mlibDisplayLayerSetCurrent"):
            cmds.editDisplayLayerGlobals(currentDisplayLayer=self.getName())
            return self
