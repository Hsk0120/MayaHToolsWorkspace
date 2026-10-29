# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""skinClusterのinfluenceと、先頭Meshの頂点ウェイトを照会・編集する。

"""

import json
import math
from decimal import Decimal, localcontext, ROUND_FLOOR
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
from ..core.fastWrite import require_range, require_writable, set_attr
from ..core.object import Object
from ..decorator import _edit_context, _require_bool, preservedSelection, undoChunk
from ..maths import easing
from ..util import _world_space
from .dagNode import DagNode
from .joint import Joint
from .node import Node, Nodes
from typing import Any, Iterable, Iterator, Sequence
from mlib.components.vertex import Vertex
from mlib.components.vertex import Vertices
from mlib.nodes.dagPose import DagPose
from typing import overload



class SkinCluster(Node):
    """skinClusterを参照し、influenceと先頭出力Meshの頂点ウェイトを照会・編集する。

    構築時の先頭geometry名・DAGパスと、自身のMFnSkinClusterを保持する。
    頂点操作はそのgeometryがMeshであることを前提とし、複数geometryの一括編集は行わない。
    influenceObjects()の物理順と、weights[]への書込みに使う論理番号を区別する。
    """
    _LAYER_TOKENS: tuple
    def __init__(self, skinCluster: str | om2.MObject | om2.MDagPath) -> None:
        """skinCluster 名または Maya オブジェクトからラッパーを初期化する。

        取得専用で、新規バインドは :meth:`bind` を使う。先頭 geometry のみを保持する。
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
    @classmethod
    def bind(cls, mesh: str | Node, influences: Sequence[str | Node], maxInfluences: int = ...) -> SkinCluster:
        """未スキニングの形状を指定influenceへバインドする。

        Args:
            mesh (str | Node): Mayaがバインド可能な形状またはtransform。
            influences (Sequence[str | Node]): バインドする骨等のtransform。
            maxInfluences (int): 1頂点に割り当てる最大数。正の整数。

        Returns:
            SkinCluster: 作成したskinCluster。
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
    def copyWeightsTo(self, target: str | SkinCluster) -> None:
        """別skinClusterへ最近傍でウェイトを転送する。

        Args:
            target (str | SkinCluster): 別のバインド済み転送先。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 転送先がskinCluster以外のノードの場合。
            ValueError: 転送先が自身の場合。
            RuntimeError: 転送先の名前が存在しない場合、またはMayaが転送を拒否した場合。

        Note:
            closestPoint、name/closestJointによる近似転送で正規化する。
            異なる基準姿勢の補正やメッシュ削減は行わない。
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
    def getBindPose(self) -> DagPose | None:
        """bindPoseアトリビュートに接続された保存ポーズを取得する。

        Returns:
            DagPose | None: 接続されたポーズ。未接続ならNone。

        Raises:
            RuntimeError: skinClusterが無効、または接続先がdagPoseでない場合。
        """
        ...
    def restoreBindPose(self, worldSpace: bool = ...) -> SkinCluster:
        """接続されたポーズの全メンバーを保存姿勢へ復元する。

        ポーズを共有する別のskinClusterや、influence以外のメンバーにも影響する。
        ロックや入力接続は解除しない。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。

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
    def getWeights(self, joints: str | Node | Iterable) -> om2.MDoubleArray:
        """指定influenceの全頂点ウェイトを、先頭Meshから取得する。

        APIにはinfluenceObjects()内の物理番号を渡し、疎なweights[]の論理番号は渡さない。

        Args:
            joints (str | Node | Iterable): 登録済みinfluence。複数は名前と参照を混在させない。

        Returns:
            om2.MDoubleArray: 頂点番号順・各頂点内はjoints順の、頂点数×指定数の平坦な値配列。
                無次元の独立した値で、配列の変更はシーンへ反映されない。

        Note:
            setWeightsの空・未登録・重複検証は行わず、入力失敗は名前解決・配列変換・APIへ委譲する。
        """
        ...
    def setWeights(self, joints: str | Node | Iterable, weights: Iterable[float], *, fast: bool = ...) -> None:
        """指定influenceの全頂点ウェイトを、正規化せず生の値として設定する。

        共通検証後、通常はcmds.setAttrで頂点・指定列の順に書く。指定順で連続する論理番号は
        範囲指定の1回のsetAttrにまとめるが、失敗時の部分更新とエラーは要素ごとの書込みと同じ。fastは全対象Plugの
        ロック・入力接続・書込み可否とアトリビュート範囲を先に検査し、MPlug.setDoubleで順に書く。
        どちらもMFnSkinCluster.setWeightsによる未指定列の再配分は使わない。

        Args:
            joints (str | Node | Iterable): 空でない登録済みinfluence。名前またはNodeを同じ形式で指定する。
                同一influenceの重複指定は拒否する。
            weights (Iterable[float]): 頂点数V・指定列数Kに対しV*K個、または全頂点共通のK個。
                V*K個の場合は頂点順で、各頂点内はjoints順。値はfloatへ変換できる有限値。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。通常setterのself返却とは異なる既存仕様。

        Raises:
            TypeError: 数値に変換できない型、またはfastがbool以外の場合。
            ValueError: influenceが空・未登録・重複、件数不一致、非有限値、または数値文字列が不正な場合。
            RuntimeError: Plugが編集不可、またはMayaが設定を拒否した場合。

        Note:
            未指定列とinfluenceのロック設定は変更しないが、lockInfluenceWeightsを保護条件として
            拒否する処理も、レイヤー検出も行わない。非負・合計1を独自には検査しない。
            normalizeWeights/maintainMaxInfluences設定に合わせた再正規化もしない。
            通常経路はUndoが有効なら同じチャンクへ記録する。後半の失敗時に完了済み変更は
            自動で戻さず、fastの事前検査も書込み中の失敗に対する原子性は保証しない。
        """
        ...
    def dumpWeights(self, path: str) -> None:
        """全 influence の頂点ウェイトを JSON ファイルへ書き出す。

        シーン間でのバックアップ・復元・転送を想定した単純な JSON 形式で書き出す。
        influence の並びは getInfluences() と一致する。

        Args:
            path (str): 書き出し先のファイルパス。

        Returns:
            None: 値を返さない。
        """
        ...
    def loadWeights(self, path: str, *, fast: bool = ...) -> None:
        """dumpWeights() が書き出した JSON ファイルからウェイトを読み込み設定する。

        ファイルに記録された influence がすべてこの skinCluster に存在し、
        頂点数が現在の mesh と一致することを要求する。一致しない場合は
        ウェイトを変更せず例外を送出する。

        Args:
            path (str): 読み込むファイルパス。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 頂点数が現在の mesh と一致しない、またはファイルに
                記録された influence の一部がこの skinCluster に存在しない場合。

        Note:
            ``fast=True`` はOpenMaya直接更新(Undoなし)。既定の ``False`` は通常処理。
            fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        ...
    def redistributeWeights(self, vertices: Vertex | Vertices | Iterable[int | Vertex], method: str = ..., *, fast: bool = ...) -> None:
        """先頭Meshの頂点ウェイトを正規化し、イージングをかけて再正規化する。

        頂点番号はint()で変換し、重複を除いて昇順に処理する。各頂点で読取り・計算・書込みを行い、
        全頂点の書込み可否は先に検査しない。0のinfluenceは0のまま。linearでも合計1へ正規化する。

        Args:
            vertices (Vertex | Vertices | Iterable[int | Vertex]): 頂点または番号列。
                Vertex/Verticesは先頭Mesh所属に限る。空列は変更しない。
            method (str): mlib.maths.easing.CURVESの曲線名。既定cubic。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。途中失敗で先行する頂点・列の変更は自動で戻さない。

        Raises:
            TypeError: methodが文字列でない、fastがbool以外、または頂点入力を変換できない型の場合。
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
        登録の解除と残りの再配分は ``cmds.skinCluster(edit=True, removeInfluence=...)`` に任せる。
        最後の登録は外せない。Undo有効時は一つのチャンクへ記録する。fast引数は持たない。
        修復・移送・解除は順次行い、後続失敗で完了済み変更は戻さない。

        Args:
            joint (Joint | str): 解除対象のinfluence。
            transferToParent (bool): 祖先へ移送するか。False、または祖先がなければ標準の再配分。
            force (bool): 不正ウェイトを修復してから処理する。修復自体は正規化・ロック解除・レイヤー回避を行わない。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: transferToParent・forceがbool以外の場合。
            ValueError: 未登録、または最後のinfluenceの場合。
            RuntimeError: レイヤー・ロック・接続、またはMayaの編集失敗。
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
    def _influence_physical_indices(self, joints: str | Node | Iterable) -> om2.MIntArray:
        """influence参照を、指定順のAPI物理番号配列へ変換する。

        Args:
            joints (str | Node | Iterable): 対象skinClusterに登録されたinfluence。

        Returns:
            om2.MIntArray: influenceObjects()内の物理番号。weights[]の論理番号ではない。

        Note:
            未登録を除外せず、Noneが残ればMIntArray変換時に失敗する。
            setWeightsの登録/重複検証をこの取得用補助へ集約したものではない。
        """
        ...
    def _prepare_weight_values(self, joints: Iterable, weights: Iterable) -> tuple:
        """指定influenceと平坦なウェイト入力を検証し、書込み用の論理番号へ変換する。

        値の数・有限性と、対象が空でなく登録済み/重複なしであることを検証する。
        非負・合計1・レイヤー・lockInfluenceWeightsは検査しない。シーンには書き込まない。

        Args:
            joints (Iterable): 指定順のinfluence参照。
            weights (Iterable): 頂点順のV*K値、または全頂点共通のK値。

        Returns:
            tuple: float値リスト、指定列数K、全頂点数V、指定順の論理番号リスト。
                物理番号はinfluenceの解決に使い、indexForInfluenceObjectで論理番号へ写す。
        """
        ...
    def _set_weight_values_fast(self, values: list[float], width: int, num_vertices: int, logical_indices: list[int]) -> None:
        """全対象ウェイトPlugを検査し、頂点・指定列の順にOpenMayaで生値を書き込む。

        writable/check_rangeを全件に適用してからsetDoubleを始める。MFnSkinCluster.setWeightsは
        未指定列を再配分し得るため使わない。liwや正規化設定も変更しない。
        事前検査後のAPI書込み失敗は自動で戻さず、Undo設定を変更しない。

        Args:
            values (list[float]): 検証済みのV*K値または共通K値。
            width (int): 指定列数K。
            num_vertices (int): 全頂点数V。
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
    def _set_weight_values_cmds(self, values: list[float], width: int, num_vertices: int, logical_indices: list[int]) -> None:
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
            num_vertices (int): 全頂点数V。
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
    def _editable_weights(self):
        """先頭meshの全influence値を取得し、ロック・接続・レイヤーを拒否する。"""
        ...
    def _editable_weight_list(self) -> tuple[list[str], om2.MPlug]:
        """正規化・整理用に全ウェイトの編集条件を検査し、名前列とweightList参照を返す。

        登録influenceが空、lockInfluenceWeightsが有効、既存weightList配下にロック/入力接続、
        またはレイヤー推定の接続があれば拒否する。値の有限性や符号はここでは検査しない。
        この厳密な編集条件は、setWeightsの直接書込みには適用しない。

        Returns:
            tuple[list[str], om2.MPlug]: 物理順のinfluence名と、シーン内weightListへの参照。
                Plugはコピーした値ではない。ロックの一時解除や設定変更は行わない。
        """
        ...
    def _weight_cleanup_plan(self) -> tuple[list[om2.MPlug], set[int]]:
        """既存の疎な要素から不正ウェイトの除去計画を作る。シーンは変更しない。

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
    mesh: Any
    mesh_path: Any


class SkinClusters(Nodes):
    """重複を除き、保持順にSkinClusterを保持するコレクション。"""
    def __iter__(self) -> Iterator[SkinCluster]: ...
    @overload
    def __getitem__(self, index: int) -> SkinCluster: ...
    @overload
    def __getitem__(self, index: slice) -> SkinClusters: ...
    item_class: Any
