"""Joint削除時のウェイト移送と階層保持。公開コレクションから分離する。"""

import maya.cmds as cmds

from ..common._fast import is_fast
from ..decorator import undoChunk


class _JointDeletion:
    """一回のジョイント削除を実行する内部処理。"""

    def __init__(self, joints):
        """削除するJointsを保持する。構築時にはシーンを変更しない。

        Args:
            joints (Joints): 階層の深い順に削除するジョイント群。
        """
        self._joints = joints

    @undoChunk("mlibJointDelete")
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
        plans = self._prepare()
        for joint, transfers in plans:
            name = joint.getFullName()
            stage = "transfer weights"
            try:
                for skin, target in transfers:
                    skin.transferWeights([(joint.getFullName(), target)])
                    stage = "remove influence"
                    if not is_fast():
                        skin.removeInfluence(joint.getFullName(), transfer_to_parent=False)
                    # OMのノード削除もMaya標準のinfluence削除通知を発火する。
                    # fastでは後のdeleteNodeへ構造の解除を任せ、二重解除を避ける。
                    stage = "transfer weights"
                stage = "reparent children"
                parent = joint.getParent()
                for child in joint.getChildren():
                    if is_fast() and child.isType("joint"):
                        from .jointEdit import reparent, reparent_plan
                        reparent(reparent_plan(child, parent))
                    elif is_fast():
                        child.setParent(parent, fast=True)
                    elif parent is None:
                        cmds.parent(child.getFullName(), world=True)
                    else:
                        cmds.parent(child.getFullName(), parent.getFullName())
                stage = "delete joint"
                if is_fast():
                    from .nodeEdit import delete_node
                    delete_node(joint.mnode())
                else:
                    cmds.delete(joint.getFullName())
            except Exception as exc:
                raise RuntimeError(f"Failed to {stage} for {name}: {exc}") from exc

    def _prepare(self):
        """変更前に全Joint・ウェイト・最終階層の計画を検査する。

        Returns:
            list[tuple[Joint, list]]: 入力順に実行する検証済みの移送計画。
        """
        # コレクションはインスタンスパスを保持するが、削除・ウェイト移送は
        # ノード全体の操作。同一UUIDの別パスを二度処理しない。
        target_joints, seen = [], set()
        for joint in self._joints.sortedByDepth():
            if not joint.isValid():
                raise RuntimeError("Cannot delete an invalid joint")
            key = joint.getUuid()
            if key not in seen:
                seen.add(key)
                target_joints.append(joint)
        # 祖先influenceへMaya標準の移送を行う組を計画する。それ以外は標準削除に任せる。
        plans = []
        for joint in target_joints:
            if not joint.isJoint():
                raise RuntimeError("Cannot delete an invalid joint")
            transfers = []
            for skin in joint.getSkinClusters():
                target = joint.getTransferTarget(skin)
                if target:
                    skin._raise_if_layers()
                    transfers.append((skin, target))
            plans.append((joint, transfers))
        if is_fast():
            from .jointEdit import reparent_plan
            from .nodeEdit import require_editable
            deleted_ids = {joint.getUuid() for joint in target_joints}
            for joint, transfers in plans:
                for skin, _ in transfers:
                    if len(skin.fn.getOutputGeometry()) != 1:
                        raise NotImplementedError("fast weight transfer requires one geometry")
                    skin._editable_weights()
                require_editable(joint.mnode(), descendants=True)
                for skin in joint.getSkinClusters():
                    skin._raise_if_layers()
                parent = joint.getParent()
                while parent is not None and parent.getUuid() in deleted_ids:
                    parent = parent.getParent()
                pending = list(joint.getChildren())
                while pending:
                    child = pending.pop()
                    if child.getUuid() in deleted_ids:
                        pending.extend(child.getChildren())
                    elif child.isType("joint"):
                        # 最終親への移動で中間Transformが必要な場合は、
                        # ウェイト移送を始める前に拒否する。
                        reparent_plan(child, parent)
                    else:
                        child._set_parent_fast(parent, False, False, validate_only=True)
        return plans
