"""skinCluster のウェイト操作と joint 削除を支援する。"""

from ..decorators._fast import fast_edit, is_fast
from .._core.fast_write import set_attr
from .._core.fast_write import writable, check_range

from ..decorators.undo import undo_chunk

import json
import math
from decimal import Decimal, localcontext, ROUND_FLOOR

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2

from .._core.registry import collection_export, node_wrapper
from .._core.collection import BulkCollection, bulk_api
from ..decorators.selection import preserved_selection
from ..maths import easing
from .joint import Joint
from .node import Node


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
        self.fn = oma2.MFnSkinCluster(self.mobject())

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
        selection = om2.MSelectionList()
        selection.add(name)
        path = selection.getDagPath(0)
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
        geometries = oma2.MFnGeometryFilter(self.mobject()).getOutputGeometry()
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
        uuid = self._uuid(joint)
        for index, path in enumerate(self.fn.influenceObjects()):
            if uuid and self._uuid(path.fullPathName()) == uuid:
                return index
            if path.partialPathName() == joint:
                return index
        return None

    def _all_verts(self):
        """mesh の全頂点 component と頂点数を生成する。

        Returns:
            tuple[om2.MObject, int]: 全頂点を含む component と頂点数。
        """
        vertex_count = om2.MFnMesh(self.mesh_path).numVertices
        component_fn = om2.MFnSingleIndexedComponent()
        vertices = component_fn.create(om2.MFn.kMeshVertComponent)
        component_fn.addElements(range(vertex_count))
        return vertices, vertex_count

    def _jnt_indices(self, joints):
        """joint 群を skinCluster influence インデックス配列へ変換する。

        未登録名を除外しない。解決結果が None のまま配列変換されると失敗する。

        Args:
            joints (Iterable[str]): すべて対象 skinCluster に存在する influence 名。

        Returns:
            om2.MIntArray: 指定順の物理インデックス配列。
        """
        return om2.MIntArray([self._jnt_index(joint) for joint in joints])

    def influences(self):
        """influence joint名のリストを取得する。

        Returns:
            list[str]: influence joint名のリスト。
        """
        return [path.partialPathName() for path in self.fn.influenceObjects()]

    @undo_chunk("hlibSkinClusterAddInfluences")
    def add_influences(self, joints):
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
        from .._core.coerce import to_names

        existing = {Node(path.node()).uuid() for path in self.fn.influenceObjects()}
        names = []
        for name in to_names(joints):
            node = Node(name)
            if not node.is_type("joint"):
                raise ValueError(f"Expected a joint: {name}")
            if node.uuid() not in existing:
                existing.add(node.uuid())
                names.append(node.full_name())
        if names:
            cmds.skinCluster(self.full_name(), edit=True, addInfluence=names, weight=0.0)
        return self

    def bind_pose(self):
        """bindPose属性に接続された保存ポーズを取得する。

        Returns:
            DagPose | None: 接続されたポーズ。未接続ならNone。

        Raises:
            RuntimeError: skinClusterが無効、または接続先がdagPoseでない場合。
        """
        from .dagPose import DagPose

        return DagPose.from_skin_cluster(self)

    @undo_chunk("hlibSkinClusterRestoreBindPose")
    def restore_bind_pose(self, ws=True):
        """接続されたポーズの全メンバーを保存姿勢へ復元する。

        ポーズを共有する別のskinClusterや、influence以外のメンバーにも影響する。
        ロックや入力接続は解除しない。

        Args:
            ws (bool): Trueならワールド姿勢、Falseならローカル姿勢を復元する。

        Returns:
            SkinCluster: 自身。

        Raises:
            RuntimeError: ポーズが未接続、ノードが無効、またはMayaが復元を拒否した場合。
        """
        pose = self.bind_pose()
        if pose is None:
            raise RuntimeError(f"No bind pose connected to {self.full_name()}")
        pose.restore(ws=ws)
        return self

    @undo_chunk("hlibSkinClusterResetBindPose")
    def reset_bind_pose(self):
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
        pose = self.bind_pose()
        if pose is None:
            raise RuntimeError(f"No bind pose connected to {self.full_name()}")
        pose.reset(self.influences())
        return self

    def unused_influences(self):
        """ウェイトを持たないinfluenceを検索する。シーンは変更しない。

        Returns:
            list[Node]: influence順のノードラッパー。微小値も使用中として扱い、
                閾値による切り捨てはしない。全geometryをMayaのweightedInfluenceで判定する。

        Raises:
            RuntimeError: skinClusterが無効、または照会に失敗した場合。
        """
        weighted = cmds.skinCluster(self.full_name(), query=True, weightedInfluence=True) or []
        used = {Node(name).uuid() for name in weighted}
        return [Node(path.node()) for path in self.fn.influenceObjects()
                if Node(path.node()).uuid() not in used]

    @undo_chunk("hlibSkinClusterRemoveUnusedInfluences")
    def remove_unused_influences(self):
        """未使用influenceの登録を外す。jointノード自体は削除しない。

        Returns:
            list[Node]: 登録を外したノード。変更は一回のUndoで戻せる。

        Raises:
            ValueError: 全influenceが未使用で、削除すると登録が空になる場合。
            RuntimeError: Mayaが削除を拒否した場合。完了済み処理は自動では戻さない。
        """
        unused = self.unused_influences()
        if unused and len(unused) == len(self.influences()):
            raise ValueError("Cannot remove every influence from a skinCluster")
        for node in unused:
            self.remove_influence(node.full_name(), transfer_to_parent=False)
        return unused

    def has_influence(self, joint):
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

    def get_weights(self, joints):
        """指定したjointの全頂点ウェイトを取得する。

        Args:
            joints (Iterable[str]): ウェイト取得対象の登録済み influence 名。

        Returns:
            om2.MDoubleArray: 頂点順、各頂点内は指定 influence 順に並んだ平坦なウェイト配列。
        """
        vertices, _ = self._all_verts()
        return self.fn.getWeights(self.mesh_path, vertices, self._jnt_indices(joints))

    @fast_edit
    @undo_chunk("hlibSkinClusterSetWeights")
    def set_weights(self, joints, weights, *, fast=False):
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
            RuntimeError: 属性がロックされているなど、Maya が設定を拒否した場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        joints = list(joints)
        physical_indices = [self._jnt_index(joint) for joint in joints]
        if not joints or None in physical_indices or len(set(physical_indices)) != len(joints):
            raise ValueError("Influences must be non-empty, registered and unique")
        values = [float(value) for value in weights]
        vertex_count = om2.MFnMesh(self.mesh_path).numVertices
        width = len(joints)
        if len(values) not in (width, vertex_count * width):
            raise ValueError("Weight count must match influence count or vertex count times influence count")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Weights must be finite")
        influences = self.fn.influenceObjects()
        # 削除済み influence による配列の穴を考慮し、物理番号を属性の論理番号へ変換する。
        logical_indices = [self.fn.indexForInfluenceObject(influences[i]) for i in physical_indices]
        if is_fast():
            weights_plug = om2.MFnDependencyNode(self.mobject()).findPlug("weightList", False)
            edits = []
            for vertex in range(vertex_count):
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
        name = self.full_name()
        for vertex in range(vertex_count):
            offset = 0 if len(values) == width else vertex * width
            for column, logical_index in enumerate(logical_indices):
                set_attr(
                    f"{name}.weightList[{vertex}].weights[{logical_index}]",
                    values[offset + column],
                )

    def dump_weights(self, path):
        """全 influence の頂点ウェイトを JSON ファイルへ書き出す。

        シーン間でのバックアップ・復元・転送を想定した単純な JSON 形式で書き出す。
        influence の並びは influences() と一致する。

        Args:
            path (str): 書き出し先のファイルパス。

        Returns:
            None: 値を返さない。
        """
        influences = self.influences()
        _, vertex_count = self._all_verts()
        payload = {
            "influences": influences,
            "vertex_count": vertex_count,
            "weights": list(self.get_weights(influences)),
        }
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file)

    @fast_edit
    @undo_chunk("hlibSkinClusterLoadWeights")
    def load_weights(self, path, *, fast=False):
        """dump_weights() が書き出した JSON ファイルからウェイトを読み込み設定する。

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
        _, vertex_count = self._all_verts()
        if payload["vertex_count"] != vertex_count:
            raise ValueError(
                f"Stored vertex count ({payload['vertex_count']}) does not match "
                f"the current mesh vertex count ({vertex_count})"
            )
        influences = payload["influences"]
        current_influences = set(self.influences())
        missing = [name for name in influences if name not in current_influences]
        if missing:
            raise ValueError(f"Influences missing from this skinCluster: {missing}")
        self.set_weights(influences, payload["weights"])

    @undo_chunk("hlib.nodes.skinCluster.redistribute_weights")
    def redistribute_weights(self, vertices, method="cubic"):
        """頂点ごとのウェイト配分を、イージング曲線で強弱をつけて配り直す。

        対象頂点それぞれについて、influence 別のウェイトを合計1に揃えた
        割合として読み、各割合を ``hlib.maths.easing.ease`` の曲線に通す。
        その結果をもう一度合計1に揃えて書き戻す。割合の大小の差が強調される
        ため、境界がくっきりした配分に寄る。どの influence が効いているかは
        変わらず、ウェイト0の influence は0のまま。

        Args:
            vertices (Iterable[int]): 対象頂点インデックス。重複は1回として扱う。
            method (str): 曲線名。``hlib.maths.easing.CURVES`` のいずれか
                (例: ``"cubic"``、``"sine"``、``"exponential"``)。互換のため
                旧名 ``"sinusoidal"`` も ``"sine"`` として受け付ける。
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
        curve = {"sinusoidal": "sine"}.get(method, method)
        if curve not in easing.CURVES:
            raise ValueError(f"Unsupported easing method: {method}")
        vertex_count = om2.MFnMesh(self.mesh_path).numVertices
        vertex_indices = sorted({int(index) for index in vertices})
        for vertex in vertex_indices:
            if not (0 <= vertex < vertex_count):
                raise IndexError(f"Vertex index out of range: {vertex}")
        if not vertex_indices:
            return
        influence_paths = self.fn.influenceObjects()
        all_indices = om2.MIntArray(range(len(influence_paths)))
        logical_indices = [self.fn.indexForInfluenceObject(path) for path in influence_paths]
        name = self.full_name()
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

    @undo_chunk("hlib.nodes.skinCluster.transfer_weight")
    def transfer_weight(self, source_joint, target_joint):
        """単一のsource influenceからtarget influenceへウェイトを移す。

        元 influence に影響される頂点を選択し、skinPercent の transformMoveWeights を実行する。処理後に元の選択状態を復元する。

        Args:
            source_joint (str): 移送元の influence 名。
            target_joint (str): 移送先の influence 名。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: スキニングレイヤーを検出、または Maya の操作に失敗した場合。
        """
        self.transfer_weights_batch([(source_joint, target_joint)])

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

    @undo_chunk("hlib.nodes.skinCluster.transfer_weights_batch")
    def transfer_weights_batch(self, source_target_pairs):
        """複数のsource/target組についてウェイトを移す。

        処理が途中で失敗しても選択状態は preserved_selection により復元される。完了済みの
        ウェイト変更はロールバックしない。

        Args:
            source_target_pairs (Iterable[tuple[str, str]]): (移送元, 移送先) の influence 名の組。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 接続ノード名・型名からスキニングレイヤーを検出した場合、または Maya 操作に失敗した場合。
        """
        self._raise_if_layers()
        with preserved_selection():
            for source_joint, target_joint in source_target_pairs:
                self._xfer_pair(source_joint, target_joint)

    @undo_chunk("hlib.nodes.skinCluster.remove_influence")
    def remove_influence(self, joint, transfer_to_parent=True):
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
            ValueError: 未登録、または最後の一つのinfluenceの場合。
            RuntimeError: スキニングレイヤーを検出、または Maya が削除を拒否した場合。
        """
        source, target = self._influence_removal_target(joint, transfer_to_parent)
        if target is not None:
            # skinPercentの移送は正規化設定に依存するため、保存値を明示的に加算する。
            weights = list(self.get_weights([source.full_name(), target]))
            summed = []
            for i in range(0, len(weights), 2):
                summed.extend((0.0, weights[i] + weights[i + 1]))
            self.set_weights([source.full_name(), target], summed)
        cmds.skinCluster(self.name(), edit=True, removeInfluence=source.full_name())

    def _influence_removal_target(self, joint, transfer_to_parent=True):
        """削除可否と祖先移送先を変更前に確認する。"""
        self._raise_if_layers()
        source = joint if isinstance(joint, Node) else Node(joint)
        if not source.is_valid() or not self.has_influence(source.full_name()):
            raise ValueError("Joint is not an influence of this skinCluster")
        if len(self.influences()) <= 1:
            raise ValueError("Cannot remove the last influence")
        target = source.transfer_target(self) if transfer_to_parent and isinstance(source, Joint) else None
        if target is not None:
            self._editable_weights()
        return source, target

    def _editable_weights(self):
        """先頭meshの全influence値を取得し、ロック・接続・レイヤーを拒否する。"""
        self._raise_if_layers()
        names = self.influences()
        if not names:
            raise ValueError("No influences")
        for name in names:
            if cmds.objExists(name + ".lockInfluenceWeights") and cmds.getAttr(name + ".lockInfluenceWeights"):
                raise RuntimeError("Influence is locked: " + name)
        path = self.full_name() + ".weightList"
        if cmds.getAttr(path, lock=True) or cmds.listConnections(path, source=True, destination=False):
            raise RuntimeError("Weights are locked or connected")
        for attr in cmds.listAttr(path, multi=True) or []:
            if cmds.getAttr(self.full_name() + "." + attr, lock=True):
                raise RuntimeError("Weight element is locked: " + attr)
        weights = list(self.get_weights(names))
        if any(not math.isfinite(v) or v < 0 for v in weights):
            raise ValueError("Weights must be finite and non-negative")
        return names, weights

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

    @fast_edit
    @undo_chunk("hlibSkinClusterNormalizeWeights")
    def normalize_weights(self, decimals=None, *, fast=False):
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
        self.set_weights(names, values)
        return self

    def max_influences(self):
        """int: skinClusterのmaxInfluences設定値。実際の非ゼロ数ではない。"""
        return cmds.getAttr(self.full_name() + ".maxInfluences")

    @fast_edit
    @undo_chunk("hlibSkinClusterSetMaxInfluences")
    def set_max_influences(self, count, maintain=True, prune=False, *, fast=False):
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

        skinCluster編集コマンドの再バインドを避け、属性を直接設定する。Undo対応。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if type(count) is not int or not 1 <= count <= 2147483647:
            raise ValueError("count must be a positive 32-bit integer")
        if type(maintain) is not bool or type(prune) is not bool:
            raise TypeError("maintain and prune must be bool")
        for attr in ("maxInfluences", "maintainMaxInfluences"):
            if not cmds.getAttr(self.full_name() + "." + attr, settable=True):
                raise RuntimeError("Setting is locked or connected: " + attr)
        computed = self._normalized_weights(limit=count) if prune else None
        set_attr(self.full_name() + ".maxInfluences", count)
        set_attr(self.full_name() + ".maintainMaxInfluences", maintain)
        if computed:
            self.set_weights(*computed)
        return self

    def _has_layer_plugs(self):
        """スキニングレイヤー関連ノードが接続されているか判定する。

        Returns:
            bool: 接続ノードの名前または型名にレイヤー判定用トークンが含まれる場合は True。実際のレイヤーデータの有無は調べない。
        """
        # ノード名・型だけが必要。generic属性を含む接続のPlug生成は避ける。
        for name in cmds.listConnections(self.full_name(), source=True, destination=True) or []:
            node_name = name.lower()
            node_type = cmds.nodeType(name).lower()
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
            raise RuntimeError("skinning layersが存在するため実行できません。")


@collection_export()
@bulk_api(SkinCluster, per_item_only=("dump_weights", "load_weights"))
class SkinClusters(BulkCollection):
    """重複を除き、保持順にSkinClusterを操作するコレクション。"""

    def __init__(self, names=()):
        """Iterable[str | SkinCluster]からコレクションを構築する。"""
        self._items = []
        seen = set()
        for item in names:
            skin = item if isinstance(item, SkinCluster) else SkinCluster(item)
            if skin.name() not in seen:
                seen.add(skin.name())
                self._items.append(skin)

    def __iter__(self):
        """Iterator[SkinCluster]: 保持順のスキンクラスター。"""
        return iter(self._items)

    @undo_chunk("hlibSkinClustersRemoveInfluences")
    def remove_influences(self, joints, transfer_to_parent=True):
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
            None: 値を返さない。
        Raises:
            TypeError: transfer_to_parentがboolでない場合。
            ValueError: 最後のinfluenceまで解除しようとした場合。
            RuntimeError: 無効なjoint、編集不可、またはMayaの処理失敗。
        """
        from .joint import Joints

        if not isinstance(transfer_to_parent, bool):
            raise TypeError("transfer_to_parent must be a bool")
        targets = Joints([joints] if isinstance(joints, (Node, str)) else joints)
        if any(not joint.is_joint() for joint in targets):
            raise RuntimeError("Expected valid joints")
        targets = targets.sorted_by_depth()
        plans = []
        for skin in self:
            names = [joint.full_name() for joint in targets if skin.has_influence(joint.full_name())]
            if names and len(names) >= len(skin.influences()):
                raise ValueError("Cannot remove all influences of " + skin.full_name())
            for name in names:
                skin._influence_removal_target(name, transfer_to_parent)
                plans.append((skin, name))
        for skin, name in plans:
            skin.remove_influence(name, transfer_to_parent=transfer_to_parent)

    def remove_joints(self, joints, transfer_to_parent=True):
        """指定jointをinfluenceから外す。jointノード自体は削除しない。

        remove_influencesのjoint指定用入口。以前の同名APIと異なり、
        ノードを削除するにはJoint.delete()/Joints.delete()を使う。

        Args:
            joints (Joint | str | Iterable[Joint | str]): 登録を解除するjoint。
            transfer_to_parent (bool): Trueは祖先へ移送。FalseはMaya標準の解除のみ。
        Returns:
            None: 値を返さない。検証・例外・Undoはremove_influencesと同じ。
        """
        return self.remove_influences(joints, transfer_to_parent=transfer_to_parent)
