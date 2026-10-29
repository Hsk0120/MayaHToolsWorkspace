# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""joint ラッパーと joint コレクションを提供する。"""

import math
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..core.fastWrite import set_attr
from ..decorator import _edit_context, _require_bool, undoChunk
from ..maths import EulerRotate, Matrix, Scale
from .node import Node, Nodes
from .transform import Transform, _closest_euler
from typing import Any, Iterable, Iterator
from mlib.components.component import Component
from mlib.nodes.ikHandle import IkHandle
from mlib.nodes.skinCluster import SkinCluster
from mlib.nodes.skinCluster import SkinClusters
from mlib.plugs.plug import Plug
from typing import overload



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
    def jointOrientToRotate(self, *, fast: bool = ...) -> Joint:
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
        ...
    def freezeRotate(self, *, fast: bool = ...) -> Joint:
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
    def getInverseScale(self) -> Scale:
        """inverseScaleの無次元XYZ値を、独立したScaleとして取得する。

        アトリビュート値の逆数は計算せず、SSCの有効フラグによって値を変えない。

        Returns:
            Scale: inverseScaleの新しい値。無効ノードではXYZとも0。
                実際の補償状態や有効性を判定する戻り値ではない。
        """
        ...
    def getParentJointName(self) -> str | None:
        """親 joint の名前を取得する。

        Returns:
            str | None: 親 joint 名。親が joint でない場合は ``None``。
        """
        ...
    def getChildJointNames(self) -> list[str]:
        """直接の子 joint 名を取得する。

        Returns:
            list[str]: 子 joint 名のリスト。
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
        ...
    def getTransferTarget(self, skin: SkinCluster) -> str | None:
        """ウェイト移送先となる最も近い親 influence を探索する。

        Args:
            skin (SkinCluster): influence の有無を調べる skinCluster。

        Returns:
            str | None: 移送先の親 joint 名。見つからない場合は ``None``。
        """
        ...
    def reparentChildren(self, parentJoint: str | Node | Plug | Component | om2.MObject | om2.MDagPath | om2.MPlug, *, fast: bool = ...) -> Joint:
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
    def getIkHandles(self) -> list[IkHandle]:
        """自身を start joint とする IK ハンドルを取得する。

        自身が IK チェーンの途中や末端の joint である場合は対象にならない。
        Maya は IK ハンドルの ``startJoint`` への接続を通じてのみ joint から
        IK ハンドルを解決できるため。

        Returns:
            list[IkHandle]: 自身を start joint とする IkHandle。無ければ空リスト。
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
    def _apply_rotate_transfer(self, values: tuple | None, to_orient: bool = ..., *, fast: bool = ...) -> None:
        """検証済みの回転移送値を、指定した更新モードで適用する。

        Args:
            values (tuple | None): 現在のUI角度単位の3成分。Noneなら更新しない。
            to_orient (bool): TrueならjointOrientへ移しrotateを0にする。
            fast (bool): TrueならOpenMayaで直接更新する。

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
    def sortedByDepth(self) -> Joints:
        """深い joint から順に並べた新しいコレクションを返す。

        Returns:
            Joints: 子 joint を先に処理できる深さ順コレクション。
        """
        ...
    def getSkinClusters(self) -> SkinClusters:
        """全 joint に関連する skinCluster を取得する。

        Returns:
            SkinClusters: 重複を除いた skinCluster コレクション。
        """
        ...
