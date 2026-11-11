# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""skinClusterのinfluenceと、先頭Meshの頂点ウェイトを照会・編集する。

"""

import math
from collections.abc import Mapping
from contextlib import contextmanager
from decimal import Decimal, localcontext, ROUND_FLOOR
from itertools import groupby
from typing import List
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
from ..core.fastWrite import require_range, require_writable, set_attr
from ..core.ngSkinLayers import _layer_api, _move_layer_weights
from ..core.object import Object
from ..decorator import _edit_context, _pick_alias, _require_bool, preservedSelection, undoChunk
from ..maths import easing
from ..util import _MIRROR_PLANES, _PointGrid, _UNSET, _mirror_axis, _world_space
from .dagNode import DagNode
from .geometryFilter import GeometryFilter
from .joint import Joint, _unlocked_influences
from .node import Node, Nodes
from typing import Any, Iterable, Iterator, Literal, Sequence
from mlib._stubtypes import GeneratorContextManager
from mlib.common.namespace import Namespace
from mlib.components.component import Component
from mlib.components.component import Components
from mlib.components.vertex import Vertex
from mlib.components.vertex import Vertices
from mlib.json.nameMapping import NameMapping
from mlib.json.snapshot import ValidationReport
from mlib.nodes.dagPose import DagPose
from mlib.nodes.mesh import Mesh
from mlib.nodes.shadingEngine import ShadingEngine
from mlib.plugs.plug import Plug
from pathlib import Path
from types import ModuleType
from typing import overload
import os
import pathlib


def _finite_number(value: object) -> bool:
    """boolを除く有限の数値か判定する。

    Args:
        value (object): 判定する値。

    Returns:
        bool: int・floatの有限値ならTrue。
    """
    ...


class SkinCluster(GeometryFilter):
    """skinClusterを参照し、influenceと先頭出力Meshの頂点ウェイトを照会・編集する。

    構築時の先頭geometry名・DAGパスと、自身のMFnSkinClusterを保持する。
    頂点操作はそのgeometryがMeshであることを前提とし、複数geometryの一括編集は行わない。
    influenceObjects()の物理順と、weights[]への書込みに使う論理番号を区別する。
    """
    mesh: None
    mesh_path: None
    def __init__(self, skinCluster: str | om2.MObject | om2.MDagPath) -> None:
        """skinCluster 名または Maya オブジェクトからラッパーを初期化する。

        取得専用で、新規バインドは :func:`mlib.bindSkin <mlib.cmds.bindSkin.bindSkin>` を使う。先頭 geometry のみを保持する。
        頂点ウェイト操作ではその geometry が mesh であることを前提とする。

        Args:
            skinCluster (str | om2.MObject | om2.MDagPath): skinCluster の名前または API オブジェクト。

        Returns:
            None: 値を返さない。

        Raises:
            IndexError: 対象 geometry がない場合。
            RuntimeError: geometry を解決できない場合。
        """
        ...
    def mfn(self) -> oma2.MFnSkinCluster:
        """このskinClusterのMFnSkinClusterを、呼び出すたびに新しく作って返す。

        ``oma2.MFnSkinCluster`` は ``om2.MFnDependencyNode`` の派生で、:meth:`Node.mfn` の契約どおり
        内部で使い回す function set とは共有しない。

        Returns:
            oma2.MFnSkinCluster: このskinClusterの function set。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        ...
    def deforms(self, geometry: str | Node) -> bool:
        """指定形状を自身が変形するか照会する。

        :meth:`mlib.nodes.DagNode.getSkinClusters` と同じく、Shapeは自身、Transformは直下の
        非中間Shapeの上流から、出力geometryがその形状であるskinClusterを探す。
        Jointは形状を持たないためFalseで、influenceとしての登録は :meth:`hasInfluence` で調べる。

        Args:
            geometry (str | Node): 調べる形状またはtransform。

        Returns:
            bool: 自身が対象形状を変形する場合True。DAGノード以外もFalse。

        Raises:
            RuntimeError: 名前が存在しない場合、またはMayaの検索が失敗した場合。
        """
        ...
    def copyWeightsTo(self, target: str | Node) -> SkinCluster:
        """別skinClusterへ最近傍でウェイトを転送する。

        転送先にはskinClusterのほか、形状(Shape)またはその親Transformも指定できる。形状を変形する
        skinClusterがあればそれへ転送し、無ければ自身の全influence・同じmaxInfluencesで
        :func:`mlib.bindSkin <mlib.cmds.bindSkin.bindSkin>` でバインドしてから転送する。バインドと転送は1回のUndoで戻る。fast引数は持たない
        (OpenMayaにバインド・コピーのAPIが無いため)。

        Args:
            target (str | Node): 転送先のskinCluster、または形状・その親Transform。

        Returns:
            SkinCluster: ウェイトを書き込んだ転送先。新しくバインドした場合はそのskinCluster。

        Raises:
            TypeError: 転送先がskinClusterでも形状でもない場合(Joint・形状の無いTransform・DGノード等)。
            ValueError: 転送先が自身(または自身が変形する形状)の場合、または形状を複数のskinClusterが変形している場合。
            RuntimeError: 転送先の名前が存在しない場合、またはMayaがバインド・転送を拒否した場合。

        Note:
            closestPoint、name/closestJointによる近似転送で正規化する。
            異なる基準姿勢の補正やメッシュ削減は行わない。
        """
        ...
    def mirrorWeights(self, axis: str | int = ..., positiveToNegative: bool = ..., surfaceAssociation: str = ..., influenceAssociation: str | Sequence[str] = ..., normalize: bool = ...) -> SkinCluster:
        """自身の形状の片側のウェイトを、鏡映面の反対側へ写す。

        ``cmds.copySkinWeights(sourceSkin=自身, destinationSkin=自身, mirrorMode=axis, ...)`` を
        1回のUndoにまとめて実行する。fast引数は持たない(OpenMayaにミラーのAPIが無いため)。

        Args:
            axis (str | int): 鏡映面 ``"YZ"``・``"XZ"``・``"XY"``、または反転する軸 ``"x"``・``"y"``・``"z"``
                (x⇔YZ、y⇔XZ、z⇔XY。文字の順序・大文字小文字は問わない)、または0/1/2。
                既定の ``"YZ"`` (``"x"`` と同じ)はX軸方向の左右反転。
            positiveToNegative (bool): Trueは面の正側(YZならX>0)から負側へ写す。Falseは負側から正側へ
                (``mirrorInverse=True``)。
            surfaceAssociation (str): 頂点の対応。``"closestPoint"``・``"rayCast"``・``"closestComponent"``。
            influenceAssociation (str | Sequence[str]): influenceの対応を1〜3個、優先順に指定する。
                ``"closestJoint"``・``"closestBone"``・``"label"``・``"name"``・``"oneToOne"`` から選ぶ。
                ジョイントのラベル(side/type)を設定済みなら ``("label", "closestJoint")`` が確実。
            normalize (bool): Trueは写した後の各頂点を正規化する(copySkinWeightsのnormalize)。

        Returns:
            SkinCluster: 自身。

        Raises:
            TypeError: 引数の型が不正な場合。
            ValueError: 面・対応方法の名前が不正、またはinfluenceの対応が0個・4個以上・重複の場合。
            RuntimeError: Mayaがミラーを拒否した場合。
        """
        ...
    def pruneWeights(self, threshold: float, normalize: bool = ..., *, fast: bool = ...) -> SkinCluster:
        """先頭Meshの各頂点で、閾値未満の小さなウェイトを0にする。

        ``cmds.skinPercent(skin, mesh, pruneWeights=threshold)`` と同じく、値が ``0 < w < threshold``
        のinfluenceを0にし(閾値と等しい値は残す)、ロック以外の全てが閾値未満になる頂点は刈り込みも正規化もしない。
        lockInfluenceWeightsが有効なinfluenceは0にせず、正規化でも値を保つ。値が変わった頂点・列だけを
        書き込む。通常はcmds.setAttrで書き、1回のUndoで戻る。``fast=True`` は :meth:`setWeights` の
        fastと同じく、全対象の書込み可否を先に調べてからOpenMayaでウェイトのPlugへ直接書き込み、
        Undoに記録しない。

        Args:
            threshold (float): 0以上の有限な閾値。boolは不可。
            normalize (bool): Trueは上記の頂点を除く全頂点(刈り込みの無い頂点を含む)を、ロックされていないinfluenceの
                比率を保ったまま合計1(ロック分を除いた残り)へ戻す。ロック以外が全て0の頂点は変えない。
                ロックが無ければskinPercentの刈り込みと同じ値になる。Falseは0にするだけで、他の値は変えない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            SkinCluster: 自身。

        Raises:
            TypeError: thresholdが数値でない、またはnormalize・fastがbool以外の場合。
            ValueError: thresholdが負・非有限、または刈り込む頂点に負値・非有限値・合計1を超えるロック値がある場合。
            RuntimeError: ウェイトがロック・入力接続されている、またはMayaが書込みを拒否した場合。
        """
        ...
    def getInfluences(self) -> list[Node]:
        """登録influenceをAPIの物理順で参照する。

        Returns:
            list[Node]: influenceObjects()のDAGパスから作る新しいラッパーのリスト。
                登録型に応じJoint以外も返す。リスト位置はweights[]の論理番号とは限らず、ノードは複製しない。
        """
        ...
    def addInfluences(self, joints: Joint | str | Iterable[Joint | str]) -> SkinCluster:
        """ジョイントをウェイト0で登録する。既存influence・重複指定は無視する。

        Args:
            joints (Joint | str | Iterable[Joint | str]): 追加するジョイント。空は何もしない。

        Returns:
            SkinCluster: 自身。

        Raises:
            ValueError: Joint以外を指定した場合。全対象を編集前に検査する。
            RuntimeError: 対象が無効、またはMayaが追加を拒否した場合。

        Note:
            既存ウェイトの再配分や正規化は行わず、既存のロック設定も変更しない。
        """
        ...
    def removeInfluences(self, joints: str | Node | Iterable, transferToParent: bool = ..., *, force: bool = ...) -> SkinCluster:
        """複数のinfluenceを、深いものから順に外す。ノード自体は削除しない。

        親子のjointを同時に渡しても、深いjointから :meth:`removeInfluence` と同じ処理で外すため、
        ウェイトは外さずに残る最も近い祖先influenceへ集まる。全対象の登録と移送先を先に検査する。
        ウェイトのロックは一時的に外して解除し、元の状態へ戻す。ngSkinTools2のレイヤーはレイヤーごとに移送する。
        Undo有効時は一つのチャンクへ記録する。fast引数は持たない。後続の失敗で完了済み変更は戻さない。

        Args:
            joints (str | Node | Iterable): 外す登録済みinfluence。名前またはNodeを同じ形式で指定する。
            transferToParent (bool): Trueは外さずに残る最も近い祖先influenceへ加算する。
                Falseは標準の再配分に任せる。
            force (bool): 不正ウェイトを修復してから処理する。修復時に正規化は行わない。

        Returns:
            SkinCluster: 自身。

        Raises:
            TypeError: transferToParent・forceがbool以外、またはinfluenceの入力型が不正な場合。
            ValueError: influenceが空・未登録・重複、すべてのinfluenceを外す場合、または
                transferToParent=Trueで残る祖先influenceが無いinfluenceがある場合。
            RuntimeError: ウェイト要素のロック・入力接続、またはMayaの編集失敗。
        """
        ...
    def getBindPose(self) -> DagPose | None:
        """bindPoseアトリビュートに接続された保存ポーズを取得する。

        Returns:
            DagPose | None: 接続されたポーズ。未接続ならNone。

        Raises:
            RuntimeError: skinClusterが無効、または接続先がdagPoseでない場合。
        """
        ...
    def resetBindPose(self) -> SkinCluster:
        """このskinClusterのinfluenceの保存姿勢を現在の姿勢へ更新する。

        接続されたバインドポーズのうちinfluenceの行だけを ``DagPose.reset`` で更新する。
        ポーズを共有する別のskinClusterからも更新が見える。bindPreMatrixやウェイトは変更しない。
        ポーズに無いinfluenceは自動追加せず、変更前に例外を出す。fast引数は持たない
        (``cmds.dagPose`` の保存規則をom2で再現しないため)。

        Returns:
            SkinCluster: 自身。

        Raises:
            ValueError: influenceが空、またはポーズに含まれていない場合。
            RuntimeError: ポーズが未接続、ノードが無効、またはMayaが更新を拒否した場合。
        """
        ...
    def restoreBindPose(self, worldSpace: bool = ..., *, ws: bool = ...) -> SkinCluster:
        """接続されたポーズの全メンバーを保存姿勢へ復元する。

        ポーズを共有する別のskinClusterや、influence以外のメンバーにも影響する。
        ロックや入力接続は解除しない。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            SkinCluster: 自身。

        Raises:
            RuntimeError: ポーズが未接続、ノードが無効、またはMayaが復元を拒否した場合。
        """
        ...
    def getUnusedInfluences(self) -> list[Node]:
        """ウェイトを持たないinfluenceを検索する。シーンは変更しない。

        Returns:
            list[Node]: influence順のノードラッパー。微小値も使用中として扱い、
                閾値による切り捨てはしない。全geometryをMFnSkinClusterで判定する。

        Raises:
            RuntimeError: skinClusterが無効、または照会に失敗した場合。
        """
        ...
    def removeUnusedInfluences(self, *, force: bool = ...) -> list[Node]:
        """未使用influenceの登録を外し、ノード自体は残す。

        force時は不正ウェイトを修復してから未使用を検索する。Undo有効時は一つのチャンクへ記録する。
        fast引数は持たない。先行した修復・解除は自動で戻さない。

        Args:
            force (bool): 修復後に未使用を調べる。正規化やロック解除は行わない。

        Returns:
            list[Node]: influence順の、登録を外したノード参照。対象がなければ空リスト。

        Raises:
            TypeError: forceがbool以外の場合。
            ValueError: 解除すると登録が空になる場合。
            RuntimeError: レイヤー・ロック・接続、またはMayaの編集失敗。
        """
        ...
    def removeInvalidWeights(self, *, fast: bool = ...) -> SkinCluster:
        """負値・非有限値・未登録influence番号のウェイト要素を除去する。

        生のweightListにある既存要素だけを対象とする。有効な非負の有限値は
        1を超えていても保持し、正規化・合計0の補填・influenceの削除は行わない。
        除去した登録済みinfluenceのウェイトは既定値0になる。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            SkinCluster: 自身。不正要素がなければ何もしない。

        Raises:
            TypeError: fastがbool以外の場合。
            RuntimeError: レイヤー・influenceやウェイトのロック・接続、または編集失敗。

        Note:
            全要素を変更前に検証する。実行途中のMayaエラーは自動では戻さない。
        """
        ...
    def hasInfluence(self, joint: str) -> bool:
        """指定したjointがinfluenceに含まれるか判定する。

        Args:
            joint (str): 判定するjoint名。

        Returns:
            bool: influenceに含まれる場合は ``True``。
        """
        ...
    def getLockedInfluences(self) -> list[Node]:
        """ウェイトをロック(lockInfluenceWeights)しているinfluenceを取得する。

        Returns:
            list[Node]: ロックしているinfluence。:meth:`getInfluences` と同じ順・同じ型。
        """
        ...
    def setInfluencesLocked(self, joints: str | Node | Iterable, state: bool = ...) -> SkinCluster:
        """influenceのウェイトのロック(lockInfluenceWeights)を設定する。

        ロックしたinfluenceの値は、Mayaのペイントや :meth:`setWeights` の ``normalize=True`` で変わらない。
        fast引数は持たない(influenceの数だけのsetAttrで、OpenMayaで書いても速くならないため)。

        Args:
            joints (str | Node | Iterable): 登録済みinfluence。複数は名前と参照を混在させない。
            state (bool): Trueはロック、Falseはロックの解除。既定True。

        Returns:
            SkinCluster: 自身。

        Raises:
            TypeError: stateがbool以外、またはinfluenceの入力型が不正な場合。
            ValueError: influenceが空・未登録・重複の場合。
            RuntimeError: lockInfluenceWeightsがロック・入力接続されている場合。
        """
        ...
    def unlockedInfluences(self, joints: str | Node | Iterable | None = ...) -> GeneratorContextManager[SkinCluster]:
        """指定したinfluenceのウェイトのロックを一時的に外し、抜けるときに元へ戻す。

        入るときにロックしていたinfluenceだけを解除し(:meth:`setInfluencesLocked` と同じ
        lockInfluenceWeights)、抜けるとき(例外でも)にそれらをロックへ戻す。入るときにロックして
        いなかったinfluenceは、with の中で変えても戻さない。with の中で削除された・influenceで
        なくなったjointは戻さない。fast引数は持たない。

        Undo有効時は、ロックの解除・with の中の操作・ロックの復元を1つのUndoチャンクにまとめる。
        抜けた後の1回のUndoで with に入る前の状態(ロックしたまま、ウェイトも元の値)へ戻る。
        with の中では ``cmds.undo()`` を呼ばないこと。開いているチャンクの中の Undo は、Mayaが記録した
        最後の1項目だけを戻すため、:meth:`setWeights` 等の1回の操作の途中までしか戻らず、操作が無ければ
        ロックの解除を戻す(ロックした状態になる)。抜けるときの復元は、その時点の状態によらず元の
        ロックを設定する。with の中の操作を取り消すなら、抜けてから Undo する。

        Args:
            joints (str | Node | Iterable | None): 対象の登録済みinfluence。Noneは全influence。
                複数は名前と参照を混在させない(:meth:`setInfluencesLocked` と同じ)。

        Yields:
            SkinCluster: 自身。

        Raises:
            TypeError: influenceの入力型が不正な場合。
            ValueError: influenceが空・未登録・重複の場合。
            RuntimeError: lockInfluenceWeightsがロック・入力接続されている場合。

        Examples:
            .. code-block:: python

                with skin.unlockedInfluences():
                    skin.setWeights(["spine_JNT"], [1.0], vertices=[0], normalize=True)
        """
        ...
    @overload
    def getWeights(self, joints: str | Node | Iterable, *, vertices: Vertex | Vertices | int | str | Iterable | None = ..., rows: Literal[True]) -> list[list[float]]: ...
    @overload
    def getWeights(self, joints: str | Node | Iterable, *, vertices: Vertex | Vertices | int | str | Iterable | None = ..., rows: Literal[False] = ...) -> om2.MDoubleArray: ...
    @overload
    def getWeights(self, joints: str | Node | Iterable, *, vertices: Vertex | Vertices | int | str | Iterable | None = ..., rows: bool = ...) -> om2.MDoubleArray | list[list[float]]:
        """指定influenceの頂点ウェイトを、先頭Meshから取得する。

        APIにはinfluenceObjects()内の物理番号を渡し、疎なweights[]の論理番号は渡さない。
        influenceは :meth:`setWeights` と同じく、空・未登録・重複を変更前に拒否する。

        Args:
            joints (str | Node | Iterable): 登録済みinfluence。複数は名前と参照を混在させない。
                頂点(Vertex・"mesh.vtx[0]"等)はinfluenceではないためTypeError。
            vertices (Vertex | Vertices | int | str | Iterable | None): 取得する頂点。Noneは全頂点。
                Vertex/Verticesは先頭Mesh所属に限り、文字列は ``"mesh.vtx[0:3]"`` のような頂点名。
                指定した順に返し、重複はValueError。
            rows (bool): Trueは頂点ごとの行(``list[list[float]]``)で返す。既定Falseは平坦な配列。

        Returns:
            om2.MDoubleArray | list[list[float]]: 既定は頂点順(Noneは番号順)・各頂点内はjoints順の、
                頂点数×指定数の平坦な値配列。無次元の独立した値で、配列の変更はシーンへ反映されない。
                i番目の頂点のj番目のinfluenceは ``weights[i * len(joints) + j]``。``rows=True`` は
                同じ値を頂点ごとの行に分けた ``weights[i][j]``。1頂点のウェイトをinfluenceごとに読むなら
                :meth:`getVertexWeights` (influenceからウェイトへの辞書)を使う。

        Raises:
            TypeError: jointsに頂点・アトリビュートを渡した、頂点の入力型が不正、またはrowsがbool以外の場合。
            ValueError: influenceが空・未登録(例: ``'arm_R_JNT' is not an influence of skinCluster1``)・重複、
                または頂点が重複・別の形状の場合。
            IndexError: 頂点番号が範囲外の場合。
        """
        ...
    def setWeights(self, joints: str | Node | Iterable, weights: Iterable[float] | Iterable[Iterable[float]], *, vertices: Vertex | Vertices | int | str | Iterable | None = ..., normalize: bool = ..., broadcast: bool = ..., rows: bool = ..., fast: bool = ...) -> None:
        """指定influenceの頂点ウェイトを設定する。既定では正規化せず生の値として書く。

        共通検証後、通常はcmds.setAttrで頂点・指定列の順に書く。指定順で連続する論理番号は
        範囲指定の1回のsetAttrにまとめるが、失敗時の部分更新とエラーは要素ごとの書込みと同じ。fastは全対象Plugの
        ロック・入力接続・書込み可否とアトリビュート範囲を先に検査し、MPlug.setDoubleで順に書く。
        どちらもMFnSkinCluster.setWeightsによる未指定列の再配分は使わない。

        ``normalize=True`` は書込み対象の各頂点を、``cmds.skinPercent(transformValue=..., normalize=True)``
        に倣って合計1へ正規化する。指定influenceには指定値を書き、lockInfluenceWeightsが有効な未指定
        influenceは値を保ち、残りの未指定influenceを比率を保ったまま ``1 - 指定値の合計 - ロック値の合計``
        へ拡大縮小する。指定値の合計がこの残りを超える場合と、拡大縮小できる未指定influenceが無い
        (値がすべて0)場合は、指定値を比率を保ったまま ``1 - ロック値の合計`` へ縮小・拡大し、未指定(ロック以外)を0にする。
        値が変わった未指定influenceの列も書き込む。後者の場合、skinPercentの結果はMayaの版で異なる
        (2022は指定値をそのまま書く)ため、mlibは版によらずこの規則で合計1にする。

        Args:
            joints (str | Node | Iterable): 空でない登録済みinfluence。名前またはNodeを同じ形式で指定する。
                同一influenceの重複指定は拒否する。頂点(Vertex・"mesh.vtx[0]"等)はTypeError。
            weights (Iterable[float] | Iterable[Iterable[float]]): 対象頂点数V・指定列数Kに対しV*K個
                (頂点順で、各頂点内はjoints順)。``broadcast=True`` の場合は全対象頂点に共通のK個。
                ``rows=True`` の場合はK個ずつの行がV個(:meth:`getWeights` の ``rows=True`` の結果)。
                値はfloatへ変換できる有限値。
            vertices (Vertex | Vertices | int | str | Iterable | None): 書き込む頂点。Noneは全頂点。
                Vertex/Verticesは先頭Mesh所属に限り、文字列は ``"mesh.vtx[0:3]"`` のような頂点名。
                weightsはこの指定順に対応する。重複はValueError、空は何もしない。
            normalize (bool): Trueは書き込んだ頂点を上記の規則で合計1へ正規化する。既定False。
                対象頂点に負値・非有限値があればValueError。
            broadcast (bool): TrueはK個の値を全対象頂点へ同じく適用する。既定False。
                5.0.0から、V>1の頂点へK個だけを渡す場合はこの指定が必要。
            rows (bool): Trueはweightsを頂点ごとの行として受け付ける。既定False。broadcastとは併用できない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。通常setterのself返却とは異なる既存仕様。

        Raises:
            TypeError: 数値に変換できない型、頂点・influenceの入力型が不正、またはbool引数がbool以外の場合。
            ValueError: influenceが空・未登録・重複、件数不一致(K個をbroadcast=Trueなしで複数頂点へ渡した場合、
                rows=Trueで行の長さがKでない場合を含む)、rowsとbroadcastの併用、非有限値、数値文字列が不正、
                頂点が重複・別の形状、または正規化できない頂点がある場合。
            IndexError: 頂点番号が範囲外の場合。
            RuntimeError: Plugが編集不可、またはMayaが設定を拒否した場合。

        Note:
            ``normalize=False`` では未指定列とinfluenceのロック設定は変更しないが、lockInfluenceWeightsを
            保護条件として拒否する処理も、レイヤー検出も行わない。非負・合計1を独自には検査しない。
            normalizeWeights/maintainMaxInfluences設定に合わせた再正規化もしない。
            通常経路はUndoが有効なら同じチャンクへ記録する。後半の失敗時に完了済み変更は
            自動で戻さず、fastの事前検査も書込み中の失敗に対する原子性は保証しない。
        """
        ...
    def getVertexWeights(self, vertex: Vertex | int | str, *, nonzero: bool = ...) -> dict[Node, float]:
        """先頭Meshの1頂点について、全influenceのウェイトを辞書で取得する。

        Args:
            vertex (Vertex | int | str): 先頭Meshの頂点。Vertex、頂点番号、または ``"mesh.vtx[3]"``。
            nonzero (bool): Trueは値が0でないinfluenceだけを返す。既定False。

        Returns:
            dict[Node, float]: influenceのラッパー(:meth:`getInfluences` と同じ型)からウェイトへの辞書。
                influenceObjects()の物理順に並ぶ。そのまま :meth:`setVertexWeights` へ渡せる。
                値は独立したコピーで、辞書の変更はシーンへ反映されない。

        Raises:
            TypeError: 頂点の入力型が不正、またはnonzeroがbool以外の場合。
            ValueError: 頂点が1つでない、または別の形状の頂点の場合。
            IndexError: 頂点番号が範囲外の場合。
        """
        ...
    def setVertexWeights(self, vertex: Vertex | int | str, weights: Mapping[str | Node, float], normalize: bool = ..., *, fast: bool = ...) -> SkinCluster:
        """先頭Meshの1頂点に、influenceごとのウェイトを設定する。

        ``setWeights(list(weights), list(weights.values()), vertices=[vertex], normalize=normalize)`` と同じ。
        既定の ``normalize=True`` では、指定influenceに指定値を書き、指定しなかったinfluenceを
        :meth:`setWeights` の正規化規則で拡大縮小(または0に)して合計1にする。
        ``normalize=False`` では指定influenceだけを生の値で書き、他は変更しない。

        Args:
            vertex (Vertex | int | str): 先頭Meshの頂点。Vertex、頂点番号、または ``"mesh.vtx[3]"``。
            weights (Mapping[str | Node, float]): 空でない、登録済みinfluenceからウェイトへの辞書。
                キーは名前またはNodeのどちらかに揃える(:meth:`getVertexWeights` の戻り値はNode)。
            normalize (bool): Trueは書いた頂点を合計1へ正規化する。既定True。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            SkinCluster: 自身。

        Raises:
            TypeError: weightsが辞書でない、頂点・値の型が不正、またはbool引数がbool以外の場合。
            ValueError: weightsが空、influenceが未登録・重複、値が非有限、頂点が1つでない・別の形状、
                または正規化できない場合。
            IndexError: 頂点番号が範囲外の場合。
            RuntimeError: Plugが編集不可、またはMayaが設定を拒否した場合。
        """
        ...
    def getWeightsData(self) -> dict:
        """全頂点のウェイトとスキニングの設定を、``mlib.skinWeights`` 形式の辞書で取得する。

        :meth:`exportWeights` が書き出すデータそのもので、:meth:`setWeightsData` へ渡せる。
        値は丸めない。シーンは変更しない。

        データの形(版1):

        - ``geometry``: 先頭geometry(Shape)の参照(:class:`mlib.json.NodeRef` の辞書)。
        - ``vertexCount``: 頂点数。
        - ``influences``: influenceの参照の list。influenceObjects()の物理順で、以下の番号はこの位置。
        - ``influenceLocks``: influenceごとのウェイトのロック(lockInfluenceWeights)。``influences`` と同じ順。
        - ``weights``: 0でない値だけの疎な形。``{"indices": [[...], ...], "values": [[...], ...]}`` で、
          頂点ごとにinfluenceの位置と値を並べる(i番目の頂点は ``indices[i]`` と ``values[i]``)。
        - ``blendWeights``: 頂点ごとのDQブレンドウェイト(blendWeights)。
        - ``positions``: 頂点ごとの位置 ``[x, y, z]``。skinClusterに入る前の形状のオブジェクト空間(cm)。
          ``method="position"`` の対応付けに使う。
        - ``settings``: ``skinningMethod``・``normalizeWeights`` (名前)、``maxInfluences`` (int)、
          ``maintainMaxInfluences`` (bool)。
        - ``ngSkinLayers``: ngSkinTools2のレイヤーの list。レイヤーが無い、またはngSkinTools2を使えない場合はNone。
          各レイヤーは ``name``・``enabled``・``opacity``・``parent`` (親レイヤーのlist内の位置、またはNone)・
          ``index`` (親の中の順番)・``weights`` (``[[influenceの位置, 頂点ごとの値], ...]``)・
          ``mask``・``dq`` (頂点ごとの値、またはNone)を持つ。

        Returns:
            dict: 上の形の辞書。数値・文字列・list・辞書だけを含み、JSONへそのまま書ける。

        Raises:
            RuntimeError: skinClusterまたはgeometryが無効な場合。

        Examples:
            .. code-block:: python

                data = skin.getWeightsData()
                other.setWeightsData(data, namespaceMap={"chrA": "chrB"})
        """
        ...
    def setWeightsData(self, data: dict, *, nameMap: dict[str, str] | None = ..., replace: Iterable[tuple[str, str]] | None = ..., namespaceMap: dict[str, str] | None = ..., method: str = ..., fast: bool = ...) -> ValidationReport:
        """:meth:`getWeightsData` の辞書から、ウェイトとスキニングの設定をこのskinClusterへ書き戻す。

        保存したinfluenceは名前の対応付け(``nameMap``・``replace``・``namespaceMap``。規則は
        :class:`mlib.json.NameMapping`)でシーンのノードへ対応させる。

        - シーンにあるがこのskinClusterのinfluenceでないノードは、ウェイト0で追加してから書く。
        - シーンに無いinfluenceは報告の ``missing`` に記録して警告し、その値を除いた残りを、頂点ごとの
          元の合計へ比率を保って拡大する。残りがすべて0の頂点は書き換えず、``skipped`` に記録する。
        - 保存に無いinfluence(このskinClusterだけのinfluence)の値は0にする。
        - DQブレンドウェイト・スキニングの設定(方法・最大インフルエンス数・その維持・正規化)を書き、
          ウェイトのロックは保存した状態にする(保存に無いinfluenceのロックは変えない)。
          ロック・入力接続されている設定は書かずに ``skipped`` に記録する。
        - ``ngSkinLayers`` があり、ngSkinTools2を使える場合は、既存のレイヤーを消して保存したレイヤーを
          作り直す(合成結果のウェイトはngSkinTools2が書く)。使えない場合は ``skipped`` に記録して、
          合成結果のウェイトだけを書く。保存にレイヤーが無く、このskinClusterにレイヤーがある場合は
          レイヤーを変えず ``skipped`` に記録する。

        ``method="index"`` は頂点番号で対応させ、頂点数が違えば何も変えずにValueErrorにする。
        ``method="position"`` は各頂点に、保存した位置(skinClusterに入る前の形状のオブジェクト空間)で最も近い
        保存頂点の値(ウェイト・DQブレンドウェイト・レイヤーの値)を使う。頂点数が違うメッシュにも使える。

        Args:
            data (dict): :meth:`getWeightsData` の形の辞書。
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。
            method (str): ``"index"`` (既定)または ``"position"``。
            fast (bool): TrueはUndoなしのOpenMaya更新(``MFnSkinCluster.setWeights``)。既定False。

        Returns:
            ValidationReport: 見つからなかったinfluence(missing)と書かなかったもの(skipped)。

        Raises:
            TypeError: 引数の型が不正な場合。
            ValueError: データの形が不正、methodが不正、``method="index"`` で頂点数が違う、または
                保存したinfluenceが1つもシーンに無い場合。いずれもシーンを変えない。
            RuntimeError: ウェイトが編集不可、またはMayaが設定を拒否した場合。通常経路は巻き戻す。

        Note:
            通常経路は全体を1回のUndoにまとめ(cmds.setAttr)、途中の失敗は巻き戻す。``fast=True`` はUndoへ
            記録しない。ただしinfluenceの追加(``cmds.skinCluster``)と、ngSkinTools2のレイヤーの作成は
            ``fast=True`` でもMayaのコマンドで行う。
        """
        ...
    def exportWeights(self, path: str | os.PathLike) -> pathlib.Path:
        """:meth:`getWeightsData` のデータを、ヘッダー付きのJSONファイル(``mlib.skinWeights`` 版1)へ書き出す。

        Args:
            path (str | os.PathLike): 書き出し先。フォルダは作らない。

        Returns:
            pathlib.Path: 書き出したファイルの絶対パス。

        Raises:
            OSError: 書き出しに失敗した場合。

        Examples:
            .. code-block:: python

                skin.exportWeights("body_weights.json")
                skin.importWeights("body_weights.json", method="position")
        """
        ...
    def importWeights(self, path: str | os.PathLike, *, nameMap: dict[str, str] | None = ..., replace: Iterable[tuple[str, str]] | None = ..., namespaceMap: dict[str, str] | None = ..., method: str = ..., fast: bool = ...) -> ValidationReport:
        """:meth:`exportWeights` のファイルを読み込み、:meth:`setWeightsData` と同じ規則で書き戻す。

        Args:
            path (str | os.PathLike): ``mlib.skinWeights`` 版1のファイル。
            nameMap (dict[str, str] | None): 名前空間を除いた名前の対応表。
            replace (Iterable[tuple[str, str]] | None): 順に当てる文字列置換。
            namespaceMap (dict[str, str] | None): 名前空間の対応。
            method (str): ``"index"`` (既定)または ``"position"``。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            ValidationReport: 見つからなかったinfluenceと書かなかったもの。

        Raises:
            TypeError: 引数の型が不正な場合。
            ValueError: 形式名・版・データの形が不正、methodが不正、``method="index"`` で頂点数が違う、
                または保存したinfluenceが1つもシーンに無い場合。
            OSError: 読み込みに失敗した場合。
            RuntimeError: ウェイトが編集不可、またはMayaが設定を拒否した場合。
        """
        ...
    def invertShape(self, sculpted: str | Node, name: str | None = ...) -> Mesh:
        """現在のポーズで形を整えたメッシュから、スキンの変形を逆にかけた補正形状を作る。

        各頂点で、スキンが使うマトリクス(``geomMatrix``・``bindPreMatrix``・``matrix``)をウェイトで
        重み付けした和(classicLinear の変形)を求め、その逆マトリクスを sculpted の頂点に掛けて、
        skinCluster に入る前の空間の形状を求める(cvShapeInverter と同じ考え方)。envelope も考慮する。
        結果は skinCluster が変形する先頭のメッシュを複製し(同じ親の下)、頂点を置き換えて作る。
        結果をこのメッシュの blendShape のターゲットとして(skinCluster より前に)足すと、
        現在のポーズで sculpted と同じ形になる。複製と頂点の書込みは1回のUndoで戻せる。fast引数は持たない。

        Args:
            sculpted (str | Node): 現在のポーズで形を整えたメッシュ(transformまたはmeshのshape)。
                頂点の番号と数が先頭のメッシュと同じであること。位置はオブジェクト空間の座標を使うため、
                横へ移動した複製でもよい。
            name (str | None): 作るメッシュのtransformの名前。Noneは ``<sculptedの名前>_inverted``。

        Returns:
            Mesh: 作ったメッシュのshape。

        Raises:
            TypeError: sculpted がメッシュでない、または name が文字列・None以外の場合。
            ValueError: 頂点数が先頭のメッシュと違う、または name が空文字列の場合。
            RuntimeError: 名前を解決できない、またはMayaが複製・書込みを拒否した場合。

        Note:
            skinCluster より前に別のデフォーマーがある場合は、その出力(skinCluster の入力)と元の形状
            (Orig)の差を足し戻すので、blendShape のように位置を足すだけのデフォーマーは現在の値のまま
            正しく扱える(ターゲットの形状を削除して差分だけになった blendShape。ターゲットの形状を
            つないだままの blendShape は入力に対する絶対位置として働くため、その分ずれる)。回転・拡大を伴うデフォーマー(cluster・nonLinear 等)の効果は逆にしないため、
            その分ずれる。skinningMethod が dualQuaternion・weightBlended の場合も線形の変形として
            逆にするので、近似になる。スキンのマトリクスの和が特異な(ウェイトがほぼ0の)頂点は、
            skinCluster の入力の位置をそのまま使う。頂点の書込みは :meth:`Mesh.setPoints
            <mlib.nodes.mesh.Mesh.setPoints>` を使い、頂点数に比例して時間がかかる。
        """
        ...
    def redistributeWeights(self, vertices: Vertex | Vertices | Iterable[int | Vertex], method: str = ...) -> None:
        """先頭Meshの頂点ウェイトを正規化し、イージングをかけて再正規化する。

        頂点番号はint()で変換し、重複を除いて昇順に処理する。各頂点で読取り・計算・書込みを行い、
        全頂点の書込み可否は先に検査しない。0のinfluenceは0のまま。linearでも合計1へ正規化する。
        fast引数は持たない(処理の大半が頂点ごとの読取りと計算で、OpenMayaで書いても速くならないため)。

        Args:
            vertices (Vertex | Vertices | Iterable[int | Vertex]): 頂点または番号列。
                Vertex/Verticesは先頭Mesh所属に限る。空列は変更しない。
            method (str): mlib.maths.easing.CURVESの曲線名。既定cubic。

        Returns:
            None: 値を返さない。途中失敗で先行する頂点・列の変更は自動で戻さない。

        Raises:
            TypeError: methodが文字列でない、または頂点入力を変換できない型の場合。
            ValueError: 曲線名・所属・頂点番号の変換が不正、ウェイト合計が0以下、またはイージング計算が成立しない場合。
            IndexError: 頂点番号が現在の範囲外の場合。
            RuntimeError: Mayaが読取り・書込みを拒否した場合。
        """
        ...
    def transferWeights(self, sourceTargetPairs: Iterable[tuple[Node | str, Node | str]], *, fast: bool = ...) -> None:
        """指定順のsource/target組で、sourceの影響頂点からtargetへウェイトを移す。

        全組の参照と登録を検証してから処理し、同じinfluence同士は省く。
        targetへ加算せずsource値で置換し、sourceを0にする。source=0の頂点は変更しない。
        通常はskinPercentとnormalizeWeights設定に従い、preservedSelectionで選択復元を試みる。
        fastは単一geometryと編集条件を検査し、interactive正規化を再現する。完了済み変更は戻さない。

        Args:
            sourceTargetPairs (Iterable[tuple[Node | str, Node | str]]): 登録済みinfluenceの組。
                Maya APIのノード参照も受理する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: ペアを反復できない、未対応の参照型、またはfastがbool以外の場合。
            ValueError: ペアが2要素でない、または未登録influenceの場合。
            RuntimeError: レイヤー・ロック等の編集制限、またはMayaの処理失敗。
            NotImplementedError: fastでgeometryが1個でない場合。
        """
        ...
    def removeInfluence(self, joint: Joint | str, transferToParent: bool = ..., *, force: bool = ...) -> None:
        """祖先influenceへ加算してから登録を外す。ノード自体は削除しない。

        移送先は同じskinClusterの最も近い祖先influence。生ウェイトを加算してsourceを0にし、登録を外す。
        書き込むのはsourceにウェイトがある頂点の2列だけで、ロック・入力接続もその要素だけを拒否する。
        登録の解除と残りの再配分は ``cmds.skinCluster(edit=True, removeInfluence=...)`` に任せる。
        ウェイトのロックは一時的に外して解除し、元の状態へ戻す。ngSkinTools2のレイヤーはレイヤーごとに移送する。
        ngSkinTools2を使えない場合のレイヤーは拒否せず、skinClusterのウェイトだけを書き換える。
        最後の登録は外せない。Undo有効時は一つのチャンクへ記録する。fast引数は持たない。
        修復・移送・解除は順次行い、後続失敗で完了済み変更は戻さない。

        Args:
            joint (Joint | str): 解除対象のinfluence。
            transferToParent (bool): 祖先へ移送するか。False、または祖先がなければ標準の再配分。
            force (bool): 不正ウェイトを修復してから処理する。修復時に正規化は行わない。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: transferToParent・forceがbool以外の場合。
            ValueError: 未登録、または最後のinfluenceの場合。
            RuntimeError: ウェイト要素のロック・入力接続、またはMayaの編集失敗。
        """
        ...
    def normalizeWeights(self, decimals: int | None = ..., *, fast: bool = ...) -> SkinCluster:
        """先頭Meshの各頂点について、全登録influenceのウェイトを合計1へ正規化する。

        全頂点を計算・検証してからsetWeightsへ渡す。負値・非有限値・合計ゼロ、
        influenceのlockInfluenceWeights、既存ウェイトのロック/入力接続、
        レイヤーと推定される接続があれば拒否する。normalizeWeights設定自体は変えない。

        Args:
            decimals (int | None): 0〜15の小数桁数。boolは不可。Noneは桁丸めなし。
                桁指定時は最大剰余法で十進の合計1を保ち、同率はinfluenceObjects()の物理順を優先する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            SkinCluster: 自身。influence登録数とnormalizeWeights設定は変更しない。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 桁数が不正、influenceがない、負値・非有限値・合計ゼロの頂点がある場合。
            RuntimeError: ロック・入力接続・レイヤー推定、またはMayaの編集失敗。

        Note:
            レイヤー判定は接続相手の名前/型の固定トークン照合で、実レイヤーデータの検査ではない。
            保存時はfloatへ戻すため、二進浮動小数点での厳密な合計1は保証しない。
            書込み途中の失敗時に完了済み変更を自動ロールバックしない。
        """
        ...
    def getMaxInfluences(self) -> int:
        """skinClusterのmaxInfluences設定値。実際の非ゼロ数ではない。

        Returns:
            int: skinClusterのmaxInfluences設定値。実際の非ゼロ数ではない。
        """
        ...
    def setMaxInfluences(self, count: int, maintain: bool = ..., prune: bool = ..., *, fast: bool = ...) -> SkinCluster:
        """最大influenceの設定を変更し、任意で先頭Meshの非ゼロ列数を制限する。

        maxInfluencesとmaintainMaxInfluencesをPlugで設定し、skinCluster編集コマンドの
        再バインドは使わない。prune=Falseは設定2Plugだけを検査し、全ウェイトやレイヤーは調べない。
        prune=Trueは全ウェイトの編集可否と正規化結果を先に確認する。

        Args:
            count (int): 1〜2147483647。bool不可。登録influence数より大きい値も受け付ける。
            maintain (bool): maintainMaxInfluencesへ設定する値。
            prune (bool): Trueは各頂点の大きいcount列だけを残し、他列を0にして正規化する。
                同率は物理順を優先する。influenceの登録は削除しない。Falseは既存値を変更しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            SkinCluster: 自身。通常経路はUndoが有効なら同じチャンクへ記録する。

        Raises:
            TypeError: maintain・prune・fastがbool以外の場合。
            ValueError: countが不正、またはprune時にウェイトを正規化できない場合。
            RuntimeError: 設定がロック/入力接続されている、pruneの編集制限、またはMayaの設定失敗。

        Note:
            maxInfluences、maintainMaxInfluences、prune済み値の順に適用する。
            後続の書込みに失敗した場合、先に変更した設定や値を自動で戻す処理は持たない。
        """
        ...
    def isMaintainingMaxInfluences(self) -> bool:
        """ペイント等の編集で最大influence数を保つ設定(maintainMaxInfluences)かを判定する。

        Returns:
            bool: maintainMaxInfluencesが有効ならTrue。
        """
        ...
    def getSkinningMethod(self) -> str:
        """スキニングの方法(skinningMethod)を取得する。

        Returns:
            str: ``"classicLinear"``・``"dualQuaternion"``・``"weightBlended"`` のどれか。
        """
        ...
    def setSkinningMethod(self, method: str) -> SkinCluster:
        """スキニングの方法(skinningMethod)を設定する。

        fast引数は持たない(1つのsetAttrで、OpenMayaで書いても速くならないため)。

        Args:
            method (str): ``"classicLinear"``・``"dualQuaternion"``・``"weightBlended"`` のどれか。

        Returns:
            SkinCluster: 自身。

        Raises:
            TypeError: methodが文字列でない場合。
            ValueError: methodが上の名前のどれでもない場合。
            RuntimeError: アトリビュートがロック・入力接続されている場合。
        """
        ...
    def getNormalizeMode(self) -> str:
        """ウェイトの正規化の方法(normalizeWeights)を取得する。

        Returns:
            str: ``"none"``・``"interactive"``・``"post"`` のどれか。
        """
        ...
    def setNormalizeMode(self, mode: str) -> SkinCluster:
        """ウェイトの正規化の方法(normalizeWeights)を設定する。

        既存のウェイトは書き換えない(正規化し直すには :meth:`normalizeWeights` を使う)。
        fast引数は持たない(1つのsetAttrで、OpenMayaで書いても速くならないため)。

        Args:
            mode (str): ``"none"``・``"interactive"``・``"post"`` のどれか。

        Returns:
            SkinCluster: 自身。

        Raises:
            TypeError: modeが文字列でない場合。
            ValueError: modeが上の名前のどれでもない場合。
            RuntimeError: アトリビュートがロック・入力接続されている場合。
        """
        ...
    def _prepare_weights_data(self, data: dict, mapping: NameMapping, method: str) -> tuple[dict, list[Node | None], ValidationReport]:
        """:meth:`setWeightsData` の検査を行い、適用に使う値を返す。シーンは変更しない。

        Args:
            data (dict): :meth:`getWeightsData` の形の辞書。
            mapping (NameMapping): 名前の対応付け。
            method (str): ``"index"`` または ``"position"``。

        Returns:
            tuple[dict, list[Node | None], ValidationReport]: 検査済みのデータ、保存した
                influenceごとのシーンのノード(見つからなければNone)、missingを記録した報告。

        Raises:
            ValueError: データの形が不正、``method="index"`` で頂点数が違う、位置が無い、または
                保存したinfluenceが1つもシーンに無い場合。
        """
        ...
    def _apply_weights_data(self, saved: dict, nodes: list[Node | None], method: str, report: ValidationReport, fast: bool) -> None:
        """検査済みのデータを書き戻す(:meth:`setWeightsData` の本体)。Undoの文脈は呼出し側が持つ。

        Args:
            saved (dict): :meth:`_parse_weights_data` の戻り値。
            nodes (list[Node | None]): 保存したinfluenceごとのシーンのノード。
            method (str): ``"index"`` または ``"position"``。
            report (ValidationReport): 書かなかったものの記録先。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            None: 値を返さない。
        """
        ...
    def _weight_sources(self, saved: dict, method: str) -> Sequence[int]:
        """現在の各頂点が値を使う、保存した頂点の番号を返す。

        Args:
            saved (dict): 検査済みのデータ。
            method (str): ``"index"`` は同じ番号、``"position"`` は最も近い保存位置の頂点。

        Returns:
            Sequence[int]: 現在の頂点番号順の、保存した頂点の番号。
        """
        ...
    def _weight_rows(self, saved: dict, columns: list[int | None], width: int, sources: Sequence[int], report: ValidationReport) -> tuple[list[int], list[float]]:
        """現在の頂点ごとに、全influence(物理順)のウェイトの行を作る。シーンは変更しない。

        見つからないinfluenceの値は除き、残りを元の合計へ比率を保って拡大する。残りがすべて0の頂点は
        書かずにreportへ記録する。

        Args:
            saved (dict): 検査済みのデータ。
            columns (list[int | None]): 保存したinfluenceごとの、現在の物理番号。見つからなければNone。
            width (int): 現在のinfluenceの数。
            sources (Sequence[int]): 現在の頂点ごとの、保存した頂点の番号。
            report (ValidationReport): 書かない頂点の記録先。

        Returns:
            tuple[list[int], list[float]]: 書き込む頂点番号(昇順)と、頂点順・物理順の平坦な値。
        """
        ...
    def _write_blend_weights(self, blend: list[float] | None, sources: Sequence[int], fast: bool) -> None:
        """DQブレンドウェイトを、現在の値と違う場合だけ全頂点へ書く。

        Args:
            blend (list[float] | None): 保存した頂点ごとの値。Noneは書かない。
            sources (Sequence[int]): 現在の頂点ごとの、保存した頂点の番号。
            fast (bool): TrueはMFnSkinCluster.setBlendWeights、Falseは範囲指定の1回のsetAttr。

        Returns:
            None: 値を返さない。
        """
        ...
    def _apply_weight_settings(self, settings: dict, report: ValidationReport, fast: bool) -> None:
        """スキニングの設定を、現在の値と違うものだけ書く。書けない設定はreportへ記録する。

        Args:
            settings (dict): 検査済みの ``settings``。
            report (ValidationReport): 書かなかった設定の記録先。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            None: 値を返さない。
        """
        ...
    def _capture_ngskin_layers(self, paths: om2.MDagPathArray) -> list[dict] | None:
        """ngSkinTools2のレイヤーを、:meth:`getWeightsData` の ``ngSkinLayers`` の形で取得する。

        Args:
            paths (om2.MDagPathArray): influenceObjects()。レイヤーの論理番号を保存の位置へ変換する。

        Returns:
            list[dict] | None: レイヤーごとの辞書。ngSkinTools2を使えない、またはレイヤーが無ければNone。
        """
        ...
    def _apply_ngskin_layers(self, saved_layers: list[dict] | None, columns: list[int | None], logical: list[int], sources: Sequence[int], report: ValidationReport, fast: bool) -> None:
        """保存したngSkinTools2のレイヤーで、このskinClusterのレイヤーを作り直す。

        Args:
            saved_layers (list[dict] | None): 検査済みの ``ngSkinLayers``。
            columns (list[int | None]): 保存したinfluenceごとの、現在の物理番号。
            logical (list[int]): 現在の物理番号ごとのweights[]の論理番号(ngSkinTools2のinfluence番号)。
            sources (Sequence[int]): 現在の頂点ごとの、保存した頂点の番号。
            report (ValidationReport): 書かなかったものの記録先。
            fast (bool): TrueはレイヤーのウェイトのUndoを記録しない。

        Returns:
            None: 値を返さない。
        """
        ...
    @staticmethod
    def _ngskin_api() -> ModuleType | None:
        """読み込み済みのngSkinTools2のAPIを返す。

        Returns:
            module | None: ``ngSkinTools2.api``。プラグイン未ロード・APIなしはNone。
        """
        ...
    def _input_points(self) -> om2.MPointArray:
        """skinClusterに入る前の形状の頂点位置(オブジェクト空間、cm)を返す。

        入力の形状を読めない場合は、出力のMeshの位置を返す。

        Returns:
            om2.MPointArray: 頂点番号順の位置。
        """
        ...
    @classmethod
    def _parse_weights_data(cls, data: dict) -> dict:
        """:meth:`getWeightsData` の辞書の形を確かめ、適用に使う形へ変える。シーンは変更しない。

        Args:
            data (dict): 確かめる辞書。

        Returns:
            dict: ``vertexCount``・``influences`` (NodeRefのlist)・``influenceLocks``・
                ``weights`` (indicesとvaluesの組)・``blendWeights``・``positions``・``settings``・
                ``ngSkinLayers`` を持つ辞書。

        Raises:
            TypeError: dataが辞書でない場合。
            ValueError: 形が不正な場合。
        """
        ...
    @classmethod
    def _parse_weight_settings(cls, settings: dict | None) -> dict:
        """``settings`` の形を確かめる。

        Args:
            settings (dict | None): 保存した設定。Noneは設定を書かない。

        Returns:
            dict: 4つの設定。保存に無い設定はNone。

        Raises:
            ValueError: 形または値が不正な場合。
        """
        ...
    @staticmethod
    def _parse_ngskin_layers(layers: list[dict] | None, width: int, count: int) -> list[dict] | None:
        """``ngSkinLayers`` の形と、親の対応(循環が無いこと)を確かめる。

        Args:
            layers (list[dict] | None): 保存したレイヤー。
            width (int): 保存したinfluenceの数。
            count (int): 保存した頂点数。

        Returns:
            list[dict] | None: 確かめたレイヤー。無ければNone。

        Raises:
            ValueError: 形が不正、または親が循環する場合。
        """
        ...
    def _inverted_points(self, sculpted_points: om2.MPointArray) -> list[tuple[float, float, float]]:
        """:meth:`invertShape` の頂点の位置(Origの空間)を計算する。シーンは変更しない。

        Args:
            sculpted_points (om2.MPointArray): 現在のポーズで整えた形のオブジェクト空間の頂点。

        Returns:
            list[tuple[float, float, float]]: 頂点番号順の補正形状の位置(cm)。
        """
        ...
    @staticmethod
    def _plug_matrix(plug: om2.MPlug) -> om2.MMatrix:
        """matrix 型のアトリビュートの値を読む。値の無い要素は単位マトリクスにする。

        Args:
            plug (om2.MPlug): matrix 型のアトリビュートの Plug。

        Returns:
            om2.MMatrix: 値。
        """
        ...
    @staticmethod
    def _geometry_skin_uuids(node: Node) -> list[str]:
        """形状を変形するskinClusterのUUIDを、DagNode.getSkinClustersの規則で集める。

        Jointの同名メソッドはinfluence接続の照会なので、DagNodeの実装を直接呼ぶ。

        Args:
            node (Node): 調べるノード。DAGノード以外は空。

        Returns:
            list[str]: skinClusterのUUID文字列。getSkinClustersと同じ順。
        """
        ...
    def _uuid_or_none(self, node: str) -> str | None:
        """ノード名から Maya UUID を取得する。

        Args:
            node (str): UUID を問い合わせるノード名。

        Returns:
            str | None: 対応する UUID。ノードが存在しない場合は None。
        """
        ...
    @staticmethod
    def _path_uuid(path: om2.MDagPath) -> str | None:
        """influenceのDAGパスから、名前を経由せずにMaya UUIDを取得する。

        ``_uuid_or_none(path.fullPathName())`` と同じ値を、名前の再解決なしで求める。

        Args:
            path (om2.MDagPath): influenceObjects()のパス。

        Returns:
            str | None: 対応するUUID。パスまたはノードが無効ならNone。
        """
        ...
    def _mesh_node(self) -> om2.MObject:
        """初期化時の先頭geometryのMObjectを返す。

        Returns:
            om2.MObject: mesh_pathが指すノード。
        """
        ...
    def _geometry_dag_path(self, name: str) -> om2.MDagPath:
        """geometry 名から shape まで展開した MDagPath を取得する。

        Args:
            name (str): geometry のノード名。

        Returns:
            om2.MDagPath: Transform なら shape へ展開した DAG パス。
        """
        ...
    def _first_geometry_name(self) -> str:
        """skinCluster が変形する先頭 geometry 名を取得する。

        Returns:
            str: skinCluster に登録された先頭 geometry 名(フルパス)。

        Raises:
            IndexError: geometry がない場合。
        """
        ...
    def _influence_index(self, joint: str) -> int | None:
        """登録influenceの名前/UUIDを照合し、対応する物理番号を取得する。

        Args:
            joint (str): 検索するinfluence名。

        Returns:
            int | None: influenceObjects()のリスト位置。一致するUUIDまたはpartial名の候補のうち
                最初の物理番号を選び、weights[]の論理番号は返さない。未登録はNone。
        """
        ...
    def _all_vertices(self) -> tuple[om2.MObject, int]:
        """mesh の全頂点 component と頂点数を生成する。

        Returns:
            tuple[om2.MObject, int]: 全頂点を含む component と頂点数。
        """
        ...
    def _require_influences(self, joints: str | Node | Iterable) -> list[int]:
        """influence指定を検証し、指定順の物理番号へ変換する。シーンは変更しない。

        Args:
            joints (str | Node | Iterable): 指定順のinfluence参照。

        Returns:
            list[int]: influenceObjects()内の物理番号。weights[]の論理番号ではない。

        Raises:
            TypeError: 頂点・コンポーネントやアトリビュートを渡した場合、または入力型が不正な場合。
            ValueError: 空・未登録・重複の場合。
        """
        ...
    def _vertex_indices(self, vertices: Vertex | Vertices | int | str | Iterable | None) -> list[int] | None:
        """頂点指定を、先頭Meshの頂点番号のリストへ変換する。シーンは変更しない。

        Args:
            vertices (Vertex | Vertices | int | str | Iterable | None): 頂点参照・番号・頂点名
                (``"mesh.vtx[0:3]"`` の範囲も可)、またはそれらの反復可能オブジェクト。

        Returns:
            list[int] | None: 指定順の頂点番号。Noneを渡した場合はNone(全頂点)。

        Raises:
            TypeError: 入力型が頂点以外(bool・float・エッジ等)の場合。
            ValueError: 先頭Mesh以外の頂点、または同じ頂点の重複の場合。
            IndexError: 頂点番号が範囲外の場合。
        """
        ...
    @staticmethod
    def _vertex_name_indices(name: str, mesh: om2.MObject, num_vertices: int) -> list[int]:
        """``"mesh.vtx[0:3]"`` のような頂点名を、先頭Meshの頂点番号へ展開する。

        Args:
            name (str): 頂点の名前。範囲・``[*]`` を含んでよい。
            mesh (om2.MObject): 先頭MeshのShape。
            num_vertices (int): 先頭Meshの頂点数。complete指定の展開に使う。

        Returns:
            list[int]: Mayaが返す順の頂点番号。

        Raises:
            TypeError: 頂点以外のコンポーネント、またはノード名だけの場合。
            ValueError: 空文字、または先頭Mesh以外の頂点の場合。
            RuntimeError: 名前を解決できない場合。
        """
        ...
    def _single_vertex_index(self, vertex: Vertex | int | str) -> int:
        """1頂点の指定を頂点番号へ変換する。

        Args:
            vertex (Vertex | int | str): 先頭Meshの1頂点。

        Returns:
            int: 頂点番号。

        Raises:
            TypeError: Noneや頂点以外の型の場合。
            ValueError: 1頂点でない、または先頭Mesh以外の頂点の場合。
            IndexError: 頂点番号が範囲外の場合。
        """
        ...
    def _read_rows(self, vertex_indices: Sequence[int], physical_indices: Iterable[int]) -> list[list[float]]:
        """指定頂点・指定influenceのウェイトを、頂点ごとの行として読み取る。

        MFnSkinCluster.getWeightsはcomponentの番号を昇順で返すため、昇順で読んでから指定順へ並べ直す。

        Args:
            vertex_indices (Sequence[int]): 検証済みの頂点番号。重複なし。
            physical_indices (Iterable[int]): influenceObjects()内の物理番号。

        Returns:
            list[list[float]]: vertex_indicesの順の行。各行はphysical_indicesの順。
        """
        ...
    @staticmethod
    def _influence_locked(path: om2.MDagPath) -> bool:
        """influenceのlockInfluenceWeightsが有効か調べる。アトリビュートが無い型はFalse。

        Args:
            path (om2.MDagPath): influenceObjects()のパス。

        Returns:
            bool: ロックされている場合True。
        """
        ...
    @staticmethod
    def _normalize_row(row: list[float], vertex: int, specified: Iterable[int], free: Iterable[int], locked: Iterable[int]) -> None:
        """1頂点の全influence行を、指定列を優先して合計1へ正規化する(rowをその場で書き換える)。

        ロック列は保ち、空き(``1 - ロック合計``)から指定列の合計を引いた残りへ自由列を比率で合わせる。
        指定列の合計が空きを超えるか自由列がすべて0なら、指定列を空きへ比率で合わせ、自由列を0にする。

        Args:
            row (list[float]): 物理順の全influenceの値。
            vertex (int): エラー表示用の頂点番号。
            specified (Iterable[int]): 値を指定した物理番号。
            free (Iterable[int]): 指定もロックもされていない物理番号。
            locked (Iterable[int]): 値を保つ、ロックされた未指定の物理番号。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 負値・非有限値がある、ロック値の合計が1を超える、または合計0で正規化できない場合。
        """
        ...
    def _normalized_write(self, values: list[float], width: int, vertex_indices: Sequence[int], physical_indices: list[int]) -> tuple[list[float], list[int]]:
        """setWeights(normalize=True)の書込み値を、対象頂点の現在値から計算する。シーンは変更しない。

        Args:
            values (list[float]): 検証済みのV*K値または共通K値。
            width (int): 指定列数K。
            vertex_indices (Sequence[int]): 書き込む頂点番号。
            physical_indices (list[int]): 指定influenceの物理番号。

        Returns:
            tuple[list[float], list[int]]: 頂点順の平坦な値と、その列の物理番号。
                指定列の後に、値が変わった未指定列を物理順で続ける。
        """
        ...
    def _copy_destination(self, target: str | Node) -> SkinCluster:
        """copyWeightsToの転送先を、既存またはバインドしたSkinClusterへ解決する。

        Args:
            target (str | Node): skinCluster、または形状・その親Transform。

        Returns:
            SkinCluster: 転送先。形状にskinClusterが無ければ自身のinfluenceでバインドする。

        Raises:
            TypeError: skinClusterでも形状でもない場合。
            ValueError: 形状を複数のskinClusterが変形している場合。
            RuntimeError: 名前が存在しない、またはMayaがバインドを拒否した場合。
        """
        ...
    @staticmethod
    def _has_geometry(path: om2.MDagPath) -> bool:
        """DAGパスが形状、または直下に中間でない形状を持つTransformか調べる。

        Args:
            path (om2.MDagPath): 調べるパス。

        Returns:
            bool: 形状を持つ場合True。
        """
        ...
    @staticmethod
    def _require_choice(value: str, name: str, choices: Sequence[str]) -> str:
        """文字列の選択肢を検証する。

        Args:
            value (str): 検証する値。
            name (str): エラー表示用の引数名。
            choices (Sequence[str]): 受け付ける値。

        Returns:
            str: 検証済みの値。

        Raises:
            TypeError: 文字列でない場合。
            ValueError: 選択肢にない場合。
        """
        ...
    def _flatten_weight_rows(self, joints: str | Node | Iterable, weights: Iterable[Iterable[float]]) -> list[object]:
        """頂点ごとの行を、:meth:`setWeights` の平坦な値の並びへ変換する。

        Args:
            joints (str | Node | Iterable): 指定influence。行の長さの基準。
            weights (Iterable[Iterable[float]]): 頂点ごとの行。

        Returns:
            list[object]: 行を順につないだ値。値の検証は呼出し側が行う。

        Raises:
            TypeError: 行が反復できない、または文字列の場合。
            ValueError: 行の長さが指定influenceの数と合わない場合。
        """
        ...
    def _prepare_weight_values(self, joints: Iterable, weights: Iterable, vertices: object = ..., broadcast: bool = ...) -> tuple:
        """指定influence・頂点と平坦なウェイト入力を検証する。

        値の数・有限性と、対象が空でなく登録済み/重複なしであることを検証する。
        非負・合計1・レイヤー・lockInfluenceWeightsは検査しない。シーンには書き込まない。

        Args:
            joints (Iterable): 指定順のinfluence参照。
            weights (Iterable): 頂点順のV*K値、またはbroadcast時の共通K値。
            vertices (object): :meth:`_vertex_indices` が受け付ける頂点指定。Noneは全頂点。
            broadcast (bool): TrueはK個の値を全対象頂点へ適用する。

        Returns:
            tuple: float値リスト、指定列数K、対象頂点番号の列、指定順の物理番号リスト。

        Raises:
            ValueError: 件数不一致。K個をbroadcastなしで複数頂点へ渡した場合は、broadcast=True・vertices=の
                指定を促す。
        """
        ...
    def _set_weight_values_fast(self, values: list[float], width: int, vertex_indices: Sequence[int], logical_indices: list[int]) -> None:
        """全対象ウェイトPlugを検査し、頂点・指定列の順にOpenMayaで生値を書き込む。

        writable/check_rangeを全件に適用してからsetDoubleを始める。MFnSkinCluster.setWeightsは
        未指定列を再配分し得るため使わない。liwや正規化設定も変更しない。
        事前検査後のAPI書込み失敗は自動で戻さず、Undo設定を変更しない。

        Args:
            values (list[float]): 検証済みのV*K値または共通K値。
            width (int): 指定列数K。
            vertex_indices (Sequence[int]): 書き込む頂点番号。valuesの行の順。
            logical_indices (list[int]): weights[]の論理番号。指定influence順。

        Returns:
            None: 値を返さない。
        """
        ...
    @staticmethod
    def _plug_chain_blocked(plug: om2.MPlug) -> bool:
        """Plugと、その親・マルチアトリビュート側の全段にロックまたは入力接続があるか調べる。

        :func:`mlib.core.fastWrite.writable` が要素から辿る親側の判定を、同じ頂点の要素で
        共有するために使う。例外は送出せず、書込み不能アトリビュートの判定も行わない。

        Args:
            plug (om2.MPlug): 調べる起点。weightList[v].weights のようなマルチアトリビュートのPlug。

        Returns:
            bool: いずれかの段がロックされているか、入力接続を持つ場合True。
        """
        ...
    def _set_weight_values_cmds(self, values: list[float], width: int, vertex_indices: Sequence[int], logical_indices: list[int]) -> None:
        """頂点・指定influence列の順に、cmdsで生のウェイト値を書き込む。

        weights[]には疎な論理番号を使う。指定順で論理番号が1ずつ増える列は
        ``weights[a:b]`` の範囲指定で1回のsetAttrにまとめ、番号の穴や順序の入れ替わりで区切る。
        全Plugの事前検査はせず、途中で拒否された場合も先行する書込みを自動で戻さない。
        Undoチャンクは呼出し側が管理する。

        範囲指定のsetAttrはロック・入力接続などで拒否されると範囲内のどの要素も更新しない。
        その場合だけ同じ範囲を要素ごとのsetAttrで書き直し、従来の要素ごとの書込みと同じく
        拒否された要素の手前まで更新して、その要素のMayaのエラーを送出する。

        Args:
            values (list[float]): 検証済みのV*K値または共通K値。
            width (int): 指定列数K。
            vertex_indices (Sequence[int]): 書き込む頂点番号。valuesの行の順。
            logical_indices (list[int]): weights[]の論理番号。指定influence順。

        Returns:
            None: 値を返さない。
        """
        ...
    @staticmethod
    def _consecutive_runs(logical_indices: Sequence[int]) -> list[tuple[int, int, int]]:
        """指定順の論理番号を、1ずつ増える連続した区間へ分ける。

        Args:
            logical_indices (Sequence[int]): weights[]の論理番号。指定influence順。

        Returns:
            list[tuple[int, int, int]]: 区間ごとの、指定列での開始位置・先頭の論理番号・要素数。
                例えば[0, 1, 3, 2]は[(0, 0, 2), (2, 3, 1), (3, 2, 1)]。
        """
        ...
    def _influence_indices(self, joints: Iterable[str], influences: om2.MDagPathArray) -> list[int | None]:
        """一回の操作内でUUIDと名前の検索表を共有する。

        Args:
            joints (Iterable[str]): 入力順のinfluence名。
            influences (om2.MDagPathArray): 操作開始時のinfluence配列。

        Returns:
            list[int | None]: 入力順の物理番号。未登録はNone。
                同じUUIDの複数パスは従来の逐次検索と同じ先頭を選ぶ。
        """
        ...
    def _transfer_pair(self, source_joint: str, target_joint: str) -> None:
        """選択された source influence 頂点のウェイトを target へ移す。

        元 influence に影響される頂点を選択し、skinPercent の transformMoveWeights を実行する。選択状態の復元は呼び出し側が行う。

        Args:
            source_joint (str): 移送元の influence 名。
            target_joint (str): 移送先の influence 名。

        Returns:
            None: 値を返さない。
        """
        ...
    def _influence_removal_target(self, joint, transfer_to_parent=..., *, force=...):
        """削除可否と祖先移送先を変更前に確認する。

        Args:
            joint: 処理対象のジョイント。
            transfer_to_parent: 削除前にウェイトを親インフルエンスへ移すか。
            force: 不正ウェイトの除去を許可するか。検証中は変更しない。
        """
        ...
    def _influence_removal_plans(self, nodes: list[Node], transfer_to_parent: bool = ..., *, force: bool = ...) -> tuple[list[tuple[Node, str | None]], tuple[list[int], list[float]] | None]:
        """複数のinfluenceの解除を変更前に検査し、深いものから順の解除計画を返す。シーンは変更しない。

        Args:
            nodes (list[Node]): 解除するinfluence。
            transfer_to_parent (bool): 祖先influenceへウェイトを移すか。
            force (bool): 不正ウェイトの修復を許可するか。検証中は変更しない。

        Returns:
            tuple[list[tuple[Node, str | None]], tuple[list[int], list[float]] | None]: 深い順の、解除する
                influenceと移送先のinfluence名の列と、検査で読んだ列と値(未読ならNone)。
        """
        ...
    def _apply_influence_removals(self, plans: list[tuple[Node, str | None]], snapshot: tuple[list[int], list[float]] | None, *, force: bool = ..., fast: bool = ..., deleting: bool = ...) -> None:
        """検査済みのinfluenceのウェイトを1回の読み書きで移送し、登録をまとめて解除する。

        親子を同時に外す場合も、途中の列を経由せず最終の移送先へ直接加算する。ngSkinTools2のレイヤーが
        使えるときはレイヤーごとに移送し、skinClusterのウェイトはレイヤーの再計算に任せる。

        Args:
            plans (list[tuple[Node, str | None]]): 深い順の、解除するinfluenceと移送先のinfluence名。
            snapshot (tuple[list[int], list[float]] | None): 検査時に読んだ列と値。Noneは読み直す。
            force (bool): 不正ウェイトを修復してから処理する。
            fast (bool): Trueはウェイトの書込みをOpenMayaで行い、登録解除もUndoへ記録しない。
            deleting (bool): Trueは直後にノードを削除する。0にした列の登録はMayaの削除処理が解除する。

        Returns:
            None: 値を返さない。
        """
        ...
    def _without_undo(self, enabled: bool) -> GeneratorContextManager[None]:
        """enabledのとき、処理をUndoへ記録しない。キューは消さない。

        Args:
            enabled (bool): TrueはUndoの記録を止める。Falseは何もしない。

        Yields:
            None: 値を渡さない。
        """
        ...
    def _move_weights(self, moves: dict[int, int], logical: list[int], snapshot: tuple[list[int], list[float]] | None, *, fast: bool = ...) -> None:
        """移送元の値を移送先へ加算し、変わった要素だけを書き込む。

        保存値を明示的に加算する(skinPercentの移送は正規化設定に依存するため)。

        Args:
            moves (dict[int, int]): 移送元と最終の移送先の物理番号。
            logical (list[int]): 物理番号から論理番号への対応。
            snapshot (tuple[list[int], list[float]] | None): 読み済みの列と値。Noneは読む。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            None: 値を返さない。
        """
        ...
    def _write_weight_entries(self, entries: list[tuple[tuple[int, int], float]], *, fast: bool = ...) -> None:
        """頂点と論理番号で指定した要素へ、生のウェイト値を書き込む。

        Args:
            entries (list[tuple[tuple[int, int], float]]): 頂点と論理番号の順に並べた ((頂点, 論理番号), 値) の列。
            fast (bool): Trueは全要素を検査してからOpenMayaで書き込み、Undoへ記録しない。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 要素がロック・入力接続されている、またはMayaが設定を拒否した場合。
        """
        ...
    def _remove_weight_elements(self, elements: list[om2.MPlug], *, fast: bool = ...) -> None:
        """検査済みのウェイト要素を除去する。

        Args:
            elements (list[om2.MPlug]): 除去する要素。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            None: 値を返さない。
        """
        ...
    def _require_transferable(self, pairs: list[tuple[Node, str]]) -> tuple[list[int], list[float]]:
        """祖先移送で読み書きする列を、変更前に検査する。シーンは変更しない。

        値は読み書きする列の全頂点を調べ、ロック・入力接続は移送元のいずれかにウェイトがある頂点の
        各列だけを調べる。親子を同時に外すと子のウェイトが親の列を経由するため、頂点は全移送元の和で扱う。

        Args:
            pairs (list[tuple[Node, str]]): 移送元のinfluenceと移送先のinfluence名の組。

        Returns:
            tuple[list[int], list[float]]: 読んだ列の物理番号と、頂点順の値。移送で読み直さずに使う。

        Raises:
            ValueError: 対象の列に負値・非有限値がある場合。
            RuntimeError: 書き込む要素のロック・入力接続がある場合。
        """
        ...
    def _editable_weights(self):
        """先頭meshの全influence値を取得し、ロック・接続・レイヤーを拒否する。"""
        ...
    def _editable_weight_list(self, *, check_layers: bool = ...) -> tuple[list[str], om2.MPlug]:
        """正規化・整理用に全ウェイトの編集条件を検査し、名前列とweightList参照を返す。

        登録influenceが空、lockInfluenceWeightsが有効、既存weightList配下にロック/入力接続、
        またはレイヤー推定の接続があれば拒否する。値の有限性や符号はここでは検査しない。
        この厳密な編集条件は、setWeightsの直接書込みには適用しない。

        Args:
            check_layers (bool): Falseはレイヤー推定の接続を拒否しない。

        Returns:
            tuple[list[str], om2.MPlug]: 物理順のinfluence名と、シーン内weightListへの参照。
                Plugはコピーした値ではない。ロックの一時解除や設定変更は行わない。
        """
        ...
    def _require_unlocked_influences(self) -> list[Node]:
        """lockInfluenceWeightsが有効なinfluenceを拒否する。

        Returns:
            list[Node]: 物理順のinfluence。

        Raises:
            RuntimeError: ロックされたinfluenceがある場合。
        """
        ...
    def _weight_cleanup_plan(self, *, check_layers: bool = ...) -> tuple[list[om2.MPlug], set[int]]:
        """既存の疎な要素から不正ウェイトの除去計画を作る。シーンは変更しない。

        Args:
            check_layers (bool): Falseはレイヤー推定の接続を拒否しない。

        Returns:
            tuple[list[om2.MPlug], set[int]]: 除去対象と、修復後も正値を持つ
                登録済みinfluenceの論理番号。存在しない要素は作成しない。

        Raises:
            RuntimeError: ウェイトが編集不可、または除去対象に出力接続がある場合。
        """
        ...
    @staticmethod
    def _validate_weight_locks(plug: om2.MPlug) -> None:
        """既存の疎なウェイト要素だけを辿りロックを検証する。

        Args:
            plug (om2.MPlug): weightListとその子。未存在要素は作成しない。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 要素または親のアトリビュートがロックされている場合。
        """
        ...
    def _normalized_weights(self, decimals: int | None = ..., limit: int | None = ...) -> tuple[list[str], list[float]]:
        """全頂点ウェイトの正規化・任意の列削減・十進丸めをメモリ上で計算する。

        編集可否と非負/有限値を検証し、各頂点の合計がゼロなら拒否する。
        limit指定時は大きい列を残して他列を0にし、桁指定時は最大剰余法で配分する。
        同率は物理順を優先する。結果はfloatへ戻し、シーンには書き込まない。

        Args:
            decimals (int | None): 0〜15の小数桁数。Noneは桁丸めなし。bool不可。
            limit (int | None): 呼出し側で検証した残列数の上限。Noneは列削減なし。

        Returns:
            tuple[list[str], list[float]]: 物理順のinfluence名と、頂点順×influence順の平坦な値。
        """
        ...
    def _has_layer_plugs(self) -> bool:
        """スキニングレイヤー関連ノードが接続されているか判定する。

        Returns:
            bool: 接続ノードの名前または型名にレイヤー判定用トークンが含まれる場合は True。実際のレイヤーデータの有無は調べない。
        """
        ...
    def _raise_if_layers(self) -> None:
        """スキニングレイヤー検出時に安全のため処理を中断する。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: _has_layer_plugs() が True の場合。
        """
        ...


