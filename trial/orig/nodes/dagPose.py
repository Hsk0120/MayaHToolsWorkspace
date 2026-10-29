"""DAG階層の保存姿勢とバインドポーズを扱う。"""

import maya.cmds as cmds

from ..core.object import Object
from ..decorator import undoChunk
from ..util import _world_space
from .node import Node


class DagPose(Node):
    """dagPoseノードの参照を保持し、保存姿勢の作成・取得・復元を扱う。

    バインドポーズも同じノード型。restore()はシーンの姿勢を保存姿勢へ戻す。
    保存・復元はMaya標準コマンドを使い、fast引数は提供しない。メンバーの編集・
    保存姿勢の更新・統合は ``cmds.dagPose`` を直接使う。
    """

    @classmethod
    @undoChunk("mlibDagPoseCreate")
    def create(cls, members, name=None, bindPose=False, hierarchy=True):
        """現在の姿勢を新しいポーズに保存する。選択状態は参照しない。

        対象/nameを検証して保存し、指定名は保存後の改名で適用する。
        改名失敗でも保存は自動で戻さない。

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
    def fromSkinCluster(cls, skinCluster):
        """skinClusterに接続されているバインドポーズを取得する。

        Args:
            skinCluster (Node | str): 照会するskinCluster。

        Returns:
            DagPose | None: bindPoseアトリビュートに接続されたポーズ。未接続ならNone。

        Raises:
            ValueError: skinCluster以外を指定した場合。
            RuntimeError: 無効なノード、またはdagPose以外が接続されている場合。
        """
        skin = Node._resolve_input(skinCluster)
        if not skin.isValid():
            raise RuntimeError("Cannot access an invalid skinCluster")
        if not skin.isType("skinCluster"):
            raise ValueError("Expected a skinCluster")
        source = skin.getPlug("bindPose").getSource(skipConversionNodes=False)
        if source is None:
            return None
        pose = source.getNode()
        if not pose.isType("dagPose"):
            raise RuntimeError("skinCluster.bindPose is not connected to a dagPose")
        return pose

    def restore(self, worldSpace=False):
        """保存した姿勢へ戻す。接続やロックの解除は行わない。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。

        Returns:
            DagPose: 自身。

        Raises:
            RuntimeError: 無効なノード、またはMayaが復元を拒否した場合。
        """
        with undoChunk("mlibDagPoseRestore"):
            ws = _world_space(worldSpace)
            cmds.dagPose(self._pose_name(), restore=True, g=ws)
            return self

    @staticmethod
    def _transform_names(members):
        """対象を有効なTransformの完全パスに揃える。空入力はValueError。

        Args:
            members: 所属または保存対象として扱うノード・コンポーネント。
        """
        names = []
        for name in Object._input_names(members):
            node = Node(name)
            if not node.isValid() or not node.isType("transform"):
                raise ValueError(f"Expected a valid transform or joint: {name}")
            if node.getFullName() not in names:
                names.append(node.getFullName())
        if not names:
            raise ValueError("At least one transform or joint is required")
        return names

    def _pose_name(self):
        """有効なdagPoseの名前を返す。削除済みならRuntimeError。"""
        self._require_valid("access")
        return self.getFullName()
