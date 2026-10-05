"""skinCluster のウェイト操作と joint 削除を支援する。"""

from .._core.flags import flag_aliases

import json
import math
from decimal import Decimal, localcontext, ROUND_FLOOR

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace

from .._core.collection import bulk_api
from .._core.fastWrite import set_attr
from .._core.fastWrite import writable, check_range
from .._core.registry import collection_export, node_wrapper
from .._core.space import world_space
from ..decorators._fast import fast_edit, is_fast
from ..decorators.selection import preservedSelection
from ..decorators.undo import undoChunk
from ..maths import easing
from .joint import Joint
from .node import Node, Nodes


@node_wrapper("skinCluster")
class SkinCluster(Node):
    """Maya の skinCluster と先頭 geometry を保持するラッパー。"""

    _LAYER_TOKENS = ("ngskin", "ngst", "ngskintools", "skinlayer", "skinninglayer", "layerdata")

    def __init__(self, skin_cluster):
        """skinCluster 名または Maya オブジェクトからラッパーを初期化する。

        先頭 geometry のみを保持する。頂点ウェイト操作ではその geometry が mesh であることを前提とする。

        Args:
            skin_cluster (str | om2.MObject | om2.MDagPath): skinCluster の名前または API オブジェクト。

        Returns:
            None: 値を返さない。

        Raises:
            IndexError: 対象 geometry がない場合。
            RuntimeError: geometry を解決できない場合。
        """
        super().__init__(skin_cluster)
        self.mesh = self._mesh()
        self.mesh_path = self._get_dag_path(self.mesh)
        self.fn = oma2.MFnSkinCluster(self.mnode())

    @classmethod
    @undoChunk("hlib.SkinCluster.bind")
    def bind(cls, mesh, influences, max_influences=4):
        """未スキニングの形状を指定influenceへバインドする。

        Args:
            mesh (str | Node): Mayaがバインド可能な形状またはtransform。
            influences (Sequence[str | Node]): バインドする骨等のtransform。
            max_influences (int): 1頂点に割り当てる最大数。正の整数。

        Returns:
            SkinCluster: 作成したskinCluster。
        """
        from ..nodes.node import Nodes as _InputNodes
        mesh = Node(mesh)
        influences = [Node(n) for n in _InputNodes._resolve_inputs(influences)]
        if not influences or type(max_influences) is not int or max_influences < 1:
            raise ValueError("Expected influences and a positive maximum influence count")
        if cmds.ls(cmds.listHistory(mesh.fullName()) or [], type="skinCluster"):
            raise ValueError("Geometry already has a skinCluster")
        return cls(cmds.skinCluster([n.fullName() for n in influences], mesh.fullName(),
                                   toSelectedBones=True, maximumInfluences=max_influences,
                                   normalizeWeights=1)[0])

    def deforms(self, geometry):
        """指定形状の履歴に自身が含まれるか照会する。

        Args:
            geometry (str | Node): 調べる形状またはtransform。

        Returns:
            bool: 履歴内に存在する場合True。
        """
        history = cmds.ls(cmds.listHistory(Node(geometry).fullName()) or [], type="skinCluster") or []
        return self.uuid() in [Node(n).uuid() for n in history]

    @undoChunk("hlib.SkinCluster.copyWeightsTo")
    def copyWeightsTo(self, target):
        """別skinClusterへ最近傍でウェイトを転送する。

        Args:
            target (str | SkinCluster): 別のバインド済み転送先。

        Note:
            closestPoint、name/closestJointによる近似転送で正規化する。
            異なる基準姿勢の補正やメッシュ削減は行わない。
        """
        target = SkinCluster(target)
        if target.uuid() == self.uuid():
            raise ValueError("Source and destination skinClusters must differ")
        cmds.copySkinWeights(sourceSkin=self.fullName(), destinationSkin=target.fullName(),
                             noMirror=True, surfaceAssociation="closestPoint",
                             influenceAssociation=["name", "closestJoint"], normalize=True)

    def influences(self):
        """influenceのDAGパスを保持するノードラッパーを取得する。

        Returns:
            list[Node]: Mayaのinfluence順のラッパー。Joint以外も型を維持する。
        """
        return [Node(path) for path in self.fn.influenceObjects()]

    @undoChunk("hlibSkinClusterAddInfluences")
    def addInfluences(self, joints):
        """ジョイントをウェイト0で登録する。既存influence・重複指定は無視する。

        Args:
            joints (Joint | str | Iterable[Joint | str]): 追加するジョイント。空は何もしない。
        Returns:
            SkinCluster: 自身。
        Raises:
            ValueError: Joint以外を指定した場合。全対象を編集前に検査する。
            RuntimeError: 対象が無効、またはMayaが追加を拒否した場合。

        既存ウェイトの再配分や正規化は行わず、既存のロック設定も変更しない。
        """
        from ..object import Object as _InputObject

        existing = {Node(path.node()).uuid() for path in self.fn.influenceObjects()}
        names = []
        for name in _InputObject._input_names(joints):
            node = Node(name)
            if not node.isType("joint"):
                raise ValueError(f"Expected a joint: {name}")
            if node.uuid() not in existing:
                existing.add(node.uuid())
                names.append(node.fullName())
        if names:
            cmds.skinCluster(self.fullName(), edit=True, addInfluence=names, weight=0.0)
        return self

    def bindPose(self):
        """bindPoseアトリビュートに接続された保存ポーズを取得する。

        Returns:
            DagPose | None: 接続されたポーズ。未接続ならNone。

        Raises:
            RuntimeError: skinClusterが無効、または接続先がdagPoseでない場合。
        """
        from .dagPose import DagPose

        return DagPose.fromSkinCluster(self)

    @flag_aliases(ws="worldSpace")
    @undoChunk("hlibSkinClusterRestoreBindPose")
    def restoreBindPose(self, worldSpace=True):
        """接続されたポーズの全メンバーを保存姿勢へ復元する。

        ポーズを共有する別のskinClusterや、influence以外のメンバーにも影響する。
        ロックや入力接続は解除しない。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。

        Returns:
            SkinCluster: 自身。

        Raises:
            RuntimeError: ポーズが未接続、ノードが無効、またはMayaが復元を拒否した場合。
        """
        ws = world_space(worldSpace)
        pose = self.bindPose()
        if pose is None:
            raise RuntimeError(f"No bind pose connected to {self.fullName()}")
        pose.restore(ws=ws)
        return self

    @undoChunk("hlibSkinClusterResetBindPose")
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
        pose = self.bindPose()
        if pose is None:
            raise RuntimeError(f"No bind pose connected to {self.fullName()}")
        pose.reset(self.influences())
        return self

    def unusedInfluences(self):
        """ウェイトを持たないinfluenceを検索する。シーンは変更しない。

        Returns:
            list[Node]: influence順のノードラッパー。微小値も使用中として扱い、
                閾値による切り捨てはしない。全geometryをMayaのweightedInfluenceで判定する。

        Raises:
            RuntimeError: skinClusterが無効、または照会に失敗した場合。
        """
        weighted = cmds.skinCluster(self.fullName(), query=True, weightedInfluence=True) or []
        used = {Node(name).uuid() for name in weighted}
        return [Node(path.node()) for path in self.fn.influenceObjects()
                if Node(path.node()).uuid() not in used]

    @undoChunk("hlibSkinClusterRemoveUnusedInfluences")
    def removeUnusedInfluences(self):
        """未使用influenceの登録を外す。jointノード自体は削除しない。

        Returns:
            list[Node]: 登録を外したノード。変更は一回のUndoで戻せる。

        Raises:
            ValueError: 全influenceが未使用で、削除すると登録が空になる場合。
            RuntimeError: Mayaが削除を拒否した場合。完了済み処理は自動では戻さない。
        """
        unused = self.unusedInfluences()
        if unused and len(unused) == len(self.influences()):
            raise ValueError("Cannot remove every influence from a skinCluster")
        for node in unused:
            self.removeInfluence(node.fullName(), transfer_to_parent=False)
        return unused

    def hasInfluence(self, joint):
        """指定したjointがinfluenceに含まれるか判定する。

        Args:
            joint (str): 判定するjoint名。

        Returns:
            bool: influenceに含まれる場合は ``True``。
        """
        uuid = self._uuid(joint)
        if not uuid:
            return False
        return any(
            self._uuid(path.fullPathName()) == uuid
            for path in self.fn.influenceObjects()
        )

    def getWeights(self, joints):
        """指定したjointの全頂点ウェイトを取得する。

        Args:
            joints (Iterable[str]): ウェイト取得対象の登録済み influence 名。

        Returns:
            om2.MDoubleArray: 頂点順、各頂点内は指定 influence 順に並んだ平坦なウェイト配列。
        """
        vertices, _ = self._all_verts()
        return self.fn.getWeights(self.mesh_path, vertices, self._jnt_indices(joints))

    @fast_edit
    @undoChunk("hlibSkinClusterSetWeights")
    def setWeights(self, joints, weights, *, fast=False):
        """指定したjointの全頂点ウェイトを設定する。

        cmds.setAttr で指定 influence のみを書き換える。正規化は行わず、
        influence のロック設定や未指定のウェイトは変更しない。一回の Undo で戻せる。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            joints (Iterable[str]): 設定する登録済み influence 名。
            weights (Iterable[float]): 頂点順、各頂点内は指定 influence 順の平坦な配列。
                頂点数×influence数、または全頂点に共通適用するinfluence数の値。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: influence が空・未登録・重複、値の数が不一致、または非有限値の場合。
            TypeError: ウェイトを数値に変換できない場合。
            RuntimeError: アトリビュートがロックされているなど、Maya が設定を拒否した場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        from ..object import Object as _InputObject
        joints = _InputObject._input_names(joints)
        influences = self.fn.influenceObjects()
        physical_indices = self._influence_indices(joints, influences)
        if not joints or None in physical_indices or len(set(physical_indices)) != len(joints):
            raise ValueError("Influences must be non-empty, registered and unique")
        values = [float(value) for value in weights]
        numVertices = om2.MFnMesh(self.mesh_path).numVertices
        width = len(joints)
        if len(values) not in (width, numVertices * width):
            raise ValueError("Weight count must match influence count or vertex count times influence count")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Weights must be finite")
        # 削除済み influence による配列の穴を考慮し、物理番号をアトリビュートの論理番号へ変換する。
        logical_indices = [self.fn.indexForInfluenceObject(influences[i]) for i in physical_indices]
        if is_fast():
            weights_plug = om2.MFnDependencyNode(self.mnode()).findPlug("weightList", False)
            edits = []
            for vertex in range(numVertices):
                row = weights_plug.elementByLogicalIndex(vertex).child(0)
                offset = 0 if len(values) == width else vertex * width
                for column, index in enumerate(logical_indices):
                    plug = row.elementByLogicalIndex(index)
                    writable(plug)
                    check_range(plug, values[offset + column])
                    edits.append((plug, values[offset + column]))
            # MFnSkinCluster.setWeightsはliw等の設定によって未指定値を再配分する。
            # 通常モードと同じ生値を維持するため、MPlugに直接書き込む。
            for plug, value in edits:
                plug.setDouble(value)
            return
        name = self.fullName()
        for vertex in range(numVertices):
            offset = 0 if len(values) == width else vertex * width
            for column, logical_index in enumerate(logical_indices):
                set_attr(
                    f"{name}.weightList[{vertex}].weights[{logical_index}]",
                    values[offset + column],
                )

    def dumpWeights(self, path):
        """全 influence の頂点ウェイトを JSON ファイルへ書き出す。

        シーン間でのバックアップ・復元・転送を想定した単純な JSON 形式で書き出す。
        influence の並びは influences() と一致する。

        Args:
            path (str): 書き出し先のファイルパス。

        Returns:
            None: 値を返さない。
        """
        influences = [node.name() for node in self.influences()]
        _, numVertices = self._all_verts()
        payload = {
            "influences": influences,
            "numVertices": numVertices,
            "weights": list(self.getWeights(influences)),
        }
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file)

    @fast_edit
    @undoChunk("hlibSkinClusterLoadWeights")
    def loadWeights(self, path, *, fast=False):
        """dumpWeights() が書き出した JSON ファイルからウェイトを読み込み設定する。

        ファイルに記録された influence がすべてこの skinCluster に存在し、
        頂点数が現在の mesh と一致することを要求する。一致しない場合は
        ウェイトを変更せず例外を送出する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            path (str): 読み込むファイルパス。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 頂点数が現在の mesh と一致しない、またはファイルに
                記録された influence の一部がこの skinCluster に存在しない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        _, numVertices = self._all_verts()
        if payload["numVertices"] != numVertices:
            raise ValueError(
                f"Stored vertex count ({payload['numVertices']}) does not match "
                f"the current mesh vertex count ({numVertices})"
            )
        influences = payload["influences"]
        current_influences = {node.name() for node in self.influences()}
        missing = [name for name in influences if name not in current_influences]
        if missing:
            raise ValueError(f"Influences missing from this skinCluster: {missing}")
        self.setWeights(influences, payload["weights"])

    @undoChunk("hlib.nodes.skinCluster.redistributeWeights")
    def redistributeWeights(self, vertices, method="cubic"):
        """頂点ごとのウェイト配分を、イージング曲線で強弱をつけて配り直す。

        対象頂点それぞれについて、influence 別のウェイトを合計1に揃えた
        割合として読み、各割合を ``hlib.maths.easing.ease`` の曲線に通す。
        その結果をもう一度合計1に揃えて書き戻す。割合の大小の差が強調される
        ため、境界がくっきりした配分に寄る。どの influence が効いているかは
        変わらず、ウェイト0の influence は0のまま。

        Args:
            vertices (Iterable[int]): 対象頂点インデックス。重複は1回として扱う。
            method (str): 曲線名。``hlib.maths.easing.CURVES`` のいずれか
                (例: ``"cubic"``、``"sine"``、``"exponential"``)。
                ``"linear"`` は配分を変えない。

        Returns:
            None: 値を返さない。一回の Undo で戻せる。

        Raises:
            TypeError: method が文字列でない場合。
            ValueError: method が未対応、または対象頂点のウェイト合計が0の場合。
            IndexError: 頂点インデックスが mesh の範囲外の場合。
        """
        if not isinstance(method, str):
            raise TypeError(f"Easing method must be a str, got {type(method).__name__}")
        curve = method
        if curve not in easing.CURVES:
            raise ValueError(f"Unsupported easing method: {method}")
        numVertices = om2.MFnMesh(self.mesh_path).numVertices
        vertex_indices = sorted({int(index) for index in vertices})
        for vertex in vertex_indices:
            if not (0 <= vertex < numVertices):
                raise IndexError(f"Vertex index out of range: {vertex}")
        if not vertex_indices:
            return
        influence_paths = self.fn.influenceObjects()
        all_indices = om2.MIntArray(range(len(influence_paths)))
        logical_indices = [self.fn.indexForInfluenceObject(path) for path in influence_paths]
        name = self.fullName()
        for vertex in vertex_indices:
            component_fn = om2.MFnSingleIndexedComponent()
            component = component_fn.create(om2.MFn.kMeshVertComponent)
            component_fn.addElement(vertex)
            row = list(self.fn.getWeights(self.mesh_path, component, all_indices))
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
                set_attr(f"{name}.weightList[{vertex}].weights[{logical_index}]", value)

    @undoChunk("hlib.nodes.skinCluster.transferWeights")
    def transferWeights(self, source_target_pairs):
        """複数のsource/target組についてウェイトを移す。

        処理が途中で失敗しても選択状態は preservedSelection により復元される。完了済みの
        ウェイト変更はロールバックしない。正規化はMayaのskinPercentと
        skinClusterのnormalizeWeights設定に従う。

        Args:
            source_target_pairs (Iterable[tuple[Node | str, Node | str]]): influenceの組。
                Maya APIのノード参照も受け付ける。全組を検証後、指定順に移送する。
                同じinfluence同士の組は何もしない。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: ペアの要素数が2でない、または未登録のinfluenceの場合。
            TypeError: ペアが反復可能でない、または未対応の参照型の場合。
            RuntimeError: 接続ノード名・型名からスキニングレイヤーを検出した場合、または Maya 操作に失敗した場合。
        """
        from ..nodes.node import Node as _InputNode
        self._raise_if_layers()

        pairs = []
        for pair in source_target_pairs:
            if isinstance(pair, (str, bytes)):
                raise ValueError("Expected a source/target pair, not a string")
            pair = tuple(pair)
            if len(pair) != 2:
                raise ValueError("Expected exactly two influences per pair")
            source, target = (_InputNode._resolve_input(value) for value in pair)
            if any(not node.isValid() or not self.hasInfluence(node.fullName()) for node in (source, target)):
                raise ValueError("Both nodes must be influences of this skinCluster")
            if source.uuid() != target.uuid():
                pairs.append((source.fullName(), target.fullName()))
        with preservedSelection():
            for source_joint, target_joint in pairs:
                self._xfer_pair(source_joint, target_joint)

    @undoChunk("hlib.nodes.skinCluster.removeInfluence")
    def removeInfluence(self, joint, transfer_to_parent=True):
        """祖先influenceへ加算後、登録を外す。jointノードは削除しない。

        同じskinClusterの最も近い祖先influenceを移送先にする。
        移送先がなければMaya標準のremoveInfluenceに再配分を任せる。
        最後の一つのinfluenceは削除しない。全体は一回のUndoで戻せる。

        Args:
            joint (Joint | str): 削除対象の influence。
            transfer_to_parent (bool): 祖先への移送を行うか。Falseは標準削除のみ。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: transfer_to_parentがboolでない場合。
            ValueError: 未登録、または最後の一つのinfluenceの場合。
            RuntimeError: スキニングレイヤーを検出、または Maya が削除を拒否した場合。
        """
        source, target = self._influence_removal_target(joint, transfer_to_parent)
        if target is not None:
            # skinPercentの移送は正規化設定に依存するため、保存値を明示的に加算する。
            weights = list(self.getWeights([source.fullName(), target]))
            summed = []
            for i in range(0, len(weights), 2):
                summed.extend((0.0, weights[i] + weights[i + 1]))
            self.setWeights([source.fullName(), target], summed)
        cmds.skinCluster(self.name(), edit=True, removeInfluence=source.fullName())

    @fast_edit
    @undoChunk("hlibSkinClusterNormalizeWeights")
    def normalizeWeights(self, decimals=None, *, fast=False):
        """先頭meshの各頂点ウェイトを合計1へ正規化する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            decimals (int | None): 0〜15の小数桁数。Noneは桁丸めなし。
                桁指定時は端数を配分し、十進数として合計1を維持する。
                同率の場合はinfluenceの登録順を優先する。
        Returns:
            SkinCluster: 自身。
        Raises:
            ValueError: 不正な桁数、負値・非有限値・合計ゼロの頂点の場合。
            RuntimeError: ロック・接続・レイヤー、またはMayaの編集失敗。

        全頂点を事前検証する。normalizeWeights設定・influence数は変更しない。
        保存値は浮動小数点のため合計に機械精度の誤差は生じ得る。Undo対応。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        names, values = self._normalized_weights(decimals)
        self.setWeights(names, values)
        return self

    def getMaxInfluences(self):
        """int: skinClusterのmaxInfluences設定値。実際の非ゼロ数ではない。"""
        return self.plug("maxInfluences").get()

    @fast_edit
    @undoChunk("hlibSkinClusterSetMaxInfluences")
    def setMaxInfluences(self, count, maintain=True, prune=False, *, fast=False):
        """最大influence設定を変更し、任意で既存ウェイトも制限する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            count (int): 1以上の最大数。
            maintain (bool): maintainMaxInfluencesを有効にするか。
            prune (bool): Trueで先頭meshの各頂点の大きいcount個だけを残し正規化。
                Falseは設定だけ変更し、既存ウェイトを変更しない。
        Returns:
            SkinCluster: 自身。
        Raises:
            ValueError: 不正なcount、またはprune時に正規化できないウェイト。
            TypeError: maintain/pruneがboolでない場合。
            RuntimeError: ロック・レイヤー・Mayaの編集失敗。

        skinCluster編集コマンドの再バインドを避け、アトリビュートを直接設定する。Undo対応。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if type(count) is not int or not 1 <= count <= 2147483647:
            raise ValueError("count must be a positive 32-bit integer")
        if type(maintain) is not bool or type(prune) is not bool:
            raise TypeError("maintain and prune must be bool")
        settings = [self.plug(attr) for attr in ("maxInfluences", "maintainMaxInfluences")]
        for plug in settings:
            if plug.mplug().isFreeToChange() != om2.MPlug.kFreeToChange:
                attr = plug.longName()
                raise RuntimeError("Setting is locked or connected: " + attr)
        computed = self._normalized_weights(limit=count) if prune else None
        settings[0].set(count)
        settings[1].set(maintain)
        if computed:
            self.setWeights(*computed)
        return self

    def _uuid(self, node):
        """ノード名から Maya UUID を取得する。

        Args:
            node (str): UUID を問い合わせるノード名。

        Returns:
            str | None: 対応する UUID。ノードが存在しない場合は None。
        """
        try:
            return Node(node).uuid()
        except RuntimeError:
            return None

    def _get_dag_path(self, name):
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

    def _mesh(self):
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

    def _jnt_index(self, joint):
        """influence 配列内の joint インデックスを UUID 優先で取得する。

        Args:
            joint (str): 検索する influence 名。

        Returns:
            int | None: influenceObjects() 内の物理インデックス。UUID、次いでパーシャル名を比較する。見つからなければ None。
        """
        return self._influence_indices((joint,), self.fn.influenceObjects())[0]

    def _all_verts(self):
        """mesh の全頂点 component と頂点数を生成する。

        Returns:
            tuple[om2.MObject, int]: 全頂点を含む component と頂点数。
        """
        numVertices = om2.MFnMesh(self.mesh_path).numVertices
        component_fn = om2.MFnSingleIndexedComponent()
        vertices = component_fn.create(om2.MFn.kMeshVertComponent)
        component_fn.addElements(range(numVertices))
        return vertices, numVertices

    def _jnt_indices(self, joints):
        """joint 群を skinCluster influence インデックス配列へ変換する。

        未登録名を除外しない。解決結果が None のまま配列変換されると失敗する。

        Args:
            joints (Iterable[str]): すべて対象 skinCluster に存在する influence 名。

        Returns:
            om2.MIntArray: 指定順の物理インデックス配列。
        """
        from ..object import Object as _InputObject
        return om2.MIntArray(self._influence_indices(_InputObject._input_names(joints), self.fn.influenceObjects()))

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
            uuid = self._uuid(joint)
            for index, path in enumerate(influences):
                if ((uuid and self._uuid(path.fullPathName()) == uuid)
                        or path.partialPathName() == joint):
                    return [index]
            return [None]
        by_uuid, by_name = {}, {}
        for index, path in enumerate(influences):
            uuid = self._uuid(path.fullPathName())
            if uuid:
                by_uuid.setdefault(uuid, index)
            by_name.setdefault(path.partialPathName(), index)
        result = []
        for joint in joints:
            candidates = (by_uuid.get(self._uuid(joint)), by_name.get(joint))
            result.append(min((i for i in candidates if i is not None), default=None))
        return result

    def _xfer_pair(self, source_joint, target_joint):
        """選択された source influence 頂点のウェイトを target へ移す。

        元 influence に影響される頂点を選択し、skinPercent の transformMoveWeights を実行する。選択状態の復元は呼び出し側が行う。

        Args:
            source_joint (str): 移送元の influence 名。
            target_joint (str): 移送先の influence 名。

        Returns:
            None: 値を返さない。
        """
        cmds.skinCluster(self.name(), edit=True, selectInfluenceVerts=source_joint)
        if om2.MGlobal.getActiveSelectionList().length():
            cmds.skinPercent(self.name(), transformMoveWeights=[source_joint, target_joint])

    def _influence_removal_target(self, joint, transfer_to_parent=True):
        """削除可否と祖先移送先を変更前に確認する。"""
        if not isinstance(transfer_to_parent, bool):
            raise TypeError("transfer_to_parent must be a bool")
        self._raise_if_layers()
        source = joint if isinstance(joint, Node) else Node(joint)
        if not source.isValid() or not self.hasInfluence(source.fullName()):
            raise ValueError("Joint is not an influence of this skinCluster")
        if len(self.influences()) <= 1:
            raise ValueError("Cannot remove the last influence")
        target = source.transferTarget(self) if transfer_to_parent and isinstance(source, Joint) else None
        if target is not None:
            self._editable_weights()
        return source, target

    def _editable_weights(self):
        """先頭meshの全influence値を取得し、ロック・接続・レイヤーを拒否する。"""
        self._raise_if_layers()
        influences = self.influences()
        names = [node.name() for node in influences]
        if not names:
            raise ValueError("No influences")
        for node in influences:
            if node.hasAttr("lockInfluenceWeights") and node.plug("lockInfluenceWeights").get():
                raise RuntimeError("Influence is locked: " + node.name())
        path = self.fullName() + ".weightList"
        weight_list = self.plug("weightList").mplug()
        if weight_list.isLocked or cmds.listConnections(path, source=True, destination=False):
            raise RuntimeError("Weights are locked or connected")
        self._validate_weight_locks(weight_list)
        weights = list(self.getWeights(names))
        if any(not math.isfinite(v) or v < 0 for v in weights):
            raise ValueError("Weights must be finite and non-negative")
        return names, weights

    @staticmethod
    def _validate_weight_locks(plug):
        """既存の疎なウェイト要素だけを辿りロックを検証する。

        Args:
            plug (om2.MPlug): weightListとその子。未存在要素は作成しない。

        Raises:
            RuntimeError: 要素または親のアトリビュートがロックされている場合。
        """
        if plug.isLocked:
            raise RuntimeError("Weight element is locked: " + plug.name())
        if plug.isArray:
            for index in plug.getExistingArrayAttributeIndices():
                SkinCluster._validate_weight_locks(plug.elementByLogicalIndex(index))
        elif plug.isCompound:
            for index in range(plug.numChildren()):
                SkinCluster._validate_weight_locks(plug.child(index))

    def _normalized_weights(self, decimals=None, limit=None):
        """正規化結果をメモリ上で計算する。丸めは最大剰余法で合計を維持する。"""
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
                    raise ValueError("Cannot normalize zero-total weights at vertex {}".format(start // width))
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
        for name in cmds.listConnections(self.fullName(), source=True, destination=True) or []:
            nodeName = name.lower()
            node_type = Node(name).type().lower()
            if any(token in nodeName or token in node_type for token in self._LAYER_TOKENS):
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
            raise RuntimeError("skinning layersが存在するため実行できません。")


@collection_export()
@bulk_api(
    SkinCluster,
    per_item_only=(
        'dumpWeights',
        'loadWeights',
    ),
    reads=(
        'deforms',
        'influences',
        'bindPose',
        'unusedInfluences',
        'removeUnusedInfluences',
        'hasInfluence',
        'getWeights',
        'dumpWeights',
        'getMaxInfluences',
    ),
    writes=(
        'redistributeWeights',
        'copyWeightsTo',
        'addInfluences',
        'restoreBindPose',
        'resetBindPose',
        'setWeights',
        'loadWeights',
        'transferWeights',
        'removeInfluence',
        'normalizeWeights',
        'setMaxInfluences',
    ),
)
class SkinClusters(Nodes):
    """重複を除き、保持順にSkinClusterを操作するコレクション。"""

    item_class = SkinCluster

    @undoChunk("hlibSkinClustersRemoveInfluences")
    def removeInfluences(self, joints, transfer_to_parent=True):
        """保持するskinClusterのinfluence登録だけを解除する。

        jointノードや親子関係は変更しない。祖先influenceがあればウェイトを
        加算し、なければMaya標準のremoveInfluenceに再配分を任せる。
        未登録の組は無視する。全登録の解除は変更前に拒否する。
        深いjointから順に処理し、全体を一回のUndoにまとめる。
        実行途中のMayaエラーは伝播し、完了済み変更は自動では戻さない。

        Args:
            joints (Joint | str | Iterable[Joint | str]): 登録を解除するjoint。
            transfer_to_parent (bool): Trueは祖先へ移送。FalseはMaya標準の解除のみ。
        Returns:
            SkinClusters: 自身。
        Raises:
            TypeError: transfer_to_parentがboolでない場合。
            ValueError: 最後のinfluenceまで解除しようとした場合。
            RuntimeError: 無効なjoint、編集不可、またはMayaの処理失敗。
        """
        from .joint import Joints

        if not isinstance(transfer_to_parent, bool):
            raise TypeError("transfer_to_parent must be a bool")
        targets = Joints([joints] if isinstance(joints, (Node, str)) else joints)
        if any(not joint.isJoint() for joint in targets):
            raise RuntimeError("Expected valid joints")
        targets = targets.sortedByDepth()
        plans = []
        for skin in self:
            names = [joint.fullName() for joint in targets if skin.hasInfluence(joint.fullName())]
            if names and len(names) >= len(skin.influences()):
                raise ValueError("Cannot remove all influences of " + skin.fullName())
            for name in names:
                skin._influence_removal_target(name, transfer_to_parent)
                plans.append((skin, name))
        for skin, name in plans:
            skin.removeInfluence(name, transfer_to_parent=transfer_to_parent)
        return self