class SkinClusters(Nodes[SkinCluster]):
    """重複を除き、保持順にSkinClusterを保持するコレクション。"""
    def __iter__(self) -> Iterator[SkinCluster]: ...
    @overload
    def __getitem__(self, index: int) -> SkinCluster: ...
    @overload
    def __getitem__(self, index: slice) -> SkinClusters: ...
    item_class: Any
    def mfn(self) -> list[oma2.MFnSkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.mfn` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def deforms(self, geometry: str | Node) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.deforms` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def copyWeightsTo(self, target: str | Node) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.copyWeightsTo` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def mirrorWeights(self, axis: str | int = ..., positiveToNegative: bool = ..., surfaceAssociation: str = ..., influenceAssociation: str | Sequence[str] = ..., normalize: bool = ...) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.mirrorWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def pruneWeights(self, threshold: float, normalize: bool = ..., *, fast: bool = ...) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.pruneWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getInfluences(self) -> list[list[Node]]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.getInfluences` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def addInfluences(self, joints: Joint | str | Iterable[Joint | str]) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.addInfluences` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def removeInfluences(self, joints: str | Node | Iterable, transferToParent: bool = ..., *, force: bool = ...) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.removeInfluences` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getBindPose(self) -> list[DagPose | None]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.getBindPose` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def resetBindPose(self) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.resetBindPose` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def restoreBindPose(self, worldSpace: bool = ..., *, ws: bool = ...) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.restoreBindPose` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getUnusedInfluences(self) -> list[list[Node]]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.getUnusedInfluences` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def removeUnusedInfluences(self, *, force: bool = ...) -> list[list[Node]]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.removeUnusedInfluences` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def removeInvalidWeights(self, *, fast: bool = ...) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.removeInvalidWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def hasInfluence(self, joint: str) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.hasInfluence` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getLockedInfluences(self) -> list[list[Node]]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.getLockedInfluences` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def setInfluencesLocked(self, joints: str | Node | Iterable, state: bool = ...) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.setInfluencesLocked` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getWeights(self, joints: str | Node | Iterable, *, vertices: Vertex | Vertices | int | str | Iterable | None = ..., rows: bool = ...) -> list[om2.MDoubleArray | list[list[float]]]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.getWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def setWeights(self, joints: str | Node | Iterable, weights: Iterable[float] | Iterable[Iterable[float]], *, vertices: Vertex | Vertices | int | str | Iterable | None = ..., normalize: bool = ..., broadcast: bool = ..., rows: bool = ..., fast: bool = ...) -> list[None]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.setWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getVertexWeights(self, vertex: Vertex | int | str, *, nonzero: bool = ...) -> list[dict[Node, float]]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.getVertexWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def setVertexWeights(self, vertex: Vertex | int | str, weights: Mapping[str | Node, float], normalize: bool = ..., *, fast: bool = ...) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.setVertexWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getWeightsData(self) -> list[dict]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.getWeightsData` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def setWeightsData(self, data: dict, *, nameMap: dict[str, str] | None = ..., replace: Iterable[tuple[str, str]] | None = ..., namespaceMap: dict[str, str] | None = ..., method: str = ..., fast: bool = ...) -> list[ValidationReport]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.setWeightsData` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def exportWeights(self, path: str | os.PathLike) -> list[pathlib.Path]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.exportWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def importWeights(self, path: str | os.PathLike, *, nameMap: dict[str, str] | None = ..., replace: Iterable[tuple[str, str]] | None = ..., namespaceMap: dict[str, str] | None = ..., method: str = ..., fast: bool = ...) -> list[ValidationReport]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.importWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def invertShape(self, sculpted: str | Node, name: str | None = ...) -> list[Mesh]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.invertShape` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def redistributeWeights(self, vertices: Vertex | Vertices | Iterable[int | Vertex], method: str = ...) -> list[None]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.redistributeWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def transferWeights(self, sourceTargetPairs: Iterable[tuple[Node | str, Node | str]], *, fast: bool = ...) -> list[None]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.transferWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def removeInfluence(self, joint: Joint | str, transferToParent: bool = ..., *, force: bool = ...) -> list[None]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.removeInfluence` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def normalizeWeights(self, decimals: int | None = ..., *, fast: bool = ...) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.normalizeWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getMaxInfluences(self) -> list[int]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.getMaxInfluences` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def setMaxInfluences(self, count: int, maintain: bool = ..., prune: bool = ..., *, fast: bool = ...) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.setMaxInfluences` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isMaintainingMaxInfluences(self) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.isMaintainingMaxInfluences` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getSkinningMethod(self) -> list[str]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.getSkinningMethod` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def setSkinningMethod(self, method: str) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.setSkinningMethod` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getNormalizeMode(self) -> list[str]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.getNormalizeMode` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def setNormalizeMode(self, mode: str) -> list[SkinCluster]:
        """各要素の :meth:`~mlib.nodes.skinCluster.SkinCluster.setNormalizeMode` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getDeformerWeights(self, geometryIndex: int = ...) -> list[list[float]]:
        """各要素の :meth:`~mlib.nodes.geometryFilter.GeometryFilter.getDeformerWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def setDeformerWeights(self, weights: Iterable[float], *, vertices: Component | Components | Iterable[int] | None = ..., geometryIndex: int = ..., fast: bool = ...) -> list[GeometryFilter]:
        """各要素の :meth:`~mlib.nodes.geometryFilter.GeometryFilter.setDeformerWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def dumpDeformerWeights(self, path: str | Path, geometryIndex: int | None = ...) -> list[None]:
        """各要素の :meth:`~mlib.nodes.geometryFilter.GeometryFilter.dumpDeformerWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def loadDeformerWeights(self, path: str | Path, *, fast: bool = ...) -> list[None]:
        """各要素の :meth:`~mlib.nodes.geometryFilter.GeometryFilter.loadDeformerWeights` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def copyDeformerWeightsTo(self, other: GeometryFilter | str, *, geometryIndex: int = ..., otherGeometryIndex: int = ..., fast: bool = ...) -> list[GeometryFilter]:
        """各要素の :meth:`~mlib.nodes.geometryFilter.GeometryFilter.copyDeformerWeightsTo` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getShadingEngines(self) -> list[list[ShadingEngine]]:
        """各要素の :meth:`~mlib.nodes.node.Node.getShadingEngines` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def sameNode(self, other: object) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.node.Node.sameNode` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isValid(self) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.node.Node.isValid` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isAlive(self) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.node.Node.isAlive` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def mnode(self) -> list[om2.MObject]:
        """各要素の :meth:`~mlib.nodes.node.Node.mnode` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getType(self, inherited: bool = ...) -> list[str | list[str]]:
        """各要素の :meth:`~mlib.nodes.node.Node.getType` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def hasFn(self, fn: int) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.node.Node.hasFn` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getTypeId(self) -> list[int]:
        """各要素の :meth:`~mlib.nodes.node.Node.getTypeId` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getPluginName(self) -> list[str]:
        """各要素の :meth:`~mlib.nodes.node.Node.getPluginName` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getClassification(self) -> list[list[str]]:
        """各要素の :meth:`~mlib.nodes.node.Node.getClassification` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isType(self, nodeType: str) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.node.Node.isType` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isLocked(self) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.node.Node.isLocked` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isFromReferencedFile(self) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.node.Node.isFromReferencedFile` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isAncestorOf(self, other: Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.node.Node.isAncestorOf` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isParentOf(self, other: Node | str | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.node.Node.isParentOf` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isRoot(self) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.node.Node.isRoot` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getNodeName(self, removeNamespace: bool = ...) -> list[str]:
        """各要素の :meth:`~mlib.nodes.node.Node.getNodeName` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getNamespace(self) -> list[Namespace]:
        """各要素の :meth:`~mlib.nodes.node.Node.getNamespace` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def setNamespace(self, namespace: str | Namespace, *, fast: bool = ...) -> list[Node]:
        """各要素の :meth:`~mlib.nodes.node.Node.setNamespace` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def delete(self, *, safe: bool = ..., fast: bool = ...) -> list[None]:
        """各要素の :meth:`~mlib.nodes.node.Node.delete` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def rename(self, name: str, ignoreShape: bool = ..., *, fast: bool = ...) -> list[Node]:
        """各要素の :meth:`~mlib.nodes.node.Node.rename` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def duplicate(self, name: str | None = ..., *, suffix: str | None = ..., **kwargs: object) -> list[Node]:
        """各要素の :meth:`~mlib.nodes.node.Node.duplicate` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getConnections(self, s: bool = ..., d: bool = ..., c: bool = ..., t: str | None = ..., et: bool = ..., scn: bool = ..., source: bool = ..., destination: bool = ..., connections: bool = ..., type: str | None = ..., exactType: bool = ..., skipConversionNodes: bool = ..., asPair: bool = ..., asNode: bool = ..., index: int | None = ...) -> list[list | Plug | Node | tuple | None]:
        """各要素の :meth:`~mlib.nodes.node.Node.getConnections` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def setKey(self, attributes: str | Iterable[str] | None = ..., *, unit: str | None = ..., timeUnit: str | None = ..., uiUnits: bool = ..., **kwargs) -> list[Node]:
        """各要素の :meth:`~mlib.nodes.node.Node.setKey` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def removeKey(self, attributes: str | Iterable[str] | None = ..., *, time: float | Sequence[float] | None = ..., timeUnit: str | None = ...) -> list[Node]:
        """各要素の :meth:`~mlib.nodes.node.Node.removeKey` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def moveKey(self, attributes: str | Iterable[str] | None = ..., *, time: float | Sequence[float] | None = ..., timeOffset: float = ..., valueOffset: float = ..., unit: str | None = ..., timeUnit: str | None = ...) -> list[Node]:
        """各要素の :meth:`~mlib.nodes.node.Node.moveKey` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getHistory(self, type: str | None = ..., future: bool = ...) -> list[list[Node]]:
        """各要素の :meth:`~mlib.nodes.node.Node.getHistory` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def findCycles(self) -> list[list[list[Plug]]]:
        """各要素の :meth:`~mlib.nodes.node.Node.findCycles` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getPlugs(self, userDefined: bool = ..., includeChildren: bool = ..., *, writable: bool = ..., **listAttrFlags) -> list[list[Plug]]:
        """各要素の :meth:`~mlib.nodes.node.Node.getPlugs` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getAliases(self) -> list[list[tuple[str, Plug]]]:
        """各要素の :meth:`~mlib.nodes.node.Node.getAliases` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def addAttr(self, longName: str = ..., type: str | None = ..., subType: str | None = ..., channelBox: bool = ..., childNames: Sequence[str] | None = ..., childShortNames: Sequence[str] | None = ..., childSuffixes: Sequence[str] | None = ..., proxy: Plug | str | None = ..., getPlug: bool = ..., *, safe: bool = ..., fast: bool = ..., unit: str = ..., timeUnit: str = ..., attributeType: str = ..., at: str = ..., binaryTag: str = ..., bt: str = ..., cachedInternally: bool = ..., ci: bool = ..., category: str | Sequence[str] = ..., ct: str | Sequence[str] = ..., dataType: str | Sequence[str] = ..., dt: str | Sequence[str] = ..., defaultValue: object = ..., dv: object = ..., disconnectBehaviour: int = ..., dcb: int = ..., edit: bool = ..., e: bool = ..., enforcingUniqueName: bool = ..., eun: bool = ..., enumName: str = ..., en: str = ..., exists: bool = ..., ex: bool = ..., fromPlugin: bool = ..., fp: bool = ..., hasMaxValue: bool = ..., hxv: bool = ..., hasMinValue: bool = ..., hnv: bool = ..., hasSoftMaxValue: bool = ..., hsx: bool = ..., hasSoftMinValue: bool = ..., hsn: bool = ..., hidden: bool = ..., h: bool = ..., indexMatters: bool = ..., im: bool = ..., internalSet: bool = ..., keyable: bool = ..., k: bool = ..., ln: str = ..., maxValue: float | om2.MAngle | om2.MDistance | om2.MTime = ..., max: float | om2.MAngle | om2.MDistance | om2.MTime = ..., minValue: float | om2.MAngle | om2.MDistance | om2.MTime = ..., min: float | om2.MAngle | om2.MDistance | om2.MTime = ..., multi: bool = ..., m: bool = ..., niceName: str = ..., nn: str = ..., numberOfChildren: int = ..., nc: int = ..., parent: str = ..., p: str = ..., pxy: Plug | str | None = ..., query: bool = ..., q: bool = ..., readable: bool = ..., r: bool = ..., shortName: str = ..., sn: str = ..., softMaxValue: float | om2.MAngle | om2.MDistance | om2.MTime = ..., smx: float | om2.MAngle | om2.MDistance | om2.MTime = ..., softMinValue: float | om2.MAngle | om2.MDistance | om2.MTime = ..., smn: float | om2.MAngle | om2.MDistance | om2.MTime = ..., storable: bool = ..., s: bool = ..., usedAsColor: bool = ..., uac: bool = ..., usedAsFilename: bool = ..., uaf: bool = ..., usedAsProxy: bool = ..., uap: bool = ..., worldSpace: bool = ..., ws: bool = ..., writable: bool = ..., w: bool = ..., cb: bool = ..., **kwargs) -> list[Plug | None]:
        """各要素の :meth:`~mlib.nodes.node.Node.addAttr` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def moveAttrOrder(self, name: str, offset: int) -> list[Node]:
        """各要素の :meth:`~mlib.nodes.node.Node.moveAttrOrder` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getPlug(self, name: str) -> list[Plug]:
        """各要素の :meth:`~mlib.nodes.node.Node.getPlug` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def hasAttr(self, name: str) -> list[bool]:
        """各要素の :meth:`~mlib.nodes.node.Node.hasAttr` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getUuid(self) -> list[str | None]:
        """各要素の :meth:`~mlib.nodes.node.Node.getUuid` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getName(self) -> list[str]:
        """各要素の :meth:`~mlib.nodes.node.Node.getName` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getFullName(self) -> list[str]:
        """各要素の :meth:`~mlib.nodes.node.Node.getFullName` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def asString(self) -> list[str]:
        """各要素の :meth:`~mlib.core.object.Object.asString` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
