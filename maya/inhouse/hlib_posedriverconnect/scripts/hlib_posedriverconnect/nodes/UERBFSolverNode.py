"""PoseDriverConnectのRBFソルバーをhlibノードとして扱う。"""

from epic_pose_wrangler.v2.model.api import RBFNode

from .._binding import coreModule

Node = coreModule('nodes').Node
node_wrapper = coreModule('extensions').node_wrapper
undoChunk = coreModule('decorators').undoChunk


@node_wrapper("UERBFSolverNode")
class UERBFSolverNode(Node):
    """PoseDriverConnect v2のRBFソルバー。"""

    def native_api(self):
        """RBFNode: 現在名から外部APIラッパーを取得する。直接編集のUndoは外部仕様。"""
        return RBFNode(self.fullName())

    def drivers(self):
        """list[Node]: 接続されたドライバーを外部APIの順序で取得する。"""
        return [Node(name) for name in self.native_api().drivers()]

    def num_poses(self):
        """int: 登録されているポーズ数を取得する。"""
        return self.native_api().num_poses()

    def radius(self):
        """float: 外部APIの半径設定値を取得する。"""
        return self.native_api().radius()

    @undoChunk("hlibPoseDriverConnectSetRadius")
    def setRadius(self, value):
        """ソルバー半径を変更する。Maya cmds経由でUndo可能。

        Args:
            value (float): 外部APIへ渡す半径。
        Returns:
            None: 値を返さない。
        """
        self.native_api().set_radius(value)
