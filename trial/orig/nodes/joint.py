"""joint ラッパーと joint コレクションを提供する。"""

import math
from typing import Any, Dict, List

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.fastWrite import set_attr
from ..decorator import _edit_context, _require_bool, undoChunk
from ..maths import EulerRotate, Matrix, Scale
from .node import Node, Nodes
from .transform import Transform, _closest_euler

#: :meth:`Joint.orient` の orientation に指定できる値(``cmds.joint(orientJoint=...)`` と同じ)。
_ORIENTATIONS = ("xyz", "yzx", "zxy", "zyx", "yxz", "xzy", "none")

#: :meth:`Joint.orient` の secondaryAxisOrient に指定できる値(``cmds.joint`` と同じ)。
_SECONDARY_AXES = ("xup", "xdown", "yup", "ydown", "zup", "zdown")

#: :meth:`Joint.mirror` の axis(鏡映面)と ``cmds.mirrorJoint`` のフラグの対応。
_MIRROR_PLANES = {"XY": "mirrorXY", "YZ": "mirrorYZ", "XZ": "mirrorXZ"}


def _orient_flags(orientation, secondaryAxisOrient, children, zeroScaleOrient):
    """Joint.orientの引数を検証し、cmds.jointへ渡すフラグを返す。

    Args:
        orientation (str): 主軸・副軸・第3軸の順の軸名、または ``"none"``。
        secondaryAxisOrient (str): 副軸を向けるワールド軸。
        children (bool): 子孫jointも処理するか。
        zeroScaleOrient (bool): scaleOrientを0にするか。

    Returns:
        dict: ``cmds.joint(edit=True, ...)`` のフラグ。

    Raises:
        TypeError: 文字列・bool以外の場合。
        ValueError: 対応しない軸名の場合。
    """
    for value, label in ((orientation, "orientation"), (secondaryAxisOrient, "secondaryAxisOrient")):
        if not isinstance(value, str):
            raise TypeError(f"{label} must be a string")
    if orientation not in _ORIENTATIONS:
        raise ValueError(f"orientation must be one of {', '.join(_ORIENTATIONS)}: {orientation!r}")
    if secondaryAxisOrient not in _SECONDARY_AXES:
        raise ValueError(f"secondaryAxisOrient must be one of {', '.join(_SECONDARY_AXES)}: {secondaryAxisOrient!r}")
    _require_bool(children, "children")
    _require_bool(zeroScaleOrient, "zeroScaleOrient")
    return {"edit": True, "orientJoint": orientation, "secondaryAxisOrient": secondaryAxisOrient,
            "children": children, "zeroScaleOrient": zeroScaleOrient}


