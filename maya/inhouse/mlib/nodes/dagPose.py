"""DAG階層の保存姿勢とバインドポーズを扱う。"""

import maya.cmds as cmds

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
        source = skin.getPlug("bindPose").getSource()
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

    def _pose_name(self):
        """有効なdagPoseの名前を返す。削除済みならRuntimeError。"""
        self._require_valid("access")
        return self.getFullName()
