"""SkinCluster operations for Hlib joint removal."""

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2

from ..core.registry import collection_export, node_wrapper
from .joint import Joint
from .node import Node


@node_wrapper("skinCluster")
class SkinCluster(Node):
    """Wrapper around a Maya skinCluster node."""

    _LAYER_TOKENS = ("ngskin", "ngst", "ngskintools", "skinlayer", "skinninglayer", "layerdata")

    def __init__(self, skin_cluster):
        """skinCluster 名または Maya オブジェクトからラッパーを初期化する。"""
        super().__init__(skin_cluster)
        self.mesh = self._mesh()
        self.mesh_path = self._get_dag_path(self.mesh)
        self.fn = oma2.MFnSkinCluster(self.mobject())

    def _uuid(self, node):
        """ノード名から Maya UUID を取得する。"""
        uuids = cmds.ls(node, uuid=True) or []
        return uuids[0] if uuids else None

    def _get_dag_path(self, name):
        """geometry 名から shape まで展開した MDagPath を取得する。"""
        selection = om2.MSelectionList()
        selection.add(name)
        path = selection.getDagPath(0)
        if path.node().hasFn(om2.MFn.kTransform):
            path.extendToShape()
        return path

    def _mesh(self):
        """skinCluster が変形する先頭 geometry 名を取得する。"""
        geometries = cmds.skinCluster(self.name, query=True, geometry=True) or []
        return geometries[0]

    def _jnt_index(self, joint):
        """influence 配列内の joint インデックスを UUID 優先で取得する。"""
        uuid = self._uuid(joint)
        for index, path in enumerate(self.fn.influenceObjects()):
            if uuid and self._uuid(path.fullPathName()) == uuid:
                return index
            if path.partialPathName() == joint:
                return index
        return None

    def _all_verts(self):
        """mesh の全頂点 component と頂点数を生成する。"""
        vertex_count = om2.MFnMesh(self.mesh_path).numVertices
        component_fn = om2.MFnSingleIndexedComponent()
        vertices = component_fn.create(om2.MFn.kMeshVertComponent)
        component_fn.addElements(range(vertex_count))
        return vertices, vertex_count

    def _jnt_indices(self, joints):
        """joint 群を skinCluster influence インデックス配列へ変換する。"""
        return om2.MIntArray([self._jnt_index(joint) for joint in joints])

    def influences(self):
        return [path.partialPathName() for path in self.fn.influenceObjects()]

    def has_influence(self, joint):
        uuid = self._uuid(joint)
        if not uuid:
            return False
        return any(
            self._uuid(path.fullPathName()) == uuid
            for path in self.fn.influenceObjects()
        )

    def get_weights(self, joints):
        vertices, _ = self._all_verts()
        return self.fn.getWeights(self.mesh_path, vertices, self._jnt_indices(joints))

    def set_weights(self, joints, weights):
        vertices, _ = self._all_verts()
        self.fn.setWeights(
            self.mesh_path,
            vertices,
            self._jnt_indices(joints),
            om2.MDoubleArray(weights),
            False,
        )

    def transfer_weight(self, source_joint, target_joint):
        self.transfer_weights_batch([(source_joint, target_joint)])

    def _xfer_pair(self, source_joint, target_joint):
        """選択された source influence 頂点のウェイトを target へ移す。"""
        cmds.skinCluster(self.name, edit=True, selectInfluenceVerts=source_joint)
        if cmds.ls(sl=True):
            cmds.skinPercent(self.name, transformMoveWeights=[source_joint, target_joint])

    @staticmethod
    def _restore_selection(original_selection):
        """処理前に保存した Maya 選択状態を復元する。"""
        if original_selection:
            cmds.select(original_selection, replace=True)
        else:
            cmds.select(clear=True)

    def transfer_weights_batch(self, source_target_pairs):
        self._raise_if_layers()
        original_selection = cmds.ls(sl=True, long=True) or []
        try:
            for source_joint, target_joint in source_target_pairs:
                self._xfer_pair(source_joint, target_joint)
        finally:
            self._restore_selection(original_selection)

    def remove_influence(self, joint):
        self._raise_if_layers()
        cmds.skinCluster(self.name, edit=True, removeInfluence=joint)

    def _has_layer_plugs(self):
        """スキニングレイヤー関連ノードが接続されているか判定する。"""
        nodes = cmds.listConnections(self.name, source=True, destination=True) or []
        for node in nodes:
            node_name = node.lower()
            node_type = cmds.nodeType(node).lower()
            if any(token in node_name or token in node_type for token in self._LAYER_TOKENS):
                return True
        return False

    def _raise_if_layers(self):
        """スキニングレイヤー検出時に安全のため処理を中断する。"""
        if self._has_layer_plugs():
            raise RuntimeError("skinning layersが存在するため実行できません。")


@collection_export()
class SkinClusters:
    """Batch skinCluster operations for a collection of joints."""

    def __init__(self, names=()):
        """skinCluster 名またはラッパーから重複なしコレクションを初期化する。"""
        self._items = []
        self.cache = {}
        self.ops = {}
        self.parents = {}
        self.op_counts = {}
        self.counts = {}
        for item in names:
            skin = item if isinstance(item, SkinCluster) else SkinCluster(item)
            if skin.name in self.cache:
                continue
            self._items.append(skin)
            self.cache[skin.name] = skin

    def __iter__(self):
        """保持している SkinCluster を順に反復する。"""
        return iter(self._items)

    def gather(self, joints):
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
        for skin_name, pairs in self.ops.items():
            skin = self.cache[skin_name]
            skin.transfer_weights_batch(pairs)
            self._remove_influences(skin, pairs)

    def finalize(self, joints):
        for joint in joints:
            if not self._can_finalize(joint):
                continue
            parent_joint = self.parents[joint.uuid]
            joint.reparent_children(parent_joint)
            cmds.delete(joint.name)

    def _skin(self, skin_cluster):
        """入力をキャッシュ済みまたは新規 SkinCluster ラッパーへ正規化する。"""
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
        """joint のウェイト移送操作を収集し、操作数を返す。"""
        op_count = 0
        for skin in skin_clusters:
            skin = self._skin(skin)
            target_joint = joint.transfer_target(skin)
            if not target_joint:
                continue
            self.ops.setdefault(skin.name, []).append((joint.name, target_joint))
            op_count += 1
        return op_count

    def _remove_influences(self, skin, pairs):
        """移送済み influence を skinCluster から削除する。"""
        for source_joint, _ in pairs:
            skin.remove_influence(source_joint)
            self.counts[source_joint] = self.counts.get(source_joint, 0) + 1

    def _can_finalize(self, joint):
        """すべての移送操作が完了し joint を削除可能か判定する。"""
        expected = self.op_counts.get(joint.uuid, 0)
        return bool(
            expected
            and self.counts.get(joint.name, 0) == expected
            and self.parents.get(joint.uuid)
        )

    def remove_joints(self, joints):
        target_joints = joints.sorted_by_depth()
        self.gather(target_joints)
        self.apply()
        self.finalize(target_joints)

    def remove_influences(self, joints):
        target_joints = joints.sorted_by_depth()
        self.gather(target_joints)
        self.apply()
