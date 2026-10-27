"""skinClusterのinfluenceと、先頭Meshの頂点ウェイトを照会・編集する。

"""

import inspect
import json
import math
from decimal import Decimal, localcontext, ROUND_FLOOR

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace

from ..core.fastWrite import require_range, require_writable, set_attr
from ..core.object import Object
from ..decorator import _edit_context, _pick_alias, _require_bool, preservedSelection, undoChunk
from ..maths import easing
from ..util import _world_space
from ..util import _ArgumentError, _UNSET
from .dagNode import DagNode
from .joint import Joint
from .node import Node, Nodes, _PerItemOnly


class SkinCluster(Node):
    """skinClusterを参照し、influenceと先頭出力Meshの頂点ウェイトを照会・編集する。

    構築時の先頭geometry名・DAGパスと、自身のMFnSkinClusterを保持する。
    頂点操作はそのgeometryがMeshであることを前提とし、複数geometryの一括編集は行わない。
    influenceObjects()の物理順と、weights[]への書込みに使う論理番号を区別する。
    """

    _LAYER_TOKENS = ("ngskin", "ngst", "ngskintools", "skinlayer", "skinninglayer", "layerdata")

    def __init__(self, skinCluster):
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
        super().__init__(skinCluster)
        self.mesh = self._first_geometry_name()
        self.mesh_path = self._geometry_dag_path(self.mesh)
        # 内部の照会で使い回す。公開の取得口は毎回新しく作る mfn()。
        self._skin_fn = oma2.MFnSkinCluster(self.mnode())

    @classmethod
    @undoChunk("mlibSkinClusterBind")
    def bind(cls, mesh, influences, maxInfluences=4):
        """未スキニングの形状を指定influenceへバインドする。

        Args:
            mesh (str | Node): Mayaがバインド可能な形状またはtransform。
            influences (Sequence[str | Node]): バインドする骨等のtransform。
            maxInfluences (int): 1頂点に割り当てる最大数。正の整数。

        Returns:
            SkinCluster: 作成したskinCluster。
        """
        mesh = Node(mesh)
        influences = [Node(n) for n in Nodes._resolve_inputs(influences)]
        if not influences or type(maxInfluences) is not int or maxInfluences < 1:
            raise ValueError("Expected influences and a positive maximum influence count")
        if SkinCluster._geometry_skin_uuids(mesh):
            raise ValueError("Geometry already has a skinCluster")
        return cls(cmds.skinCluster([n.getFullName() for n in influences], mesh.getFullName(),
                                   toSelectedBones=True, maximumInfluences=maxInfluences,
                                   normalizeWeights=1)[0])

    def mfn(self):
        """このskinClusterのMFnSkinClusterを、呼び出すたびに新しく作って返す。

        ``oma2.MFnSkinCluster`` は ``om2.MFnDependencyNode`` の派生で、:meth:`Node.mfn` の契約どおり
        内部で使い回す function set とは共有しない。

        Returns:
            oma2.MFnSkinCluster: このskinClusterの function set。

        Raises:
            RuntimeError: ノードが破棄されている(削除後にUndoの記録から消えた)場合。
        """
        # 破棄済みノードへ function set を作るとMayaが異常終了するため、先に確かめる。
        self._alive_fn()
        return oma2.MFnSkinCluster(self.mnode())

    def deforms(self, geometry):
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
        return self.getUuid() in self._geometry_skin_uuids(Node(geometry))

    @undoChunk("mlibSkinClusterCopyWeightsTo")
    def copyWeightsTo(self, target):
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
        target = SkinCluster(target)
        if target.getUuid() == self.getUuid():
            raise ValueError("Source and destination skinClusters must differ")
        cmds.copySkinWeights(sourceSkin=self.getFullName(), destinationSkin=target.getFullName(),
                             noMirror=True, surfaceAssociation="closestPoint",
                             influenceAssociation=["name", "closestJoint"], normalize=True)

    def getInfluences(self):
        """登録influenceをAPIの物理順で参照する。

        Returns:
            list[Node]: influenceObjects()のDAGパスから作る新しいラッパーのリスト。
                登録型に応じJoint以外も返す。リスト位置はweights[]の論理番号とは限らず、ノードは複製しない。
        """
        # influenceObjects()が返したばかりの有効なパスなので、入力の再解決を省いてラッパーにする。
        return [Node._wrap_dag_path(path) for path in self._skin_fn.influenceObjects()]

    @undoChunk("mlibSkinClusterAddInfluences")
    def addInfluences(self, joints):
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

        existing = {om2.MFnDependencyNode(path.node()).uuid().asString() for path in self._skin_fn.influenceObjects()}
        names = []
        for name in Object._input_names(joints):
            node = Node(name)
            if not node.isType("joint"):
                raise ValueError(f"Expected a joint: {name}")
            if node.getUuid() not in existing:
                existing.add(node.getUuid())
                names.append(node.getFullName())
        if names:
            cmds.skinCluster(self.getFullName(), edit=True, addInfluence=names, weight=0.0)
        return self

    def getBindPose(self):
        """bindPoseアトリビュートに接続された保存ポーズを取得する。

        Returns:
            DagPose | None: 接続されたポーズ。未接続ならNone。

        Raises:
            RuntimeError: skinClusterが無効、または接続先がdagPoseでない場合。
        """
        from .dagPose import DagPose

        return DagPose.fromSkinCluster(self)

    def restoreBindPose(self, worldSpace=_UNSET, *, ws=_UNSET):
        """接続されたポーズの全メンバーを保存姿勢へ復元する。

        ポーズを共有する別のskinClusterや、influence以外のメンバーにも影響する。
        ロックや入力接続は解除しない。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            SkinCluster: 自身。

        Raises:
            RuntimeError: ポーズが未接続、ノードが無効、またはMayaが復元を拒否した場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=True)
        with undoChunk("mlibSkinClusterRestoreBindPose"):
            ws = _world_space(worldSpace)
            pose = self.getBindPose()
            if pose is None:
                raise RuntimeError(f"No bind pose connected to {self.getFullName()}")
            pose.restore(ws=ws)
            return self

    @undoChunk("mlibSkinClusterResetBindPose")
    def resetBindPose(self):
        """このskinClusterのinfluenceの保存姿勢を現在の姿勢へ更新する。

        接続されたポーズ内のinfluenceだけを更新する。共有ポーズを参照する他の
        skinClusterからも更新が見える。bindPreMatrixやウェイトは変更しない。
        ポーズに存在しないinfluenceは自動追加せず、更新前に例外を出す。

        Returns:
            SkinCluster: 自身。

        Raises:
            ValueError: influenceが空、またはポーズに含まれていない場合。
            RuntimeError: ポーズが未接続、ノードが無効、またはMayaが更新を拒否した場合。
        """
        pose = self.getBindPose()
        if pose is None:
            raise RuntimeError(f"No bind pose connected to {self.getFullName()}")
        pose.reset(self.getInfluences())
        return self

    def getUnusedInfluences(self):
        """ウェイトを持たないinfluenceを検索する。シーンは変更しない。

        Returns:
            list[Node]: influence順のノードラッパー。微小値も使用中として扱い、
                閾値による切り捨てはしない。全geometryをMFnSkinClusterで判定する。

        Raises:
            RuntimeError: skinClusterが無効、または照会に失敗した場合。
        """
        result = []
        for path in self._skin_fn.influenceObjects():
            selection, _ = self._skin_fn.getPointsAffectedByInfluence(path)
            if not selection.length():
                result.append(Node._wrap_dag_path(path))
        return result

    def removeUnusedInfluences(self, *, force=_UNSET, fast=False, f=_UNSET):
        """未使用influenceの登録を外し、ノード自体は残す。

        force時は不正ウェイトを修復してから未使用を検索する。fastでは、その後で
        解除対象の構造を全件検査してから登録を外す。先行した修復・解除は自動で戻さない。

        Args:
            force (bool): 修復後に未使用を調べる。正規化やロック解除は行わない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            list[Node]: influence順の、登録を外したノード参照。対象がなければ空リスト。

        Raises:
            TypeError: force/fastがbool以外、またはforce/fを同時指定した場合。
            ValueError: 解除すると登録が空になる場合。
            RuntimeError: レイヤー・ロック・接続、またはMayaの編集失敗。
            NotImplementedError: fastで単一geometry条件を満たさない場合。
        """
        force = _pick_alias(force, f, "force", "f", default=False)
        with _edit_context("mlibSkinClusterRemoveUnusedInfluences", fast):
            _require_bool(force, "force")
            if force:
                _, used = self._weight_cleanup_plan()
                if not used:
                    raise ValueError("Cannot remove every influence from a skinCluster")
                self.removeInvalidWeights(fast=fast)
            unused = self.getUnusedInfluences()
            if unused and len(unused) == len(self.getInfluences()):
                raise ValueError("Cannot remove every influence from a skinCluster")
            if fast:
                from ..core.skinEdit import validate_removals
                for node in unused:
                    validate_removals(self, [(node, None)])
            for node in unused:
                self.removeInfluence(node.getFullName(), transferToParent=False, fast=fast)
            return unused

    def removeInvalidWeights(self, *, fast=False):
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
        with _edit_context("mlibSkinClusterRemoveInvalidWeights", fast):
            elements, _ = self._weight_cleanup_plan()
            if fast:
                modifier = om2.MDGModifier()
                for plug in elements:
                    modifier.removeMultiInstance(plug, False)
                if elements:
                    modifier.doIt()
            else:
                names = [plug.name() for plug in elements]
                for name in names:
                    cmds.removeMultiInstance(name, b=False)
            return self

    def hasInfluence(self, joint):
        """指定したjointがinfluenceに含まれるか判定する。

        Args:
            joint (str): 判定するjoint名。

        Returns:
            bool: influenceに含まれる場合は ``True``。
        """
        uuid = self._uuid_or_none(joint)
        if not uuid:
            return False
        return any(
            self._path_uuid(path) == uuid
            for path in self._skin_fn.influenceObjects()
        )

    def getWeights(self, joints):
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
        vertices, _ = self._all_vertices()
        return self._skin_fn.getWeights(self.mesh_path, vertices, self._influence_physical_indices(joints))

    def setWeights(self, joints, weights, *, fast=False):
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
        with _edit_context("mlibSkinClusterSetWeights", fast):
            values, width, num_vertices, logical_indices = self._prepare_weight_values(joints, weights)
            if fast:
                self._set_weight_values_fast(values, width, num_vertices, logical_indices)
            else:
                self._set_weight_values_cmds(values, width, num_vertices, logical_indices)

    def dumpWeights(self, path):
        """全 influence の頂点ウェイトを JSON ファイルへ書き出す。

        シーン間でのバックアップ・復元・転送を想定した単純な JSON 形式で書き出す。
        influence の並びは getInfluences() と一致する。

        Args:
            path (str): 書き出し先のファイルパス。

        Returns:
            None: 値を返さない。
        """
        influences = [node.getName() for node in self.getInfluences()]
        _, num_vertices = self._all_vertices()
        payload = {
            "influences": influences,
            "numVertices": num_vertices,
            "weights": list(self.getWeights(influences)),
        }
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file)

    def loadWeights(self, path, *, fast=False):
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
        with _edit_context("mlibSkinClusterLoadWeights", fast):
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            _, num_vertices = self._all_vertices()
            if payload["numVertices"] != num_vertices:
                raise ValueError(
                    f"Stored vertex count ({payload['numVertices']}) does not match "
                    f"the current mesh vertex count ({num_vertices})"
                )
            influences = payload["influences"]
            current_influences = {node.getName() for node in self.getInfluences()}
            missing = [name for name in influences if name not in current_influences]
            if missing:
                raise ValueError(f"Influences missing from this skinCluster: {missing}")
            self.setWeights(influences, payload["weights"], fast=fast)

    def redistributeWeights(self, vertices, method="cubic", *, fast=False):
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
        with _edit_context("mlibSkinClusterRedistributeWeights", fast):
            if not isinstance(method, str):
                raise TypeError(f"Easing method must be a str, got {type(method).__name__}")
            curve = method
            if curve not in easing.CURVES:
                raise ValueError(f"Unsupported easing method: {method}")
            num_vertices = om2.MFnMesh(self.mesh_path).numVertices
            from ..components.vertex import Vertex, Vertices

            if isinstance(vertices, Vertices):
                if vertices.shape.mnode() != self.mesh_path.node():
                    raise ValueError("Vertices must belong to this skinCluster's first mesh")
                vertices = vertices.indices
            elif isinstance(vertices, Vertex):
                vertices = [vertices]
            vertex_indices = set()
            for vertex in vertices:
                if isinstance(vertex, Vertex):
                    if vertex.shape.mnode() != self.mesh_path.node():
                        raise ValueError("Vertex must belong to this skinCluster's first mesh")
                    vertex = vertex.index
                # 既存番号入力のint変換を維持し、新しい頂点参照だけを所有者検証する。
                vertex_indices.add(int(vertex))
            vertex_indices = sorted(vertex_indices)
            for vertex in vertex_indices:
                if not (0 <= vertex < num_vertices):
                    raise IndexError(f"Vertex index out of range: {vertex}")
            if not vertex_indices:
                return
            influence_paths = self._skin_fn.influenceObjects()
            all_indices = om2.MIntArray(range(len(influence_paths)))
            logical_indices = [self._skin_fn.indexForInfluenceObject(path) for path in influence_paths]
            name = self.getFullName()
            for vertex in vertex_indices:
                component_fn = om2.MFnSingleIndexedComponent()
                component = component_fn.create(om2.MFn.kMeshVertComponent)
                component_fn.addElement(vertex)
                row = list(self._skin_fn.getWeights(self.mesh_path, component, all_indices))
                total = sum(row)
                if total <= 0.0:
                    raise ValueError(f"Vertex {vertex} has no weight to redistribute")
                normalized = [value / total for value in row]
                eased = [easing.ease(value, curve) for value in normalized]
                eased_total = sum(eased)
                if eased_total <= 0.0:
                    raise ValueError(f"Vertex {vertex} produced a zero-sum weight distribution")
                final = [value / eased_total for value in eased]
                for logical_index, value in zip(logical_indices, final):
                    set_attr(f"{name}.weightList[{vertex}].weights[{logical_index}]", value, fast=fast)

    def transferWeights(self, sourceTargetPairs, *, fast=False):
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
        with _edit_context("mlibSkinClusterTransferWeights", fast):
            self._raise_if_layers()

            pairs = []
            for pair in sourceTargetPairs:
                if isinstance(pair, (str, bytes)):
                    raise ValueError("Expected a source/target pair, not a string")
                pair = tuple(pair)
                if len(pair) != 2:
                    raise ValueError("Expected exactly two influences per pair")
                source, target = (Node._resolve_input(value) for value in pair)
                if any(not node.isValid() or not self.hasInfluence(node.getFullName()) for node in (source, target)):
                    raise ValueError("Both nodes must be influences of this skinCluster")
                if source.getUuid() != target.getUuid():
                    pairs.append((source.getFullName(), target.getFullName()))
            if fast:
                from ..core.skinEdit import transfer_weights
                transfer_weights(self, pairs)
            else:
                with preservedSelection():
                    for source_joint, target_joint in pairs:
                        self._transfer_pair(source_joint, target_joint)

    def removeInfluence(self, joint, transferToParent=True, *, force=_UNSET, fast=False, f=_UNSET):
        """祖先influenceへ加算してから登録を外す。ノード自体は削除しない。

        移送先は同じskinClusterの最も近い祖先influence。生ウェイトを加算してsourceを0にし、登録を外す。
        移送しない場合は通常cmds、fastはOM2で再配分する。最後の登録は外せない。
        fastの再配分はcmdsの規則(:mod:`mlib.core.skinEdit` に記載)を再現し、同じ生ウェイトになる。
        修復・移送・解除は順次行い、後続失敗で完了済み変更は戻さない。

        Args:
            joint (Joint | str): 解除対象のinfluence。
            transferToParent (bool): 祖先へ移送するか。False、または祖先がなければ標準の再配分。
            force (bool): 不正ウェイトを修復してから処理する。修復自体は正規化・ロック解除・レイヤー回避を行わない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: transferToParent・force・fastがbool以外、またはforce/fを同時指定した場合。
            ValueError: 未登録、または最後のinfluenceの場合。
            RuntimeError: レイヤー・ロック・接続、またはMayaの編集失敗。
            NotImplementedError: fastでgeometryが1個のmeshでない、負値・非有限値のウェイトがある、
                または再配分を再現できない場合(残りの合計が0になる頂点があり、ロックがなく
                bindMethodがClosest distance以外、配分先がjoint以外かロック済みだけ等)。
                修復・移送より前に送出し、何も変更しない。
        """
        force = _pick_alias(force, f, "force", "f", default=False)
        with _edit_context("mlibSkinClusterRemoveInfluence", fast):
            source, target = self._influence_removal_target(joint, transferToParent, force=force)
            if fast:
                from ..core.skinEdit import validate_removals
                validate_removals(self, [(source, target)], force=force)
            if force:
                self.removeInvalidWeights(fast=fast)
            if target is not None:
                # skinPercentの移送は正規化設定に依存するため、保存値を明示的に加算する。
                weights = list(self.getWeights([source.getFullName(), target]))
                summed = []
                for i in range(0, len(weights), 2):
                    summed.extend((0.0, weights[i] + weights[i + 1]))
                self.setWeights([source.getFullName(), target], summed, fast=fast)
            if fast:
                from ..core.skinEdit import remove_influence
                remove_influence(self, source)
            else:
                cmds.skinCluster(self.getName(), edit=True, removeInfluence=source.getFullName())

    def normalizeWeights(self, decimals=None, *, fast=False):
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
        with _edit_context("mlibSkinClusterNormalizeWeights", fast):
            names, values = self._normalized_weights(decimals)
            self.setWeights(names, values, fast=fast)
            return self

    def getMaxInfluences(self):
        """skinClusterのmaxInfluences設定値。実際の非ゼロ数ではない。

        Returns:
            int: skinClusterのmaxInfluences設定値。実際の非ゼロ数ではない。
        """
        return self.getPlug("maxInfluences").get()

    def setMaxInfluences(self, count, maintain=True, prune=False, *, fast=False):
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
        with _edit_context("mlibSkinClusterSetMaxInfluences", fast):
            if type(count) is not int or not 1 <= count <= 2147483647:
                raise ValueError("count must be a positive 32-bit integer")
            _require_bool(maintain, "maintain")
            _require_bool(prune, "prune")
            settings = [self.getPlug(attr) for attr in ("maxInfluences", "maintainMaxInfluences")]
            for plug in settings:
                if plug.mplug().isFreeToChange() != om2.MPlug.kFreeToChange:
                    attr = plug.getLongName()
                    raise RuntimeError(f"Setting is locked or connected: {attr}")
            computed = self._normalized_weights(limit=count) if prune else None
            settings[0].set(count, fast=fast)
            settings[1].set(maintain, fast=fast)
            if computed:
                self.setWeights(*computed, fast=fast)
            return self

    @staticmethod
    def _geometry_skin_uuids(node):
        """形状を変形するskinClusterのUUIDを、DagNode.getSkinClustersの規則で集める。

        Jointの同名メソッドはinfluence接続の照会なので、DagNodeの実装を直接呼ぶ。

        Args:
            node (Node): 調べるノード。DAGノード以外は空。

        Returns:
            list[str]: skinClusterのUUID文字列。getSkinClustersと同じ順。
        """
        if not isinstance(node, DagNode):
            return []
        return [skin.getUuid() for skin in DagNode.getSkinClusters(node)]

    def _uuid_or_none(self, node):
        """ノード名から Maya UUID を取得する。

        Args:
            node (str): UUID を問い合わせるノード名。

        Returns:
            str | None: 対応する UUID。ノードが存在しない場合は None。
        """
        try:
            return Node(node).getUuid()
        except RuntimeError:
            return None

    @staticmethod
    def _path_uuid(path):
        """influenceのDAGパスから、名前を経由せずにMaya UUIDを取得する。

        ``_uuid_or_none(path.fullPathName())`` と同じ値を、名前の再解決なしで求める。

        Args:
            path (om2.MDagPath): influenceObjects()のパス。

        Returns:
            str | None: 対応するUUID。パスまたはノードが無効ならNone。
        """
        if not path.isValid():
            return None
        node = path.node()
        if not om2.MObjectHandle(node).isValid():
            return None
        return om2.MFnDependencyNode(node).uuid().asString()

    def _geometry_dag_path(self, name):
        """geometry 名から shape まで展開した MDagPath を取得する。

        Args:
            name (str): geometry のノード名。

        Returns:
            om2.MDagPath: Transform なら shape へ展開した DAG パス。
        """
        # 名前とインスタンスパスの解決は既存Node/DagNodeの経路を共有する。
        path = Node(name).mpath()
        if path.node().hasFn(om2.MFn.kTransform):
            path.extendToShape()
        return path

    def _first_geometry_name(self):
        """skinCluster が変形する先頭 geometry 名を取得する。

        Returns:
            str: skinCluster に登録された先頭 geometry 名(フルパス)。

        Raises:
            IndexError: geometry がない場合。
        """
        geometries = oma2.MFnGeometryFilter(self.mnode()).getOutputGeometry()
        if not geometries:
            raise IndexError("This skinCluster has no output geometry")
        return om2.MFnDagNode(geometries[0]).fullPathName()

    def _influence_index(self, joint):
        """登録influenceの名前/UUIDを照合し、対応する物理番号を取得する。

        Args:
            joint (str): 検索するinfluence名。

        Returns:
            int | None: influenceObjects()のリスト位置。一致するUUIDまたはpartial名の候補のうち
                最初の物理番号を選び、weights[]の論理番号は返さない。未登録はNone。
        """
        return self._influence_indices((joint,), self._skin_fn.influenceObjects())[0]

    def _all_vertices(self):
        """mesh の全頂点 component と頂点数を生成する。

        Returns:
            tuple[om2.MObject, int]: 全頂点を含む component と頂点数。
        """
        num_vertices = om2.MFnMesh(self.mesh_path).numVertices
        component_fn = om2.MFnSingleIndexedComponent()
        vertices = component_fn.create(om2.MFn.kMeshVertComponent)
        component_fn.addElements(range(num_vertices))
        return vertices, num_vertices

    def _influence_physical_indices(self, joints):
        """influence参照を、指定順のAPI物理番号配列へ変換する。

        Args:
            joints (str | Node | Iterable): 対象skinClusterに登録されたinfluence。

        Returns:
            om2.MIntArray: influenceObjects()内の物理番号。weights[]の論理番号ではない。

        Note:
            未登録を除外せず、Noneが残ればMIntArray変換時に失敗する。
            setWeightsの登録/重複検証をこの取得用補助へ集約したものではない。
        """
        return om2.MIntArray(self._influence_indices(Object._input_names(joints), self._skin_fn.influenceObjects()))

    def _prepare_weight_values(self, joints, weights):
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
        joints = Object._input_names(joints)
        influences = self._skin_fn.influenceObjects()
        physical_indices = self._influence_indices(joints, influences)
        if not joints or None in physical_indices or len(set(physical_indices)) != len(joints):
            raise ValueError("Influences must be non-empty, registered and unique")
        values = [float(value) for value in weights]
        num_vertices = om2.MFnMesh(self.mesh_path).numVertices
        width = len(joints)
        if len(values) not in (width, num_vertices * width):
            raise ValueError("Weight count must match influence count or vertex count times influence count")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Weights must be finite")
        # 削除済み influence による配列の穴を考慮し、物理番号をアトリビュートの論理番号へ変換する。
        logical_indices = [self._skin_fn.indexForInfluenceObject(influences[i]) for i in physical_indices]
        return values, width, num_vertices, logical_indices

    def _set_weight_values_fast(self, values, width, num_vertices, logical_indices):
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
        weights_plug = self._dependency_fn().findPlug("weightList", False)
        # 全要素が同じweightsアトリビュートなので、書込み可否と範囲の定義を読むfunction setは
        # 1つを共有する。ロック・入力接続は要素ごと、親側(weightList[v].weights より上)は
        # 頂点ごとに毎回調べる。拒否する要素ではrequire_writable()を呼び、従来と同じ例外を送出する。
        attribute_fn = range_fn = None
        attribute_writable = has_limits = True
        edits = []
        for vertex in range(num_vertices):
            row = weights_plug.elementByLogicalIndex(vertex).child(0)
            row_blocked = self._plug_chain_blocked(row)
            offset = 0 if len(values) == width else vertex * width
            for column, index in enumerate(logical_indices):
                plug = row.elementByLogicalIndex(index)
                if attribute_fn is None:
                    attribute = plug.attribute()
                    attribute_fn = om2.MFnAttribute(attribute)
                    attribute_writable = attribute_fn.writable
                    if attribute.hasFn(om2.MFn.kNumericAttribute):
                        range_fn = om2.MFnNumericAttribute(attribute)
                        has_limits = range_fn.hasMin() or range_fn.hasMax()
                if row_blocked or plug.isLocked or plug.isDestination or not attribute_writable:
                    require_writable(plug, attribute_fn)
                if has_limits:
                    require_range(plug, values[offset + column], range_fn)
                edits.append((plug, values[offset + column]))
        # MFnSkinCluster.setWeightsはliw等の設定によって未指定値を再配分する。
        # 通常モードと同じ生値を維持するため、MPlugに直接書き込む。
        for plug, value in edits:
            plug.setDouble(value)

    @staticmethod
    def _plug_chain_blocked(plug):
        """Plugと、その親・配列側の全段にロックまたは入力接続があるか調べる。

        :func:`mlib.core.fastWrite.writable` が要素から辿る親側の判定を、同じ頂点の要素で
        共有するために使う。例外は送出せず、書込み不能アトリビュートの判定も行わない。

        Args:
            plug (om2.MPlug): 調べる起点。weightList[v].weights のような配列Plug。

        Returns:
            bool: いずれかの段がロックされているか、入力接続を持つ場合True。
        """
        current = plug
        while True:
            if current.isLocked or current.isDestination:
                return True
            if current.isChild:
                current = current.parent()
            elif current.isElement:
                current = current.array()
            else:
                return False

    def _set_weight_values_cmds(self, values, width, num_vertices, logical_indices):
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
        name = self.getFullName()
        runs = self._consecutive_runs(logical_indices)
        shared = len(values) == width
        for vertex in range(num_vertices):
            offset = 0 if shared else vertex * width
            prefix = f"{name}.weightList[{vertex}].weights"
            for column, first, count in runs:
                start = offset + column
                if count == 1:
                    set_attr(f"{prefix}[{first}]", values[start])
                    continue
                row = values[start:start + count]
                try:
                    set_attr(f"{prefix}[{first}:{first + count - 1}]", *row)
                except RuntimeError:
                    # 範囲指定は失敗時に何も書かないため、要素ごとに書き直して
                    # 拒否された要素までの部分更新とエラーを従来と揃える。
                    for position, value in enumerate(row):
                        set_attr(f"{prefix}[{first + position}]", value)

    @staticmethod
    def _consecutive_runs(logical_indices):
        """指定順の論理番号を、1ずつ増える連続した区間へ分ける。

        Args:
            logical_indices (Sequence[int]): weights[]の論理番号。指定influence順。

        Returns:
            list[tuple[int, int, int]]: 区間ごとの、指定列での開始位置・先頭の論理番号・要素数。
                例えば[0, 1, 3, 2]は[(0, 0, 2), (2, 3, 1), (3, 2, 1)]。
        """
        runs = []
        for column, index in enumerate(logical_indices):
            if runs:
                start, first, count = runs[-1]
                if index == first + count:
                    runs[-1] = (start, first, count + 1)
                    continue
            runs.append((column, index, 1))
        return runs

    def _influence_indices(self, joints, influences):
        """一回の操作内でUUIDと名前の検索表を共有する。

        Args:
            joints (Iterable[str]): 入力順のinfluence名。
            influences (om2.MDagPathArray): 操作開始時のinfluence配列。

        Returns:
            list[int | None]: 入力順の物理番号。未登録はNone。
                同じUUIDの複数パスは従来の逐次検索と同じ先頭を選ぶ。
        """
        joints = list(joints)
        if not joints:
            return []
        if len(joints) == 1:
            # 単数指定では検索表全体を構築せず、一致した時点で終了する。
            joint = joints[0]
            uuid = self._uuid_or_none(joint)
            for index, path in enumerate(influences):
                if ((uuid and self._path_uuid(path) == uuid)
                        or path.partialPathName() == joint):
                    return [index]
            return [None]
        by_uuid, by_name = {}, {}
        for index, path in enumerate(influences):
            uuid = self._path_uuid(path)
            if uuid:
                by_uuid.setdefault(uuid, index)
            by_name.setdefault(path.partialPathName(), index)
        result = []
        for joint in joints:
            candidates = (by_uuid.get(self._uuid_or_none(joint)), by_name.get(joint))
            result.append(min((i for i in candidates if i is not None), default=None))
        return result

    def _transfer_pair(self, source_joint, target_joint):
        """選択された source influence 頂点のウェイトを target へ移す。

        元 influence に影響される頂点を選択し、skinPercent の transformMoveWeights を実行する。選択状態の復元は呼び出し側が行う。

        Args:
            source_joint (str): 移送元の influence 名。
            target_joint (str): 移送先の influence 名。

        Returns:
            None: 値を返さない。
        """
        cmds.skinCluster(self.getName(), edit=True, selectInfluenceVerts=source_joint)
        if om2.MGlobal.getActiveSelectionList().length():
            cmds.skinPercent(self.getName(), transformMoveWeights=[source_joint, target_joint])

    def _influence_removal_target(self, joint, transfer_to_parent=True, *, force=False):
        """削除可否と祖先移送先を変更前に確認する。

        Args:
            joint: 処理対象のジョイント。
            transfer_to_parent: 削除前にウェイトを親インフルエンスへ移すか。
            force: 不正ウェイトの除去を許可するか。検証中は変更しない。
        """
        _require_bool(transfer_to_parent, "transferToParent")
        _require_bool(force, "force")
        self._raise_if_layers()
        source = joint if isinstance(joint, Node) else Node(joint)
        if not source.isValid() or not self.hasInfluence(source.getFullName()):
            raise ValueError("Joint is not an influence of this skinCluster")
        if len(self.getInfluences()) <= 1:
            raise ValueError("Cannot remove the last influence")
        target = source.getTransferTarget(self) if transfer_to_parent and isinstance(source, Joint) else None
        if force:
            if target is not None:
                # 既存の祖先移送は先頭mesh専用。未対応形状の拒否を修復より前に行う。
                om2.MFnMesh(self.mesh_path)
            self._weight_cleanup_plan()
        elif target is not None:
            self._editable_weights()
        return source, target

    def _editable_weights(self):
        """先頭meshの全influence値を取得し、ロック・接続・レイヤーを拒否する。"""
        names, _ = self._editable_weight_list()
        weights = list(self.getWeights(names))
        if any(not math.isfinite(v) or v < 0 for v in weights):
            raise ValueError("Weights must be finite and non-negative")
        return names, weights

    def _editable_weight_list(self):
        """正規化・整理用に全ウェイトの編集条件を検査し、名前列とweightList参照を返す。

        登録influenceが空、lockInfluenceWeightsが有効、既存weightList配下にロック/入力接続、
        またはレイヤー推定の接続があれば拒否する。値の有限性や符号はここでは検査しない。
        この厳密な編集条件は、setWeightsの直接書込みには適用しない。

        Returns:
            tuple[list[str], om2.MPlug]: 物理順のinfluence名と、シーン内weightListへの参照。
                Plugはコピーした値ではない。ロックの一時解除や設定変更は行わない。
        """
        self._raise_if_layers()
        influences = self.getInfluences()
        names = [node.getName() for node in influences]
        if not names:
            raise ValueError("No influences")
        for node in influences:
            if node.hasAttr("lockInfluenceWeights") and node.getPlug("lockInfluenceWeights").get():
                raise RuntimeError(f"Influence is locked: {node.getName()}")
        path = self.getFullName() + ".weightList"
        weight_list = self.getPlug("weightList").mplug()
        if weight_list.isLocked or weight_list.isDestination:
            raise RuntimeError("Weights are locked or connected")
        self._validate_weight_locks(weight_list)
        return names, weight_list

    def _weight_cleanup_plan(self):
        """既存の疎な要素から不正ウェイトの除去計画を作る。シーンは変更しない。

        Returns:
            tuple[list[om2.MPlug], set[int]]: 除去対象と、修復後も正値を持つ
                登録済みinfluenceの論理番号。存在しない要素は作成しない。

        Raises:
            RuntimeError: ウェイトが編集不可、または除去対象に出力接続がある場合。
        """
        _, weight_list = self._editable_weight_list()
        registered = {self._skin_fn.indexForInfluenceObject(path) for path in self._skin_fn.influenceObjects()}
        elements, used = [], set()
        for vertex in weight_list.getExistingArrayAttributeIndices():
            row = weight_list.elementByLogicalIndex(vertex).child(0)
            for index in row.getExistingArrayAttributeIndices():
                plug = row.elementByLogicalIndex(index)
                value = plug.asDouble()
                if index not in registered or not math.isfinite(value) or value < 0:
                    if plug.isConnected:
                        raise RuntimeError(f"Invalid weight is connected: {plug.name()}")
                    elements.append(plug)
                elif value > 0:
                    used.add(index)
        return elements, used

    @staticmethod
    def _validate_weight_locks(plug):
        """既存の疎なウェイト要素だけを辿りロックを検証する。

        Args:
            plug (om2.MPlug): weightListとその子。未存在要素は作成しない。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 要素または親のアトリビュートがロックされている場合。
        """
        if plug.isLocked or plug.isDestination:
            raise RuntimeError(f"Weight element is locked or connected: {plug.name()}")
        if plug.isArray:
            for index in plug.getExistingArrayAttributeIndices():
                SkinCluster._validate_weight_locks(plug.elementByLogicalIndex(index))
        elif plug.isCompound:
            for index in range(plug.numChildren()):
                SkinCluster._validate_weight_locks(plug.child(index))

    def _normalized_weights(self, decimals=None, limit=None):
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
        if decimals is not None and (type(decimals) is not int or not 0 <= decimals <= 15):
            raise ValueError("decimals must be an integer between 0 and 15")
        names, weights = self._editable_weights()
        width, result = len(names), []
        with localcontext() as context:
            context.prec = 64
            for start in range(0, len(weights), width):
                row = [Decimal(str(v)) for v in weights[start:start + width]]
                if limit is not None:
                    keep = set(sorted(range(width), key=lambda i: (-row[i], i))[:limit])
                    row = [v if i in keep else Decimal(0) for i, v in enumerate(row)]
                total = sum(row)
                if not total:
                    raise ValueError(f"Cannot normalize zero-total weights at vertex {start // width}")
                row = [v / total for v in row]
                if decimals is not None:
                    scale = 10 ** decimals
                    scaled = [v * scale for v in row]
                    ticks = [int(v.to_integral_value(rounding=ROUND_FLOOR)) for v in scaled]
                    remaining = scale - sum(ticks)
                    order = sorted(range(width), key=lambda i: (-(scaled[i] - ticks[i]), i))
                    for i in order[:remaining]:
                        ticks[i] += 1
                    row = [Decimal(v) / scale for v in ticks]
                result.extend(float(v) for v in row)
        return names, result

    def _has_layer_plugs(self):
        """スキニングレイヤー関連ノードが接続されているか判定する。

        Returns:
            bool: 接続ノードの名前または型名にレイヤー判定用トークンが含まれる場合は True。実際のレイヤーデータの有無は調べない。
        """
        # ノード名・型だけが必要。genericアトリビュートを含む接続のPlug生成は避ける。
        fn = self._dependency_fn()
        connected = {om2.MObjectHandle(other.node()).hashCode(): other.node()
                     for plug in fn.getConnections() for other in plug.connectedTo(True, True)}
        for obj in connected.values():
            other_fn = om2.MFnDependencyNode(obj)
            node_name = other_fn.name().lower()
            node_type = other_fn.typeName.lower()
            if any(token in node_name or token in node_type for token in self._LAYER_TOKENS):
                return True
        return False

    def _raise_if_layers(self):
        """スキニングレイヤー検出時に安全のため処理を中断する。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: _has_layer_plugs() が True の場合。
        """
        if self._has_layer_plugs():
            raise RuntimeError("Cannot run while skinning layers exist")


class SkinClusters(Nodes):
    """重複を除き、保持順にSkinClusterを操作するコレクション。"""

    item_class = SkinCluster

    # 単数の呼出し先と返却方針を同じ行で宣言し、追加漏れを防ぐ。
    _bulk_entries = {
        "deforms": (SkinCluster.deforms, "list"),
        "getInfluences": (SkinCluster.getInfluences, "list"),
        "getBindPose": (SkinCluster.getBindPose, "list"),
        "getUnusedInfluences": (SkinCluster.getUnusedInfluences, "list"),
        "removeUnusedInfluences": (SkinCluster.removeUnusedInfluences, "list"),
        "hasInfluence": (SkinCluster.hasInfluence, "list"),
        "getWeights": (SkinCluster.getWeights, "list"),
        "dumpWeights": (SkinCluster.dumpWeights, "list"),
        "getMaxInfluences": (SkinCluster.getMaxInfluences, "list"),
        "redistributeWeights": (SkinCluster.redistributeWeights, "self"),
        "copyWeightsTo": (SkinCluster.copyWeightsTo, "self"),
        "addInfluences": (SkinCluster.addInfluences, "self"),
        "restoreBindPose": (SkinCluster.restoreBindPose, "self"),
        "resetBindPose": (SkinCluster.resetBindPose, "self"),
        "setWeights": (SkinCluster.setWeights, "self"),
        "loadWeights": (SkinCluster.loadWeights, "self"),
        "transferWeights": (SkinCluster.transferWeights, "self"),
        "removeInfluence": (SkinCluster.removeInfluence, "self"),
        "removeInvalidWeights": (SkinCluster.removeInvalidWeights, "self"),
        "normalizeWeights": (SkinCluster.normalizeWeights, "self"),
        "setMaxInfluences": (SkinCluster.setMaxInfluences, "self"),
    }
    _bulk_per_item_only = frozenset(("dumpWeights", "loadWeights"))
    dumpWeights = _PerItemOnly("dumpWeights")
    loadWeights = _PerItemOnly("loadWeights")

    def deforms(self, *args, **kwargs):
        """各要素のdeformsを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("deforms", args, kwargs)

    deforms.__signature__ = inspect.signature(SkinCluster.deforms)

    def getInfluences(self, *args, **kwargs):
        """各要素のgetInfluencesを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getInfluences", args, kwargs)

    getInfluences.__signature__ = inspect.signature(SkinCluster.getInfluences)

    def getBindPose(self, *args, **kwargs):
        """各要素のgetBindPoseを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getBindPose", args, kwargs)

    getBindPose.__signature__ = inspect.signature(SkinCluster.getBindPose)

    def getUnusedInfluences(self, *args, **kwargs):
        """各要素のgetUnusedInfluencesを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getUnusedInfluences", args, kwargs)

    getUnusedInfluences.__signature__ = inspect.signature(SkinCluster.getUnusedInfluences)

    def removeUnusedInfluences(self, *args, **kwargs):
        """各要素のremoveUnusedInfluencesを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("removeUnusedInfluences", args, kwargs)

    removeUnusedInfluences.__signature__ = inspect.signature(SkinCluster.removeUnusedInfluences)

    def hasInfluence(self, *args, **kwargs):
        """各要素のhasInfluenceを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("hasInfluence", args, kwargs)

    hasInfluence.__signature__ = inspect.signature(SkinCluster.hasInfluence)

    def getWeights(self, *args, **kwargs):
        """各要素のgetWeightsを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getWeights", args, kwargs)

    getWeights.__signature__ = inspect.signature(SkinCluster.getWeights)

    def setWeights(self, *args, **kwargs):
        """各要素のsetWeightsを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            SkinClusters | list: コレクション自身。
        """
        return self._dispatch_shared("setWeights", args, kwargs)

    setWeights.__signature__ = inspect.signature(SkinCluster.setWeights)

    def getMaxInfluences(self, *args, **kwargs):
        """各要素のgetMaxInfluencesを同じ引数で呼び、保持順の戻り値リストを返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            list: 保持順の戻り値リスト。
        """
        return self._dispatch_shared("getMaxInfluences", args, kwargs)

    getMaxInfluences.__signature__ = inspect.signature(SkinCluster.getMaxInfluences)

    def setMaxInfluences(self, *args, **kwargs):
        """各要素のsetMaxInfluencesを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            SkinClusters | list: コレクション自身。
        """
        return self._dispatch_shared("setMaxInfluences", args, kwargs)

    setMaxInfluences.__signature__ = inspect.signature(SkinCluster.setMaxInfluences)

    def redistributeWeights(self, *args, **kwargs):
        """各要素のredistributeWeightsを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            SkinClusters | list: コレクション自身。
        """
        return self._dispatch_shared("redistributeWeights", args, kwargs)

    redistributeWeights.__signature__ = inspect.signature(SkinCluster.redistributeWeights)

    def copyWeightsTo(self, *args, **kwargs):
        """各要素のcopyWeightsToを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            SkinClusters | list: コレクション自身。
        """
        return self._dispatch_shared("copyWeightsTo", args, kwargs)

    copyWeightsTo.__signature__ = inspect.signature(SkinCluster.copyWeightsTo)

    def addInfluences(self, *args, **kwargs):
        """各要素のaddInfluencesを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            SkinClusters | list: コレクション自身。
        """
        return self._dispatch_shared("addInfluences", args, kwargs)

    addInfluences.__signature__ = inspect.signature(SkinCluster.addInfluences)

    def removeInfluences(self, joints, transferToParent=True, *, force=_UNSET, fast=False, f=_UNSET):
        """保持するskinClusterだけから、指定jointのinfluence登録を外す。

        jointノードと親子関係は残す。未登録の組は省き、全登録の解除は変更前に拒否する。
        全組を事前確認し、skinClusterの保持順、各skin内は深いjoint順に処理する。
        通常処理はUndo有効時に一つのチャンクへ記録する。fastは各組を単数の
        :meth:`SkinCluster.removeInfluence` へ ``fast=True`` で渡し、Undoに記録しない。
        先行変更は自動で戻さない。

        Args:
            joints (Joint | str | Iterable[Joint | str]): 登録を解除するjoint。
            transferToParent (bool): Trueは最も近い祖先influenceへ加算し、なければ標準再配分。Falseも標準再配分。
            force (bool): 不正ウェイトを修復してから登録解除する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            SkinClusters: 自身。

        Raises:
            TypeError: transferToParent/force/fastがbool以外、またはforce/fを同時指定した場合。
            ValueError: 最後のinfluenceまで解除しようとした場合。
            RuntimeError: 無効joint、レイヤー・ロック、またはMayaの編集失敗。
            NotImplementedError: fastで、解除する組のskinClusterが単数
                :meth:`SkinCluster.removeInfluence` のfastの未対応条件に当たる場合。
                同じskinでの連続解除を順に試算する全組の事前確認で送出し、どのskinClusterも変更しない。
        """
        force = _pick_alias(force, f, "force", "f", default=False)
        with _edit_context("mlibSkinClustersRemoveInfluences", fast):
            from .joint import Joints

            _require_bool(transferToParent, "transferToParent")
            _require_bool(force, "force")
            targets = Joints([joints] if isinstance(joints, (Node, str)) else joints)
            if any(not joint.isValid() for joint in targets):
                raise RuntimeError("Expected valid joints")
            targets = targets.sortedByDepth()
            plans = []
            for skin in self:
                names = [joint.getFullName() for joint in targets if skin.hasInfluence(joint.getFullName())]
                if names and len(names) >= len(skin.getInfluences()):
                    raise ValueError(f"Cannot remove all influences of {skin.getFullName()}")
                steps = []
                for name in names:
                    steps.append(skin._influence_removal_target(name, transferToParent, force=force))
                    plans.append((skin, name))
                if fast and steps:
                    # 単数fastの未対応(geometryが1個でない、再配分を再現できない等)を、
                    # 同じskinでの連続解除を順に試算して、どのskinも変更する前に検出する。
                    from ..core.skinEdit import validate_removals
                    validate_removals(skin, steps, force=force)
            for skin, name in plans:
                skin.removeInfluence(name, transferToParent=transferToParent, force=force, fast=fast)
            return self

    def restoreBindPose(self, *args, **kwargs):
        """各要素のrestoreBindPoseを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            SkinClusters | list: コレクション自身。
        """
        return self._dispatch_shared("restoreBindPose", args, kwargs)

    restoreBindPose.__signature__ = inspect.signature(SkinCluster.restoreBindPose)

    def resetBindPose(self, *args, **kwargs):
        """各要素のresetBindPoseを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            SkinClusters | list: コレクション自身。
        """
        return self._dispatch_shared("resetBindPose", args, kwargs)

    resetBindPose.__signature__ = inspect.signature(SkinCluster.resetBindPose)

    def transferWeights(self, *args, **kwargs):
        """各要素のtransferWeightsを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            SkinClusters | list: コレクション自身。
        """
        return self._dispatch_shared("transferWeights", args, kwargs)

    transferWeights.__signature__ = inspect.signature(SkinCluster.transferWeights)

    def removeInfluence(self, *args, **kwargs):
        """各要素のremoveInfluenceを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            SkinClusters | list: コレクション自身。
        """
        return self._dispatch_shared("removeInfluence", args, kwargs)

    removeInfluence.__signature__ = inspect.signature(SkinCluster.removeInfluence)

    def removeInvalidWeights(self, *args, **kwargs):
        """各skinClusterの不正ウェイトを除去し、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。fastを指定できる。

        Returns:
            SkinClusters: 自身。
        """
        return self._dispatch_shared("removeInvalidWeights", args, kwargs)

    removeInvalidWeights.__signature__ = inspect.signature(SkinCluster.removeInvalidWeights)

    def normalizeWeights(self, *args, **kwargs):
        """各要素のnormalizeWeightsを同じ引数で呼び、コレクション自身を返す。

        Args:
            *args: 単数メソッドに渡す位置引数。
            **kwargs: 単数メソッドに渡すキーワード引数。

        Returns:
            SkinClusters | list: コレクション自身。
        """
        return self._dispatch_shared("normalizeWeights", args, kwargs)

    normalizeWeights.__signature__ = inspect.signature(SkinCluster.normalizeWeights)
