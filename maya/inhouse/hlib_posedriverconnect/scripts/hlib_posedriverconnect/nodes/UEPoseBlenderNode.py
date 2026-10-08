"""PoseDriverConnectのポーズブレンダーをhlibノードとして扱う。"""

from epic_pose_wrangler.v2.model.pose_blender import UEPoseBlenderNode as NativePoseBlender

from .._binding import coreModule

Node = coreModule('nodes').Node


class UEPoseBlenderNode(Node):
    """PoseDriverConnect v2のポーズブレンダー。"""

    def native_api(self):
        """現在名から外部APIラッパーを取得する。

        Returns:
            NativePoseBlender: 現在名から外部APIラッパーを取得する。
        """
        return NativePoseBlender(self.getFullName())

    def driven_transform(self):
        """接続された駆動先。未接続ならNone。

        Returns:
            Node | None: 接続された駆動先。未接続ならNone。
        """
        name = self.native_api().driven_transform
        return Node(name) if name else None

    def envelope(self):
        """外部APIで現在のenvelopeを取得する。

        Returns:
            float: 外部APIで現在のenvelopeを取得する。
        """
        return self.native_api().envelope
