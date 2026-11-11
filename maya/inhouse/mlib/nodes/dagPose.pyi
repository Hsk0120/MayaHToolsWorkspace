# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""DAG階層の保存姿勢とバインドポーズを扱う。"""

import math
import shlex
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..core.nodeEdit import require_editable
from ..core.object import Object
from ..decorator import _require_bool, undoChunk, undoTransaction
from ..maths import Matrix
from ..util import _world_space
from .node import Node, Nodes
from typing import Iterable
from mlib.nodes.skinCluster import SkinCluster



class DagPose(Node):
    """dagPoseノードの参照を保持し、DAGメンバーの保存姿勢とバインドポーズを扱う。

    membersの接続と保存マトリクス/親情報を照会・編集する。バインドポーズも同じノード型で、
    isBindPose()で区別する。reset()は保存姿勢を現在の姿勢へ更新し、restore()はシーンの
    姿勢を保存姿勢へ戻す。skinCluster.bindPreMatrixの再設定は担当しない。

    保存・復元・メンバー編集はMaya標準の ``cmds.dagPose`` を使い、fast引数は提供しない
    (Mayaの階層補完・復元規則をom2で再現しないため)。merge()は保存情報の統合と
    skinCluster.bindPoseの再接続を行う。作成は ``mlib.createDagPose`` で行う。
    """
    @classmethod
    def fromSkinCluster(cls, skinCluster: Node | str) -> DagPose | None:
        """skinClusterに接続されているバインドポーズを取得する。

        Args:
            skinCluster (Node | str): 照会するskinCluster。

        Returns:
            DagPose | None: bindPoseアトリビュートに接続されたポーズ。未接続ならNone。

        Raises:
            ValueError: skinCluster以外を指定した場合。
            RuntimeError: 無効なノード、またはdagPose以外が接続されている場合。
        """
        ...
    def isBindPose(self) -> bool:
        """バインドポーズとして保存されたノードか判定する。

        Returns:
            bool: bindPoseアトリビュートがTrueならTrue。

        Raises:
            RuntimeError: 無効なノードの場合。
        """
        ...
    def getMemberIndices(self) -> list[int]:
        """現在も接続された保存メンバーの論理番号を取得する。

        members配列の既存番号のうち、入力接続がある要素だけを返す。切断済みの空要素を除き、
        欠番を詰めずにworldMatrix・xformMatrixとの対応を保つ。

        Returns:
            list[int]: membersの論理番号の昇順。物理位置ではない。

        Raises:
            RuntimeError: 無効なノードの場合。
        """
        ...
    def getMembers(self) -> list[Node]:
        """保存対象をmembers配列の論理番号順に取得する。

        Returns:
            list[Node]: 保存対象。getMemberIndices()と同じ順序。

        Raises:
            RuntimeError: 無効なノードの場合。
        """
        ...
    def getMemberIndex(self, member: Node | str) -> int:
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
        ...
    def getMatrix(self, member: Node | str, worldSpace: bool = ...) -> Matrix:
        """指定メンバーの保存マトリクスを、独立したMatrixとして取得する。

        membersと共通の論理番号でworldMatrixまたはxformMatrixを読む。現在のTransformの
        マトリクスの照会や姿勢の復元は行わない。

        Args:
            member (Node | str): このポーズの保存メンバー。
            worldSpace (bool): Trueは保存したワールドマトリクス、Falseは保存したローカルの
                マトリクス(xformMatrix)。

        Returns:
            Matrix: 保存マトリクスの新しいコピー。変更してもポーズやシーンは変化しない。

        Raises:
            TypeError: worldSpaceがbool以外、またはmemberが対応しない型の場合。
            ValueError: このポーズのメンバーでない場合。
            RuntimeError: 無効なdagPoseの場合。
        """
        ...
    def getNotAtPose(self) -> list[Node]:
        """Mayaが保存姿勢と異なると判定したメンバーを取得する。

        ``cmds.dagPose(query=True, atPose=True)`` (Bind Poseメニューの判定と同じ)を使い、
        許容誤差はMayaの判定に従う。

        Returns:
            list[Node]: 保存姿勢と異なるメンバー。全員が保存姿勢なら空。

        Raises:
            RuntimeError: 無効なdagPoseの場合。
        """
        ...
    def isAtPose(self) -> bool:
        """全メンバーが保存姿勢にあるか判定する。

        Returns:
            bool: getNotAtPose()が空ならTrue。

        Raises:
            RuntimeError: 無効なdagPoseの場合。
        """
        ...
    def getSkinClusters(self) -> list[SkinCluster]:
        """このポーズをbindPoseとして参照するskinClusterを取得する。

        Returns:
            list[SkinCluster]: message→skinCluster.bindPoseの接続先。重複なし。

        Raises:
            RuntimeError: 無効なdagPoseの場合。
        """
        ...
    def restore(self, worldSpace: bool = ...) -> DagPose:
        """保存した姿勢へ戻す。接続やロックの解除は行わない。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。

        Returns:
            DagPose: 自身。

        Raises:
            RuntimeError: 無効なノード、またはMayaが復元を拒否した場合。
        """
        ...
    def reset(self, members: Node | str | Iterable[Node | str] | None = ...) -> DagPose:
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
        ...
    def addMembers(self, *members: Node | str | Iterable[Node | str]) -> DagPose:
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
        ...
    def removeMembers(self, *members: Node | str | Iterable[Node | str]) -> DagPose:
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
        ...
    def merge(self, sources: DagPose | str | Iterable[DagPose | str], *, currentPose: bool = ..., deleteSources: bool = ...) -> DagPose:
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
        ...
    def _member_sources(self) -> list[tuple[int, om2.MPlug]]:
        """接続されたmembers要素の論理番号と接続元を取得する。

        Returns:
            list[tuple[int, om2.MPlug]]: 論理番号の昇順の(番号, 接続元のPlug)。
        """
        ...
    def _merge_collect_poses(self, sources: object) -> tuple:
        """対象自身と統合元を入力順に解決し、同じポーズを一度だけ扱う。

        Args:
            sources (object): 統合元のポーズ入力。

        Returns:
            tuple: 対象名、対象を先頭とするポーズ辞書、対象自身を除いた統合元のlist。
        """
        ...
    def _merge_collect_rows(self, poses: dict, current_pose: bool, delete_sources: bool) -> tuple:
        """保存行とskinClusterを集め、姿勢の競合と統合元の削除可否を検査する。

        Args:
            poses (dict): 対象を先頭とするポーズ辞書。
            current_pose (bool): 保存姿勢の競合を許容し、現在の姿勢を後で保存するか。
            delete_sources (bool): 統合元の削除可否を検査するか。

        Returns:
            tuple: 統合する保存行、対象の既存保存行、再接続するskinCluster辞書。
        """
        ...
    def _merge_check_targets(self, skins: dict):
        """対象の保存先とskinClusterの再接続先が編集できることを検査する。

        Args:
            skins (dict): 再接続するskinCluster辞書。
        """
        ...
    def _merge_allocate_indices(self, rows: dict, target_rows: dict) -> dict:
        """既存の疎な保存番号を保ち、未登録メンバーへ後続の番号を割り当てる。

        Args:
            rows (dict): 統合する保存行。
            target_rows (dict): 対象の既存保存行。

        Returns:
            dict: メンバー名から保存先の論理番号への対応。
        """
        ...
    def _merge_write_rows(self, name: str, rows: dict, target_rows: dict, indices: dict, current_pose: bool):
        """メンバー・マトリクス・親情報を既存の順序でMayaの保存先へ書き込む。

        Args:
            name (str): 対象ポーズの名前。
            rows (dict): 統合する保存行。
            target_rows (dict): 対象の既存保存行。
            indices (dict): メンバー名から保存先の論理番号への対応。
            current_pose (bool): 既存メンバーも現在姿勢の行で更新するか。
        """
        ...
    @staticmethod
    def _merge_set_matrix(destination: str, values: tuple):
        """完全なxformデータをcmdsの複合引数へ変換してUndo可能に設定する。

        Args:
            destination (str): 設定先のアトリビュート名。
            values (tuple): _merge_matrix_payload()の戻り値。
        """
        ...
    @staticmethod
    def _merge_matrix_payload(plug: om2.MPlug) -> tuple:
        """Mayaの保存表現からcmds.setAttr用の完全なmatrixデータを読む。

        16要素のマトリクスへ変換するとjointOrient・pivot等のxform情報が失われる。
        Maya生成のsetAttrを実行せず、数値・bool・xformマーカーだけを取り出す。

        Args:
            plug (om2.MPlug): worldMatrixまたはxformMatrixの要素。

        Returns:
            tuple: setAttrの引数に変換できる値の並び。
        """
        ...
    def _merge_snapshot(self) -> dict:
        """メンバー・親の対応・完全な保存姿勢を取得し、不正な接続を拒否する。

        Returns:
            dict: メンバーの完全パスから保存行(index・parent・externalParent・
                worldMatrix・xformMatrix・global)への対応。
        """
        ...
    @staticmethod
    def _merge_rows_equal(left: dict, right: dict) -> bool:
        """同じメンバーの親・復元範囲・xformの内部情報まで比較する。

        Args:
            left (dict): 保存行。
            right (dict): 保存行。

        Returns:
            bool: 一致すればTrue。
        """
        ...
    def _merge_check_delete(self):
        """統合元の削除で失われる外部接続とロックを事前に検査する。"""
        ...
    @staticmethod
    def _transform_names(members: object) -> list[str]:
        """対象を有効なTransformの完全パスに揃える。

        Args:
            members (object): 単体または反復可能な対象。

        Returns:
            list[str]: 入力順・重複なしの完全パス。

        Raises:
            TypeError: 対応しない型の場合。
            ValueError: 空入力、または有効なTransform以外を含む場合。
        """
        ...
    def _pose_name(self):
        """有効なdagPoseの名前を返す。削除済みならRuntimeError。"""
        ...
