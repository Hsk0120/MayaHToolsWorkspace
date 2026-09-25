"""joint ラッパーと joint コレクションを提供する。"""

from ..decorators._fast import fast_edit
from .._core.fast_write import set_attr

from ..decorators.undo import undo_chunk

import math

import maya.cmds as cmds
import maya.api.OpenMaya as om2

from .._core.registry import collection_export, node_wrapper
from .._core.collection import BulkCollection, bulk_api
from ..maths import EulerRotation, Matrix, Scale
from .transform import Transform


@node_wrapper("joint")
class Joint(Transform):
    """Maya joint ノード用の Transform ラッパー。

    Joint 固有の orientation、親子探索、skinCluster 連携を提供する。
    """

    @property
    def joint_orient(self):
        """jointOrient 属性を EulerRotation として取得する。

        Returns:
            EulerRotation: radian に変換した jointOrient 値。
        """
        values = self._compound_values("jointOrient", angle=True)
        return EulerRotation(*(math.radians(value) for value in values))

    def _rotation_order(self):
        """Maya の rotateOrder を API の回転順序へ変換する。

        Returns:
            int: rotateOrder に対応する Maya API 2.0 の MEulerRotation 定数。
        """
        order_index = int(self.plug("ro").get())
        return (
            om2.MEulerRotation.kXYZ,
            om2.MEulerRotation.kYZX,
            om2.MEulerRotation.kZXY,
            om2.MEulerRotation.kXZY,
            om2.MEulerRotation.kYXZ,
            om2.MEulerRotation.kZYX,
        )[order_index]

    def _joint_rotation_transfer_values(self, to_orient=False):
        """書込み可否を検証し、合成後の回転を現在の角度単位で返す。

        Args:
            to_orient (bool): TrueでjointOrient用XYZ、FalseでrotateOrderのrotate用。
        Returns:
            tuple[float, float, float] | None: 合成値。移送元が0ならNone。
        Raises:
            RuntimeError: 無効joint、ロック、入力接続、書込み不可の場合。
        """
        if not self.is_joint():
            raise RuntimeError("Cannot change orientation of an invalid joint")
        orient = self._compound_values("jointOrient", angle=True)
        rotate = self._compound_values("rotate", angle=True)
        if not any(rotate if to_orient else orient):
            return None
        name = self.full_name
        for attribute in ("rotate", "jointOrient"):
            for suffix in ("", "X", "Y", "Z"):
                plug = name + "." + attribute + suffix
                if (not cmds.getAttr(plug, settable=True)
                        or cmds.connectionInfo(plug, isDestination=True)):
                    raise RuntimeError("Attribute must be unlocked and have no input connection: " + plug)
        rotation = om2.MEulerRotation(
            *(math.radians(v) for v in rotate),
            self._rotation_order())
        # jointOrientはrotateOrderに関係なくXYZ。MayaのR * JOを合成する。
        orientation = om2.MEulerRotation(*(math.radians(v) for v in orient))
        combined = om2.MTransformationMatrix(rotation.asMatrix() * orientation.asMatrix())
        result = combined.rotation(asQuaternion=True).asEulerRotation()
        result.reorderIt(om2.MEulerRotation.kXYZ if to_orient else self._rotation_order())
        return tuple(om2.MAngle(v).asUnits(om2.MAngle.uiUnit()) for v in result)

    @fast_edit
    def joint_orient_to_rotate(self, *, fast=False):
        """現在の姿勢を保ち、jointOrientをrotateに合成して0にする。

        XYZの数値加算ではなく回転を合成する。rotateOrder、rotateAxis、移動、
        スケールは保持する。現在フレームの操作であり、アニメーションのベイクは
        行わない。rotate/jointOrientに入力接続やロックがある場合は変更前に拒否する。
        jointOrientが既に0なら何もしない。Undo一回で元へ戻せる。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Joint: 自身。
        Raises:
            RuntimeError: 無効joint、書込み不可、またはMayaの編集失敗。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if not self.is_joint():
            raise RuntimeError("Cannot change orientation of an invalid joint")
        Joints([self]).joint_orient_to_rotate()
        return self

    @fast_edit
    def freeze_rotation(self, *, fast=False):
        """姿勢を保ち、rotateをjointOrientへ合成してrotateを0にする。

        スキニング済みjointにも使用できる。jointの行列を保持するため、
        skinClusterのウェイト・bindPreMatrix・バインドポーズは変更しない。
        rotateAxis、rotateOrder、移動、スケールも保持する。現在フレームの操作で、
        アニメーションをベイクしない。rotate/jointOrientのロックや入力接続は拒否する。
        rotateが既に0なら何もしない。Undo一回で戻せる。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Joint: 自身。
        Raises:
            RuntimeError: 無効joint、書込み不可、またはMayaの編集失敗。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if not self.is_joint():
            raise RuntimeError("Cannot freeze rotation of an invalid joint")
        Joints([self]).freeze_rotation()
        return self

    def _rotation_quaternion(self, attribute):
        """Euler の Maya degrees 属性を API quaternion へ変換する。

        属性値は度であると仮定してラジアンへ変換する。

        Args:
            attribute (str): 度の3成分として読み取る回転属性名。

        Returns:
            om2.MQuaternion: ノードの rotateOrder で解釈した回転。
        """
        values = self._compound_values(attribute, angle=True)
        rotation = om2.MEulerRotation(*(math.radians(value) for value in values), self._rotation_order())
        return rotation.asQuaternion()

    def _remove_segment_scale_compensation(self, matrix):
        """ssc と inverseScale が適用された後の行列から補正前の値を戻す。

        Args:
            matrix (Matrix): スケール補正を取り除く対象行列。

        Returns:
            Matrix: ssc が無効なら入力そのもの。有効なら inverseScale の逆数からなる行列を右から乗じた新しい行列。

        Raises:
            ValueError: ssc が有効で inverseScale の成分の絶対値が 1e-12 未満の場合。
        """
        if not self.plug("ssc").get():
            return matrix
        inverse_scale = self._compound_values("inverseScale")
        if any(abs(value) < 1e-12 for value in inverse_scale):
            raise ValueError("inverseScale components must be non-zero when segmentScaleCompensate is enabled")
        compensation = Matrix(scale=tuple(1.0 / value for value in inverse_scale))
        return matrix * compensation

    def _apply_local_matrix(self, matrix):
        """jointOrient と rotateAxis を保持して local 行列を適用する。

        jointOrient と rotateAxis を回転から除き、rotateOrder に並べ替えて書き込む。角度の読み書きは Maya の角度単位が度であることを前提とする。

        Args:
            matrix (Matrix): 適用するローカル行列。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: inverseScale がゼロに近い、または行列を分解できない場合。
            RuntimeError: Maya が属性の書き込みを拒否した場合。
        """
        matrix = self._remove_segment_scale_compensation(matrix)
        target = om2.MTransformationMatrix(matrix.to_mmatrix())
        target_quaternion = target.rotation(asQuaternion=True)
        rotate_axis = self._rotation_quaternion("rotateAxis")
        joint_orient = self._rotation_quaternion("jointOrient")
        rotate_quaternion = rotate_axis.conjugate() * target_quaternion * joint_orient.conjugate()
        rotation = om2.MEulerRotation()
        rotation.setValue(rotate_quaternion)
        rotation.reorderIt(self._rotation_order())

        name = self.full_name
        set_attr(f"{name}.translate", *matrix.translate)
        set_attr(f"{name}.rotate", *(math.degrees(component) for component in rotation))
        set_attr(f"{name}.scale", *matrix.scale)
        set_attr(f"{name}.shear", *matrix.shear)

    @property
    def orientation(self):
        """joint の orientation 成分を取得する。

        Returns:
            EulerRotation: 現在は ``joint_orient`` と同じ値。
        """
        return self.joint_orient

    @property
    def inverse_scale(self):
        """inverseScale 属性を意味付き Scale として取得する。

        Returns:
            Scale: joint の inverseScale 値。
        """
        return Scale(*self._compound_values("inverseScale"))

    def _compound_values(self, attribute, angle=False):
        """compound 属性を 3 要素の tuple として取得する。

        Args:
            attribute (str): 読み取る複合属性名。
            angle (bool): True の場合、各子を角度属性として度数法の値で取得する
                (``cmds.getAttr`` が角度属性を現在の角度単位で返すのに合わせる)。
                False の場合は単位変換のない生の double として取得する。

        Returns:
            tuple: 属性値のタプル。無効なノードでは (0.0, 0.0, 0.0)。有効時は要素数を検査しない。
        """
        if not self.is_valid():
            return (0.0, 0.0, 0.0)
        plug = om2.MFnDependencyNode(self._mobject).findPlug(attribute, False)
        if angle:
            return tuple(plug.child(index).asMAngle().asDegrees() for index in range(3))
        return tuple(plug.child(index).asDouble() for index in range(3))

    def parent(self):
        """親 joint の名前を取得する。

        Returns:
            str | None: 親 joint 名。親が joint でない場合は ``None``。
        """
        if not self.is_valid():
            return None
        parent = self.parent_node()
        if parent is None or not parent.is_valid():
            return None
        if not parent.mobject().hasFn(om2.MFn.kJoint):
            return None
        return parent.name()

    def children(self):
        """直接の子 joint 名を取得する。

        Returns:
            list[str]: 子 joint 名のリスト。
        """
        if not self.is_valid():
            return []
        return [
            child.name()
            for child in self.child_nodes()
            if child.mobject().hasFn(om2.MFn.kJoint)
        ]

    def depth(self):
        """joint 階層内の深さを取得する。

        Returns:
            int: root joint を 0 とする階層深度。
        """
        depth = 0
        current_joint = self.parent()
        while current_joint:
            depth += 1
            current_joint = Joint(current_joint).parent()
        return depth

    def is_joint(self):
        """ラップ対象が joint か判定する。

        Returns:
            bool: 有効な joint の場合は ``True``。
        """
        return self.is_valid() and self.mobject().hasFn(om2.MFn.kJoint)

    def delete(self):
        """祖先influenceへウェイトを移送し、このjointを削除する。

        Joints.delete()と同じ処理を使う。同じskinClusterの最も近い祖先
        influenceがある場合だけ加算し、なければMaya標準の削除に任せる。
        未スキニングjointも削除する。子Transformは直接の親へ、親がなければ
        ワールドへ移す。全体は一回のUndoにまとまり、途中失敗は例外で通知する。
        完了済みの変更は自動ロールバックしない。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 無効なjoint、ウェイト移送・再親付け・削除の失敗。
        """
        if not self.is_joint():
            raise RuntimeError("Cannot delete an invalid joint")
        Joints([self]).delete()

    def skin_clusters(self):
        """この joint に接続する skinCluster を取得する。

        Returns:
            list[SkinCluster]: 重複を除いた skinCluster ラッパー。
        """
        from .skinCluster import SkinCluster

        if not self.is_valid():
            return []
        seen = set()
        result = []
        for plug in self.connections(type="skinCluster"):
            node = plug.node
            if node.uuid in seen:
                continue
            seen.add(node.uuid)
            result.append(SkinCluster(node.mobject()))
        return result

    @undo_chunk("hlibJointRemoveInfluence")
    def remove_influence(self, skin_cluster=None):
        """祖先へウェイトを移しinfluence登録を外す。joint自体は残す。

        Args:
            skin_cluster (SkinCluster | str | None): 対象。Noneは接続する全skinCluster。
        Returns:
            Joint: 自身。未スキニングで対象省略の場合は何もしない。
        Raises:
            ValueError: 未登録の対象、または最後の一つのinfluenceの場合。
            RuntimeError: 無効joint、レイヤー、移送・削除失敗。

        祖先influenceがなければMaya標準の再配分に任せる。全対象の削除可否を
        事前検証する。途中失敗は例外で停止し、完了済み操作は一回のUndoで戻せる。
        """
        from .skinCluster import SkinCluster
        if not self.is_joint():
            raise RuntimeError("Cannot remove an invalid joint influence")
        skins = self.skin_clusters() if skin_cluster is None else [skin_cluster if isinstance(skin_cluster, SkinCluster) else SkinCluster(skin_cluster)]
        for skin in skins:
            skin._influence_removal_target(self)
        for skin in skins:
            skin.remove_influence(self)
        return self

    def transfer_target(self, skin):
        """ウェイト移送先となる最も近い親 influence を探索する。

        Args:
            skin (SkinCluster): influence の有無を調べる skinCluster。

        Returns:
            str | None: 移送先の親 joint 名。見つからない場合は ``None``。
        """
        ancestor = self.parent()
        while ancestor:
            if skin.has_influence(ancestor):
                return ancestor
            ancestor = Joint(ancestor).parent()
        return None

    @undo_chunk("hlib.nodes.joint.reparent_children")
    def reparent_children(self, parent_joint):
        """子 joint を指定した親 joint へ付け替える。

        Args:
            parent_joint (str): 直接の子 joint を付け替える親ノード名。

        Returns:
            None: 値を返さない。
        """
        for child_joint in self.children():
            cmds.parent(child_joint, parent_joint)

    @staticmethod
    def _unique_ordered(items):
        """順序を保ったまま重複要素を除外する。

        Args:
            items (Iterable[Hashable]): 重複を除去するハッシュ可能な要素。

        Returns:
            list: 最初の出現順を維持した要素リスト。
        """
        seen = set()
        unique_items = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            unique_items.append(item)
        return unique_items

    def chain_from_here(self, to=None):
        """自身を起点とする joint チェーンを順に取得する。

        Args:
            to (Joint | str | None): チェーンの終端 joint。指定した場合は自身から
                その joint までの経路を辿る（子孫でなければならない）。省略時は、
                子 joint がちょうど1つの間だけ辿り、分岐（子が0または2つ以上）に
                達したところで止める。

        Returns:
            list[Joint]: 自身から to まで、または最初の分岐点までの joint。
                自身を含む。

        Raises:
            RuntimeError: 自身が無効な場合。
            ValueError: to が自身の子孫でない場合。
        """
        if not self.is_valid():
            raise RuntimeError("Cannot build a chain from an invalid joint")
        if to is None:
            chain = [self]
            current = self
            while True:
                children = current.children()
                if len(children) != 1:
                    return chain
                current = Joint(children[0])
                chain.append(current)
        target = to if isinstance(to, Joint) else Joint(to)
        if not self.is_ancestor_of(target):
            raise ValueError("to must be a descendant of this joint")
        chain = [self]
        current = self
        while current.uuid != target.uuid:
            next_joint = next(
                (
                    Joint(name) for name in current.children()
                    if Joint(name).uuid == target.uuid or Joint(name).is_ancestor_of(target)
                ),
                None,
            )
            if next_joint is None:
                raise ValueError("to must be a descendant of this joint")
            chain.append(next_joint)
            current = next_joint
        return chain

    def ik_handles(self):
        """自身を start joint とする IK ハンドルを取得する。

        自身が IK チェーンの途中や末端の joint である場合は対象にならない。
        Maya は IK ハンドルの ``startJoint`` への接続を通じてのみ joint から
        IK ハンドルを解決できるため。

        Returns:
            list[IkHandle]: 自身を start joint とする IkHandle。無ければ空リスト。
        """
        from .ikHandle import IkHandle

        if not self.is_valid():
            return []
        seen = set()
        result = []
        for plug in self.connections(type="ikHandle"):
            node = plug.node
            if node.uuid in seen:
                continue
            seen.add(node.uuid)
            result.append(IkHandle(node.mobject()))
        return result

    def __eq__(self, other):
        """UUID を基準に別の Joint と同一か判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool | types.NotImplementedType: Joint 同士は UUID の一致。相手が Joint でなければ NotImplemented。両方が無効で UUID が None なら一致する。
        """
        if not isinstance(other, Joint):
            return NotImplemented
        return self.uuid == other.uuid

    def __hash__(self):
        """UUID を使ったハッシュ値を返す。

        Returns:
            int: 現在の UUID のハッシュ。無効な場合は None のハッシュ。
        """
        return hash(self.uuid)


