"""DAG階層の保存姿勢とバインドポーズを扱う。"""

import math
import shlex

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.nodeEdit import require_editable
from ..core.object import Object
from ..decorator import _pick_alias, _require_bool, undoChunk, undoTransaction
from ..maths import Matrix
from ..util import _UNSET, _world_space
from .node import Node, Nodes


class DagPose(Node):
    """dagPoseノードの参照を保持し、DAGメンバーの保存姿勢とバインドポーズを扱う。

    membersの接続と保存マトリクス/親情報を照会・編集する。バインドポーズも同じノード型で、
    isBindPose()で区別する。reset()は保存姿勢を現在の姿勢へ更新し、restore()はシーンの
    姿勢を保存姿勢へ戻す。skinCluster.bindPreMatrixの再設定は担当しない。

    保存・復元・メンバー編集はMaya標準の ``cmds.dagPose`` を使い、fast引数は提供しない
    (Mayaの階層補完・復元規則をom2で再現しないため)。merge()は保存情報の統合と
    skinCluster.bindPoseの再接続を行う。作成は ``mlib.createDagPose`` で行う。
    """

    #: 保存情報を持つマルチアトリビュート。members と共通の論理番号を使う。
    _POSE_ARRAYS = ("members", "parents", "worldMatrix", "xformMatrix", "global")

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

    def isBindPose(self):
        """バインドポーズとして保存されたノードか判定する。

        Returns:
            bool: bindPoseアトリビュートがTrueならTrue。

        Raises:
            RuntimeError: 無効なノードの場合。
        """
        self._pose_name()
        return bool(self.getPlug("bindPose").mplug().asBool())

    def getMemberIndices(self):
        """現在も接続された保存メンバーの論理番号を取得する。

        members配列の既存番号のうち、入力接続がある要素だけを返す。切断済みの空要素を除き、
        欠番を詰めずにworldMatrix・xformMatrixとの対応を保つ。

        Returns:
            list[int]: membersの論理番号の昇順。物理位置ではない。

        Raises:
            RuntimeError: 無効なノードの場合。
        """
        return [index for index, _ in self._member_sources()]

    def getMembers(self):
        """保存対象をmembers配列の論理番号順に取得する。

        Returns:
            list[Node]: 保存対象。getMemberIndices()と同じ順序。

        Raises:
            RuntimeError: 無効なノードの場合。
        """
        return [Node(source.node()) for _, source in self._member_sources()]

    def getMemberIndex(self, member):
        """指定メンバーの論理番号を取得する。

        Args:
            member (Node | str): 保存対象のノード。

        Returns:
            int: members・worldMatrix・xformMatrixに共通の論理番号。

        Raises:
            TypeError: 対応しない型を指定した場合。
            ValueError: 存在しないノード、またはこのポーズのメンバーでない場合。
            RuntimeError: 無効なdagPoseの場合。
        """
        name = self._pose_name()
        node = Node._resolve_input(member)
        target = node.mnode()
        for index, source in self._member_sources():
            if source.node() == target:
                return index
        raise ValueError(f"Not a member of {name}: {node.getFullName()}")

    def getMatrix(self, member, worldSpace=_UNSET, *, ws=_UNSET):
        """指定メンバーの保存マトリクスを、独立したMatrixとして取得する。

        membersと共通の論理番号でworldMatrixまたはxformMatrixを読む。現在のTransformの
        マトリクスの照会や姿勢の復元は行わない。

        Args:
            member (Node | str): このポーズの保存メンバー。
            worldSpace (bool): Trueは保存したワールドマトリクス、Falseは保存したローカルの
                マトリクス(xformMatrix)。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Matrix: 保存マトリクスの新しいコピー。変更してもポーズやシーンは変化しない。

        Raises:
            TypeError: worldSpaceがbool以外、またはmemberが対応しない型の場合。
            ValueError: このポーズのメンバーでない場合。
            RuntimeError: 無効なdagPoseの場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        ws = _world_space(worldSpace)
        index = self.getMemberIndex(member)
        attribute = "worldMatrix" if ws else "xformMatrix"
        plug = self.getPlug(attribute).mplug().elementByLogicalIndex(index)
        return Matrix.fromMMatrix(om2.MFnMatrixData(plug.asMObject()).matrix())

    def getNotAtPose(self):
        """Mayaが保存姿勢と異なると判定したメンバーを取得する。

        ``cmds.dagPose(query=True, atPose=True)`` (Bind Poseメニューの判定と同じ)を使い、
        許容誤差はMayaの判定に従う。

        Returns:
            list[Node]: 保存姿勢と異なるメンバー。全員が保存姿勢なら空。

        Raises:
            RuntimeError: 無効なdagPoseの場合。
        """
        names = cmds.dagPose(self._pose_name(), query=True, atPose=True) or []
        return [Node(name) for name in names]

    def isAtPose(self):
        """全メンバーが保存姿勢にあるか判定する。

        Returns:
            bool: getNotAtPose()が空ならTrue。

        Raises:
            RuntimeError: 無効なdagPoseの場合。
        """
        return not cmds.dagPose(self._pose_name(), query=True, atPose=True)

    def getSkinClusters(self):
        """このポーズをbindPoseとして参照するskinClusterを取得する。

        Returns:
            list[SkinCluster]: message→skinCluster.bindPoseの接続先。重複なし。

        Raises:
            RuntimeError: 無効なdagPoseの場合。
        """
        self._pose_name()
        nodes = []
        for plug in self.getPlug("message").mplug().destinations():
            if (plug.node().hasFn(om2.MFn.kSkinClusterFilter)
                    and om2.MFnAttribute(plug.attribute()).name == "bindPose"):
                node = Node(plug.node())
                if node not in nodes:
                    nodes.append(node)
        return nodes

    def restore(self, worldSpace=_UNSET, *, ws=_UNSET):
        """保存した姿勢へ戻す。接続やロックの解除は行わない。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            DagPose: 自身。

        Raises:
            RuntimeError: 無効なノード、またはMayaが復元を拒否した場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        with undoChunk("mlibDagPoseRestore"):
            ws = _world_space(worldSpace)
            cmds.dagPose(self._pose_name(), restore=True, g=ws)
            return self

    def reset(self, members=None):
        """指定メンバーの保存姿勢を、シーンの現在姿勢へ更新する。

        ノードを保存姿勢へ動かすrestore()とは異なり、保存側だけを更新する。
        skinCluster.bindPreMatrixやウェイトは変更しない。対象を全件検証してから
        Mayaの ``dagPose -reset`` を呼び、1回のUndoにまとめる。

        Args:
            members (Node | str | Iterable[Node | str] | None): 更新対象。Noneは全メンバー。
                Noneでメンバーがなければ何も変更しない。

        Returns:
            DagPose: 自身。

        Raises:
            TypeError: 対応しない型を指定した場合。
            ValueError: 明示入力が空、Transform以外、またはメンバー以外を含む場合。
            RuntimeError: 無効なノード、またはMayaが保存姿勢の更新を拒否した場合。
        """
        with undoChunk("mlibDagPoseReset"):
            name = self._pose_name()
            if members is None:
                names = [node.getFullName() for node in self.getMembers()]
                if not names:
                    return self
            else:
                names = self._transform_names(members)
                for target in names:
                    self.getMemberIndex(target)
            cmds.dagPose(names, reset=True, name=name)
            return self

    def addMembers(self, *members):
        """TransformまたはJointを現在の姿勢でポーズへ追加する。

        Mayaの ``dagPose -addToPose`` を使い、復元に必要な親の情報もMayaの規則で保存する。
        既存メンバーは無視し、その保存姿勢も更新しない(更新はreset()を使う)。

        Args:
            *members (Node | str | Iterable[Node | str]): 追加する対象。空は不可。

        Returns:
            DagPose: 自身。

        Raises:
            TypeError: 対応しない型を指定した場合。
            ValueError: 空入力、またはTransform以外を含む場合。
            RuntimeError: 無効なノード、またはMayaが追加を拒否した場合。
        """
        with undoChunk("mlibDagPoseAddMembers"):
            name = self._pose_name()
            names = self._transform_names(members)
            current = [source.node() for _, source in self._member_sources()]
            names = [target for target in names
                     if not any(Node(target).mnode() == obj for obj in current)]
            if names:
                cmds.dagPose(names, addToPose=True, name=name)
            return self

    def removeMembers(self, *members):
        """メンバーをポーズから外す。シーンのノード自体は削除しない。

        残るメンバーの親として必要なノードはMayaによって保持される場合がある。

        Args:
            *members (Node | str | Iterable[Node | str]): 除外する既存メンバー。空は不可。

        Returns:
            DagPose: 自身。

        Raises:
            TypeError: 対応しない型を指定した場合。
            ValueError: 空入力、Transform以外、またはメンバー以外を含む場合。
            RuntimeError: 無効なノード、またはMayaが除外を拒否した場合。
        """
        with undoChunk("mlibDagPoseRemoveMembers"):
            name = self._pose_name()
            names = self._transform_names(members)
            for target in names:
                self.getMemberIndex(target)
            cmds.dagPose(names, remove=True, name=name)
            return self

    def merge(self, sources, *, currentPose=False, deleteSources=True):
        """他の保存ポーズを自身へ統合し、skinClusterのbindPose参照先を自身へ揃える。

        currentPose=Falseでは保存姿勢・親情報・xformの内部情報の競合を変更前に拒否する。
        currentPose=Trueは競合を許容し、自身の既存メンバーを含めて現在姿勢を保存する。
        既存の疎な論理番号は保持する。ジョイントの姿勢・ウェイト・bindPreMatrixは変更しない。

        変更前に入力・競合・ロック・参照・削除可否を検査し、変更は1回のUndoにまとめる。
        Undo有効時は途中の失敗をUndoで巻き戻す(undoTransaction)。完了は保証しない。

        Args:
            sources (DagPose | str | Iterable[DagPose | str]): 統合元のdagPose。
                自身や重複の指定は無視する。空入力は不可。
            currentPose (bool): 保存済み姿勢ではなく現在の姿勢・階層を保存する。
            deleteSources (bool): 統合後に統合元を削除する。メンバー・親情報・
                skinCluster.bindPose・joint.bindPoseからの保存マトリクス以外の接続があれば拒否する。

        Returns:
            DagPose: 自身。

        Raises:
            TypeError: currentPose・deleteSourcesがbool以外、またはsourcesが対応しない型の場合。
            ValueError: 空入力・dagPose以外・保存情報の競合・通常ポーズとbindPoseの混在。
            RuntimeError: ロック・参照・インスタンス・不正な保存情報、またはMayaの編集失敗。
        """
        _require_bool(currentPose, "currentPose")
        _require_bool(deleteSources, "deleteSources")
        name, poses, others = self._merge_collect_poses(sources)
        if not others:
            return self
        rows, target_rows, skins = self._merge_collect_rows(poses, currentPose, deleteSources)
        self._merge_check_targets(skins)

        with undoTransaction("mlibDagPoseMerge"):
            temp = None
            if currentPose:
                # 一時的な通常ポーズなら既存bindPoseを再利用せず、現在姿勢のxform内部情報
                # (jointOrient等)もMaya自身が正しく保存する。
                temp = Node(cmds.dagPose(list(rows), save=True, selection=True))
                rows = temp._merge_snapshot()
            indices = self._merge_allocate_indices(rows, target_rows)
            self._merge_write_rows(name, rows, target_rows, indices, currentPose)
            if temp is not None:
                cmds.delete(temp.getFullName())
            for skin in skins.values():
                cmds.connectAttr(name + ".message", skin.getFullName() + ".bindPose", force=True)
            if deleteSources:
                cmds.delete([pose.getFullName() for pose in others])
        return self

    def _member_sources(self):
        """接続されたmembers要素の論理番号と接続元を取得する。

        Returns:
            list[tuple[int, om2.MPlug]]: 論理番号の昇順の(番号, 接続元のPlug)。
        """
        self._pose_name()
        members = self.getPlug("members").mplug()
        result = []
        for index in members.getExistingArrayAttributeIndices():
            plug = members.elementByLogicalIndex(index)
            if plug.isDestination:
                result.append((index, plug.source()))
        return result

    def _merge_collect_poses(self, sources):
        """対象自身と統合元を入力順に解決し、同じポーズを一度だけ扱う。

        Args:
            sources (object): 統合元のポーズ入力。

        Returns:
            tuple: 対象名、対象を先頭とするポーズ辞書、対象自身を除いた統合元のlist。
        """
        name = self._pose_name()
        nodes = Nodes._resolve_inputs(sources)
        if not nodes:
            raise ValueError("At least one source pose is required")
        poses = {name: self}
        for value in nodes:
            node = Node._resolve_input(value)
            if not node.isValid() or not node.isType("dagPose"):
                raise ValueError(f"Expected a dagPose: {value}")
            poses.setdefault(node.getFullName(), node)
        others = [pose for key, pose in poses.items() if key != name]
        return name, poses, others

    def _merge_collect_rows(self, poses, current_pose, delete_sources):
        """保存行とskinClusterを集め、姿勢の競合と統合元の削除可否を検査する。

        Args:
            poses (dict): 対象を先頭とするポーズ辞書。
            current_pose (bool): 保存姿勢の競合を許容し、現在の姿勢を後で保存するか。
            delete_sources (bool): 統合元の削除可否を検査するか。

        Returns:
            tuple: 統合する保存行、対象の既存保存行、再接続するskinCluster辞書。
        """
        rows = {}
        target_rows = {}
        skins = {}
        bind_pose = self.isBindPose()
        for pose in poses.values():
            if pose.isBindPose() != bind_pose:
                raise ValueError("Cannot mix bind poses and ordinary poses")
            snapshot = pose._merge_snapshot()
            if pose is self:
                target_rows = snapshot
            for member, row in snapshot.items():
                if not current_pose and member in rows:
                    if not self._merge_rows_equal(rows[member], row):
                        raise ValueError(f"Conflicting saved pose: {member}")
                else:
                    rows[member] = row
            if pose is not self:
                for skin in pose.getSkinClusters():
                    skins[skin.getFullName()] = skin
                if delete_sources:
                    pose._merge_check_delete()
        if not rows:
            raise ValueError("Cannot merge empty poses")
        return rows, target_rows, skins

    def _merge_check_targets(self, skins):
        """対象の保存先とskinClusterの再接続先が編集できることを検査する。

        Args:
            skins (dict): 再接続するskinCluster辞書。
        """
        require_editable(self.mnode())
        for attr in self._POSE_ARRAYS:
            plug = self.getPlug(attr).mplug()
            if plug.isLocked or any(plug.elementByLogicalIndex(i).isLocked
                                    for i in plug.getExistingArrayAttributeIndices()):
                raise RuntimeError(f"Locked pose attribute: {plug.name()}")
        for skin in skins.values():
            require_editable(skin.mnode())
            if skin.getPlug("bindPose").mplug().isLocked:
                raise RuntimeError(f"Locked bindPose: {skin.getFullName()}")

    def _merge_allocate_indices(self, rows, target_rows):
        """既存の疎な保存番号を保ち、未登録メンバーへ後続の番号を割り当てる。

        Args:
            rows (dict): 統合する保存行。
            target_rows (dict): 対象の既存保存行。

        Returns:
            dict: メンバー名から保存先の論理番号への対応。
        """
        used = set()
        for attr in self._POSE_ARRAYS:
            used.update(self.getPlug(attr).mplug().getExistingArrayAttributeIndices())
        next_index = max(used, default=-1) + 1
        indices = {member: row["index"] for member, row in target_rows.items()}
        for member in rows:
            if member not in indices:
                indices[member] = next_index
                next_index += 1
        return indices

    def _merge_write_rows(self, name, rows, target_rows, indices, current_pose):
        """メンバー・マトリクス・親情報を既存の順序でMayaの保存先へ書き込む。

        Args:
            name (str): 対象ポーズの名前。
            rows (dict): 統合する保存行。
            target_rows (dict): 対象の既存保存行。
            indices (dict): メンバー名から保存先の論理番号への対応。
            current_pose (bool): 既存メンバーも現在姿勢の行で更新するか。
        """
        for member, row in rows.items():
            index = indices[member]
            if member not in target_rows:
                cmds.connectAttr(member + ".message", f"{name}.members[{index}]")
            if not current_pose and member in target_rows:
                continue
            for attr in ("worldMatrix", "xformMatrix"):
                plug = self.getPlug(attr).mplug().elementByLogicalIndex(index)
                if plug.isDestination:
                    cmds.disconnectAttr(plug.source().name(), plug.name())
                self._merge_set_matrix(f"{name}.{attr}[{index}]", row[attr])
            cmds.setAttr(f"{name}.global[{index}]", row["global"])
            dest = self.getPlug("parents").mplug().elementByLogicalIndex(index)
            if dest.isDestination:
                cmds.disconnectAttr(dest.source().name(), dest.name())
            parent = row["parent"]
            if parent is None:
                src = name + ".world"
            elif row["externalParent"]:
                src = parent + ".message"
            else:
                src = f"{name}.members[{indices[parent]}]"
            cmds.connectAttr(src, dest.name())

    @staticmethod
    def _merge_set_matrix(destination, values):
        """完全なxformデータをcmdsの複合引数へ変換してUndo可能に設定する。

        Args:
            destination (str): 設定先のアトリビュート名。
            values (tuple): _merge_matrix_payload()の戻り値。
        """
        if values[0] == "xform":
            args = ["xform", values[1:4], values[4:7], values[7]]
            args.extend(values[i:i + 3] for i in range(8, 26, 3))
            args.extend((values[26:30], values[30:34], values[34:37], values[37]))
            cmds.setAttr(destination, *args, type="matrix")
        else:
            cmds.setAttr(destination, values, type="matrix")

    @staticmethod
    def _merge_matrix_payload(plug):
        """Mayaの保存表現からcmds.setAttr用の完全なmatrixデータを読む。

        16要素のマトリクスへ変換するとjointOrient・pivot等のxform情報が失われる。
        Maya生成のsetAttrを実行せず、数値・bool・xformマーカーだけを取り出す。

        Args:
            plug (om2.MPlug): worldMatrixまたはxformMatrixの要素。

        Returns:
            tuple: setAttrの引数に変換できる値の並び。
        """
        commands = plug.getSetAttrCmds(om2.MPlug.kAll, True)
        if len(commands) != 1:
            raise RuntimeError(f"Unsupported matrix data: {plug.name()}")
        tokens = shlex.split(commands[0].strip().rstrip(";"))
        if "-type" not in tokens:
            raise RuntimeError(f"Unsupported matrix data: {plug.name()}")
        start = tokens.index("-type")
        if tokens[start + 1] != "matrix":
            raise RuntimeError(f"Expected matrix data: {plug.name()}")
        values = []
        for token in tokens[start + 2:]:
            if token == "xform":
                values.append(token)
            elif token in ("yes", "no"):
                values.append(token == "yes")
            else:
                value = float(token)
                if not math.isfinite(value):
                    raise ValueError(f"Non-finite pose data: {plug.name()}")
                values.append(value)
        if values and values[0] == "xform":
            # rotationOrderはcmdsが整数を要求する。
            values[7] = int(values[7])
        return tuple(values)

    def _merge_snapshot(self):
        """メンバー・親の対応・完全な保存姿勢を取得し、不正な接続を拒否する。

        Returns:
            dict: メンバーの完全パスから保存行(index・parent・externalParent・
                worldMatrix・xformMatrix・global)への対応。
        """
        members = self.getPlug("members").mplug()
        indices = {}
        for index, source in self._member_sources():
            node = Node(source.node())
            if not node.isType("transform") or source.partialName(useLongNames=True) != "message":
                raise RuntimeError(f"Unsupported pose member: {members.name()}[{index}]")
            if om2.MFnDagNode(source.node()).isInstanced():
                raise RuntimeError(f"Instanced pose member: {node.getFullName()}")
            indices[index] = node.getFullName()
        if len(set(indices.values())) != len(indices):
            raise RuntimeError(f"Duplicate pose members: {self.getFullName()}")
        world = self.getPlug("world").mplug()
        rows = {}
        for index, member in indices.items():
            parent_plug = self.getPlug("parents").mplug().elementByLogicalIndex(index)
            if not parent_plug.isDestination:
                raise RuntimeError(f"Missing saved parent: {member}")
            source = parent_plug.source()
            external_parent = False
            if source == world:
                parent = None
            elif source.isElement and source.array() == members and source.logicalIndex() in indices:
                parent = indices[source.logicalIndex()]
            elif (source.node().hasFn(om2.MFn.kTransform)
                    and source.partialName(useLongNames=True) == "message"):
                parent = Node(source.node()).getFullName()
                external_parent = True
            else:
                raise RuntimeError(f"Unsupported saved parent: {member}")
            row = {"index": index, "parent": parent, "externalParent": external_parent}
            member_node = Node(member)
            for attr in ("worldMatrix", "xformMatrix", "global"):
                plug = self.getPlug(attr).mplug().elementByLogicalIndex(index)
                if plug.isDestination:
                    source = plug.source()
                    # Maya標準のbindPoseはjoint.bindPoseから保存ワールドマトリクスを受け取る。
                    expected = member_node.getPlug("bindPose").mplug() if member_node.isType("joint") else None
                    if attr != "worldMatrix" or source != expected or source.isDestination:
                        raise RuntimeError(f"Driven pose data: {plug.name()}")
                    plug = source
                row[attr] = plug.asBool() if attr == "global" else self._merge_matrix_payload(plug)
            rows[member] = row
        return rows

    @staticmethod
    def _merge_rows_equal(left, right):
        """同じメンバーの親・復元範囲・xformの内部情報まで比較する。

        Args:
            left (dict): 保存行。
            right (dict): 保存行。

        Returns:
            bool: 一致すればTrue。
        """
        if any(left[key] != right[key] for key in ("parent", "externalParent", "global")):
            return False
        for attr in ("worldMatrix", "xformMatrix"):
            a, b = left[attr], right[attr]
            if len(a) != len(b):
                return False
            for x, y in zip(a, b):
                if isinstance(x, str) or isinstance(y, str):
                    if x != y:
                        return False
                elif not math.isclose(x, y, rel_tol=0.0, abs_tol=1e-10):
                    return False
        return True

    def _merge_check_delete(self):
        """統合元の削除で失われる外部接続とロックを事前に検査する。"""
        require_editable(self.mnode())
        fn = om2.MFnDependencyNode(self.mnode())
        for plug in fn.getConnections():
            for other in plug.connectedTo(True, True):
                if other.node() == fn.object():
                    continue
                attr = om2.MFnAttribute(plug.attribute()).name
                other_attr = om2.MFnAttribute(other.attribute()).name
                if attr == "members" and plug.isDestination and other_attr == "message":
                    continue
                if (attr == "parents" and plug.isDestination and other_attr == "message"
                        and other.node().hasFn(om2.MFn.kTransform)):
                    continue
                if (attr == "worldMatrix" and plug.isDestination and other_attr == "bindPose"
                        and other.node().hasFn(om2.MFn.kJoint)):
                    continue
                if (attr == "message" and other_attr == "bindPose"
                        and other.node().hasFn(om2.MFn.kSkinClusterFilter)):
                    continue
                raise RuntimeError(f"Source pose has another connection: {plug.name()}")

    @staticmethod
    def _transform_names(members):
        """対象を有効なTransformの完全パスに揃える。

        Args:
            members (object): 単体または反復可能な対象。

        Returns:
            list[str]: 入力順・重複なしの完全パス。

        Raises:
            TypeError: 対応しない型の場合。
            ValueError: 空入力、または有効なTransform以外を含む場合。
        """
        names = []
        for name in Object._input_names(members, allow_plugs=False):
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
