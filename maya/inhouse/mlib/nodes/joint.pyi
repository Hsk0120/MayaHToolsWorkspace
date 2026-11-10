# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""joint ラッパーと joint コレクションを提供する。"""

import math
from contextlib import contextmanager
from typing import Any, Dict, List
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..core.fastWrite import set_attr
from ..core.nodeEdit import check_deletion, delete_nodes
from ..decorator import _edit_context, _require_bool, undoChunk
from ..maths import EulerRotate, Matrix, Scale, Vector
from ..util import _MIRROR_PLANES, _finite_vector, _mirror_axis, _world_space
from .node import Node, Nodes
from .transform import Transform, _closest_euler
from typing import Any, Iterable, Iterator, Sequence
from mlib._stubtypes import GeneratorContextManager
from mlib.components.component import Component
from mlib.nodes.ikHandle import IkHandle
from mlib.nodes.skinCluster import SkinCluster
from mlib.nodes.skinCluster import SkinClusters
from mlib.plugs.plug import Plug
from typing import overload

_ORIENTATIONS: tuple
_SECONDARY_AXES: tuple

def _orient_flags(orientation: str, secondaryAxisOrient: str, children: bool, zeroScaleOrient: bool) -> dict:
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
    ...

def _unlocked_influences(skins: Iterable[SkinCluster], fast: bool = ...) -> GeneratorContextManager[None]:
    """skinClusterのウェイトのロックを一時的に外し、抜けるときに元へ戻す。

    Args:
        skins (Iterable[SkinCluster]): ロックを外すskinCluster。
        fast (bool): Trueはロックの切替えをUndoへ記録しない。

    Yields:
        None: 値を渡さない。

    Raises:
        RuntimeError: lockInfluenceWeightsがロック・入力接続されていて切り替えられない場合。何も変更しない。
    """
    ...

def _influences_by_skin(joints: Iterable[Joint]) -> list[tuple[SkinCluster, list[Joint]]]:
    """jointを、登録先のskinClusterごとにまとめる。

    Args:
        joints (Iterable[Joint]): 調べるjoint。

    Returns:
        list[tuple[SkinCluster, list[Joint]]]: skinClusterと、そこへ登録されたjoint。
    """
    ...

def _remove_influences(groups: list[tuple[SkinCluster, list[Joint]]], transfer_to_parent: bool, force: bool, fast: bool = ..., deleting: bool = ...) -> None:
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
    ...

def _delete_joints(joints: Sequence[Joint], safe: bool, fast: bool, remove_influence: bool, transfer_to_parent: bool, force: bool) -> None:
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
    ...


