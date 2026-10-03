"""PoseDriverConnectのポーズブレンダーをhlibノードとして扱う。"""

from epic_pose_wrangler.v2.model.pose_blender import UEPoseBlenderNode as NativePoseBlender

from .._binding import coreModule

Node = coreModule('nodes').Node
node_wrapper = coreModule('extensions').node_wrapper


@node_wrapper("UEPoseBlenderNode")
class UEPoseBlenderNode(Node):
    """PoseDriverConnect v2のポーズブレンダー。"""

    def native_api(self):
        """NativePoseBlender: 現在名から外部APIラッパーを取得する。"""
        return NativePoseBlender(self.fullName())

    def driven_transform(self):
        """Node | None: 接続された駆動先。未接続ならNone。"""
        name = self.native_api().driven_transform
        return Node(name) if name else None

    def envelope(self):
        """float: 外部APIで現在のenvelopeを取得する。"""
        return self.native_api().envelope
