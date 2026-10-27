"""ウェイト移送と子階層の保持を伴う、明示的なジョイント整理。"""

from contextlib import nullcontext

import maya.cmds as cmds
import mlib
from mlib.decorator import undoChunk


class JointHierarchy:
    """Maya標準の削除とは別に、ジョイント階層を整理する。"""

    @staticmethod
    def delete(joints, *, safe=False, fast=False):
        """子を親へ移し、祖先influenceへウェイトを移送してジョイントを削除する。

        Args:
            joints (Joint | str | Iterable[Joint | str]): 整理するジョイント。
                名前とNodeを同じ列で混在させない。深い階層からノード単位で処理する。
            safe (bool): Trueは自身か子孫にDG接続があるジョイントを除外する。
            fast (bool): Trueは対応するOpenMaya直接更新でUndoなし。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: safe/fastがbool以外、または対象がJoint以外の場合。
            RuntimeError: 無効な対象、ウェイト移送、親変更、削除の失敗。
            NotImplementedError: fastで中間Transform等が必要な条件の場合。

        Note:
            同じskinClusterの最も近い祖先influenceがあれば、sourceの値でtargetを
            置換する。加算ではなく、正規化はskinClusterのnormalizeWeights設定に従う。
            移送先がなければMaya標準の削除に任せる。子は直接の親、親がなければworldへ移す。
            通常は一回のUndoで戻せる。途中失敗では完了済み変更を自動で戻さない。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlrigJointHierarchyDelete"):
            if type(safe) is not bool:
                raise TypeError("safe must be bool")
            if isinstance(joints, (str, mlib.nodes.Node)):
                joints = [joints]
            targets = mlib.nodes.Joints(joints)
            for joint in targets:
                if not joint.isType("joint"):
                    raise RuntimeError("Cannot delete an invalid joint")
            if safe:
                targets = mlib.nodes.Joints([joint for joint in targets if not joint._has_delete_connections()])
            plans = JointHierarchy._prepare(targets, fast=fast)
            for joint, transfers in plans:
                name = joint.getFullName()
                stage = "transfer weights"
                try:
                    for skin, target in transfers:
                        skin.transferWeights([(joint, target)], fast=fast)
                        stage = "remove influence"
                        if not fast:
                            skin.removeInfluence(joint, transferToParent=False, fast=fast)
                        # fast削除はMaya標準の削除通知でinfluence構造も解除する。
                        stage = "transfer weights"
                    stage = "reparent children"
                    parent = joint.getParent()
                    for child in joint.getChildren():
                        if fast and child.isType("joint"):
                            from mlib.core.jointEdit import reparent, reparent_plan

                            reparent(reparent_plan(child, parent))
                        elif fast:
                            child.setParent(parent, fast=True)
                        elif parent is None:
                            cmds.parent(child.getFullName(), world=True)
                        else:
                            cmds.parent(child.getFullName(), parent.getFullName())
                    stage = "delete joint"
                    joint.delete(fast=fast)
                except Exception as exc:
                    raise RuntimeError(f"Failed to {stage} for {name}: {exc}") from exc

    @staticmethod
    def _prepare(joints, *, fast=False):
        """全対象の移送先とfastの最終階層を、変更前に検査する。

        Args:
            joints (Joints): 入力を検証済みのジョイント列。

        Returns:
            list[tuple[Joint, list]]: 深い階層順の対象と移送先。
        """
        targets, seen = [], set()
        for joint in joints.sortedByDepth():
            key = joint.getUuid()
            if key not in seen:
                seen.add(key)
                targets.append(joint)
        plans = []
        for joint in targets:
            transfers = []
            for skin in joint.getSkinClusters():
                target = joint.getTransferTarget(skin)
                if target:
                    skin._raise_if_layers()
                    transfers.append((skin, target))
            plans.append((joint, transfers))
        if fast:
            # 更新前検証はmlibの実更新と同じ制限を使い、リグ側に制約を複製しない。
            from mlib.core.jointEdit import reparent_plan
            from mlib.core.nodeEdit import require_editable

            deleted_ids = {joint.getUuid() for joint in targets}
            for joint, transfers in plans:
                for skin, _ in transfers:
                    if len(skin.mfn().getOutputGeometry()) != 1:
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
                        reparent_plan(child, parent)
                    else:
                        child._set_parent_fast(parent, False, False, validate_only=True)
        return plans