class Joint(Transform):
    """Jointの参照と、回転移送・スケール補償の操作を提供する。

    マトリクス・TRSはTransformを継承し、rotateAxis・jointOrient・segmentScaleCompensateを考慮する。
    SSCの切替、inverseScaleの接続、姿勢を保つ回転移送は独立した操作。
    """
    def getSegmentScaleCompensate(self) -> bool:
        """segmentScaleCompensateの有効フラグを取得する。

        inverseScaleに親のscaleが接続されているか、補償が期待どおり効くかは検査しない。

        Returns:
            bool: segmentScaleCompensateの現在値。
        """
        ...
    def setSegmentScaleCompensate(self, state: bool, *, fast: bool = ...) -> Joint:
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
        ...
    def getJointOrient(self) -> EulerRotate:
        """jointOrientをXYZ順・rad単位の独立したEulerRotateとして取得する。

        ノードのrotateOrderやUI角度単位は使わない。
        rotateやrotateAxis、親の回転は合成しない。

        Returns:
            EulerRotate: jointOrientの新しい値。無効ノードではXYZとも0。
                有効性の確認にはisValidを使う。
        """
        ...
    def jointOrientToRotate(self) -> Joint:
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
        ...
    def freezeRotate(self) -> Joint:
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
        ...
    def orient(self, orientation: str = ..., secondaryAxisOrient: str = ..., children: bool = ..., zeroScaleOrient: bool = ...) -> Joint:
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
        ...
    def mirror(self, axis: str | int = ..., behavior: bool = ..., searchReplace: tuple[str, str] | None = ...) -> Joint:
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
        ...
    def connectInverseScale(self, source: object | None = ..., force: bool = ..., *, fast: bool = ...) -> Joint:
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
        ...
    def disconnectInverseScale(self, *, fast: bool = ...) -> Joint:
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
        ...
    def getRadius(self) -> float:
        """ジョイント個別の表示半径を取得する。

        Returns:
            float: radiusアトリビュート値。Maya全体のjointDisplayScaleとは別の値。
        """
        ...
    def setRadius(self, value: float, *, fast: bool = ...) -> Joint:
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
        ...
    def setPreferredAngle(self, value: Sequence[float] | None = ..., *, unit: str = ...) -> Joint:
        """IKが曲げる向きの基準になる preferredAngle を設定する。

        省略時は今の rotate を preferredAngle にする(Skeleton > Set Preferred Angle、
        ``cmds.joint(edit=True, setPreferredAngles=True)`` と同じ)。子孫のjointには適用しない。

        Args:
            value (Sequence[float] | None): XYZの角度。Noneは今のrotate。
            unit (str): valueの角度の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン。

        Returns:
            Joint: 自身。

        Raises:
            TypeError: valueが3つの数値の列・None以外、またはunitが文字列以外の場合。
            ValueError: valueの成分数が3でない・有限でない、またはunitが未対応の単位名の場合。
            RuntimeError: jointが無効、またはpreferredAngleがロック・入力接続で書き込めない場合。
        """
        ...
    def getInverseScale(self) -> Scale:
        """inverseScaleの無次元XYZ値を、独立したScaleとして取得する。

        アトリビュート値の逆数は計算せず、SSCの有効フラグによって値を変えない。

        Returns:
            Scale: inverseScaleの新しい値。無効ノードではXYZとも0。
                実際の補償状態や有効性を判定する戻り値ではない。
        """
        ...
    def getDepth(self) -> int:
        """joint 階層内の深さを取得する。

        Returns:
            int: root joint を 0 とする階層深度。
        """
        ...
    def getSkinClusters(self) -> list[SkinCluster]:
        """この joint に接続する skinCluster を取得する。

        Returns:
            list[SkinCluster]: 重複を除いた skinCluster ラッパー。
        """
        ...
    def removeInfluence(self, skinCluster: SkinCluster | str | None = ..., *, transferToParent: bool = ..., force: bool = ...) -> Joint:
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
        ...
    def delete(self, *, safe: bool = ..., fast: bool = ..., removeInfluence: bool = ..., transferToParent: bool = ..., force: bool = ...) -> None:
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
        ...
    def isInfluenceLocked(self) -> bool:
        """スキンのウェイトをロック(lockInfluenceWeights)しているかを判定する。

        lockInfluenceWeights は skinCluster へバインドしたときに追加されるアトリビュート。

        Returns:
            bool: ロックしていればTrue。アトリビュートが無い(どの skinCluster のinfluenceにもなっていない)場合はFalse。
        """
        ...
    def setInfluenceLocked(self, state: bool = ...) -> Joint:
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
        ...
    def getBoneSegments(self, worldSpace: bool = ...) -> list[tuple[Vector, Vector]]:
        """自身から子の joint までのボーンの線分を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間(親側の空間)。既定True。

        Returns:
            list[tuple[Vector, Vector]]: 子の joint ごとの (始点, 終点)。始点は自身の位置(回転ピボット)。
                子の joint が無い場合は始点と同じ点を終点にした1組だけを返す。位置は cm。
        """
        ...
    def getTransferTarget(self, skin: SkinCluster) -> str | None:
        """ウェイト移送先となる最も近い親 influence を探索する。

        Args:
            skin (SkinCluster): influence の有無を調べる skinCluster。

        Returns:
            str | None: 移送先の親 joint 名。見つからない場合は ``None``。
        """
        ...
    def reparentChildren(self, parentJoint: str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug) -> Joint:
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
        ...
    def getChainFromHere(self, to: Joint | str | None = ...) -> list[Joint]:
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
        ...
    def insertJoints(self, count: int) -> list[Joint]:
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
        ...
    def getPolePosition(self, distance: float | None = ...) -> Vector:
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
        ...
    def getIkHandles(self) -> list[IkHandle]:
        """自身を start joint とする IK ハンドルを取得する。

        自身が IK チェーンの途中や末端の joint である場合は対象にならない。
        Maya は IK ハンドルの ``startJoint`` への接続を通じてのみ joint から
        IK ハンドルを解決できるため。

        Returns:
            list[IkHandle]: 自身を start joint とする IkHandle。無ければ空リスト。
        """
        ...
    def _orient(self, flags: dict) -> None:
        """検証済みのフラグで向きを揃え、末端jointのjointOrientを0にする。

        Args:
            flags (dict): :func:`_orient_flags` が返したcmds.jointのフラグ。

        Returns:
            None: 値を返さない。
        """
        ...
    def _joint_rotate_order(self) -> int:
        """Maya の rotateOrder を API の回転順序へ変換する。

        rotateOrder の番号(0=xyz〜5=zyx)は MEulerRotation.kXYZ〜kZYX と同じ並び。

        Returns:
            int: rotateOrder に対応する Maya API 2.0 の MEulerRotation 定数。
        """
        ...
    def _joint_rotate_transfer_values(self, to_orient: bool = ...) -> tuple[float, float, float] | None:
        """書込み可否を検証し、合成後の回転を現在の角度単位で返す。

        Args:
            to_orient (bool): TrueでjointOrient用XYZ、FalseでrotateOrderのrotate用。

        Returns:
            tuple[float, float, float] | None: 合成値。移送元が0ならNone。

        Raises:
            RuntimeError: 無効joint、ロック、入力接続、書込み不可の場合。
        """
        ...
    def _apply_rotate_transfer(self, values: tuple | None, to_orient: bool = ...) -> None:
        """検証済みの回転移送値をcmdsで適用する。

        Args:
            values (tuple | None): 現在のUI角度単位の3成分。Noneなら更新しない。
            to_orient (bool): TrueならjointOrientへ移しrotateを0にする。

        Returns:
            None: 値を返さない。
        """
        ...
    def _rotate_quaternion(self, attribute: str) -> om2.MQuaternion:
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
        ...
    def _remove_segment_scale_compensation(self, matrix: Matrix) -> Matrix:
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
        ...
    def _rotate_reference(self, reference: om2.MEulerRotation) -> om2.MEulerRotation:
        """:meth:`getRotate` が Euler の解を選ぶ基準を返す。

        joint の getRotate は jointOrient と rotateAxis を含む回転で rotate チャンネルとは
        別の回転なので、チャンネル値ではなく 0 回転(ノードの rotateOrder)を基準にする。

        Args:
            reference (om2.MEulerRotation): 現在の rotate チャンネル値(順序だけを使う)。

        Returns:
            om2.MEulerRotation: 0 回転。順序はノードの rotateOrder。
        """
        ...
    def _channel_rotate(self, quaternion: om2.MQuaternion, reference: om2.MEulerRotation) -> om2.MEulerRotation:
        """ローカルマトリクスの回転から jointOrient と rotateAxis を除き、rotate の値へ変換する。

        Maya の joint の回転は rotateAxis、rotate、jointOrient の順に適用されるため、
        rotate = rotateAxis⁻¹ · マトリクスの回転 · jointOrient⁻¹(om2 のクォータニオンの積の順序)。

        Args:
            quaternion (om2.MQuaternion): ローカルマトリクスの回転。
            reference (om2.MEulerRotation): 現在の rotate チャンネル値。

        Returns:
            om2.MEulerRotation: ノードの rotateOrder で表した、reference に最も近い解。
        """
        ...
    def _apply_local_matrix(self, matrix: Matrix, scale_reference: Iterable[float] | None = ..., *, fast: bool = ...) -> None:
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
        ...
    def _compound_values(self, attribute: str, angle: bool = ...) -> tuple[float, float, float]:
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
        ...


