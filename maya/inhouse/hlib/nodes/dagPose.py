"""DAG階層の保存姿勢とバインドポーズを扱う。"""

import math
import shlex

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace

from .._core.flags import flag_aliases
from .._core.getterAlias import _getter_alias, _is_alias
from .._core.space import world_space
from ..decorator import undoChunk, undoTransaction
from ..maths import Matrix
from .node import Node, Nodes


class DagPose(Node):
    """MayaのdagPose。姿勢の保存・復元と、保存済み行列の照会を提供する。

    バインドポーズも同じノード型で、isBindPose()で区別する。
    reset()はこのノードの保存姿勢を更新し、skinCluster.bindPreMatrixは変更しない。
    """

    @classmethod
    @undoChunk("hlibDagPoseCreate")
    def create(cls, members, name=None, bindPose=False, hierarchy=True):
        """現在の姿勢を新しいポーズに保存する。選択状態は参照しない。

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
    def fromSkinCluster(cls, skin_cluster):
        """skinClusterに接続されているバインドポーズを取得する。

        Args:
            skin_cluster (Node | str): 照会するskinCluster。

        Returns:
            DagPose | None: bindPoseアトリビュートに接続されたポーズ。未接続ならNone。

        Raises:
            ValueError: skinCluster以外を指定した場合。
            RuntimeError: 無効なノード、またはdagPose以外が接続されている場合。
        """
        from .node import Node as _InputNode
        skin = _InputNode._resolve_input(skin_cluster)
        if not skin.isValid():
            raise RuntimeError("Cannot access an invalid skinCluster")
        if not skin.isType("skinCluster"):
            raise ValueError("Expected a skinCluster")
        names = cmds.listConnections(skin.getFullName() + ".bindPose", source=True,
                                     destination=False) or []
        if not names:
            return None
        pose = Node(names[0])
        if not pose.isType("dagPose"):
            raise RuntimeError("skinCluster.bindPose is not connected to a dagPose")
        return pose

    def isBindPose(self):
        """バインドポーズとして保存されたノードならTrue。

        Returns:
            bool: バインドポーズとして保存されたノードならTrue。
        """
        self._pose_name()
        return bool(self.getPlug("bindPose").get())

    @_is_alias(isBindPose)
    def bindPose(self, *args, **kwargs):
        """isBindPoseへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isBindPose(*args, **kwargs)

    def getMemberIndices(self):
        """現在もメンバーが接続されている論理番号。欠番は保持する。

        Returns:
            list[int]: 現在もメンバーが接続されている論理番号。欠番は保持する。
        """
        name = self._pose_name()
        return [i for i in self.getPlug("members").mplug().getExistingArrayAttributeIndices()
                if cmds.listConnections(f"{name}.members[{i}]", source=True, destination=False)]

    def getMembers(self):
        """保存対象をmembers配列の論理番号順に返す。

        Returns:
            list[Node]: 保存対象をmembers配列の論理番号順に返す。
        """
        name = self._pose_name()
        return [Node(cmds.listConnections(f"{name}.members[{i}]", source=True,
                                          destination=False)[0]) for i in self.getMemberIndices()]

    def getMemberIndex(self, member):
        """指定メンバーの論理番号を返す。

        Args:
            member (Node | str): 保存対象のノード。
        Returns:
            int: members・worldMatrix・xformMatrixに共通の論理番号。
        Raises:
            ValueError: このポーズのメンバーでない場合。
        """
        from .node import Node as _InputNode
        node = _InputNode._resolve_input(member)
        for index, item in zip(self.getMemberIndices(), self.getMembers()):
            if item.getFullName() == node.getFullName():
                return index
        raise ValueError(f"Not a member of {self._pose_name()}: {member}")

    @flag_aliases(ws="worldSpace")
    def getMatrix(self, member, worldSpace=False):
        """現在のノード行列ではなく、保存時の行列を取得する。

        Args:
            member (Node | str): 保存対象のノード。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
        Returns:
            Matrix: 保存行列のコピー。
        Raises:
            ValueError: メンバーでない場合。
        """
        ws = world_space(worldSpace)
        index = self.getMemberIndex(member)
        attribute = "worldMatrix" if ws else "xformMatrix"
        return Matrix(self.getPlug(attribute)[index].get())

    def getNotAtPose(self):
        """MayaのatPose照会で保存姿勢と異なると判定されたメンバー。

        Returns:
            list[Node]: MayaのatPose照会で保存姿勢と異なると判定されたメンバー。
        """
        return [Node(name) for name in
                (cmds.dagPose(self._pose_name(), query=True, atPose=True) or [])]

    def isAtPose(self):
        """MayaのatPose照会で差異がない場合はTrue。

        Returns:
            bool: MayaのatPose照会で差異がない場合はTrue。
        """
        return not self.getNotAtPose()

    @_is_alias(isAtPose)
    def atPose(self, *args, **kwargs):
        """isAtPoseへ委譲するis省略の判定入口。

        Args:
            *args: 判定本体へ渡す位置引数。
            **kwargs: 判定本体へ渡すキーワード引数。

        Returns:
            object: 判定本体と同じ結果。
        """
        return self.isAtPose(*args, **kwargs)

    def getSkinClusters(self):
        """このポーズをbindPoseとして参照するskinCluster。

        Returns:
            list[SkinCluster]: このポーズをbindPoseとして参照するskinCluster。
        """
        plugs = cmds.listConnections(self._pose_name() + ".message", source=False,
                                     destination=True, type="skinCluster", plugs=True) or []
        names = [plug.rsplit(".", 1)[0] for plug in plugs if plug.endswith(".bindPose")]
        return [Node(name) for name in dict.fromkeys(names)]

    def merge(self, sources, *, currentPose=False, deleteSources=True):
        """他の保存ポーズを自身へ統合し、skinClusterの参照先も揃える。

        保存済みの姿勢・親情報が競合する場合は変更前に拒否する。
        currentPose=Trueは自身の既存メンバーを含む全対象を現在姿勢で保存する。
        ジョイントの現在姿勢・ウェイト・bindPreMatrixは変更しない。
        Maya標準コマンドによる1回のUndoに対応し、失敗時は巻き戻す。

        Args:
            sources (Node | str | Iterable[Node | str]): 統合元のdagPose。
                自身と重複指定は無視する。空入力は不可。
            currentPose (bool): 保存済み姿勢ではなく現在の姿勢・階層を保存する。
                復元に必要な親もMaya標準処理で含める。
            deleteSources (bool): 統合後に元ポーズを削除する。既定はTrue。
                メンバー・親情報とskinCluster.bindPose以外の接続があれば拒否する。

        Returns:
            DagPose: 自身。

        Raises:
            ValueError: 型・フラグ・保存情報の競合、通常ポーズとbindPoseの混在。
            RuntimeError: ロック・参照・インスタンス・不正な保存情報、編集失敗。
        """
        if type(currentPose) is not bool or type(deleteSources) is not bool:
            raise ValueError("currentPose and deleteSources must be bool")
        name, poses, sources = self._merge_collect_poses(sources)
        if not sources:
            return self
        rows, target_rows, skins = self._merge_collect_rows(poses, currentPose, deleteSources)
        self._merge_check_targets(skins)

        with undoTransaction("hlibDagPoseMerge"):
            if currentPose:
                # 一時的な通常ポーズなら既存bindPoseを再利用せず、現在姿勢の
                # xform内部情報（jointOrient等）もMaya自身が正しく保存する。
                temp = Node(cmds.dagPose(list(rows), save=True, selection=True))
                rows = temp._merge_snapshot()
            indices = self._merge_allocate_indices(rows, target_rows)
            self._merge_write_rows(name, rows, target_rows, indices, currentPose)
            if currentPose:
                cmds.delete(temp.getFullName())
            for skin in skins.values():
                cmds.connectAttr(name + ".message", skin.getFullName() + ".bindPose", force=True)
            if deleteSources:
                cmds.delete([pose.getFullName() for pose in sources])
        return self

    @flag_aliases(ws="worldSpace")
    @undoChunk("hlibDagPoseRestore")
    def restore(self, worldSpace=False):
        """保存した姿勢へ戻す。接続やロックの解除は行わない。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
        Returns:
            DagPose: 自身。
        Raises:
            RuntimeError: 無効なノード、またはMayaが復元を拒否した場合。
        """
        ws = world_space(worldSpace)
        cmds.dagPose(self._pose_name(), restore=True, g=ws)
        return self

    @undoChunk("hlibDagPoseReset")
    def reset(self, members=None):
        """保存姿勢を現在の姿勢へ更新する。ノードを保存姿勢へ戻す操作ではない。

        skinClusterの変形基準行列(bindPreMatrix)は更新しない。

        Args:
            members (Node | str | Iterable[Node | str] | None): 更新対象。Noneなら全メンバー。
        Returns:
            DagPose: 自身。
        Raises:
            ValueError: 明示した対象が空、またはメンバーでない場合。
            RuntimeError: Mayaが更新を拒否した場合。
        """
        name = self._pose_name()
        targets = self.getMembers() if members is None else members
        if members is None and not targets:
            return self
        names = self._transform_names(targets)
        for target in names:
            self.getMemberIndex(target)
        cmds.dagPose(names, reset=True, name=name)
        return self

    @undoChunk("hlibDagPoseAdd")
    def addMembers(self, *members):
        """TransformまたはJointを現在の姿勢で追加する。

        Args:
            members (Node | str | Iterable[Node | str]): 追加する対象。空は不可。
        Returns:
            DagPose: 自身。
        """
        cmds.dagPose(self._transform_names(members), addToPose=True, name=self._pose_name())
        return self

    @undoChunk("hlibDagPoseRemove")
    def removeMembers(self, *members):
        """メンバーをポーズから外す。シーンのノード自体は削除しない。

        残るメンバーの親として必要なノードはMayaによって保持される場合がある。

        Args:
            members (Node | str | Iterable[Node | str]): 除外する既存メンバー。空は不可。
        Returns:
            DagPose: 自身。
        Raises:
            ValueError: ポーズのメンバーでない対象が含まれる場合。
        """
        names = self._transform_names(members)
        for target in names:
            self.getMemberIndex(target)
        cmds.dagPose(names, remove=True, name=self._pose_name())
        return self

    @_getter_alias(getMemberIndices)
    def memberIndices(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getMemberIndices(*args, **kwargs)

    @_getter_alias(getMembers)
    def members(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getMembers(*args, **kwargs)

    @_getter_alias(getMemberIndex)
    def memberIndex(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getMemberIndex(*args, **kwargs)

    @_getter_alias(getMatrix)
    def matrix(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getMatrix(*args, **kwargs)

    @_getter_alias(getNotAtPose)
    def notAtPose(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getNotAtPose(*args, **kwargs)

    @_getter_alias(getSkinClusters)
    def skinClusters(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getSkinClusters(*args, **kwargs)

    def _merge_collect_poses(self, sources):
        """対象自身と統合元を入力順に解決し、同じポーズを一度だけ扱う。

        Args:
            sources (Iterable[DagPose]): 統合元のポーズ入力。

        Returns:
            tuple: 対象名、対象を先頭とするポーズ辞書、対象自身を除いた統合元。
        """
        name = self._pose_name()
        nodes = Nodes._resolve_inputs(sources)
        if not nodes:
            raise ValueError("At least one source pose is required")
        poses = {name: self}
        for value in nodes:
            node = Node._resolve_input(value)
            if not node.isType("dagPose"):
                raise ValueError("Expected a dagPose: " + node.getFullName())
            poses.setdefault(node.getFullName(), node)
        sources = [pose for key, pose in poses.items() if key != name]
        return name, poses, sources

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
        target_rows = None
        skins = {}
        for pose in poses.values():
            if pose.isBindPose() != self.isBindPose():
                raise ValueError("Cannot mix bind poses and ordinary poses")
            snapshot = pose._merge_snapshot()
            if pose is self:
                target_rows = snapshot
            for member, row in snapshot.items():
                if not current_pose and member in rows:
                    if not self._merge_rows_equal(rows[member], row):
                        raise ValueError("Conflicting saved pose: " + member)
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
        self._merge_check_editable(self)
        for attr in ("members", "parents", "worldMatrix", "xformMatrix", "global"):
            plug = self.getPlug(attr).mplug()
            if plug.isLocked or any(plug.elementByLogicalIndex(i).isLocked
                                    for i in plug.getExistingArrayAttributeIndices()):
                raise RuntimeError("Locked pose attribute: " + plug.name())
        for skin in skins.values():
            self._merge_check_editable(skin)
            if skin.getPlug("bindPose").mplug().isLocked:
                raise RuntimeError("Locked bindPose: " + skin.getFullName())

    def _merge_allocate_indices(self, rows, target_rows):
        """既存の疎な保存番号を保ち、未登録メンバーへ後続の番号を割り当てる。

        Args:
            rows (dict): 統合する保存行。
            target_rows (dict): 対象の既存保存行。

        Returns:
            dict: メンバー名から保存先の論理番号への対応。
        """
        used = set()
        for attr in ("members", "parents", "worldMatrix", "xformMatrix", "global"):
            used.update(self.getPlug(attr).mplug().getExistingArrayAttributeIndices())
        next_index = max(used, default=-1) + 1
        indices = {member: row["index"] for member, row in target_rows.items()}
        for member in rows:
            if member not in indices:
                indices[member] = next_index
                next_index += 1
        return indices

    def _merge_write_rows(self, name, rows, target_rows, indices, current_pose):
        """メンバー・行列・親情報を既存の順序でMayaの保存先へ書き込む。

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
            if current_pose or member not in target_rows:
                for attr in ("worldMatrix", "xformMatrix"):
                    plug = self.getPlug(attr)[index].mplug()
                    if plug.isDestination:
                        cmds.disconnectAttr(plug.source().name(), plug.name())
                    self._merge_set_matrix(f"{name}.{attr}[{index}]", row[attr])
                cmds.setAttr(f"{name}.global[{index}]", row["global"])
                dest = self.getPlug("parents")[index].mplug()
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
        """完全なxformデータをcmdsの複合引数へ変換してUndo可能に設定する。"""
        if values[0] == "xform":
            args = ["xform", values[1:4], values[4:7], values[7]]
            args.extend(values[i:i + 3] for i in range(8, 26, 3))
            args.extend((values[26:30], values[30:34], values[34:37], values[37]))
            cmds.setAttr(destination, *args, type="matrix")
        else:
            cmds.setAttr(destination, values, type="matrix")

    @staticmethod
    def _merge_check_editable(node):
        """参照とノードロックを変更前に拒否する。"""
        fn = om2.MFnDependencyNode(node.getPlug("message").mplug().node())
        if fn.isFromReferencedFile or fn.isLocked:
            raise RuntimeError("Referenced or locked node: " + node.getFullName())

    @staticmethod
    def _merge_matrix_payload(plug):
        """Mayaの保存表現からcmds.setAttr用の完全なmatrixデータを読む。

        16要素の行列へ変換するとjointOrient・pivot等のxform情報が失われる。
        Maya生成のsetAttrを実行せず、数値・bool・xformマーカーだけを取り出す。
        """
        commands = plug.getSetAttrCmds(om2.MPlug.kAll, True)
        if len(commands) != 1:
            raise RuntimeError("Unsupported matrix data: " + plug.name())
        tokens = shlex.split(commands[0].strip().rstrip(";"))
        start = tokens.index("-type")
        if tokens[start + 1] != "matrix":
            raise RuntimeError("Expected matrix data: " + plug.name())
        values = []
        for token in tokens[start + 2:]:
            if token == "xform":
                values.append(token)
            elif token in ("yes", "no"):
                values.append(token == "yes")
            else:
                value = float(token)
                if not math.isfinite(value):
                    raise ValueError("Non-finite pose data: " + plug.name())
                values.append(value)
        if values and values[0] == "xform":
            # rotationOrderはcmdsが整数を要求する。
            values[7] = int(values[7])
        return tuple(values)

    def _merge_snapshot(self):
        """OMでメンバー・親対応・完全な保存姿勢を取得し不正な接続を拒否する。"""
        members = self.getPlug("members").mplug()
        indices = {}
        for index in members.getExistingArrayAttributeIndices():
            plug = members.elementByLogicalIndex(index)
            if not plug.isDestination:
                continue
            source = plug.source()
            node = Node(source.node())
            if not node.isType("transform") or source.partialName(useLongNames=True) != "message":
                raise RuntimeError("Unsupported pose member: " + plug.name())
            if om2.MFnDagNode(source.node()).isInstanced():
                raise RuntimeError("Instanced pose member: " + node.getFullName())
            indices[index] = node.getFullName()
        if len(set(indices.values())) != len(indices):
            raise RuntimeError("Duplicate pose members: " + self.getFullName())
        rows = {}
        for index, member in indices.items():
            parent_plug = self.getPlug("parents")[index].mplug()
            if not parent_plug.isDestination:
                raise RuntimeError("Missing saved parent: " + member)
            source = parent_plug.source()
            external_parent = False
            if source == self.getPlug("world").mplug():
                parent = None
            elif source.isElement and source.array() == members and source.logicalIndex() in indices:
                parent = indices[source.logicalIndex()]
            elif source.node().hasFn(om2.MFn.kTransform) and source.partialName(useLongNames=True) == "message":
                parent = Node(source.node()).getFullName()
                external_parent = True
            else:
                raise RuntimeError("Unsupported saved parent: " + member)
            row = {"index": index, "parent": parent, "externalParent": external_parent}
            for attr in ("worldMatrix", "xformMatrix", "global"):
                plug = self.getPlug(attr)[index].mplug()
                if plug.isDestination:
                    source = plug.source()
                    # Maya標準のbindPoseはjoint.bindPoseから保存ワールド行列を受け取る。
                    expected = Node(member).getPlug("bindPose").mplug() if Node(member).isType("joint") else None
                    if attr != "worldMatrix" or source != expected or source.isDestination:
                        raise RuntimeError("Driven pose data: " + plug.name())
                    plug = source
                row[attr] = plug.asBool() if attr == "global" else self._merge_matrix_payload(plug)
            rows[member] = row
        return rows

    @staticmethod
    def _merge_rows_equal(left, right):
        """同じメンバーの親・復元範囲・xform内部情報まで比較する。"""
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
        """削除で失われる外部接続とロックを事前に検査する。"""
        self._merge_check_editable(self)
        fn = om2.MFnDependencyNode(self.getPlug("message").mplug().node())
        for plug in fn.getConnections():
            for other in plug.connectedTo(True, True):
                if other.node() == fn.object():
                    continue
                attr = om2.MFnAttribute(plug.attribute()).name
                other_attr = om2.MFnAttribute(other.attribute()).name
                if attr == "members" and plug.isDestination and other_attr == "message":
                    continue
                if attr == "parents" and plug.isDestination and other_attr == "message" and other.node().hasFn(om2.MFn.kTransform):
                    continue
                if attr == "worldMatrix" and plug.isDestination and other_attr == "bindPose" and other.node().hasFn(om2.MFn.kJoint):
                    continue
                if attr == "message" and other_attr == "bindPose" and other.node().hasFn(om2.MFn.kSkinClusterFilter):
                    continue
                raise RuntimeError("Source pose has another connection: " + plug.name())

    @staticmethod
    def _transform_names(members):
        """対象を有効なTransformの完全パスに揃える。空入力はValueError。

        Args:
            members: 所属または保存対象として扱うノード・コンポーネント。
        """
        from .._core.object import Object as _InputObject
        names = []
        for name in _InputObject._input_names(members):
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
        if not self.isValid():
            raise RuntimeError("Cannot access an invalid dagPose")
        return self.getFullName()