@collection_export()
@bulk_api(Joint)
class Joints(BulkCollection):
    """UUID で重複を除いた Joint ラッパーのコレクション。"""

    def __init__(self, names=()):
        """joint 名または Joint のシーケンスから重複なしコレクションを作成する。

        Args:
            names (Iterable[str | Joint]): ノード名または Joint。UUID の重複と有効な joint でないラッパーを除外する。

        Returns:
            None: 値を返さない。
        """
        self._items = []
        seen = set()
        for item in names:
            joint = item if isinstance(item, Joint) else Joint(item)
            if not joint.is_joint() or joint.uuid in seen:
                continue
            seen.add(joint.uuid)
            self._items.append(joint)

    @property
    def names(self):
        """コレクション内の joint 名を取得する。

        Returns:
            list[str]: joint 名のリスト。
        """
        return [joint.name() for joint in self._items]

    def sorted_by_depth(self):
        """深い joint から順に並べた新しいコレクションを返す。

        Returns:
            Joints: 子 joint を先に処理できる深さ順コレクション。
        """
        return Joints(sorted(self._items, key=lambda joint: joint.depth(), reverse=True))

    @fast_edit
    @undo_chunk("hlibJointsJointOrientToRotate")
    def joint_orient_to_rotate(self, *, fast=False):
        """全jointの姿勢を保ち、jointOrientをrotateへ合成して0にする。

        全対象の値と書込み可否を変更前に検証する。回転順序・角度単位に対応し、
        jointOrientが0の対象は変更しない。全体を一回のUndoで戻せる。
        途中でMayaの編集が失敗した場合は例外で停止し、完了済み変更はUndoで戻せる。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Joints: 自身。
        Raises:
            RuntimeError: 無効joint、ロック・入力接続・書込み不可、編集失敗。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        plans = [(joint, joint._joint_rotation_transfer_values()) for joint in self]
        for joint, values in plans:
            if values is not None:
                set_attr(joint.full_name + ".jointOrient", 0, 0, 0)
                set_attr(joint.full_name + ".rotate", *values)
        return self

    @fast_edit
    @undo_chunk("hlibJointsFreezeRotation")
    def freeze_rotation(self, *, fast=False):
        """全jointのrotateをjointOrientへ移し、姿勢を保ってrotateを0にする。

        スキニング済みでも実行でき、ウェイト・bindPreMatrix・バインドポーズを
        変更しない。全対象を事前検証し、全体を一回のUndoで戻せる。
        移動・スケールのフリーズやアニメーションのベイクは行わない。
        途中の編集失敗は例外で停止し、完了済み変更はUndoで戻せる。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Joints: 自身。
        Raises:
            RuntimeError: 無効joint、ロック・入力接続・書込み不可、編集失敗。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        plans = [(joint, joint._joint_rotation_transfer_values(to_orient=True)) for joint in self]
        for joint, values in plans:
            if values is not None:
                set_attr(joint.full_name + ".jointOrient", *values)
                set_attr(joint.full_name + ".rotate", 0, 0, 0)
        return self

    def skin_clusters(self):
        """全 joint に関連する skinCluster を取得する。

        Returns:
            SkinClusters: 重複を除いた skinCluster コレクション。
        """
        from .skinCluster import SkinClusters

        skin_clusters = []
        seen = set()
        for joint in self._items:
            for skin in joint.skin_clusters():
                if skin.uuid in seen:
                    continue
                seen.add(skin.uuid)
                skin_clusters.append(skin)
        return SkinClusters(skin_clusters)

    def delete(self):
        """ウェイト移送後にコレクション内の joint を削除する。

        未スキニングjointも削除する。子Transform（jointを含む）は親へ移し、
        親がない場合はワールドへ移す。同じskinClusterの祖先influenceがあれば加算し、
        移送先がない場合のウェイト処理はMaya標準のcmds.deleteに任せる。
        途中の失敗は例外で停止し、完了済み変更は自動ロールバックしない。全体はUndoに対応。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: ウェイト移送・子の再親付け・削除ができない場合。
        """
        self.skin_clusters().remove_joints(self)

    def __iter__(self):
        """保持している Joint を順に反復する。

        Returns:
            Iterator[Joint]: 保存順に Joint を返すイテレータ。
        """
        return iter(self._items)