class Joints(Nodes):
    """Joint参照を保持するコレクション。型・重複規則はNodesに従う。"""
    def __iter__(self) -> Iterator[Joint]: ...
    @overload
    def __getitem__(self, index: int) -> Joint: ...
    @overload
    def __getitem__(self, index: slice) -> Joints: ...
    item_class: Any
    _items: List[Joint]
    def sortedByDepth(self) -> Joints:
        """深い joint から順に並べた新しいコレクションを返す。

        Returns:
            Joints: 子 joint を先に処理できる深さ順コレクション。
        """
        ...
    def orient(self, orientation: str = ..., secondaryAxisOrient: str = ..., children: bool = ..., zeroScaleOrient: bool = ...) -> Joints:
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
        ...
    def removeInfluence(self, skinCluster: SkinCluster | str | None = ..., *, transferToParent: bool = ..., force: bool = ...) -> Joints:
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
        ...
    def delete(self, *, safe: bool = ..., fast: bool = ..., removeInfluence: bool = ..., transferToParent: bool = ..., force: bool = ...) -> None:
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
        ...
    def setRadius(self, value: float, *, fast: bool = ...) -> Joints:
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
        ...
    def setSegmentScaleCompensate(self, state: bool, *, fast: bool = ...) -> Joints:
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
        ...
    def getSkinClusters(self) -> SkinClusters:
        """全 joint に関連する skinCluster を取得する。

        Returns:
            SkinClusters: 重複を除いた skinCluster コレクション。
        """
        ...
