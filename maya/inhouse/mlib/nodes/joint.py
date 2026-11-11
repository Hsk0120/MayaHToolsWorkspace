"""joint ラッパーと joint コレクションを提供する。"""

import math
from contextlib import contextmanager
from typing import Any, Dict, List

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..core.fastWrite import require_writable, set_attr
from ..core.nodeEdit import check_deletion, delete_nodes
from ..decorator import _edit_context, _pick_alias, _require_bool, undoChunk
from ..maths import EulerRotate, Matrix, Scale, Vector
from ..util import _MIRROR_PLANES, _UNSET, _finite_vector, _mirror_axis, _world_space
from .node import Node, Nodes
from .transform import Transform, _closest_euler

#: :meth:`Joint.orient` の orientation に指定できる値(``cmds.joint(orientJoint=...)`` と同じ)。
_ORIENTATIONS = ("xyz", "yzx", "zxy", "zyx", "yxz", "xzy", "none")

#: :meth:`Joint.orient` の secondaryAxisOrient に指定できる値(``cmds.joint`` と同じ)。
_SECONDARY_AXES = ("xup", "xdown", "yup", "ydown", "zup", "zdown")


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


@contextmanager
def _unlocked_influences(skins, fast=False):
    """skinClusterのウェイトのロックを一時的に外し、抜けるときに元へ戻す。

    Args:
        skins (Iterable[SkinCluster]): ロックを外すskinCluster。
        fast (bool): Trueはロックの切替えをUndoへ記録しない。

    Yields:
        None: 値を渡さない。

    Raises:
        RuntimeError: lockInfluenceWeightsがロック・入力接続されていて切り替えられない場合。何も変更しない。
    """
    locked = {}
    for skin in skins:
        for node in skin.getLockedInfluences():
            locked[node.getUuid()] = node
    for node in locked.values():
        node.getPlug("lockInfluenceWeights")._require_writable()
    for node in locked.values():
        node.getPlug("lockInfluenceWeights").set(False, fast=fast)
    try:
        yield
    finally:
        for node in locked.values():
            # 削除やinfluenceの解除で消えたアトリビュートは戻さない。
            if node.isValid() and node.hasAttr("lockInfluenceWeights"):
                node.getPlug("lockInfluenceWeights").set(True, fast=fast)


def _influences_by_skin(joints):
    """jointを、登録先のskinClusterごとにまとめる。

    Args:
        joints (Iterable[Joint]): 調べるjoint。

    Returns:
        list[tuple[SkinCluster, list[Joint]]]: skinClusterと、そこへ登録されたjoint。
    """
    groups = {}
    for joint in joints:
        for skin in joint.getSkinClusters():
            if skin.hasInfluence(joint.getFullName()):
                groups.setdefault(skin.getUuid(), (skin, []))[1].append(joint)
    return list(groups.values())


def _remove_influences(groups, transfer_to_parent, force, fast=False, deleting=False):
    """ウェイトのロックを一時的に外し、全skinClusterを検査してから深いinfluenceから順に解除する。

    Args:
        groups (list[tuple[SkinCluster, list[Joint]]]): skinClusterと解除するjoint。
        transfer_to_parent (bool): 祖先influenceへウェイトを移すか。
        force (bool): 不正ウェイトを修復してから解除するか。
        fast (bool): Trueはウェイトの書込みをOpenMayaで行い、Undoへ記録しない。
        deleting (bool): Trueは直後にjointを削除する。

    Returns:
        None: 値を返さない。
    """
    with _unlocked_influences([skin for skin, _ in groups], fast=fast):
        checked = [(skin, skin._influence_removal_plans(joints, transfer_to_parent, force=force))
                   for skin, joints in groups]
        for skin, (plans, snapshot) in checked:
            skin._apply_influence_removals(plans, snapshot, force=force, fast=fast, deleting=deleting)


