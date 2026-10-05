"""joint ラッパーと joint コレクションを提供する。"""

import math

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .._core.collection import bulk_api
from .._core.fastWrite import set_attr
from .._core.registry import collection_export, node_wrapper
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from ..maths import EulerRotation, Matrix, Scale
from .transform import Transform, Transforms, _closest_euler


@node_wrapper("joint")
class Joint(Transform):
    """Maya joint ノード用の Transform ラッパー。

    Joint 固有の orientation、親子探索、skinCluster 連携を提供する。
    """

    def getSegmentScaleCompensate(self):
        """親のスケール補正が有効か照会する。

        Returns:
            bool: segmentScaleCompensateの現在値。
        """
        return bool(self.plug("segmentScaleCompensate").get())

    @fast_edit
    @undoChunk("hlibJointSetSegmentScaleCompensate")
    def setSegmentScaleCompensate(self, state, *, fast=False):
        """親のスケール補正を切り替える。

        segmentScaleCompensateだけを変更する。inverseScaleの接続やバインド情報は
        変更しないため、親のスケールによっては姿勢やスキンの見た目が変わる。

        Args:
            state (bool): Trueで補正を有効、Falseで無効にする。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Joint: 自身。

        Raises:
            TypeError: stateまたはfastがboolでない場合。
            RuntimeError: ロックや入力接続などで編集できない場合。
        """
        if not isinstance(state, bool):
            raise TypeError("state must be a bool")
        self.plug("segmentScaleCompensate").set(state)
        return self

    def getJointOrient(self):
        """jointOrient アトリビュートを EulerRotation として取得する。

        Returns:
            EulerRotation: radian に変換した jointOrient 値。
        """
        values = self._compound_values("jointOrient", angle=True)
        return EulerRotation(*(math.radians(value) for value in values))

    @fast_edit
    @undoChunk("hlibJointsJointOrientToRotate")
    def jointOrientToRotate(self, *, fast=False):
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
        if not self.isJoint():
            raise RuntimeError("Cannot change orientation of an invalid joint")
        self._apply_rotation_transfer(self._joint_rotation_transfer_values())
        return self

    @fast_edit
    @undoChunk("hlibJointsFreezeRotation")
    def freezeRotation(self, *, fast=False):
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
        if not self.isJoint():
            raise RuntimeError("Cannot freeze rotation of an invalid joint")
        self._apply_rotation_transfer(self._joint_rotation_transfer_values(to_orient=True), to_orient=True)
        return self

    @undoChunk("hlibJointConnectInverseScale")
    def connectInverseScale(self, source=None, force=False):
        """Transformのscaleを自身のinverseScaleへ接続する。

        Args:
            source (Transform | str | None): 接続元。省略時は直上の親Transform。
                親がない場合は変更しない。
            force (bool): 既存入力を置換する。Plug.connectと同様、接続先がロック中なら
                一時解除して接続後にロックを戻す。既定False。

        Returns:
            Joint: 自身。同じ接続が既にある場合は変更しない。

        Raises:
            TypeError: sourceがTransformでない、またはforceがboolでない場合。
            ValueError: 自身を接続元に指定した場合。
            RuntimeError: 対象が無効、またはMayaが接続を拒否した場合。

        segmentScaleCompensateの値は変更しない。接続により姿勢が変わる場合がある。
        Jointsでは省略時に各joint自身の親を使用し、全体を一回のUndoで戻せる。
        """
        from ..nodes.node import Node as _InputNode
        if not isinstance(force, bool):
            raise TypeError("force must be a bool")
        if not self.isValid():
            raise RuntimeError("Cannot connect inverseScale on an invalid joint")
        source = self.parent() if source is None else _InputNode._resolve_input(source)
        if source is None:
            return self
        if not isinstance(source, Transform):
            raise TypeError("source must be a Transform")
        if source == self:
            raise ValueError("inverseScale cannot use the joint itself as its source")
        origin = source.plug("scale")
        target = self.plug("inverseScale")
        if not cmds.isConnected(origin.fullName(), target.fullName()):
            origin.connectTo(target, force=force)
        return self

    @undoChunk("hlibJointDisconnectInverseScale")
    def disconnectInverseScale(self):
        """inverseScaleと各軸の入力接続だけを切断する。

        出力接続・segmentScaleCompensateは変更しない。値のリセットや姿勢補償は
        行わず、切断後の値はMayaの切断動作に従う。接続がなければ何もしない。

        Returns:
            Joint: 自身。Jointsからも一括実行でき、通常Undoに対応する。

        Raises:
            RuntimeError: 対象が無効、ロックなどでMayaが切断を拒否した場合。
        """
        for name in ("inverseScale", "inverseScaleX", "inverseScaleY", "inverseScaleZ"):
            target = self.plug(name)
            origin = target.sourceWithConversion()
            if origin is not None:
                target.disconnect(origin)
        return self

    def getRadius(self):
        """ジョイント個別の表示半径を取得する。

        Returns:
            float: radiusアトリビュート値。Maya全体のjointDisplayScaleとは別の値。
        """
        return float(self.plug("radius").get())

    @fast_edit
    @undoChunk("hlibJointSetRadius")
    def setRadius(self, value, *, fast=False):
        """ジョイント個別の表示半径を変更する。骨の長さ・scaleは変更しない。

        Args:
            value (float): 0以上の有限値。最終表示はMaya全体の表示倍率にも依存する。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            Joint: 自身。Jointsでは各要素に同じ値を設定する。

        Raises:
            ValueError: valueが負数・非有限値の場合。
            TypeError: valueが数値でない、またはfastがboolでない場合。
            RuntimeError: Mayaが編集を拒否した場合。
        """
        import numbers
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise TypeError("radius must be a number")
        value = float(value)
        if not math.isfinite(value) or value < 0:
            raise ValueError("radius must be finite and non-negative")
        self.plug("radius").set(value)
        return self

    def getInverseScale(self):
        """inverseScale アトリビュートを意味付き Scale として取得する。

        Returns:
            Scale: joint の inverseScale 値。
        """
        return Scale(*self._compound_values("inverseScale"))

    def parentJointName(self):
        """親 joint の名前を取得する。

        Returns:
            str | None: 親 joint 名。親が joint でない場合は ``None``。
        """
        if not self.isValid():
            return None
        parent = self.parent()
        if parent is None or not parent.isValid():
            return None
        if not parent.mnode().hasFn(om2.MFn.kJoint):
            return None
        return parent.name()

    def childJointNames(self):
        """直接の子 joint 名を取得する。

        Returns:
            list[str]: 子 joint 名のリスト。
        """
        if not self.isValid():
            return []
        return [
            child.name()
            for child in self.childNodes()
            if child.mnode().hasFn(om2.MFn.kJoint)
        ]

    def depth(self):
        """joint 階層内の深さを取得する。

        Returns:
            int: root joint を 0 とする階層深度。
        """
        depth = 0
        current_joint = self.parentJointName()
        while current_joint:
            depth += 1
            current_joint = Joint(current_joint).parentJointName()
        return depth

    def isJoint(self):
        """ラップ対象が joint か判定する。

        Returns:
            bool: 有効な joint の場合は ``True``。
        """
        return self.isValid() and self.mnode().hasFn(om2.MFn.kJoint)

    def delete(self):
        """祖先influenceへウェイトを移送し、このjointを削除する。

        Joints.delete()と同じ処理を使う。同じskinClusterの最も近い祖先
        influenceがある場合だけ加算し、なければMaya標準の削除に任せる。
        同じjointの複数インスタンスパスはノード単位で一度だけ処理する。
        未スキニングjointも削除する。子Transformは直接の親へ、親がなければ
        ワールドへ移す。全体は一回のUndoにまとまり、途中失敗は例外で通知する。
        完了済みの変更は自動ロールバックしない。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 無効なjoint、ウェイト移送・再親付け・削除の失敗。
        """
        if not self.isJoint():
            raise RuntimeError("Cannot delete an invalid joint")
        Joints([self]).delete()

    def skinClusters(self):
        """この joint に接続する skinCluster を取得する。

        Returns:
            list[SkinCluster]: 重複を除いた skinCluster ラッパー。
        """
        from .skinCluster import SkinCluster

        if not self.isValid():
            return []
        seen = set()
        result = []
        for plug in self.connections(type="skinCluster"):
            node = plug.node()
            if node.uuid() in seen:
                continue
            seen.add(node.uuid())
            result.append(SkinCluster(node.mnode()))
        return result

    @undoChunk("hlibJointRemoveInfluence")
    def removeInfluence(self, skin_cluster=None, *, transfer_to_parent=True):
        """ウェイトの再配分方法を選んでinfluence登録を外す。joint自体は残す。

        Args:
            skin_cluster (SkinCluster | str | None): 対象。Noneは接続する全skinCluster。
            transfer_to_parent (bool): Trueは祖先へ移送、FalseはMaya標準の再配分。
        Returns:
            Joint: 自身。未スキニングで対象省略の場合は何もしない。
        Raises:
            TypeError: transfer_to_parentがboolでない場合。
            ValueError: 未登録の対象、または最後の一つのinfluenceの場合。
            RuntimeError: 無効joint、レイヤー、移送・削除失敗。

        祖先influenceがなければMaya標準の再配分に任せる。全対象の削除可否を
        事前検証する。途中失敗は例外で停止し、完了済み操作は一回のUndoで戻せる。
        """
        from .skinCluster import SkinCluster
        if not self.isJoint():
            raise RuntimeError("Cannot remove an invalid joint influence")
        if not isinstance(transfer_to_parent, bool):
            raise TypeError("transfer_to_parent must be a bool")
        skins = self.skinClusters() if skin_cluster is None else [skin_cluster if isinstance(skin_cluster, SkinCluster) else SkinCluster(skin_cluster)]
        for skin in skins:
            skin._influence_removal_target(self, transfer_to_parent=transfer_to_parent)
        for skin in skins:
            skin.removeInfluence(self, transfer_to_parent=transfer_to_parent)
        return self

    def transferTarget(self, skin):
        """ウェイト移送先となる最も近い親 influence を探索する。

        Args:
            skin (SkinCluster): influence の有無を調べる skinCluster。

        Returns:
            str | None: 移送先の親 joint 名。見つからない場合は ``None``。
        """
        ancestor = self.parentJointName()
        while ancestor:
            if skin.hasInfluence(ancestor):
                return ancestor
            ancestor = Joint(ancestor).parentJointName()
        return None

    @undoChunk("hlib.nodes.joint.reparentChildren")
    def reparentChildren(self, parent_joint):
        """子 joint を指定した親 joint へ付け替える。

        Args:
            parent_joint (str): 直接の子 joint を付け替える親ノード名。

        Returns:
            None: 値を返さない。
        """
        for child_joint in self.childJointNames():
            cmds.parent(child_joint, parent_joint)

    def chainFromHere(self, to=None):
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
        if not self.isValid():
            raise RuntimeError("Cannot build a chain from an invalid joint")
        if to is None:
            chain = [self]
            current = self
            while True:
                children = current.childJointNames()
                if len(children) != 1:
                    return chain
                current = Joint(children[0])
                chain.append(current)
        target = to if isinstance(to, Joint) else Joint(to)
        if not self.isAncestorOf(target):
            raise ValueError("to must be a descendant of this joint")
        chain = [self]
        current = self
        while current.uuid() != target.uuid():
            next_joint = next(
                (
                    Joint(name) for name in current.childJointNames()
                    if Joint(name).uuid() == target.uuid() or Joint(name).isAncestorOf(target)
                ),
                None,
            )
            if next_joint is None:
                raise ValueError("to must be a descendant of this joint")
            chain.append(next_joint)
            current = next_joint
        return chain

    def ikHandles(self):
        """自身を start joint とする IK ハンドルを取得する。

        自身が IK チェーンの途中や末端の joint である場合は対象にならない。
        Maya は IK ハンドルの ``startJoint`` への接続を通じてのみ joint から
        IK ハンドルを解決できるため。

        Returns:
            list[IkHandle]: 自身を start joint とする IkHandle。無ければ空リスト。
        """
        from .ikHandle import IkHandle

        if not self.isValid():
            return []
        seen = set()
        result = []
        for plug in self.connections(type="ikHandle"):
            node = plug.node()
            if node.uuid() in seen:
                continue
            seen.add(node.uuid())
            result.append(IkHandle(node.mnode()))
        return result

    def _rotation_order(self):
        """Maya の rotateOrder を API の回転順序へ変換する。

        rotateOrder の番号(0=xyz〜5=zyx)は MEulerRotation.kXYZ〜kZYX と同じ並び。

        Returns:
            int: rotateOrder に対応する Maya API 2.0 の MEulerRotation 定数。
        """
        return self._rotate_order()

    def _joint_rotation_transfer_values(self, to_orient=False):
        """書込み可否を検証し、合成後の回転を現在の角度単位で返す。

        Args:
            to_orient (bool): TrueでjointOrient用XYZ、FalseでrotateOrderのrotate用。
        Returns:
            tuple[float, float, float] | None: 合成値。移送元が0ならNone。
        Raises:
            RuntimeError: 無効joint、ロック、入力接続、書込み不可の場合。
        """
        if not self.isJoint():
            raise RuntimeError("Cannot change orientation of an invalid joint")
        orient = self._compound_values("jointOrient", angle=True)
        rotate = self._compound_values("rotate", angle=True)
        if not any(rotate if to_orient else orient):
            return None
        name = self.fullName()
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

    def _apply_rotation_transfer(self, values, to_orient=False):
        """検証済みの回転移送値を適用する。Undo/fastは呼出元の範囲に従う。

        Args:
            values (tuple | None): 現在のUI角度単位の3成分。Noneなら更新しない。
            to_orient (bool): TrueならjointOrientへ移しrotateを0にする。
        """
        if values is None:
            return
        set_attr(self.fullName() + ".jointOrient", *(values if to_orient else (0, 0, 0)))
        set_attr(self.fullName() + ".rotate", *((0, 0, 0) if to_orient else values))

    def _rotation_quaternion(self, attribute):
        """jointOrient / rotateAxis を API quaternion へ変換する。

        MAngle から明示的に度数法で取得し、ラジアンへ変換する。現在の UI 角度単位に依存しない。
        Maya の jointOrient と
        rotateAxis は rotateOrder にかかわらず常に XYZ 順序で評価されるため、
        XYZ として解釈する。

        Args:
            attribute (str): 度の3成分として読み取る回転アトリビュート名(jointOrient / rotateAxis)。

        Returns:
            om2.MQuaternion: XYZ 順序で解釈した回転。
        """
        values = self._compound_values(attribute, angle=True)
        rotation = om2.MEulerRotation(*(math.radians(value) for value in values))
        return rotation.asQuaternion()

    def _remove_segment_scale_compensation(self, matrix):
        """ssc と inverseScale が適用された後の行列から補正前の値を戻す。

        Maya の joint の行列は S · RA · R · JO · IS · T(IS は inverseScale の逆数の
        対角行列)なので、3x3 部分へ inverseScale の対角行列を右から掛けて IS を打ち消す。
        平行移動は IS の後に適用されるため変えない。

        Args:
            matrix (Matrix): スケール補正を取り除く対象行列。

        Returns:
            Matrix: ssc が無効なら入力そのもの。有効なら IS を打ち消した新しい行列。

        Raises:
            ValueError: ssc が有効で inverseScale の成分の絶対値が 1e-12 未満の場合。
        """
        if not self.plug("ssc").get():
            return matrix
        inverse_scale = self._compound_values("inverseScale")
        if any(abs(value) < 1e-12 for value in inverse_scale):
            raise ValueError("inverseScale components must be non-zero when segmentScaleCompensate is enabled")
        result = matrix * Matrix(scale=inverse_scale)
        result.translate = matrix.translate
        return result

    def _rotate_reference(self, reference):
        """:meth:`getRotation` が Euler の解を選ぶ基準を返す。

        joint の getRotation は jointOrient と rotateAxis を含む回転で rotate チャンネルとは
        別の回転なので、チャンネル値ではなく 0 回転(ノードの rotateOrder)を基準にする。

        Args:
            reference (om2.MEulerRotation): 現在の rotate チャンネル値(順序だけを使う)。

        Returns:
            om2.MEulerRotation: 0 回転。順序はノードの rotateOrder。
        """
        return om2.MEulerRotation(0.0, 0.0, 0.0, reference.order)

    def _channel_rotation(self, quaternion, reference):
        """ローカル行列の回転から jointOrient と rotateAxis を除き、rotate の値へ変換する。

        Maya の joint の回転は rotateAxis、rotate、jointOrient の順に適用されるため、
        rotate = rotateAxis⁻¹ · 行列の回転 · jointOrient⁻¹(om2 の四元数の積の順序)。

        Args:
            quaternion (om2.MQuaternion): ローカル行列の回転。
            reference (om2.MEulerRotation): 現在の rotate チャンネル値。

        Returns:
            om2.MEulerRotation: ノードの rotateOrder で表した、reference に最も近い解。
        """
        rotate_axis = self._rotation_quaternion("rotateAxis")
        joint_orient = self._rotation_quaternion("jointOrient")
        return _closest_euler(rotate_axis.conjugate() * quaternion * joint_orient.conjugate(), reference)

    def _apply_local_matrix(self, matrix, scale_reference=None):
        """jointOrient と rotateAxis を保持して local 行列を適用する。

        segmentScaleCompensate の補正を除いてから、Transform と同じ規約(スケールの
        符号を scale_reference または現在のチャンネル値に、Euler の解を現在のチャンネル値に
        揃える)で分解して書き込む。rotate は jointOrient と rotateAxis を回転から除いた値。
        角度の読み書きは Maya の角度単位が度であることを前提とする。

        Args:
            matrix (Matrix): 適用するローカル行列。
            scale_reference (Iterable[float] | None): 最優先で符号を合わせるスケール
                (``setScale`` で要求した値)。None なら現在の scale チャンネル値に合わせる。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: inverseScale がゼロに近い、または行列を分解できない場合。
            RuntimeError: Maya がアトリビュートの書き込みを拒否した場合。
        """
        super()._apply_local_matrix(matrix, scale_reference)

    def _compound_values(self, attribute, angle=False):
        """compound アトリビュートを 3 要素の tuple として取得する。

        Args:
            attribute (str): 読み取る複合アトリビュート名。
            angle (bool): True の場合、各子を角度アトリビュートとして度数法の値で取得する。
                現在の UI 角度単位に関係なく、MAngle.asDegrees() を使用する。
                False の場合は単位変換のない生の double として取得する。

        Returns:
            tuple[float, float, float]: 最初の子 3 要素の値。無効なノードでは (0.0, 0.0, 0.0)。
                有効時は子の数を事前検査せず、3 要素を読み取る。
        """
        if not self.isValid():
            return (0.0, 0.0, 0.0)
        plug = om2.MFnDependencyNode(self._mobject).findPlug(attribute, False)
        if angle:
            return tuple(plug.child(index).asMAngle().asDegrees() for index in range(3))
        return tuple(plug.child(index).asDouble() for index in range(3))

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