class Joint(Transform):
    """Jointの参照と、回転移送・スケール補償の操作を提供する。

    マトリクス・TRSはTransformを継承し、rotateAxis・jointOrient・segmentScaleCompensateを考慮する。
    SSCの切替、inverseScaleの接続、姿勢を保つ回転移送は独立した操作。
    """

    def getSegmentScaleCompensate(self):
        """segmentScaleCompensateの有効フラグを取得する。

        inverseScaleに親のscaleが接続されているか、補償が期待どおり効くかは検査しない。

        Returns:
            bool: segmentScaleCompensateの現在値。
        """
        return bool(self.getPlug("segmentScaleCompensate").get())

    def setSegmentScaleCompensate(self, state, *, fast=False):
        """segmentScaleCompensateの有効フラグだけを変更する。

        segmentScaleCompensateだけを変更する。inverseScaleの接続やバインド情報は
        変更しないため、親のスケールによっては姿勢やスキンの見た目が変わる。

        Args:
            state (bool): Trueで補正を有効、Falseで無効にする。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Joint: 自身。

        Raises:
            TypeError: stateまたはfastがbool以外の場合。
            RuntimeError: ロックや入力接続などで編集できない場合。
        """
        with _edit_context("mlibJointSetSegmentScaleCompensate", fast):
            _require_bool(state, "state")
            self.getPlug("segmentScaleCompensate").set(state, fast=fast)
            return self

    def getJointOrient(self):
        """jointOrientをXYZ順・rad単位の独立したEulerRotateとして取得する。

        ノードのrotateOrderやUI角度単位は使わない。
        rotateやrotateAxis、親の回転は合成しない。

        Returns:
            EulerRotate: jointOrientの新しい値。無効ノードではXYZとも0。
                有効性の確認にはisValidを使う。
        """
        values = self._compound_values("jointOrient", angle=True)
        return EulerRotate(*(math.radians(value) for value in values))

    def jointOrientToRotate(self, *, fast=False):
        """jointOrientをrotateへ合成して0にし、現在の姿勢を保つ。

        XYZの数値加算ではない。rotateAxis・rotateOrder・移動・スケールを変えず、
        現在フレームだけを処理する。jointOrientがXYZとも0なら書込み検査と更新を省略する。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Joint: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            RuntimeError: 無効joint、rotate/jointOrientのロック・入力接続・書込み不可、または編集失敗。

        Note:
            通常処理はUndo有効時に1回で戻せる。途中失敗で完了済みの変更は自動では戻さない。
        """
        with _edit_context("mlibJointJointOrientToRotate", fast):
            self._require_valid("change orientation of")
            self._apply_rotate_transfer(self._joint_rotate_transfer_values(), fast=fast)
            return self

    def freezeRotate(self, *, fast=False):
        """rotateをjointOrientへ合成し、姿勢を保ってrotateを0にする。

        rotateAxis・rotateOrder・移動・スケールは保持する。現在フレームだけを処理し、
        アニメーションはベイクしない。ウェイト・bindPreMatrix・バインドポーズは変更しない。
        rotateがXYZとも0なら書込み検査と更新を省略する。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Joint: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            RuntimeError: 無効joint、rotate/jointOrientのロック・入力接続・書込み不可、または編集失敗。

        Note:
            通常処理はUndo有効時に1回で戻せる。途中失敗で完了済みの変更は自動では戻さない。
        """
        with _edit_context("mlibJointFreezeRotate", fast):
            self._require_valid("freeze rotation of")
            self._apply_rotate_transfer(self._joint_rotate_transfer_values(to_orient=True), to_orient=True, fast=fast)
            return self

    def orient(self, orientation="xyz", secondaryAxisOrient="yup", children=True, zeroScaleOrient=True):
        """jointの向きを子jointへ向けて揃える(``cmds.joint(edit=True, orientJoint=...)`` 相当)。

        ``cmds.joint(edit=True, orientJoint=orientation, secondaryAxisOrient=secondaryAxisOrient,
        children=children, zeroScaleOrient=zeroScaleOrient)`` を実行し、処理した中で子jointを持たない
        末端jointの jointOrient を0にする(親jointと同じ向き。rotateは変えない)。子jointの位置は保つ。
        末端jointの子にあるjoint以外のノードは、jointOrientの変更に合わせて動く。
        fast引数は持たない(向きの計算をMaya標準のcmds.jointに委ねる)。Undo有効時は1回で戻せる。

        Args:
            orientation (str): 子jointへ向ける主軸・副軸・第3軸の順。``"xyz"``・``"yzx"``・``"zxy"``・
                ``"zyx"``・``"yxz"``・``"xzy"``、または jointOrient を0にする ``"none"``。
            secondaryAxisOrient (str): 副軸を向けるワールド軸。``"xup"``・``"xdown"``・``"yup"``・
                ``"ydown"``・``"zup"``・``"zdown"``。
            children (bool): Trueは子孫jointも同じ規則で処理する。Falseは自身だけ。
            zeroScaleOrient (bool): TrueはscaleOrientを0にする。

        Returns:
            Joint: 自身。

        Raises:
            TypeError: orientation・secondaryAxisOrientが文字列以外、children・zeroScaleOrientがbool以外の場合。
            ValueError: 対応しない軸名の場合。
            RuntimeError: 無効なjoint、またはロック・入力接続などでMayaが編集を拒否した場合。
        """
        flags = _orient_flags(orientation, secondaryAxisOrient, children, zeroScaleOrient)
        self._require_valid("orient")
        with undoChunk("mlibJointOrient"):
            self._orient(flags)
            return self

    def mirror(self, axis="YZ", behavior=True, searchReplace=None):
        """jointチェーンを鏡映した新しいチェーンを作成する(``cmds.mirrorJoint`` 相当)。

        自身と子孫のjoint(と子のikEffector等)をMaya標準の ``cmds.mirrorJoint`` で複製・鏡映する。
        新しいルートは自身と同じ親の下に作られ、Mayaの規則どおり選択される。元のチェーンは変更しない。
        Transformの :meth:`~mlib.nodes.Transform.mirrorTransform` (自身の値の鏡映)とは別の操作。
        fast引数は持たない(OpenMayaに同等機能が無い)。Undo有効時は1回で戻せる。

        Args:
            axis (str): 鏡映面。``"YZ"`` (X方向の左右反転)・``"XY"``・``"XZ"``。大文字小文字は区別しない。
            behavior (bool): Trueは ``mirrorBehavior`` (回転の向きを反転し、同じ回転値で逆向きに動く。
                リグの左右対称で一般的)。Falseは向き(orientation)を鏡映する。
            searchReplace (tuple[str, str] | None): 新しいjoint名の置換 ``(検索, 置換)``。
                例: ``("L_", "R_")``。NoneならMayaの自動命名。

        Returns:
            Joint: 新しいチェーンのルートjoint。チェーン全体は ``getChildren(allDescendents=True)``
                や :meth:`getChainFromHere` で取得する。

        Raises:
            TypeError: axisが文字列以外、behaviorがbool以外、searchReplaceが2つの文字列の並び・None以外の場合。
            ValueError: axisが対応しない値、またはsearchReplaceの検索文字列が空の場合。
            RuntimeError: 無効なjoint、またはMayaが鏡映を拒否した場合。

        Note:
            Mayaの ``mirrorJoint`` は、searchReplaceで名前空間を含めて置換しない限り新しいjointを
            現在の名前空間へ置く。
        """
        if not isinstance(axis, str):
            raise TypeError("axis must be a string")
        flag = _MIRROR_PLANES.get(axis.upper())
        if flag is None:
            raise ValueError(f"axis must be one of {', '.join(_MIRROR_PLANES)}: {axis!r}")
        _require_bool(behavior, "behavior")
        flags: Dict[str, Any] = {flag: True, "mirrorBehavior": behavior}
        if searchReplace is not None:
            if (isinstance(searchReplace, str) or not isinstance(searchReplace, (tuple, list))
                    or len(searchReplace) != 2 or not all(isinstance(item, str) for item in searchReplace)):
                raise TypeError("searchReplace must be a (search, replace) pair of strings or None")
            if not searchReplace[0]:
                raise ValueError("searchReplace search string must not be empty")
            flags["searchReplace"] = tuple(searchReplace)
        self._require_valid("mirror")
        with undoChunk("mlibJointMirror"):
            parent = self.getParent()
            # mirrorJointの選択変更はUndoに記録されないため、前後の選択を明示してUndo/Redoで再現する。
            cmds.select(self.getFullName(), replace=True)
            result = cmds.mirrorJoint(self.getFullName(), **flags)
            if not result:
                raise RuntimeError(f"Maya did not create a mirrored joint for {self.getName()}")
            prefix = parent.getFullName() if parent is not None else ""
            root = Joint(prefix + "|" + result[0])
            cmds.select(root.getFullName(), replace=True)
            return root

    def connectInverseScale(self, source=None, force=False, *, fast=False):
        """接続元Transformのscaleを自身のinverseScaleへ接続する。

        segmentScaleCompensateは変更せず、姿勢の補償は行わない。
        接続によって現在の姿勢が変わる場合がある。

        Args:
            source (object | None): Transformへ解決できるノード入力。Noneなら直上の親。
                親がなければ変更しない。
            force (bool): 既定False。Trueは既存入力を置換し、接続先側のロックを一時解除する。
                ロック復元の規則は :meth:`~mlib.plugs.plug.Plug.connect` と同じ。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Joint: 自身。同じ直接接続が既にあれば変更しない。

        Raises:
            TypeError: Transformへ解決できない、force/fastがbool以外の場合。
            ValueError: 自身を接続元にした、または入力参照が不正な場合。
            RuntimeError: 対象が無効、名前解決・接続・ロック復元に失敗した場合。

        Note:
            Jointsでもsource=Noneなら各要素の親を使う。通常処理はUndo有効時に1回で戻せる。
        """
        with _edit_context("mlibJointConnectInverseScale", fast):
            _require_bool(force, "force")
            self._require_valid("connect inverseScale on")
            source = self.getParent() if source is None else Node._resolve_input(source)
            if source is None:
                return self
            if not isinstance(source, Transform):
                raise TypeError("source must be a Transform")
            if source == self:
                raise ValueError("inverseScale cannot use the joint itself as its source")
            origin = source.getPlug("scale")
            target = self.getPlug("inverseScale")
            if target.getSource(skipConversionNodes=False) != origin:
                origin.connectTo(target, force=force, fast=fast)
            return self

    def disconnectInverseScale(self, *, fast=False):
        """inverseScale本体、X、Y、Zの順に直接の入力接続を切断する。

        出力接続・SSC・値のリセット・姿勢補償は扱わない。接続がない箇所は何もしない。
        切断後の値はMayaの動作に従う。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Joint: 自身。Jointsからも一括実行できる。

        Raises:
            TypeError: fastがbool以外の場合。
            RuntimeError: 無効な対象、ロック、またはMayaの切断失敗。

        Note:
            通常処理はUndo有効時に一つのチャンクへ記録する。先行した切断は自動で戻さない。
        """
        with _edit_context("mlibJointDisconnectInverseScale", fast):
            for name in ("inverseScale", "inverseScaleX", "inverseScaleY", "inverseScaleZ"):
                target = self.getPlug(name)
                origin = target.getSource(skipConversionNodes=False)
                if origin is not None:
                    target.disconnect(origin, fast=fast)
            return self

    def getRadius(self):
        """ジョイント個別の表示半径を取得する。

        Returns:
            float: radiusアトリビュート値。Maya全体のjointDisplayScaleとは別の値。
        """
        return float(self.getPlug("radius").get())

    def setRadius(self, value, *, fast=False):
        """ジョイント個別の表示半径を変更する。骨の長さ・scaleは変更しない。

        Args:
            value (float): 0以上の有限値。最終表示はMaya全体の表示倍率にも依存する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Joint: 自身。Jointsでは各要素に同じ値を設定する。

        Raises:
            TypeError: valueが数値でない、またはfastがbool以外の場合。
            ValueError: valueが負数・非有限値の場合。
            RuntimeError: Mayaが編集を拒否した場合。
        """
        with _edit_context("mlibJointSetRadius", fast):
            import numbers
            if isinstance(value, bool) or not isinstance(value, numbers.Real):
                raise TypeError("radius must be a number")
            value = float(value)
            if not math.isfinite(value) or value < 0:
                raise ValueError("radius must be finite and non-negative")
            self.getPlug("radius").set(value, fast=fast)
            return self

    def getInverseScale(self):
        """inverseScaleの無次元XYZ値を、独立したScaleとして取得する。

        アトリビュート値の逆数は計算せず、SSCの有効フラグによって値を変えない。

        Returns:
            Scale: inverseScaleの新しい値。無効ノードではXYZとも0。
                実際の補償状態や有効性を判定する戻り値ではない。
        """
        return Scale(*self._compound_values("inverseScale"))

    def getParentJointName(self):
        """親 joint の名前を取得する。

        Returns:
            str | None: 親 joint 名。親が joint でない場合は ``None``。
        """
        if not self.isValid():
            return None
        parent = self.getParent()
        if parent is None or not parent.isValid():
            return None
        if not parent._require_mnode().hasFn(om2.MFn.kJoint):
            return None
        return parent.getName()

    def getChildJointNames(self):
        """直接の子 joint 名を取得する。

        Returns:
            list[str]: 子 joint 名のリスト。
        """
        if not self.isValid():
            return []
        return [
            child.getName()
            for child in self.getChildren(shapes=True, intermediates=True)
            if child._require_mnode().hasFn(om2.MFn.kJoint)
        ]

    def getDepth(self):
        """joint 階層内の深さを取得する。

        Returns:
            int: root joint を 0 とする階層深度。
        """
        depth = 0
        current_joint = self.getParentJointName()
        while current_joint:
            depth += 1
            current_joint = Joint(current_joint).getParentJointName()
        return depth

    def getSkinClusters(self):
        """この joint に接続する skinCluster を取得する。

        Returns:
            list[SkinCluster]: 重複を除いた skinCluster ラッパー。
        """
        from .skinCluster import SkinCluster

        if not self.isValid():
            return []
        seen = set()
        result = []
        for plug in self.getConnections(type="skinCluster"):
            node = plug.getNode()
            if node.getUuid() in seen:
                continue
            seen.add(node.getUuid())
            mobject = node.mnode()
            assert mobject is not None
            result.append(SkinCluster(mobject))
        return result

    def removeInfluence(self, skinCluster=None, *, transferToParent=True, force=False):
        """指定skinClusterから自身のinfluence登録を外す。jointノードは残す。

        全対象の登録・移送条件を先に検査し、取得順にSkinCluster.removeInfluenceへ委譲する。
        Undo有効時は一つのチャンクへ記録する。fast引数は持たない。後続の失敗で先行処理は戻さない。

        Args:
            skinCluster (SkinCluster | str | None): 対象。Noneは接続する全skinCluster。
            transferToParent (bool): Trueは最も近い祖先influenceへ加算する。
                False、または移送先がなければ標準の再配分に任せる。
            force (bool): 不正ウェイトを修復してから解除する。修復時に正規化・ロック解除・レイヤー回避は行わない。

        Returns:
            Joint: 自身。対象省略で未スキニングなら変更しない。

        Raises:
            TypeError: transferToParent・forceがbool以外の場合。
            ValueError: 未登録、または最後のinfluenceを解除する場合。
            RuntimeError: 無効joint、レイヤー・ロック、または編集失敗。
        """
        with undoChunk("mlibJointRemoveInfluence"):
            from .skinCluster import SkinCluster
            self._require_valid("remove")
            _require_bool(transferToParent, "transferToParent")
            _require_bool(force, "force")
            skins = self.getSkinClusters() if skinCluster is None else [skinCluster if isinstance(skinCluster, SkinCluster) else SkinCluster(skinCluster)]
            for skin in skins:
                skin._influence_removal_target(self, transfer_to_parent=transferToParent, force=force)
            for skin in skins:
                skin.removeInfluence(self, transferToParent=transferToParent, force=force)
            return self

    def getTransferTarget(self, skin):
        """ウェイト移送先となる最も近い親 influence を探索する。

        Args:
            skin (SkinCluster): influence の有無を調べる skinCluster。

        Returns:
            str | None: 移送先の親 joint 名。見つからない場合は ``None``。
        """
        ancestor = self.getParentJointName()
        while ancestor:
            if skin.hasInfluence(ancestor):
                return ancestor
            ancestor = Joint(ancestor).getParentJointName()
        return None

    def reparentChildren(self, parentJoint, *, fast=False):
        """子 joint を指定した親 joint へ付け替える。

        Args:
            parentJoint (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                直接の子 joint を付け替える親ノード。``Node._input_name`` と同じ規則で解決する
                (Plug・MPlug は所有ノード)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Joint: 自身。

        Raises:
            TypeError: fastがbool以外、またはparentJointが対応しない型の場合。
            ValueError: parentJointが空文字列・無効な対象の場合。
            RuntimeError: parentJointを解決できない、またはMayaが親変更を拒否した場合。
        """
        with _edit_context("mlibJointReparentChildren", fast):
            parent_name = Node._input_name(parentJoint)
            if fast:
                # core.jointEdit は nodes を参照するため、循環importを避けて呼出し時に取得する。
                from ..core.jointEdit import reparent, reparent_plan
                parent = Node(parent_name)
                plans = [reparent_plan(Joint(name), parent) for name in self.getChildJointNames()]
                for plan in plans:
                    reparent(plan)
            else:
                for child_joint in self.getChildJointNames():
                    cmds.parent(child_joint, parent_name)
            return self

    def getChainFromHere(self, to=None):
        """自身を起点とする joint チェーンを順に取得する。

        Args:
            to (Joint | str | None): チェーンの終端 joint。指定した場合は自身から
                その joint までの経路を辿る(子孫でなければならない)。省略時は、
                子 joint がちょうど1つの間だけ辿り、分岐(子が0または2つ以上)に
                達したところで止める。

        Returns:
            list[Joint]: 自身から to まで、または最初の分岐点までの joint。
                自身を含む。

        Raises:
            ValueError: to が自身の子孫でない場合。
            RuntimeError: 自身が無効な場合。
        """
        self._require_valid("build a chain from")
        if to is None:
            chain: List[Joint] = [self]
            current = self
            while True:
                children = current.getChildJointNames()
                if len(children) != 1:
                    return chain
                current = Joint(children[0])
                chain.append(current)
        target = to if isinstance(to, Joint) else Joint(to)
        if not self.isAncestorOf(target):
            raise ValueError("to must be a descendant of this joint")
        chain = [self]
        current = self
        while current.getUuid() != target.getUuid():
            next_joint = next(
                (
                    Joint(name) for name in current.getChildJointNames()
                    if Joint(name).getUuid() == target.getUuid() or Joint(name).isAncestorOf(target)
                ),
                None,
            )
            if next_joint is None:
                raise ValueError("to must be a descendant of this joint")
            chain.append(next_joint)
            current = next_joint
        return chain

    def getIkHandles(self):
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
        for plug in self.getConnections(type="ikHandle"):
            node = plug.getNode()
            if node.getUuid() in seen:
                continue
            seen.add(node.getUuid())
            mobject = node.mnode()
            assert mobject is not None
            result.append(IkHandle(mobject))
        return result

    def _orient(self, flags):
        """検証済みのフラグで向きを揃え、末端jointのjointOrientを0にする。

        Args:
            flags (dict): :func:`_orient_flags` が返したcmds.jointのフラグ。

        Returns:
            None: 値を返さない。
        """
        name = self.getFullName()
        cmds.joint(name, **flags)
        targets = [name]
        if flags["children"]:
            targets += cmds.listRelatives(name, allDescendents=True, type="joint", fullPath=True) or []
        for target in targets:
            if not cmds.listRelatives(target, children=True, type="joint"):
                cmds.setAttr(target + ".jointOrient", 0.0, 0.0, 0.0)

    def _joint_rotate_order(self):
        """Maya の rotateOrder を API の回転順序へ変換する。

        rotateOrder の番号(0=xyz〜5=zyx)は MEulerRotation.kXYZ〜kZYX と同じ並び。

        Returns:
            int: rotateOrder に対応する Maya API 2.0 の MEulerRotation 定数。
        """
        return self._rotate_order()

    def _joint_rotate_transfer_values(self, to_orient=False):
        """書込み可否を検証し、合成後の回転を現在の角度単位で返す。

        Args:
            to_orient (bool): TrueでjointOrient用XYZ、FalseでrotateOrderのrotate用。

        Returns:
            tuple[float, float, float] | None: 合成値。移送元が0ならNone。

        Raises:
            RuntimeError: 無効joint、ロック、入力接続、書込み不可の場合。
        """
        self._require_valid("change orientation of")
        orient = self._compound_values("jointOrient", angle=True)
        rotate = self._compound_values("rotate", angle=True)
        if not any(rotate if to_orient else orient):
            return None
        name = self.getFullName()
        for attribute in ("rotate", "jointOrient"):
            for suffix in ("", "X", "Y", "Z"):
                plug = name + "." + attribute + suffix
                try:
                    self.getPlug(attribute + suffix)._require_writable()
                except RuntimeError as exc:
                    raise RuntimeError(f"Attribute must be unlocked and have no input connection: {plug}") from exc
        rotation = om2.MEulerRotation(
            *(math.radians(v) for v in rotate),
            self._joint_rotate_order())
        # jointOrientはrotateOrderに関係なくXYZ。MayaのR * JOを合成する。
        orientation = om2.MEulerRotation(*(math.radians(v) for v in orient))
        combined = om2.MTransformationMatrix(rotation.asMatrix() * orientation.asMatrix())
        result = combined.rotation(asQuaternion=True).asEulerRotation()
        result.reorderIt(om2.MEulerRotation.kXYZ if to_orient else self._joint_rotate_order())
        return tuple(om2.MAngle(v).asUnits(om2.MAngle.uiUnit()) for v in result)

    def _apply_rotate_transfer(self, values, to_orient=False, *, fast=False):
        """検証済みの回転移送値を、指定した更新モードで適用する。

        Args:
            values (tuple | None): 現在のUI角度単位の3成分。Noneなら更新しない。
            to_orient (bool): TrueならjointOrientへ移しrotateを0にする。
            fast (bool): TrueならOpenMayaで直接更新する。

        Returns:
            None: 値を返さない。
        """
        if values is None:
            return
        set_attr(self.getFullName() + ".jointOrient", *(values if to_orient else (0, 0, 0)), fast=fast)
        set_attr(self.getFullName() + ".rotate", *((0, 0, 0) if to_orient else values), fast=fast)

    def _rotate_quaternion(self, attribute):
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
        """ssc と inverseScale が適用された後のマトリクスから補正前の値を戻す。

        Maya の joint のマトリクスは S · RA · R · JO · IS · T(IS は inverseScale の逆数の
        対角マトリクス)なので、3x3 部分へ inverseScale の対角マトリクスを右から掛けて IS を打ち消す。
        平行移動は IS の後に適用されるため変えない。

        Args:
            matrix (Matrix): スケール補正を取り除く対象マトリクス。

        Returns:
            Matrix: ssc が無効なら入力そのもの。有効なら IS を打ち消した新しいマトリクス。

        Raises:
            ValueError: ssc が有効で inverseScale の成分の絶対値が 1e-12 未満の場合。
        """
        if not self.getPlug("ssc").get():
            return matrix
        inverse_scale = self._compound_values("inverseScale")
        if any(abs(value) < 1e-12 for value in inverse_scale):
            raise ValueError("inverseScale components must be non-zero when segmentScaleCompensate is enabled")
        result = matrix * Matrix(scale=inverse_scale)
        result.translate = matrix.translate
        return result

    def _rotate_reference(self, reference):
        """:meth:`getRotate` が Euler の解を選ぶ基準を返す。

        joint の getRotate は jointOrient と rotateAxis を含む回転で rotate チャンネルとは
        別の回転なので、チャンネル値ではなく 0 回転(ノードの rotateOrder)を基準にする。

        Args:
            reference (om2.MEulerRotation): 現在の rotate チャンネル値(順序だけを使う)。

        Returns:
            om2.MEulerRotation: 0 回転。順序はノードの rotateOrder。
        """
        return om2.MEulerRotation(0.0, 0.0, 0.0, reference.order)

    def _channel_rotate(self, quaternion, reference):
        """ローカルマトリクスの回転から jointOrient と rotateAxis を除き、rotate の値へ変換する。

        Maya の joint の回転は rotateAxis、rotate、jointOrient の順に適用されるため、
        rotate = rotateAxis⁻¹ · マトリクスの回転 · jointOrient⁻¹(om2 のクォータニオンの積の順序)。

        Args:
            quaternion (om2.MQuaternion): ローカルマトリクスの回転。
            reference (om2.MEulerRotation): 現在の rotate チャンネル値。

        Returns:
            om2.MEulerRotation: ノードの rotateOrder で表した、reference に最も近い解。
        """
        rotate_axis = self._rotate_quaternion("rotateAxis")
        joint_orient = self._rotate_quaternion("jointOrient")
        return _closest_euler(rotate_axis.conjugate() * quaternion * joint_orient.conjugate(), reference)

    def _apply_local_matrix(self, matrix, scale_reference=None, *, fast=False):
        """jointOrient と rotateAxis を保持して local マトリクスを適用する。

        Transformの共通処理へ委譲し、Jointの回転分離とSSC補償を反映した
        translate・rotate・scale・shearの設定値のうち、現在値と完全に一致しないものだけを書き込む。
        計算値は距離cm・角度radで、UI角度単位が度であることは前提にしない。

        Args:
            matrix (Matrix): 適用するローカルマトリクス。
            scale_reference (Iterable[float] | None): 最優先で符号を合わせるスケール
                (``setScale`` で要求した値)。None なら現在の scale チャンネル値に合わせる。
            fast (bool): Trueなら各チャンネルをOpenMayaで更新する。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: inverseScale がゼロに近い、またはマトリクスを分解できない場合。
            RuntimeError: Maya がアトリビュートの書き込みを拒否した場合。
        """
        super()._apply_local_matrix(matrix, scale_reference, fast=fast)

    def _compound_values(self, attribute, angle=False):
        """コンパウンドアトリビュートを 3 要素の tuple として取得する。

        Args:
            attribute (str): 読み取るコンパウンドアトリビュート名。
            angle (bool): True の場合、各子を角度アトリビュートとして度数法の値で取得する。
                現在の UI 角度単位に関係なく、MAngle.asDegrees() を使用する。
                False の場合は単位変換のない生の double として取得する。

        Returns:
            tuple[float, float, float]: 最初の子 3 要素の値。無効なノードでは (0.0, 0.0, 0.0)。
                有効時は子の数を事前検査せず、3 要素を読み取る。
        """
        if not self.isValid():
            return (0.0, 0.0, 0.0)
        plug = self._dependency_fn().findPlug(attribute, False)
        if angle:
            return tuple(plug.child(index).asMAngle().asDegrees() for index in range(3))
        return tuple(plug.child(index).asDouble() for index in range(3))