def _delete_joints(joints, safe, fast, remove_influence, transfer_to_parent, force):
    """jointを、消える階層のinfluenceを解除してから一括で削除する。

    Args:
        joints (Sequence[Joint]): 削除するjoint。
        safe (bool): Trueは自身またはDAG子孫にDG接続があるjointを削除しない。
        fast (bool): TrueはUndoなしのOpenMaya更新。
        remove_influence (bool): 削除の前にinfluenceを解除するか。
        transfer_to_parent (bool): 解除するウェイトを残る祖先influenceへ移すか。
        force (bool): 不正ウェイトを修復してから解除するか。

    Returns:
        None: 値を返さない。

    Raises:
        TypeError: safe・remove_influence・transfer_to_parent・forceがbool以外の場合。
        RuntimeError: 対象が無効、削除できない、またはinfluenceを解除できない場合。
    """
    _require_bool(safe, "safe")
    _require_bool(remove_influence, "removeInfluence")
    _require_bool(transfer_to_parent, "transferToParent")
    _require_bool(force, "force")
    for joint in joints:
        joint._require_valid("delete")
    if safe:
        joints = [joint for joint in joints if not joint._has_delete_connections()]
    if not joints:
        return
    checked = check_deletion(joints, fast=fast)
    if remove_influence:
        # 親と一緒に消える子孫も解除しないと、消えたjointの列にウェイトが残る。
        doomed = {}
        for joint in joints:
            for node in [joint] + list(joint.getChildren(allDescendents=True, type="joint")):
                doomed[node.getUuid()] = node
        # 全influenceが消えるskinClusterは解除の移送先も再配分先も無いため、Maya標準の削除に任せる。
        groups = [(skin, nodes) for skin, nodes in _influences_by_skin(doomed.values())
                  if len(nodes) < len(skin.getInfluences())]
        _remove_influences(groups, transfer_to_parent, force, fast=fast, deleting=True)
    delete_nodes(joints, fast=fast, checked=checked)


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

    def jointOrientToRotate(self):
        """jointOrientをrotateへ合成して0にし、現在の姿勢を保つ。

        XYZの数値加算ではない。rotateAxis・rotateOrder・移動・スケールを変えず、
        現在フレームだけを処理する。jointOrientがXYZとも0なら書込み検査と更新を省略する。
        fast引数は持たない(処理の大半が値の検証・計算で、OpenMayaで書いても速くならないため)。

        Returns:
            Joint: 自身。

        Raises:
            RuntimeError: 無効joint、rotate/jointOrientのロック・入力接続・書込み不可、または編集失敗。

        Note:
            通常処理はUndo有効時に1回で戻せる。途中失敗で完了済みの変更は自動では戻さない。
        """
        with undoChunk("mlibJointJointOrientToRotate"):
            self._require_valid("change orientation of")
            self._apply_rotate_transfer(self._joint_rotate_transfer_values())
            return self

    def freezeRotate(self):
        """rotateをjointOrientへ合成し、姿勢を保ってrotateを0にする。

        rotateAxis・rotateOrder・移動・スケールは保持する。現在フレームだけを処理し、
        アニメーションはベイクしない。ウェイト・bindPreMatrix・バインドポーズは変更しない。
        rotateがXYZとも0なら書込み検査と更新を省略する。fast引数は持たない(:meth:`jointOrientToRotate` と同じ理由)。

        Returns:
            Joint: 自身。

        Raises:
            RuntimeError: 無効joint、rotate/jointOrientのロック・入力接続・書込み不可、または編集失敗。

        Note:
            通常処理はUndo有効時に1回で戻せる。途中失敗で完了済みの変更は自動では戻さない。
        """
        with undoChunk("mlibJointFreezeRotate"):
            self._require_valid("freeze rotation of")
            self._apply_rotate_transfer(self._joint_rotate_transfer_values(to_orient=True), to_orient=True)
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
            axis (str | int): 鏡映面 ``"YZ"`` (X方向の左右反転)・``"XZ"``・``"XY"``、または反転する軸
                ``"x"``・``"y"``・``"z"`` (x⇔YZ、y⇔XZ、z⇔XY。文字の順序・大文字小文字は問わない)、
                または0/1/2。
            behavior (bool): Trueは ``mirrorBehavior`` (回転の向きを反転し、同じ回転値で逆向きに動く。
                リグの左右対称で一般的)。Falseは向き(orientation)を鏡映する。
            searchReplace (tuple[str, str] | None): 新しいjoint名の置換 ``(検索, 置換)``。
                例: ``("L_", "R_")``。NoneならMayaの自動命名。

        Returns:
            Joint: 新しいチェーンのルートjoint。チェーン全体は ``getChildren(allDescendents=True)``
                や :meth:`getChainFromHere` で取得する。

        Raises:
            TypeError: axisが文字列・int以外、behaviorがbool以外、searchReplaceが2つの文字列の並び・None以外の場合。
            ValueError: axisが対応しない値、またはsearchReplaceの検索文字列が空の場合。
            RuntimeError: 無効なjoint、またはMayaが鏡映を拒否した場合。

        Note:
            Mayaの ``mirrorJoint`` は、searchReplaceで名前空間を含めて置換しない限り新しいjointを
            現在の名前空間へ置く。
        """
        flag = "mirror" + _MIRROR_PLANES[_mirror_axis(axis)]
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
            if target.getSource() != origin:
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
                origin = target.getSource()
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

    def getPreferredAngle(self, *, unit="deg"):
        """IKが曲げる向きの基準になる preferredAngle を取得する。

        Args:
            unit (str): 戻り値の角度の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン。

        Returns:
            list[float]: XYZの角度。

        Raises:
            TypeError: unitが文字列・None以外の場合。
            ValueError: unitが未対応の単位名の場合。
            RuntimeError: jointが無効な場合。
        """
        self._require_valid("get the preferred angle of")
        return [float(value) for value in self.getPlug("preferredAngle").get(unit=unit)]

    def setPreferredAngle(self, value=None, *, unit="deg"):
        """IKが曲げる向きの基準になる preferredAngle を設定する。

        省略時は今の rotate を preferredAngle にする(Skeleton > Set Preferred Angle、
        ``cmds.joint(edit=True, setPreferredAngles=True)`` と同じ)。子孫のjointには適用しない。

        Args:
            value (Sequence[float] | None): XYZの角度。Noneは今のrotate。
            unit (str): valueの角度の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン。

        Returns:
            Joint: 自身。

        Raises:
            TypeError: valueが3つの数値の列・None以外、またはunitが文字列・None以外の場合。
            ValueError: valueの成分数が3でない・有限でない、またはunitが未対応の単位名の場合。
            RuntimeError: jointが無効、またはpreferredAngleがロック・入力接続で書き込めない場合。
        """
        with undoChunk("mlibJointSetPreferredAngle"):
            self._require_valid("set the preferred angle of")
            if value is None:
                value, unit = tuple(self.getPlug("rotate").get(unit="rad")), "rad"
            else:
                value = _finite_vector(value, 3, "value")
            self.getPlug("preferredAngle").set(value, unit=unit)
            return self

    def assumePreferredAngles(self, children=True):
        """rotateをpreferredAngleの値へ戻す。

        Skeleton > Assume Preferred Angle、``cmds.joint(edit=True, assumePreferredAngles=True)`` と同じ。

        Args:
            children (bool): Trueは子孫のjointにも適用する。Falseは自身だけ。既定True。

        Returns:
            Joint: 自身。

        Raises:
            TypeError: childrenがbool以外の場合。
            RuntimeError: jointが無効、またはMayaが書込みを拒否した場合。

        Note:
            Undo有効時に1回のUndoで戻る。rotateがロック・入力接続されたjointの扱いはMayaに従う。
        """
        _require_bool(children, "children")
        self._require_valid("assume the preferred angles of")
        with undoChunk("mlibJointAssumePreferredAngles"):
            cmds.joint(self.getFullName(), edit=True, assumePreferredAngles=True, children=children)
        return self

    def getDegreesOfFreedom(self):
        """回転できる軸(jointTypeX/Y/Z が有効な軸)を取得する。

        Returns:
            str: ``"xyz"`` の部分列(XYZの順)。全軸が固定なら空文字列。

        Raises:
            RuntimeError: jointが無効な場合。
        """
        self._require_valid("get the degrees of freedom of")
        return "".join(axis for axis in "xyz" if self.getPlug("jointType" + axis.upper()).get())

    def setDegreesOfFreedom(self, axes):
        """回転できる軸(jointTypeX/Y/Z)を設定する。指定しない軸は固定する。

        Args:
            axes (str): ``"xyz"``・``"xz"`` 等の軸名の並び(順不同、大文字小文字を問わない)。空文字列は全軸を固定する。

        Returns:
            Joint: 自身。

        Raises:
            TypeError: axesが文字列でない場合。
            ValueError: x・y・z以外の文字、または同じ軸を重ねて含む場合。
            RuntimeError: jointが無効、またはjointTypeがロック・入力接続で書き込めない場合。

        Note:
            Undo有効時に1回のUndoで戻る。fast引数は持たない。
        """
        if not isinstance(axes, str):
            raise TypeError(f"axes must be a string such as 'xyz': {axes!r}")
        lowered = axes.lower()
        if set(lowered) - set("xyz") or len(set(lowered)) != len(lowered):
            raise ValueError(f"axes must be a combination of 'x', 'y' and 'z' without repeats: {axes!r}")
        self._require_valid("set the degrees of freedom of")
        plugs = [self.getPlug("jointType" + axis.upper()) for axis in "XYZ"]
        # 一部の軸だけ書き換わるのを避けるため、3軸とも書き込めるか先に確かめる。
        for plug in plugs:
            require_writable(plug.mplug())
        with undoChunk("mlibJointSetDegreesOfFreedom"):
            for axis, plug in zip("xyz", plugs):
                plug.set(axis in lowered)
        return self

    def getInverseScale(self):
        """inverseScaleの無次元XYZ値を、独立したScaleとして取得する。

        アトリビュート値の逆数は計算せず、SSCの有効フラグによって値を変えない。

        Returns:
            Scale: inverseScaleの新しい値。無効ノードではXYZとも0。
                実際の補償状態や有効性を判定する戻り値ではない。
        """
        return Scale(*self._compound_values("inverseScale"))

    def getDepth(self):
        """joint 階層内の深さを取得する。

        Returns:
            int: root joint を 0 とする階層深度。
        """
        depth = 0
        parent = self.getParent() if self.isValid() else None
        while isinstance(parent, Joint):
            depth += 1
            parent = parent.getParent()
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

        全対象の登録・移送条件を先に検査し、取得順にSkinCluster.removeInfluenceと同じ処理で解除する。
        ウェイトのロックは一時的に外して解除し、元の状態へ戻す。ngSkinTools2のレイヤーはレイヤーごとに移送する。
        Undo有効時は一つのチャンクへ記録する。fast引数は持たない。後続の失敗で先行処理は戻さない。

        Args:
            skinCluster (SkinCluster | str | None): 対象。Noneは接続する全skinCluster。
            transferToParent (bool): Trueは最も近い祖先influenceへ加算する。
                False、または移送先がなければ標準の再配分に任せる。
            force (bool): 不正ウェイトを修復してから解除する。修復時に正規化は行わない。

        Returns:
            Joint: 自身。対象省略で未スキニングなら変更しない。

        Raises:
            TypeError: transferToParent・forceがbool以外の場合。
            ValueError: 未登録、または最後のinfluenceを解除する場合。
            RuntimeError: 無効joint、ウェイト要素のロック・入力接続、または編集失敗。
        """
        with undoChunk("mlibJointRemoveInfluence"):
            from .skinCluster import SkinCluster
            self._require_valid("remove")
            _require_bool(transferToParent, "transferToParent")
            _require_bool(force, "force")
            skins = self.getSkinClusters() if skinCluster is None else [skinCluster if isinstance(skinCluster, SkinCluster) else SkinCluster(skinCluster)]
            _remove_influences([(skin, [self]) for skin in skins], transferToParent, force)
            return self

    def delete(self, *, safe=False, fast=False, removeInfluence=True, transferToParent=True, force=False):
        """influenceの登録を解除してから、自身と子孫を削除する。

        Maya標準の削除では、消えたjointの列にウェイトが残る。このメソッドは自身とDAG子孫のjointを
        :meth:`removeInfluence` と同じ処理で各skinClusterから外し、ウェイトを残る最も近い祖先influenceへ
        移してから削除する。残る祖先が無ければ標準の再配分に任せ、全influenceが消えるskinClusterは解除せず
        Maya標準の削除に任せる。ウェイトのロックは一時的に外して解除し、元の状態へ戻す。全対象を変更前に検査し、
        Undo有効時は1回で戻せる。ngSkinTools2のレイヤーはレイヤーごとに移送する。ngSkinTools2を使えない場合の
        レイヤーは拒否せず、skinClusterのウェイトだけを書き換える。``mlib.delete`` はこの解除を行わず、Maya標準の削除のまま。

        Args:
            safe (bool): Trueなら自身またはDAG子孫にDG接続がある場合は何もしない(skinClusterの接続も含む)。
            fast (bool): TrueはUndoなしの更新。既定False。ウェイトの書込みと削除はOpenMayaで行い、
                OpenMayaに無いinfluenceの登録解除だけをUndoへ記録しないcmdsで行う。結果は通常と同じ。
            removeInfluence (bool): Falseは解除せずMaya標準の削除だけを行う。
            transferToParent (bool): Falseはウェイトを祖先へ移さず標準の再配分に任せる。
            force (bool): 不正ウェイトを修復してから解除する。修復時に正規化は行わない。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: safe・fast・removeInfluence・transferToParent・forceがbool以外の場合。
            ValueError: 移送するウェイトに負値・非有限値がある場合(何も変更しない)。
            RuntimeError: 対象が無効、ロック・参照のノードを含む(何も変更しない)、ウェイト要素の
                ロック・入力接続がある、またはMayaが編集を拒否した場合。
        """
        with _edit_context("mlibJointDelete", fast):
            _delete_joints([self], safe, fast, removeInfluence, transferToParent, force)

    def isInfluenceLocked(self):
        """スキンのウェイトをロック(lockInfluenceWeights)しているかを判定する。

        lockInfluenceWeights は skinCluster へバインドしたときに追加されるアトリビュート。

        Returns:
            bool: ロックしていればTrue。アトリビュートが無い(どの skinCluster のinfluenceにもなっていない)場合はFalse。
        """
        return self.hasAttr("lockInfluenceWeights") and bool(self.getPlug("lockInfluenceWeights").get())

    def setInfluenceLocked(self, state=True):
        """スキンのウェイトのロック(lockInfluenceWeights)を設定する。

        全ての skinCluster で同じ値になる(lockInfluenceWeights は joint 側のアトリビュート)。
        複数をまとめて設定するなら :meth:`SkinCluster.setInfluencesLocked
        <mlib.nodes.skinCluster.SkinCluster.setInfluencesLocked>` を使う。fast引数は持たない。

        Args:
            state (bool): Trueはロック、Falseはロックの解除。既定True。

        Returns:
            Joint: 自身。

        Raises:
            TypeError: stateがbool以外の場合。
            RuntimeError: lockInfluenceWeights が無い(influenceになっていない)、またはロック・入力接続されている場合。
        """
        with undoChunk("mlibJointSetInfluenceLocked"):
            _require_bool(state, "state")
            if not self.hasAttr("lockInfluenceWeights"):
                raise RuntimeError(f"Joint is not an influence of any skinCluster: {self.getFullName()}")
            self.getPlug("lockInfluenceWeights").set(state)
            return self

    def getBoneSegments(self, worldSpace=_UNSET, *, ws=_UNSET):
        """自身から子の joint までのボーンの線分を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間(親側の空間)。既定True。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[tuple[Vector, Vector]]: 子の joint ごとの (始点, 終点)。始点は自身の位置(回転ピボット)。
                子の joint が無い場合は始点と同じ点を終点にした1組だけを返す。位置は cm。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=True)
        ws = _world_space(worldSpace)
        children = self.getChildren(type="joint")
        if ws:
            ends = [child.getTranslation(worldSpace=True) for child in children]
        else:
            # 子の位置は自身の空間で表されるため、自身のマトリクスで親側の空間へ写す。
            matrix = self.getMatrix()
            ends = [matrix.transformPoint(child.getTranslation()) for child in children]
        start = self.getTranslation(worldSpace=ws)
        segments = [(Vector(start.x, start.y, start.z), Vector(end.x, end.y, end.z)) for end in ends]
        return segments or [(Vector(start.x, start.y, start.z), Vector(start.x, start.y, start.z))]

    def getTransferTarget(self, skin):
        """ウェイト移送先となる最も近い親 influence を探索する。

        Args:
            skin (SkinCluster): influence の有無を調べる skinCluster。

        Returns:
            str | None: 移送先の親 joint 名。見つからない場合は ``None``。
        """
        ancestor = self.getParent() if self.isValid() else None
        while isinstance(ancestor, Joint):
            if skin.hasInfluence(ancestor.getName()):
                return ancestor.getName()
            ancestor = ancestor.getParent()
        return None

    def reparentChildren(self, parentJoint):
        """子 joint を指定した親 joint へ付け替える。

        fast引数は持たない(ワールド位置を保つ付け替えはcmds.parentの方が速いため)。

        Args:
            parentJoint (str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug):
                直接の子 joint を付け替える親ノード。``Node._input_name`` と同じ規則で解決する
                (Plug・MPlug は所有ノード)。

        Returns:
            Joint: 自身。

        Raises:
            TypeError: parentJointが対応しない型の場合。
            ValueError: parentJointが空文字列・無効な対象の場合。
            RuntimeError: parentJointを解決できない、またはMayaが親変更を拒否した場合。
        """
        with undoChunk("mlibJointReparentChildren"):
            parent_name = Node._input_name(parentJoint)
            for child_joint in self.getChildren(type="joint"):
                cmds.parent(child_joint.getFullName(), parent_name)
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
                children = current.getChildren(type="joint")
                if len(children) != 1:
                    return chain
                current = children[0]
                chain.append(current)
        target = to if isinstance(to, Joint) else Joint(to)
        if not self.isAncestorOf(target):
            raise ValueError("to must be a descendant of this joint")
        chain = [self]
        current = self
        while current.getUuid() != target.getUuid():
            next_joint = next(
                (
                    child for child in current.getChildren(type="joint")
                    if child.getUuid() == target.getUuid() or child.isAncestorOf(target)
                ),
                None,
            )
            if next_joint is None:
                raise ValueError("to must be a descendant of this joint")
            chain.append(next_joint)
            current = next_joint
        return chain

    def insertJoints(self, count):
        """自身と唯一の子jointの間に、count 個のjointを等間隔に挿入する。

        新しいjointは自身から子へ向かう順に親子につなぎ、元の子jointを最後の新しいjointの子へ付け替える
        (子のワールドの位置・向きは保つ)。新しいjointのワールドの向きは自身と同じにする
        (jointOrient・rotate は0、rotateOrder・radius・segmentScaleCompensate は自身の値を写す)。
        inverseScale は親jointの scale へ接続する。名前は ``<自身の名前>_insert#``(``#`` はMayaの連番)。
        fast引数は持たない。Undo有効時は1回で戻せる。

        Args:
            count (int): 挿入する数。1以上。

        Returns:
            list[Joint]: 挿入したjoint。自身に近い順。

        Raises:
            TypeError: count が int でない場合。
            ValueError: count が1未満、または子jointが無い・2つ以上ある場合。
            RuntimeError: 自身が無効、またはMayaが作成・親の変更を拒否した場合。
        """
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError(f"count must be an int, got {type(count).__name__}")
        if count < 1:
            raise ValueError(f"count must be 1 or more, got {count}")
        self._require_valid("insert joints under")
        children = self.getChildren(type="joint")
        if len(children) != 1:
            raise ValueError(f"Joint must have exactly one child joint, got {len(children)}: {self.getFullName()}")
        child = children[0]
        start = self.getTranslation(worldSpace=True)
        end = child.getTranslation(worldSpace=True)
        base = self.getName().split("|")[-1] + "_insert#"
        name = self.getFullName()
        unit = om2.MDistance.uiUnit()
        with undoChunk("mlibJointInsertJoints"):
            created = []
            parent = name
            for number in range(1, count + 1):
                joint = cmds.createNode("joint", name=base, parent=parent, skipSelect=True)
                joint = cmds.ls(joint, long=True)[0]
                for attribute in ("rotateOrder", "radius", "segmentScaleCompensate"):
                    cmds.setAttr(joint + "." + attribute, cmds.getAttr(name + "." + attribute))
                cmds.connectAttr(parent + ".scale", joint + ".inverseScale")
                ratio = number / (count + 1.0)
                position = [om2.MDistance(a + (b - a) * ratio).asUnits(unit) for a, b in zip(start, end)]
                cmds.xform(joint, worldSpace=True, translation=position)
                created.append(joint)
                parent = joint
            cmds.parent(child.getFullName(), parent)
            return [Joint(joint) for joint in created]

    def getPolePosition(self, distance=None):
        """自身・子・孫のjointの3点の平面上で、チェーンが曲がる側へ離したワールドの位置を返す。

        自身から孫への線分へ子の位置から下ろした垂線の向き(曲がる側)へ、子の位置から distance 離した点。
        IKの poleVector のコントローラを置く位置に使う。シーンは変更しない。

        Args:
            distance (float | None): 子の位置から離す距離(cm)。正の有限な数。
                Noneはチェーンの長さ(自身→子と子→孫の長さの和)。

        Returns:
            Vector: ワールド空間の位置(cm)。

        Raises:
            TypeError: distance が数値・None以外の場合。
            ValueError: distance が正の有限な数でない、子・孫のjointがちょうど1つずつでない、
                または3点がほぼ一直線(曲がる向きが決まらない)の場合。
            RuntimeError: 自身が無効な場合。
        """
        if distance is not None:
            if isinstance(distance, bool) or not isinstance(distance, (int, float)):
                raise TypeError(f"distance must be a number or None, got {type(distance).__name__}")
            if not math.isfinite(distance) or distance <= 0:
                raise ValueError(f"distance must be positive and finite, got {distance}")
        self._require_valid("get the pole position of")
        chain = [self]
        for _ in range(2):
            children = chain[-1].getChildren(type="joint")
            if len(children) != 1:
                raise ValueError(f"Joint must have exactly one child joint, got {len(children)}: {chain[-1].getFullName()}")
            chain.append(children[0])
        start, middle, end = (om2.MVector(joint.getTranslation(worldSpace=True)) for joint in chain)
        length = (middle - start).length() + (end - middle).length()
        line = end - start
        if line.length() <= 1e-9 * max(length, 1.0):
            raise ValueError("The three joints are collinear")
        foot = start + line * (((middle - start) * line) / (line * line))
        bend = middle - foot
        if bend.length() <= 1e-6 * max(length, 1e-9):
            raise ValueError("The three joints are collinear")
        result = middle + bend.normal() * (length if distance is None else float(distance))
        return Vector(result.x, result.y, result.z)

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

    def _apply_rotate_transfer(self, values, to_orient=False):
        """検証済みの回転移送値をcmdsで適用する。

        Args:
            values (tuple | None): 現在のUI角度単位の3成分。Noneなら更新しない。
            to_orient (bool): TrueならjointOrientへ移しrotateを0にする。

        Returns:
            None: 値を返さない。
        """
        if values is None:
            return
        set_attr(self.getFullName() + ".jointOrient", *(values if to_orient else (0, 0, 0)))
        set_attr(self.getFullName() + ".rotate", *((0, 0, 0) if to_orient else values))

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

    def removeInfluence(self, skinCluster=None, *, transferToParent=True, force=False):
        """全jointのinfluence登録を外す。jointノードは残す。

        :meth:`Joint.removeInfluence` と同じ規則で、深いjointから順に解除する。親子を同時に外すと、ウェイトは
        外さずに残る最も近い祖先influenceへ集まる。ウェイトは最終の移送先へ1回で書き込み、登録もまとめて解除する。
        ウェイトのロックは一時的に外して解除し、元の状態へ戻す。ngSkinTools2のレイヤーはレイヤーごとに移送する。
        全対象を変更前に検査し、Undo有効時は1回で戻せる。

        Args:
            skinCluster (SkinCluster | str | None): 対象。Noneは各jointが登録された全skinCluster。
            transferToParent (bool): :meth:`Joint.removeInfluence` と同じ。
            force (bool): :meth:`Joint.removeInfluence` と同じ。

        Returns:
            Joints: 自身。対象省略で未スキニングのjointは変更しない。

        Raises:
            TypeError: transferToParent・forceがbool以外の場合。
            ValueError: 未登録のjointを含む、またはskinClusterの全influenceを外す場合(何も変更しない)。
            RuntimeError: 無効なjointを含む、ウェイト要素のロック・入力接続、またはMayaの編集失敗。
        """
        from .skinCluster import SkinCluster  # skinClusterがjointをimportするため循環を避ける

        with undoChunk("mlibJointsRemoveInfluence"):
            _require_bool(transferToParent, "transferToParent")
            _require_bool(force, "force")
            for joint in self._items:
                joint._require_valid("remove")
            if skinCluster is None:
                groups = _influences_by_skin(self._items)
            else:
                groups = [(skinCluster if isinstance(skinCluster, SkinCluster) else SkinCluster(skinCluster),
                           list(self._items))]
            for skin, joints in groups:
                if joints and len(joints) >= len(skin.getInfluences()):
                    raise ValueError("Cannot remove every influence")
            _remove_influences(groups, transferToParent, force)
            return self

    def delete(self, *, safe=False, fast=False, removeInfluence=True, transferToParent=True, force=False):
        """全jointのinfluenceを解除してから、全jointと子孫を1回で削除する。

        解除の規則は :meth:`Joint.delete` と同じ。一緒に消える親子をまとめて解除するため、ウェイトは残る最も近い
        祖先influenceへ集まる。全対象を変更前に検査し、Undo有効時は1回で戻せる。
        ノードの種類を問わない一括削除で解除が要らないときは ``mlib.delete`` を使う。

        Args:
            safe (bool): Trueなら自身またはDAG子孫にDG接続があるjointだけを除いて削除する。
            fast (bool): :meth:`Joint.delete` と同じ。
            removeInfluence (bool): :meth:`Joint.delete` と同じ。
            transferToParent (bool): :meth:`Joint.delete` と同じ。
            force (bool): :meth:`Joint.delete` と同じ。

        Returns:
            None: 値を返さない。空のコレクションは何もしない。

        Raises:
            TypeError: :meth:`Joint.delete` と同じ。
            ValueError: :meth:`Joint.delete` と同じ。
            RuntimeError: :meth:`Joint.delete` と同じ。
        """
        with _edit_context("mlibJointsDelete", fast):
            _delete_joints(list(self._items), safe, fast, removeInfluence, transferToParent, force)

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