@collection_export()
@bulk_api(
    Joint,
    reads=(
        'getSegmentScaleCompensate',
        'getJointOrient',
        'getRadius',
        'getInverseScale',
        'parentJointName',
        'childJointNames',
        'depth',
        'isJoint',
        'skinClusters',
        'transferTarget',
        'reparentChildren',
        'chainFromHere',
        'ikHandles',
    ),
    writes=(
        'setSegmentScaleCompensate',
        'jointOrientToRotate',
        'freezeRotation',
        'connectInverseScale',
        'disconnectInverseScale',
        'setRadius',
        'delete',
        'removeInfluence',
    ),
)
class Joints(Transforms):
    """Joint参照を保持するTransforms派生。型・重複規則はNodesに従う。"""

    item_class = Joint

    def sortedByDepth(self):
        """深い joint から順に並べた新しいコレクションを返す。

        Returns:
            Joints: 子 joint を先に処理できる深さ順コレクション。
        """
        return Joints(sorted(self._items, key=lambda joint: joint.depth(), reverse=True))

    @fast_edit
    @undoChunk("hlibJointsJointOrientToRotate")
    def jointOrientToRotate(self, *, fast=False):
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
        return self._transfer_rotation()

    @fast_edit
    @undoChunk("hlibJointsFreezeRotation")
    def freezeRotation(self, *, fast=False):
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
        return self._transfer_rotation(to_orient=True)

    def skinClusters(self):
        """全 joint に関連する skinCluster を取得する。

        Returns:
            SkinClusters: 重複を除いた skinCluster コレクション。
        """
        from .skinCluster import SkinClusters

        skinClusters = []
        seen = set()
        for joint in self._items:
            for skin in joint.skinClusters():
                if skin.uuid() in seen:
                    continue
                seen.add(skin.uuid())
                skinClusters.append(skin)
        return SkinClusters(skinClusters)

    def delete(self):
        """ウェイト移送後にコレクション内の joint を削除する。

        同じjointの複数インスタンスパスはノード単位で一度だけ処理する。
        未スキニングjointも削除する。子Transform（jointを含む）は親へ移し、
        親がない場合はワールドへ移す。同じskinClusterの祖先influenceがあれば加算し、
        移送先がない場合のウェイト処理はMaya標準のcmds.deleteに任せる。
        途中の失敗は例外で停止し、完了済み変更は自動ロールバックしない。全体はUndoに対応。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: ウェイト移送・子の再親付け・削除ができない場合。
        """
        from .._core.jointDeletion import _JointDeletion

        _JointDeletion(self).execute()

    def _transfer_rotation(self, to_orient=False):
        """全対象の準備成功後に回転移送を適用する。

        Args:
            to_orient (bool): TrueならrotateをjointOrientへ移す。

        Returns:
            Joints: 自身。途中の失敗で完了済み更新は自動で戻さない。
        """
        plans = [(joint, joint._joint_rotation_transfer_values(to_orient=to_orient)) for joint in self]
        for joint, values in plans:
            joint._apply_rotation_transfer(values, to_orient=to_orient)
        return self