class Joints(Nodes):
    """Joint参照を保持するコレクション。型・重複規則はNodesに従う。"""

    item_class = Joint
    _items: List[Joint]

    def sortedByDepth(self):
        """深い joint から順に並べた新しいコレクションを返す。

        Returns:
            Joints: 子 joint を先に処理できる深さ順コレクション。
        """
        return Joints(sorted(self._items, key=lambda joint: joint.getDepth(), reverse=True))

    def orient(self, orientation="xyz", secondaryAxisOrient="yup", children=True, zeroScaleOrient=True):
        """各jointへ保持順に :meth:`Joint.orient` を適用する。

        全体を1つのUndoチャンクに記録する。引数は全要素の処理前に1回だけ検証する。

        Args:
            orientation (str): :meth:`Joint.orient` と同じ。
            secondaryAxisOrient (str): :meth:`Joint.orient` と同じ。
            children (bool): :meth:`Joint.orient` と同じ。
            zeroScaleOrient (bool): :meth:`Joint.orient` と同じ。

        Returns:
            Joints: 自身。

        Raises:
            TypeError: :meth:`Joint.orient` と同じ。
            ValueError: :meth:`Joint.orient` と同じ。
            RuntimeError: 無効なjointを含む、またはMayaが編集を拒否した場合。先行した要素の変更は自動では戻さない。
        """
        flags = _orient_flags(orientation, secondaryAxisOrient, children, zeroScaleOrient)
        for joint in self._items:
            joint._require_valid("orient")
        with undoChunk("mlibJointsOrient"):
            for joint in self._items:
                joint._orient(flags)
            return self

    def setRadius(self, value, *, fast=False):
        """各jointへ保持順に :meth:`Joint.setRadius` を適用する。

        Args:
            value (float): :meth:`Joint.setRadius` と同じ。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Joints: 自身。通常は1回のUndoにまとめる。

        Raises:
            TypeError: :meth:`Joint.setRadius` と同じ。
            ValueError: :meth:`Joint.setRadius` と同じ。
            RuntimeError: 無効なjointを含む、またはMayaが更新を拒否した場合。
        """
        self._forward("setRadius", (value,), fast)
        return self

    def setSegmentScaleCompensate(self, state, *, fast=False):
        """各jointへ保持順に :meth:`Joint.setSegmentScaleCompensate` を適用する。

        Args:
            state (bool): :meth:`Joint.setSegmentScaleCompensate` と同じ。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Joints: 自身。通常は1回のUndoにまとめる。

        Raises:
            TypeError: :meth:`Joint.setSegmentScaleCompensate` と同じ。
            RuntimeError: 無効なjointを含む、またはMayaが更新を拒否した場合。
        """
        self._forward("setSegmentScaleCompensate", (state,), fast)
        return self

    def getSkinClusters(self):
        """全 joint に関連する skinCluster を取得する。

        Returns:
            SkinClusters: 重複を除いた skinCluster コレクション。
        """
        from .skinCluster import SkinClusters

        skin_clusters = []
        seen = set()
        for joint in self._items:
            for skin in joint.getSkinClusters():
                if skin.getUuid() in seen:
                    continue
                seen.add(skin.getUuid())
                skin_clusters.append(skin)
        return SkinClusters(skin_clusters)
