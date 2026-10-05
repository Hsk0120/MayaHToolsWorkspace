"""DAG階層の保存姿勢とバインドポーズを扱う。"""

from .._core.flags import flag_aliases

import maya.cmds as cmds
from maya.api.OpenMaya import MSpace

from .._core.registry import node_wrapper
from .._core.space import world_space
from ..decorators.undo import undoChunk
from ..maths import Matrix
from .node import Node


@node_wrapper("dagPose")
class DagPose(Node):
    """MayaのdagPose。姿勢の保存・復元と、保存済み行列の照会を提供する。

    バインドポーズも同じノード型で、isBindPose()で区別する。
    reset()はこのノードの保存姿勢を更新し、skinCluster.bindPreMatrixは変更しない。
    """

    @classmethod
    @undoChunk("hlibDagPoseCreate")
    def create(cls, members, name=None, bindPose=False, hierarchy=True):
        """現在の姿勢を新しいポーズに保存する。選択状態は参照しない。

        Args:
            members (Node | str | Iterable[Node | str]): 保存するTransformまたはJoint。
            name (str | None): 作成名。NoneならMayaの自動命名。
            bindPose (bool): バインドポーズとして保存するか。
            hierarchy (bool): TrueならMaya標準の階層保存、Falseなら指定対象のみ。
                Mayaは復元に必要な親の情報も保存する場合がある。

        Returns:
            DagPose: 作成またはMayaが再利用したポーズ。

        Raises:
            ValueError: 空対象、Transform以外、不正な名前の場合。
            RuntimeError: ノード解決・保存をMayaが拒否した場合。
        """
        names = cls._transform_names(members)
        if name is not None and (not isinstance(name, str) or not name):
            raise ValueError("name must be a non-empty string or None")
        flags = {"save": True, "bindPose": bindPose, "selection": not hierarchy}
        # dagPoseのnameフラグはRedo時に名前空間を失うため、renameに任せる。
        result = cmds.dagPose(names, **flags)
        if name is not None:
            result = cmds.rename(result, name)
        return Node(result)

    @classmethod
    def fromSkinCluster(cls, skin_cluster):
        """skinClusterに接続されているバインドポーズを取得する。

        Args:
            skin_cluster (Node | str): 照会するskinCluster。

        Returns:
            DagPose | None: bindPoseアトリビュートに接続されたポーズ。未接続ならNone。

        Raises:
            ValueError: skinCluster以外を指定した場合。
            RuntimeError: 無効なノード、またはdagPose以外が接続されている場合。
        """
        from ..nodes.node import Node as _InputNode
        skin = _InputNode._resolve_input(skin_cluster)
        if not skin.isValid():
            raise RuntimeError("Cannot access an invalid skinCluster")
        if not skin.isType("skinCluster"):
            raise ValueError("Expected a skinCluster")
        names = cmds.listConnections(skin.fullName() + ".bindPose", source=True,
                                     destination=False) or []
        if not names:
            return None
        pose = Node(names[0])
        if not pose.isType("dagPose"):
            raise RuntimeError("skinCluster.bindPose is not connected to a dagPose")
        return pose

    def isBindPose(self):
        """bool: バインドポーズとして保存されたノードならTrue。"""
        self._pose_name()
        return bool(self.plug("bindPose").get())

    def memberIndices(self):
        """list[int]: 現在もメンバーが接続されている論理番号。欠番は保持する。"""
        name = self._pose_name()
        return [i for i in self.plug("members").mplug().getExistingArrayAttributeIndices()
                if cmds.listConnections(f"{name}.members[{i}]", source=True, destination=False)]

    def members(self):
        """list[Node]: 保存対象をmembers配列の論理番号順に返す。"""
        name = self._pose_name()
        return [Node(cmds.listConnections(f"{name}.members[{i}]", source=True,
                                          destination=False)[0]) for i in self.memberIndices()]

    def memberIndex(self, member):
        """指定メンバーの論理番号を返す。

        Args:
            member (Node | str): 保存対象のノード。
        Returns:
            int: members・worldMatrix・xformMatrixに共通の論理番号。
        Raises:
            ValueError: このポーズのメンバーでない場合。
        """
        from ..nodes.node import Node as _InputNode
        node = _InputNode._resolve_input(member)
        for index, item in zip(self.memberIndices(), self.members()):
            if item.fullName() == node.fullName():
                return index
        raise ValueError(f"Not a member of {self._pose_name()}: {member}")

    @flag_aliases(ws="worldSpace")
    def getMatrix(self, member, worldSpace=False):
        """現在のノード行列ではなく、保存時の行列を取得する。

        Args:
            member (Node | str): 保存対象のノード。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
        Returns:
            Matrix: 保存行列のコピー。
        Raises:
            ValueError: メンバーでない場合。
        """
        ws = world_space(worldSpace)
        index = self.memberIndex(member)
        attribute = "worldMatrix" if ws else "xformMatrix"
        return Matrix(self.plug(attribute).element(index).get())

    def notAtPose(self):
        """list[Node]: MayaのatPose照会で保存姿勢と異なると判定されたメンバー。"""
        return [Node(name) for name in
                (cmds.dagPose(self._pose_name(), query=True, atPose=True) or [])]

    def isAtPose(self):
        """bool: MayaのatPose照会で差異がない場合はTrue。"""
        return not self.notAtPose()

    def skinClusters(self):
        """list[SkinCluster]: このポーズをbindPoseとして参照するskinCluster。"""
        plugs = cmds.listConnections(self._pose_name() + ".message", source=False,
                                     destination=True, type="skinCluster", plugs=True) or []
        names = [plug.rsplit(".", 1)[0] for plug in plugs if plug.endswith(".bindPose")]
        return [Node(name) for name in dict.fromkeys(names)]

    @flag_aliases(ws="worldSpace")
    @undoChunk("hlibDagPoseRestore")
    def restore(self, worldSpace=False):
        """保存した姿勢へ戻す。接続やロックの解除は行わない。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
        Returns:
            DagPose: 自身。
        Raises:
            RuntimeError: 無効なノード、またはMayaが復元を拒否した場合。
        """
        ws = world_space(worldSpace)
        cmds.dagPose(self._pose_name(), restore=True, g=ws)
        return self

    @undoChunk("hlibDagPoseReset")
    def reset(self, members=None):
        """保存姿勢を現在の姿勢へ更新する。ノードを保存姿勢へ戻す操作ではない。

        skinClusterの変形基準行列(bindPreMatrix)は更新しない。

        Args:
            members (Node | str | Iterable[Node | str] | None): 更新対象。Noneなら全メンバー。
        Returns:
            DagPose: 自身。
        Raises:
            ValueError: 明示した対象が空、またはメンバーでない場合。
            RuntimeError: Mayaが更新を拒否した場合。
        """
        name = self._pose_name()
        targets = self.members() if members is None else members
        if members is None and not targets:
            return self
        names = self._transform_names(targets)
        for target in names:
            self.memberIndex(target)
        cmds.dagPose(names, reset=True, name=name)
        return self

    @undoChunk("hlibDagPoseAdd")
    def addMembers(self, *members):
        """TransformまたはJointを現在の姿勢で追加する。

        Args:
            members (Node | str | Iterable[Node | str]): 追加する対象。空は不可。
        Returns:
            DagPose: 自身。
        """
        cmds.dagPose(self._transform_names(members), addToPose=True, name=self._pose_name())
        return self

    @undoChunk("hlibDagPoseRemove")
    def removeMembers(self, *members):
        """メンバーをポーズから外す。シーンのノード自体は削除しない。

        残るメンバーの親として必要なノードはMayaによって保持される場合がある。

        Args:
            members (Node | str | Iterable[Node | str]): 除外する既存メンバー。空は不可。
        Returns:
            DagPose: 自身。
        Raises:
            ValueError: ポーズのメンバーでない対象が含まれる場合。
        """
        names = self._transform_names(members)
        for target in names:
            self.memberIndex(target)
        cmds.dagPose(names, remove=True, name=self._pose_name())
        return self

    @staticmethod
    def _transform_names(members):
        """対象を有効なTransformの完全パスに揃える。空入力はValueError。"""
        from ..object import Object as _InputObject
        names = []
        for name in _InputObject._input_names(members):
            node = Node(name)
            if not node.isValid() or not node.isType("transform"):
                raise ValueError(f"Expected a valid transform or joint: {name}")
            if node.fullName() not in names:
                names.append(node.fullName())
        if not names:
            raise ValueError("At least one transform or joint is required")
        return names

    def _pose_name(self):
        """有効なdagPoseの名前を返す。削除済みならRuntimeError。"""
        if not self.isValid():
            raise RuntimeError("Cannot access an invalid dagPose")
        return self.fullName()
