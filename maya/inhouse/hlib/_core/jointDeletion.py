"""Joint削除時のウェイト移送と階層保持。公開コレクションから分離する。"""

import maya.cmds as cmds
from ..decorators.undo import undo_chunk


class _JointDeletion:
    """一回のジョイント削除を実行する内部処理。"""

    def __init__(self, joints):
        """削除するJointsを保持する。構築時にはシーンを変更しない。

        Args:
            joints (Joints): 階層の深い順に削除するジョイント群。
        """
        self._joints = joints

    @undo_chunk("hlibJointDelete")
    def execute(self):
        """joint階層を深い順に処理し、ウェイト移送後にjointを削除する。

        未スキニングjointも削除する。子Transform（jointを含む）は直接の親へ、
        親がなければワールドへ移す。同じskinClusterの祖先influenceがある場合だけ
        ウェイトを移送する。移送先なしの場合はcmds.deleteの標準処理に任せる。
        途中で失敗した場合は例外で停止する。完了済みの変更は自動では戻さない。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 無効なjoint、移送対象のスキニングレイヤー、
                またはウェイト移送・再親付け・削除に失敗した場合。
        """
        target_joints = self._joints.sorted_by_depth()
        # 祖先influenceへ加算できる組だけを計画する。それ以外は標準削除に任せる。
        plans = []
        for joint in target_joints:
            if not joint.is_joint():
                raise RuntimeError("Cannot delete an invalid joint")
            transfers = []
            for skin in joint.skin_clusters():
                target = joint.transfer_target(skin)
                if target:
                    skin._raise_if_layers()
                    transfers.append((skin, target))
            plans.append((joint, transfers))
        for joint, transfers in plans:
            name = joint.full_name()
            stage = "transfer weights"
            try:
                for skin, target in transfers:
                    skin.transfer_weight(joint.full_name(), target)
                    stage = "remove influence"
                    skin.remove_influence(joint.full_name(), transfer_to_parent=False)
                    stage = "transfer weights"
                stage = "reparent children"
                parent = joint.parent_node()
                for child in joint.child_transforms():
                    if parent is None:
                        cmds.parent(child.full_name(), world=True)
                    else:
                        cmds.parent(child.full_name(), parent.full_name())
                stage = "delete joint"
                cmds.delete(joint.full_name())
            except Exception as exc:
                raise RuntimeError(f"Failed to {stage} for {name}: {exc}") from exc
