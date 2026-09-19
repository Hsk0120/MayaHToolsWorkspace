"""選択ジョイントのウェイトを親インフルエンスへ移し、ジョイントを削除するツール。"""

import functools

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2

def undo_chunk(name=None):
    """1つの Undo チャンクで関数を実行するデコレータを返す。

    Args:
        name (str or None): Undo チャンク名。None の場合は関数名を使う。

    Returns:
        callable: 関数を Undo チャンクで包むデコレータ。
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            chunk_name = name or getattr(func, "__name__", "UndoChunk")
            cmds.undoInfo(openChunk=True, chunkName=chunk_name)
            try:
                return func(*args, **kwargs)
            finally:
                cmds.undoInfo(closeChunk=True)

        return wrapper

    return decorator


class Hlib:
    """このツール内で使用する Maya API wrapper の名前空間。"""

    @staticmethod
    def ls(*args, **kwargs):
        """Mayaの検索結果をHlibのドメインオブジェクトへ変換する。"""

        names = cmds.ls(*args, **kwargs) or []
        node_type = kwargs.get("type")

        if node_type == "joint":
            return Joints(names)

        if node_type == "skinCluster":
            return SkinClusters(names)

        return [Hlib.Node(name) for name in names]

    class Node:
        """DAG/DG ノードに共通する Maya ノード基底クラス。"""

        def __init__(self, node):
            self._mobject = None
            self._dag_path = None
            self._resolve(node)

        def _resolve(self, node):
            selection = om2.MSelectionList()

            if isinstance(node, str):
                selection.add(node)
                self._mobject = selection.getDependNode(0)
            elif isinstance(node, om2.MDagPath):
                self._dag_path = om2.MDagPath(node)
                self._mobject = self._dag_path.node()
            elif isinstance(node, om2.MObject):
                self._mobject = om2.MObject(node)
                if self._mobject.hasFn(om2.MFn.kDagNode):
                    self._dag_path = om2.MFnDagNode(self._mobject).getPath()
            else:
                raise TypeError("node must be a name, MObject, or MDagPath")

        def is_valid(self):
            if self._mobject is None or self._mobject.isNull():
                return False
            return om2.MObjectHandle(self._mobject).isValid()

        def is_alive(self):
            if self._mobject is None or self._mobject.isNull():
                return False
            return om2.MObjectHandle(self._mobject).isAlive()

        def mobject(self):
            return self._mobject

        @property
        def uuid(self):
            if not self.is_valid():
                return None
            return om2.MFnDependencyNode(self._mobject).uuid().asString()

        @property
        def name(self):
            if not self.is_valid():
                return ""
            if self._dag_path is not None:
                return self._dag_path.fullPathName()
            return om2.MFnDependencyNode(self._mobject).name()

        def __str__(self):
            return self.name

    class DGNode(Node):
        """DAGパスを持たない DG ノードの基底クラス。"""

        def dependency_node(self):
            return om2.MFnDependencyNode(self.mobject())

    class DAGNode(Node):
        """階層構造を持つ DAG ノードの基底クラス。"""

        def dag_path(self):
            if self._dag_path is None and self.is_valid():
                self._dag_path = om2.MFnDagNode(self.mobject()).getPath()
            return self._dag_path

        def dag_node(self):
            return om2.MFnDagNode(self.dag_path())

        def parent_node(self):
            if not self.is_valid() or self.dag_node().parentCount() == 0:
                return None

            parent_path = om2.MDagPath(self.dag_path())
            parent_path.pop()
            return Hlib.DAGNode(parent_path)

        def child_nodes(self):
            if not self.is_valid():
                return []

            dag_path = self.dag_path()
            dag_fn = self.dag_node()
            children = []

            for index in range(dag_fn.childCount()):
                child_path = om2.MDagPath(dag_path)
                child_path.push(dag_fn.child(index))
                children.append(Hlib.DAGNode(child_path))

            return children


class Joint(Hlib.DAGNode):
    """Maya のジョイントを扱うラッパークラス。

    The class keeps the public API compact while centralizing the
    joint-specific operations used by the remover pipeline.
    """

    def __init__(self, name):
        """ジョイント名を保持して初期化する。

        Args:
            name (str): 操作対象ジョイントの名前。
        """

        super().__init__(name)

    def parent(self):
        """親ジョイントを返す。

        Returns:
            str or None: 親ジョイント名。親がなければ None。
        """

        if not self.is_valid():
            return None

        parent = self.parent_node()
        if parent is None or not parent.is_valid() or not parent.mobject().hasFn(om2.MFn.kJoint):
            return None

        return parent.name

    def children(self):
        """子ジョイント一覧を返す。

        Returns:
            list[str]: 子ジョイント名一覧。
        """

        if not self.is_valid():
            return []

        return [
            child.name
            for child in self.child_nodes()
            if child.mobject().hasFn(om2.MFn.kJoint)
        ]

    def depth(self):
        """階層深さを返す。

        Returns:
            int: 親方向の深さ。
        """

        depth = 0
        current_joint = self.parent()

        while current_joint:
            depth += 1
            current_joint = Joint(current_joint).parent()

        return depth

    def is_joint(self):
        """有効なジョイントか判定する。

        Returns:
            bool: joint ノードなら True。
        """

        return self.is_valid() and self.mobject().hasFn(om2.MFn.kJoint)

    def skin_clusters(self):
        """このジョイントをインフルエンスに持つ skinCluster を返す。

        Returns:
            list[SkinCluster]: 関連する SkinCluster 一覧。
        """

        names = cmds.listConnections(self.name, type="skinCluster") or []
        names = self._unique_ordered(names)
        return [SkinCluster(name) for name in names]

    def transfer_target(self, skin):
        """ウェイト移動先候補の親インフルエンスを返す。

        Args:
            skin (SkinCluster): 調査対象の skinCluster。

        Returns:
            str or None: 移動先ジョイント名。
        """

        ancestor = self.parent()

        while ancestor:
            if skin.has_influence(ancestor):
                return ancestor

            ancestor = Joint(ancestor).parent()

        return None

    def reparent_children(self, parent_joint):
        """子ジョイントを指定親へ再配置する。

        Args:
            parent_joint (str): 付け替え先親ジョイント名。
        """

        for child_joint in self.children():
            cmds.parent(child_joint, parent_joint)

    @staticmethod
    def _unique_ordered(items):
        """入力順を維持して重複を除去する。"""

        seen = set()
        unique_items = []

        for item in items:
            if item in seen:
                continue

            seen.add(item)
            unique_items.append(item)

        return unique_items

    def __str__(self):
        """文字列表現を返す。

        Returns:
            str: ジョイント名。
        """

        return self.name

    def __eq__(self, other):
        """UUIDを基準にジョイントの同一性を判定する。

        Args:
            other (object): 比較対象。

        Returns:
            bool: 同じUUIDを持つジョイントなら True。
        """

        if not isinstance(other, Joint):
            return NotImplemented

        return self.uuid == other.uuid

    def __hash__(self):
        """UUIDをハッシュ値として返す。

        Returns:
            int: UUIDのハッシュ値。
        """

        return hash(self.uuid)


class Joints:
    """複数ジョイントをまとめて扱うコレクション。"""

    def __init__(self, names):
        """ジョイント名一覧からコレクションを作成する。

        Args:
            names (list[str]): 初期化対象のジョイント名一覧。
        """

        self._items = []
        seen = set()

        for item in names:
            joint = item if isinstance(item, Joint) else Joint(item)

            if not joint.is_joint() or joint.uuid in seen:
                continue

            seen.add(joint.uuid)
            self._items.append(joint)

    @property
    def names(self):
        """ジョイント名一覧を返す。

        Returns:
            list[str]: ジョイント名一覧。
        """

        return [joint.name for joint in self._items]

    def sorted_by_depth(self):
        """深い順に並べた Joints を返す。

        Returns:
            Joints: 深さ順にソートされたコレクション。
        """

        ordered = sorted(self._items, key=lambda joint: joint.depth(), reverse=True)
        return Joints(ordered)

    def skin_clusters(self):
        """このコレクションを処理する SkinClusters を返す。

        Returns:
            SkinClusters: 処理対象ジョイントに対応する skinCluster 集合。
        """

        skin_clusters = []
        seen = set()

        for joint in self._items:
            for skin in joint.skin_clusters():
                if skin.uuid in seen:
                    continue

                seen.add(skin.uuid)
                skin_clusters.append(skin)

        return SkinClusters(skin_clusters)

    def delete(self):
        """ウェイトを移動して、このコレクションのジョイントを削除する。"""

        self.skin_clusters().remove_joints(self)

    def __iter__(self):
        """イテレータを返す。

        Returns:
            iterator: ジョイントオブジェクト反復子。
        """

        return iter(self._items)


class SkinCluster(Hlib.DGNode):
    """skinCluster ノードに対する操作をまとめたユーティリティ。"""

    _LAYER_TOKENS = ("ngskin", "ngst", "ngskintools", "skinlayer", "skinninglayer", "layerdata")

    def __init__(self, skin_cluster):
        """操作対象となる skinCluster ラッパーを初期化する。

        Args:
            skin_cluster (str): skinCluster ノード名。
        """

        super().__init__(skin_cluster)
        self.mesh = self._mesh()

        self.mesh_path = self._get_dag_path(self.mesh)
        self.fn = oma2.MFnSkinCluster(self.mobject())

    def _mobj(self, name):
        """ノード名から MObject を取得する。

        Args:
            name (str): 取得対象ノード名。

        Returns:
            om2.MObject: 対象ノードの MObject。
        """

        selection = om2.MSelectionList()
        selection.add(name)
        return selection.getDependNode(0)

    def _uuid(self, node):
        """ノードの UUID を取得する。

        Args:
            node (str): UUID を調べるノード名。

        Returns:
            str or None: UUID。取得できない場合は None。
        """

        uuids = cmds.ls(node, uuid=True) or []
        return uuids[0] if uuids else None

    def _get_dag_path(self, name):
        """ノード名から MDagPath を取得し、必要に応じて shape へ拡張する。

        Args:
            name (str): 取得対象ノード名。

        Returns:
            om2.MDagPath: 対象ノードの DAG パス。
        """

        selection = om2.MSelectionList()
        selection.add(name)

        path = selection.getDagPath(0)

        if path.node().hasFn(om2.MFn.kTransform):
            path.extendToShape()

        return path

    def _mesh(self):
        """skinCluster に紐付く先頭ジオメトリ名を返す。

        Returns:
            str: skinCluster にバインドされたメッシュ名。
        """

        geometries = cmds.skinCluster(self.name, query=True, geometry=True) or []

        return geometries[0]

    def _jnt_index(self, joint):
        """インフルエンス配列内のジョイント番号を取得する。

        UUID 一致を優先し、見つからない場合は partialPathName で判定する。

        Args:
            joint (str): 検索対象ジョイント名。

        Returns:
            int or None: 見つかったインフルエンス番号。未検出なら None。
        """

        uuid = self._uuid(joint)
        infs = self.fn.influenceObjects()

        for idx, path in enumerate(infs):
            if uuid and self._uuid(path.fullPathName()) == uuid:
                return idx
            if path.partialPathName() == joint:
                return idx

        return None

    def _all_verts(self):
        """対象メッシュの全頂点コンポーネントを作成する。

        Returns:
            tuple: (全頂点コンポーネント, 頂点数)。
        """

        vtx_count = om2.MFnMesh(self.mesh_path).numVertices

        comp_fn = om2.MFnSingleIndexedComponent()

        verts = comp_fn.create(om2.MFn.kMeshVertComponent)

        comp_fn.addElements(range(vtx_count))

        return verts, vtx_count

    def _jnt_indices(self, joints):
        """ジョイント名配列をインフルエンス番号配列へ変換する。

        Args:
            joints (list[str]): 変換対象ジョイント名一覧。

        Returns:
            om2.MIntArray: インフルエンス番号配列。
        """

        return om2.MIntArray([self._jnt_index(joint) for joint in joints])

    def influences(self):
        """保持中のインフルエンス名一覧を返す。

        Returns:
            list[str]: インフルエンスの partialPathName 一覧。
        """

        return [path.partialPathName() for path in self.fn.influenceObjects()]

    def has_influence(self, joint):
        """指定ジョイントがインフルエンスとして存在するか判定する。

        Args:
            joint (str): 判定対象ジョイント名。

        Returns:
            bool: インフルエンスに存在すれば True。
        """

        uuid = self._uuid(joint)

        if not uuid:
            return False

        return any(self._uuid(path.fullPathName()) == uuid for path in self.fn.influenceObjects())

    def get_weights(self, joints):
        """指定インフルエンスのウェイトを取得する。

        Args:
            joints (list[str]): 取得対象インフルエンス名一覧。

        Returns:
            tuple: MFnSkinCluster.getWeights の戻り値。
        """

        verts, vtx_count = self._all_verts()

        jnt_ids = self._jnt_indices(joints)

        return self.fn.getWeights(self.mesh_path, verts, jnt_ids)

    def set_weights(self, joints, weights):
        """指定インフルエンスのウェイトを設定する。

        Args:
            joints (list[str]): 設定対象インフルエンス名一覧。
            weights (sequence[float]): 設定するウェイト配列。
        """

        verts, vtx_count = self._all_verts()

        jnt_ids = self._jnt_indices(joints)

        self.fn.setWeights(self.mesh_path, verts, jnt_ids, om2.MDoubleArray(weights), False)

    def transfer_weight(self, source_joint, target_joint):
        """1組のジョイント間でウェイトを移動する。

        Args:
            source_joint (str): 移動元インフルエンス。
            target_joint (str): 移動先インフルエンス。
        """

        self.transfer_weights_batch([(source_joint, target_joint)])

    def _xfer_pair(self, source_joint, target_joint):
        """1組のジョイント間でウェイト移動コマンドを実行する。

        Args:
            source_joint (str): 移動元インフルエンス。
            target_joint (str): 移動先インフルエンス。
        """

        cmds.skinCluster(self.name, edit=True, selectInfluenceVerts=source_joint)

        if not cmds.ls(sl=True):
            return

        cmds.skinPercent(self.name, transformMoveWeights=[source_joint, target_joint])

    def _restore_sel(self, original_selection):
        """一時変更した選択状態を復元する。

        Args:
            original_selection (list[str]): 復元対象の選択ノード一覧。
        """

        if original_selection:
            cmds.select(original_selection, replace=True)
            return

        cmds.select(clear=True)

    def transfer_weights_batch(self, source_target_pairs):
        """複数ジョイントペアのウェイト移動を一括実行する。

        Args:
            source_target_pairs (list[tuple[str, str]]): (移動元, 移動先) の組。

        Raises:
            RuntimeError: スキニングレイヤーが存在し編集不可な場合。
        """

        self._raise_if_layers()
        orig_sel = cmds.ls(sl=True, long=True) or []

        try:
            for source_joint, target_joint in source_target_pairs:
                self._xfer_pair(source_joint, target_joint)
        finally:
            self._restore_sel(orig_sel)

    def remove_influence(self, joint):
        """インフルエンスから指定ジョイントを削除する。

        Args:
            joint (str): 削除対象ジョイント名。

        Raises:
            RuntimeError: スキニングレイヤーが存在し編集不可な場合。
        """

        self._raise_if_layers()
        cmds.skinCluster(self.name, edit=True, removeInfluence=joint)

    def _has_layer_plugs(self):
        """スキニングレイヤー関連ノード接続があるか判定する。"""

        nodes = cmds.listConnections(self.name, source=True, destination=True) or []

        for node in nodes:
            node_name = node.lower()
            node_type = cmds.nodeType(node).lower()

            if any(token in node_name or token in node_type for token in self._LAYER_TOKENS):
                return True

        return False

    def _raise_if_layers(self):
        """スキニングレイヤー関連接続があれば例外を送出する。"""

        if self._has_layer_plugs():
            raise RuntimeError("skinning layersが存在するため実行できません。")


Hlib.Joint = Joint
Hlib.SkinCluster = SkinCluster


class SkinClusters:
    """複数 skinCluster に対するジョイント削除処理を管理する。"""

    def __init__(self, names=()):
        """skinClusterオブジェクトの集合を初期化する。

        Args:
            names (iterable[str]): skinClusterノード名の iterable。
        """

        self._items = []
        self.cache = {}
        self.ops = {}
        self.parents = {}
        self.op_counts = {}
        self.counts = {}

        for item in names:
            skin = item if isinstance(item, SkinCluster) else SkinCluster(item)
            name = skin.name

            if name in self.cache:
                continue

            self._items.append(skin)
            self.cache[name] = skin

    def __iter__(self):
        """保持しているSkinClusterオブジェクトを反復する。"""

        return iter(self._items)

    def gather(self, joints):
        """skinClusterごとのウェイト移動操作を収集する。

        Args:
            joints (Joints): 処理対象ジョイントのコレクション。
        """

        for joint in joints:
            if not joint.is_joint():
                continue

            parent_jnt = joint.parent()
            if not parent_jnt:
                continue

            skins = joint.skin_clusters()
            if not skins:
                continue

            op_count = self._ops_for_joint(joint, skins)
            if op_count == 0:
                continue

            self.parents[joint.uuid] = parent_jnt
            self.op_counts[joint.uuid] = op_count

    def apply(self):
        """収集済み操作を skinCluster 単位で適用する。"""

        for sc_name, pairs in self.ops.items():
            sc = self.cache[sc_name]
            sc.transfer_weights_batch(pairs)
            self._remove_influences(sc, pairs)

    def finalize(self, joints):
        """処理完了したジョイントを再配置して削除する。

        Args:
            joints (Joints): 処理対象ジョイントのコレクション。
        """

        for joint in joints:
            if not self._can_finalize(joint):
                continue

            parent_jnt = self.parents[joint.uuid]
            joint.reparent_children(parent_jnt)
            cmds.delete(joint.name)

    def _skin(self, skin_cluster):
        """skinClusterラッパーをキャッシュから取得する。"""

        if isinstance(skin_cluster, SkinCluster):
            skin = self.cache.get(skin_cluster.name)
            if skin is not None:
                return skin

            self._items.append(skin_cluster)
            self.cache[skin_cluster.name] = skin_cluster
            return skin_cluster

        skin = self.cache.get(skin_cluster)
        if skin is not None:
            return skin

        skin = SkinCluster(skin_cluster)
        self._items.append(skin)
        self.cache[skin_cluster] = skin
        return skin

    def _ops_for_joint(self, joint, skin_clusters):
        """1ジョイント分のウェイト移動操作を収集する。"""

        op_count = 0
        child_joint = joint.name

        for skin in skin_clusters:
            skin = self._skin(skin)
            target_joint = joint.transfer_target(skin)

            if not target_joint:
                continue

            self.ops.setdefault(skin.name, []).append((child_joint, target_joint))
            op_count += 1

        return op_count

    def _remove_influences(self, skin, pairs):
        """ウェイト移動済みインフルエンスを削除する。"""

        for source_joint, _ in pairs:
            skin.remove_influence(source_joint)
            self.counts[source_joint] = self.counts.get(source_joint, 0) + 1

    def _can_finalize(self, joint):
        """ジョイント削除フェーズへ進めるか判定する。"""

        expected = self.op_counts.get(joint.uuid, 0)
        if expected == 0:
            return False

        return self.counts.get(joint.name, 0) == expected and bool(
            self.parents.get(joint.uuid)
        )

    def remove_joints(self, joints):
        """指定されたJointsのウェイト移動とジョイント削除を実行する。

        Args:
            joints (Joints): 処理対象ジョイントのコレクション。
        """

        target_jnts = joints.sorted_by_depth()
        self.gather(target_jnts)
        self.apply()
        self.finalize(target_jnts)

    def remove_influences(self, joints):
        """指定されたJointsのインフルエンスだけを削除する。

        ウェイトを親インフルエンスへ移し、対象ジョイントと階層は残す。

        Args:
            joints (Joints): 処理対象ジョイントのコレクション。
        """

        target_jnts = joints.sorted_by_depth()
        self.gather(target_jnts)
        self.apply()


@undo_chunk("removeSelectedJoints")
def remove_selected_joint():
    """選択ジョイントのウェイト移動・インフルエンス削除・ジョイント削除を実行する。"""

    joints = Hlib.ls(sl=True, type="joint", long=True)
    joints.delete()

if __name__ == "__main__":
    remove_selected_joint()