"""ウェイト移送と子階層の保持を伴う、明示的なジョイント整理。"""

from contextlib import nullcontext

import mlib
from maya import cmds
from mlib.maths import Vector
from mlib.decorator import undoChunk, undoTransaction


class JointHierarchy:
    """Maya標準の削除とは別に、ジョイント階層を整理する。"""

    @staticmethod
    @undoTransaction("mlrigOrientJointPair")
    def orientPair(root):
        """設計中の親骨の+Xを唯一の子骨へ向け、子骨のワールド姿勢を保持する。"""
        root = mlib.Joint(root)
        parent_name = root.getName(full=True)
        children = cmds.listRelatives(parent_name, children=True, fullPath=True) or []
        if len(children) != 1 or cmds.nodeType(children[0]) != "joint":
            raise ValueError("直接の子がジョイント1本の親骨を指定してください")
        child = children[0]
        if cmds.autoKeyframe(query=True, state=True):
            raise ValueError("自動キーを無効にしてください")
        for bone in (root, mlib.Joint(child)):
            name = bone.getName(full=True)
            if bone.getSkinClusters(influence=True) or cmds.referenceQuery(name, isNodeReferenced=True):
                raise ValueError("バインド済みまたは参照の骨は調整できません: " + name)
            for attr in ("translate", "rotate", "jointOrient", "scale", "rotateAxis"):
                for axis in "XYZ":
                    plug = name + "." + attr + axis
                    if not cmds.getAttr(plug, settable=True) or cmds.connectionInfo(plug, isDestination=True):
                        raise ValueError("ロックまたは入力接続があります: " + plug)
            opm = name + ".offsetParentMatrix"
            if cmds.connectionInfo(opm, isDestination=True):
                raise ValueError("親マトリクスに入力接続があります: " + name)
        if any(abs(value) > 1e-9 for value in cmds.getAttr(parent_name + ".rotate")[0]):
            raise ValueError("親骨の回転チャンネルをゼロにしてから実行してください")
        before = cmds.xform(child, query=True, matrix=True, worldSpace=True)
        parent_world = cmds.xform(parent_name, query=True, matrix=True, worldSpace=True)
        direction = Vector(*before[12:15]) - Vector(*parent_world[12:15])
        if direction.length() <= 1e-8:
            raise ValueError("骨の長さが不足しています")
        # MayaのorientJointは子骨に回転値があると向きを変更しない。
        cmds.setAttr(child + ".rotate", 0, 0, 0)
        root.orient("xyz", secondaryAxisOrient="yup", children=False)
        cmds.xform(child, matrix=before, worldSpace=True)
        after = cmds.xform(child, query=True, matrix=True, worldSpace=True)
        aligned = cmds.xform(parent_name, query=True, matrix=True, worldSpace=True)
        if max(abs(a - b) for a, b in zip(before, after)) > 1e-6 or Vector(*aligned[:3]).normal() * direction.normal() < 1 - 1e-6:
            raise ValueError("この姿勢で軸合わせと子の姿勢保持を両立できません")
        return child

    @staticmethod
    def delete(joints, *, skipConnected=False, fast=False):
        """子を親へ移し、祖先influenceへウェイトを移送してジョイントを削除する。

        Args:
            joints (Joint | str | Iterable[Joint | str]): 整理するジョイント。
                名前とNodeを同じ列で混在させない。深い階層からノード単位で処理する。
            skipConnected (bool): Trueは自身か子孫にDG接続があるジョイントを除外する(mlibの Joint.delete と同じ名前)。
            fast (bool): Trueは対応するOpenMaya直接更新でUndoなし。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: skipConnected/fastがbool以外、または対象がJoint以外の場合。
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
            if type(skipConnected) is not bool:
                raise TypeError("skipConnected must be bool")
            if isinstance(joints, (str, mlib.Node)):
                joints = [joints]
            targets = mlib.Joints(joints)
            for joint in targets:
                if not joint.isType("joint"):
                    raise RuntimeError("Cannot delete an invalid joint")
            if skipConnected:
                targets = mlib.Joints([joint for joint in targets if not joint._has_delete_connections()])
            plans = JointHierarchy._prepare(targets, fast=fast)
            for joint, transfers in plans:
                name = joint.getName(full=True)
                stage = "transfer weights"
                try:
                    for skin, target in transfers:
                        skin.transferWeights([(joint, target)], fast=fast)
                        stage = "remove influence"
                        if not fast:
                            skin.removeInfluences(joint, transferToParent=False)
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
                        else:
                            child.setParent(parent)
                    stage = "delete joint"
                    joint.delete(fast=fast, removeInfluence=False)
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
            for skin in joint.getSkinClusters(influence=True):
                target = joint.getTransferTarget(skin)
                if target:
                    skin._raise_if_layers()
                    transfers.append((skin, target.getName()))
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
                for skin in joint.getSkinClusters(influence=True):
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
