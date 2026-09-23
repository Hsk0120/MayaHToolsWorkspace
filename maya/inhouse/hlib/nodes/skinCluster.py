"""skinCluster のウェイト操作と joint 削除を支援する。"""

import json

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2

from .._core.registry import collection_export, node_wrapper
from ..decorators.selection import preserved_selection
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
            return Node(node).uuid
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

    def set_weights(self, joints, weights):
        """指定したjointの全頂点ウェイトを設定する。

        MFnSkinCluster.setWeights に normalize=False を渡す。API による直接書き込みで、Undo チャンクは作成しない。

        Args:
            joints (Iterable[str]): 設定する登録済み influence 名。
            weights (Iterable[float]): API の setWeights が受け取る平坦な配列。通常は頂点数×influence数。influence数だけなら各頂点に共通適用する。

        Returns:
            None: 値を返さない。
        """
        vertices, _ = self._all_verts()
        self.fn.setWeights(
            self.mesh_path,
            vertices,
            self._jnt_indices(joints),
            om2.MDoubleArray(weights),
            False,
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

    def load_weights(self, path):
        """dump_weights() が書き出した JSON ファイルからウェイトを読み込み設定する。

        ファイルに記録された influence がすべてこの skinCluster に存在し、
        頂点数が現在の mesh と一致することを要求する。一致しない場合は
        ウェイトを変更せず例外を送出する。

        Args:
            path (str): 読み込むファイルパス。

        Returns:
            None: 値を返さない。

        Raises:
            ValueError: 頂点数が現在の mesh と一致しない、またはファイルに
                記録された influence の一部がこの skinCluster に存在しない場合。
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

    def transfer_weight(self, source_joint, target_joint):
        """単一のsource influenceからtarget influenceへウェイトを移す。

        元 influence に影響される頂点を選択し、skinPercent の transformMoveWeights を実行する。処理後に元の選択状態を復元する。

        Args:
            source_joint (str): 移送元の influence 名。
            target_joint (str): 移送先の influence 名。

        Returns:
            None: 値を返さない。
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

    def remove_influence(self, joint):
        """指定したjointをskinClusterのinfluenceから削除する。

        Args:
            joint (str): 削除対象の influence 名。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: スキニングレイヤーを検出、または Maya が削除を拒否した場合。
        """
        self._raise_if_layers()
        cmds.skinCluster(self.name(), edit=True, removeInfluence=joint)

    def _has_layer_plugs(self):
        """スキニングレイヤー関連ノードが接続されているか判定する。

        Returns:
            bool: 接続ノードの名前または型名にレイヤー判定用トークンが含まれる場合は True。実際のレイヤーデータの有無は調べない。
        """
        for plug in self.connections():
            node = plug.node
            node_name = node.name().lower()
            node_type = node.type().lower()
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
class SkinClusters:
    """skinCluster と移送操作のキャッシュを保持するコレクション。"""

    def __init__(self, names=()):
        """skinCluster 名またはラッパーから重複なしコレクションを初期化する。

        Args:
            names (Iterable[str | SkinCluster]): skinCluster 名またはラッパー。ノード名で重複を除外する。

        Returns:
            None: 値を返さない。
        """
        self._items = []
        self.cache = {}
        self.ops = {}
        self.parents = {}
        self.op_counts = {}
        self.counts = {}
        for item in names:
            skin = item if isinstance(item, SkinCluster) else SkinCluster(item)
            if skin.name() in self.cache:
                continue
            self._items.append(skin)
            self.cache[skin.name()] = skin

    def __iter__(self):
        """保持している SkinCluster を順に反復する。

        Returns:
            Iterator[SkinCluster]: 保存順にラッパーを返すイテレータ。
        """
        return iter(self._items)

    def gather(self, joints):
        """削除対象jointに必要なウェイト移送操作を収集する。

        既存の操作キャッシュは消去しない。

        Args:
            joints (Iterable[Joint]): 処理対象の Joint。

        Returns:
            None: 値を返さない。
        """
        for joint in joints:
            if not joint.is_joint():
                continue
            parent_joint = joint.parent()
            if not parent_joint:
                continue
            skins = joint.skin_clusters()
            if not skins:
                continue
            op_count = self._ops_for_joint(joint, skins)
            if op_count:
                self.parents[joint.uuid] = parent_joint
                self.op_counts[joint.uuid] = op_count

    def apply(self):
        """収集済みのウェイト移送とinfluence削除を実行する。

        収集済みの組ごとにウェイトを移送し、元 influence を削除する。実行後も操作キャッシュは保持する。

        Returns:
            None: 値を返さない。
        """
        for skin_name, pairs in self.ops.items():
            skin = self.cache[skin_name]
            skin.transfer_weights_batch(pairs)
            self._remove_influences(skin, pairs)

    def finalize(self, joints):
        """処理済みjointの子を再親付けしてjointを削除する。

        記録した操作数だけ influence 削除が完了した joint のみ、子を親 joint へ移して削除する。

        Args:
            joints (Iterable[Joint]): 処理対象の Joint。

        Returns:
            None: 値を返さない。
        """
        for joint in joints:
            if not self._can_finalize(joint):
                continue
            parent_joint = self.parents[joint.uuid]
            joint.reparent_children(parent_joint)
            cmds.delete(joint.name())

    def _skin(self, skin_cluster):
        """入力をキャッシュ済みまたは新規 SkinCluster ラッパーへ正規化する。

        Args:
            skin_cluster (str | SkinCluster): キャッシュから解決、または新規登録する skinCluster。

        Returns:
            SkinCluster: 既存または新規のラッパー。
        """
        if isinstance(skin_cluster, SkinCluster):
            skin = self.cache.get(skin_cluster.name())
            if skin is not None:
                return skin
            self._items.append(skin_cluster)
            self.cache[skin_cluster.name()] = skin_cluster
            return skin_cluster
        skin = self.cache.get(skin_cluster)
        if skin is not None:
            return skin
        skin = SkinCluster(skin_cluster)
        self._items.append(skin)
        self.cache[skin_cluster] = skin
        return skin

    def _ops_for_joint(self, joint, skin_clusters):
        """joint のウェイト移送操作を収集し、操作数を返す。

        Args:
            joint (Joint): 移送元の joint。
            skin_clusters (Iterable[str | SkinCluster]): 移送先となる祖先 influence を探す skinCluster 群。

        Returns:
            int: 移送先を見つけ、キャッシュに追加した組の数。
        """
        op_count = 0
        for skin in skin_clusters:
            skin = self._skin(skin)
            target_joint = joint.transfer_target(skin)
            if not target_joint:
                continue
            self.ops.setdefault(skin.name(), []).append((joint.name(), target_joint))
            op_count += 1
        return op_count

    def _remove_influences(self, skin, pairs):
        """移送済み influence を skinCluster から削除する。

        削除した移送元名ごとに完了数を加算する。

        Args:
            skin (SkinCluster): influence を削除する skinCluster。
            pairs (Iterable[tuple[str, str]]): 処理済みの (移送元, 移送先) 名の組。

        Returns:
            None: 値を返さない。
        """
        for source_joint, _ in pairs:
            skin.remove_influence(source_joint)
            self.counts[source_joint] = self.counts.get(source_joint, 0) + 1

    def _can_finalize(self, joint):
        """すべての移送操作が完了し joint を削除可能か判定する。

        Args:
            joint (Joint): 削除可否を確認する joint。

        Returns:
            bool: 予定操作数が正で、削除済み数と一致し、移動先の親が記録されている場合は True。
        """
        expected = self.op_counts.get(joint.uuid, 0)
        return bool(
            expected
            and self.counts.get(joint.name(), 0) == expected
            and self.parents.get(joint.uuid)
        )

    def remove_joints(self, joints):
        """joint階層を深い順に処理し、ウェイト移送後にjointを削除する。

        移送先の親 influence が見つかった対象を処理する。完了した joint の子を再親付けしてノードも削除する。

        Args:
            joints (Joints): 深さ順に処理する joint コレクション。

        Returns:
            None: 値を返さない。
        """
        target_joints = joints.sorted_by_depth()
        self.gather(target_joints)
        self.apply()
        self.finalize(target_joints)

    def remove_influences(self, joints):
        """joint階層を深い順に処理し、influenceだけを削除する。

        移送先の親 influence が見つかった対象を処理する。ウェイト移送と influence 削除まで行い、joint ノードは残す。

        Args:
            joints (Joints): 深さ順に処理する joint コレクション。

        Returns:
            None: 値を返さない。
        """
        target_joints = joints.sorted_by_depth()
        self.gather(target_joints)
        self.apply()
