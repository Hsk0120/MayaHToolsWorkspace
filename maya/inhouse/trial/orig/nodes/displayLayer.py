"""Maya の displayLayer を扱う。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.object import Object
from ..decorator import _edit_context
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

    def addMembers(self, *members, fast=False):
        """子階層を含めてメンバーを排他的にこのレイヤーへ移動する。

        Args:
            members (Node | str): 追加するDAGノード。
            fast (bool): TrueはdrawInfo接続をOpenMayaで直接移動し、Undoなし。
                コンポーネントとUFEパスは未対応。

        Returns:
            DisplayLayer: 自身。
        """
        with _edit_context("mlibDisplayLayerAddMembers", fast):
            if members:
                if fast:
                    self._move_members(members)
                else:
                    cmds.editDisplayLayerMembers(self.getName(), Object._input_names(members))
            return self

    def removeMembers(self, *members, fast=False):
        """子階層を含めてdefaultLayerへ移す。

        Args:
            members (Node | str): 除外するDAGノード。
            fast (bool): TrueはOpenMayaで直接移動し、Undoなし。

        Returns:
            DisplayLayer: 自身。
        """
        with _edit_context("mlibDisplayLayerRemoveMembers", fast):
            if members:
                if fast:
                    DisplayLayer("defaultLayer")._move_members(members)
                else:
                    cmds.editDisplayLayerMembers("defaultLayer", Object._input_names(members))
            return self

    def setCurrent(self, *, fast=False):
        """このレイヤーを新規作成ノードの追加先にする。

        Args:
            fast (bool): TrueはlayerManagerをOpenMayaで直接更新し、Undoなし。

        Returns:
            DisplayLayer: 自身。
        """
        with _edit_context("mlibDisplayLayerSetCurrent", fast):
            if fast:
                Node("layerManager").getPlug("currentDisplayLayer").set(self.getPlug("identification").get(), fast=fast)
            else:
                cmds.editDisplayLayerGlobals(currentDisplayLayer=self.getName())
            return self

    def _move_members(self, members):
        """標準DAGの排他レイヤー接続を事前確認して直接移動する。

        Args:
            members (Iterable): 子階層も含めて移動するノード。

        Raises:
            NotImplementedError: コンポーネント・UFE・標準外接続の場合。
            RuntimeError: ノード・レイヤーの参照やロックにより編集できない場合。
        """
        from ..core.object import Object
        from .dagNode import DagNode
        layer_fn = self._dependency_fn()
        if layer_fn.isLocked or layer_fn.isFromReferencedFile:
            raise RuntimeError("Cannot edit a locked or referenced display layer")
        nodes, seen = [], set()
        for name in Object._input_names(members):
            if "." in name or "," in name:
                raise NotImplementedError("fast display-layer edits support whole Maya DAG nodes only")
            node = Node(name)
            if not isinstance(node, DagNode):
                raise TypeError("Display-layer member must be a DAG node")
            for child in node.getChildren(True, True, allDescendents=True, includeSelf=True):
                token = om2.MObjectHandle(child.mnode()).hashCode()
                if token not in seen:
                    seen.add(token)
                    nodes.append(child)
        output = self.getPlug("drawInfo").mplug()
        default = not self.getPlug("identification").get()
        plan = []
        for node in nodes:
            fn = node.mfn()
            if fn.isLocked or fn.isFromReferencedFile:
                raise RuntimeError("Cannot move a locked or referenced display-layer member")
            target = fn.findPlug("drawOverride", False)
            if target.isLocked or any(target.child(i).isLocked for i in range(target.numChildren())):
                raise RuntimeError("Display override is locked")
            sources = target.connectedTo(True, False)
            for source in sources:
                source_fn = om2.MFnDependencyNode(source.node())
                if source_fn.typeName != "displayLayer" or source != source_fn.findPlug("drawInfo", False):
                    raise NotImplementedError("Custom display-override connections are not supported")
                if source_fn.isLocked or source_fn.isFromReferencedFile:
                    raise RuntimeError("Cannot remove a member from a locked or referenced display layer")
            if (not sources and default) or (len(sources) == 1 and sources[0] == output):
                continue
            plan.append((target, sources))
        modifier = om2.MDGModifier()
        for target, sources in plan:
            for source in sources:
                modifier.disconnect(source, target)
            if not default:
                modifier.connect(output, target)
        if plan:
            modifier.doIt()
