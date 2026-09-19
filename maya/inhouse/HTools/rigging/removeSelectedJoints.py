import functools

import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma


_SKIN_LAYER_DETECTION_TOKENS = ("ngskin", "ngst", "ngskintools", "skinlayer", "skinninglayer", "layerdata")


def undo_chunk(name=None):
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


def _has_skinning_layer_connections(skin_cluster):
    connected_nodes = cmds.listConnections(skin_cluster, source=True, destination=True) or []

    for node in connected_nodes:
        node_name = node.lower()
        node_type = cmds.nodeType(node).lower()

        if any(token in node_name or token in node_type for token in _SKIN_LAYER_DETECTION_TOKENS):
            return True

    return False


def _raise_if_skinning_layers_present(skin_cluster):
    if _has_skinning_layer_connections(skin_cluster):
        raise RuntimeError("skinning layersが存在するため実行できません。")


class SkinCluster:
    def __init__(self, skin_cluster):
        self.name = skin_cluster
        self.mesh = self._find_mesh()

        self.mesh_path = self._get_dag_path(self.mesh)
        self.fn = oma.MFnSkinCluster(self._get_mobject(self.name))

    def _get_mobject(self, name):
        selection = om.MSelectionList()
        selection.add(name)
        return selection.getDependNode(0)

    def _get_uuid(self, node):
        uuids = cmds.ls(node, uuid=True) or []
        return uuids[0] if uuids else None

    def _get_dag_path(self, name):
        selection = om.MSelectionList()
        selection.add(name)

        path = selection.getDagPath(0)

        if path.node().hasFn(om.MFn.kTransform):
            path.extendToShape()

        return path

    def _find_mesh(self):
        geometries = cmds.skinCluster(self.name, query=True, geometry=True) or []

        return geometries[0]

    def _get_joint_number(self, joint):
        target_uuid = self._get_uuid(joint)
        joints = self.fn.influenceObjects()

        for number, path in enumerate(joints):
            influence_name = path.fullPathName()

            if target_uuid:
                influence_uuid = self._get_uuid(influence_name)

                if influence_uuid == target_uuid:
                    return number

            if path.partialPathName() == joint:
                return number
        return None

    def _get_all_vertices(self):
        vertex_count = om.MFnMesh(self.mesh_path).numVertices

        component_fn = om.MFnSingleIndexedComponent()

        all_vertices = component_fn.create(om.MFn.kMeshVertComponent)

        component_fn.addElements(range(vertex_count))

        return all_vertices, vertex_count

    def _get_target_joints(self, joints):
        return om.MIntArray([self._get_joint_number(joint) for joint in joints])

    def influences(self):
        return [path.partialPathName() for path in self.fn.influenceObjects()]

    def has_influence(self, joint):
        target_uuid = self._get_uuid(joint)

        if not target_uuid:
            return False

        for path in self.fn.influenceObjects():
            influence_uuid = self._get_uuid(path.fullPathName())

            if influence_uuid == target_uuid:
                return True

        return False

    def get_weights(self, joints):
        all_vertices, vertex_count = self._get_all_vertices()

        target_joints = self._get_target_joints(joints)

        return self.fn.getWeights(self.mesh_path, all_vertices, target_joints)

    def set_weights(self, joints, weights):
        all_vertices, vertex_count = self._get_all_vertices()

        target_joints = self._get_target_joints(joints)

        self.fn.setWeights(self.mesh_path, all_vertices, target_joints, om.MDoubleArray(weights), False)

    def transfer_weight(self, source_joint, target_joint):
        self.transfer_weights_batch([(source_joint, target_joint)])

    def transfer_weights_batch(self, source_target_pairs):
        _raise_if_skinning_layers_present(self.name)
        original_selection = cmds.ls(sl=True, long=True) or []

        try:
            for source_joint, target_joint in source_target_pairs:
                cmds.skinCluster(self.name, edit=True, selectInfluenceVerts=source_joint)

                if not cmds.ls(sl=True):
                    continue

                cmds.skinPercent(self.name, transformMoveWeights=[source_joint, target_joint])
        finally:
            if original_selection:
                cmds.select(original_selection, replace=True)
            else:
                cmds.select(clear=True)

    def remove_influence(self, joint):
        _raise_if_skinning_layers_present(self.name)
        cmds.skinCluster(self.name, edit=True, removeInfluence=joint)


def _get_parent_joint(joint):
    parents = cmds.listRelatives(joint, parent=True, type="joint", fullPath=True) or []

    return parents[0] if parents else None


def _get_joint_depth(joint):
    depth = 0
    current_joint = joint

    while True:
        current_joint = _get_parent_joint(current_joint)

        if not current_joint:
            break

        depth += 1

    return depth


def _sorted_unique_joints(joints):
    seen = set()
    unique_joints = []

    for joint in joints:
        if joint in seen:
            continue

        seen.add(joint)
        unique_joints.append(joint)

    return sorted(unique_joints, key=_get_joint_depth, reverse=True)


def _find_skin_clusters_using_influence(joint):
    skin_clusters = cmds.listConnections(joint, type="skinCluster") or []

    seen = set()
    unique_clusters = []

    for skin_cluster in skin_clusters:
        if skin_cluster in seen:
            continue

        seen.add(skin_cluster)
        unique_clusters.append(skin_cluster)

    return unique_clusters


def _find_target_influence_joint(skin, child_joint):
    ancestor_joint = _get_parent_joint(child_joint)

    while ancestor_joint:
        if skin.has_influence(ancestor_joint):
            return ancestor_joint

        ancestor_joint = _get_parent_joint(ancestor_joint)

    return None


def _reparent_child_joints(child_joint, parent_joint):
    child_joints = cmds.listRelatives(child_joint, children=True, type="joint") or []

    for joint in child_joints:
        cmds.parent(joint, parent_joint)


def _collect_operations(target_joints):
    skin_cache = {}
    joint_parents = {}
    operation_counts = {}
    operations_by_skin = {}

    for child_joint in target_joints:
        if not cmds.objExists(child_joint):
            continue

        if cmds.nodeType(child_joint) != "joint":
            continue

        parent_joint = _get_parent_joint(child_joint)
        if not parent_joint:
            continue

        skin_cluster_names = _find_skin_clusters_using_influence(child_joint)
        if not skin_cluster_names:
            continue

        joint_parents[child_joint] = parent_joint

        for skin_cluster_name in skin_cluster_names:
            skin = skin_cache.get(skin_cluster_name)

            if skin is None:
                skin = SkinCluster(skin_cluster_name)
                skin_cache[skin_cluster_name] = skin

            target_joint = _find_target_influence_joint(skin, child_joint)
            if not target_joint:
                continue

            if skin_cluster_name not in operations_by_skin:
                operations_by_skin[skin_cluster_name] = []

            operations_by_skin[skin_cluster_name].append((child_joint, target_joint))
            operation_counts[child_joint] = operation_counts.get(child_joint, 0) + 1

    return skin_cache, operations_by_skin, joint_parents, operation_counts


def _apply_operations(operations_by_skin, skin_cache):
    processed_counts = {}

    for skin_cluster_name, source_target_pairs in operations_by_skin.items():
        skin = skin_cache[skin_cluster_name]
        skin.transfer_weights_batch(source_target_pairs)

        for source_joint, _ in source_target_pairs:
            skin.remove_influence(source_joint)
            processed_counts[source_joint] = processed_counts.get(source_joint, 0) + 1

    return processed_counts


def _finalize_joints(
    target_joints,
    joint_parents,
    operation_counts,
    processed_counts,
):
    for child_joint in target_joints:
        if operation_counts.get(child_joint, 0) == 0:
            continue

        if processed_counts.get(child_joint, 0) != operation_counts[child_joint]:
            continue

        parent_joint = joint_parents.get(child_joint)
        if not parent_joint:
            continue

        _reparent_child_joints(child_joint, parent_joint)
        cmds.delete(child_joint)


@undo_chunk("removeSelectedJoints")
def remove_selected_joint():
    selected_joints = cmds.ls(sl=True, type="joint", long=True) or []

    target_joints = _sorted_unique_joints(selected_joints)

    skin_cache, operations_by_skin, joint_parents, operation_counts = _collect_operations(target_joints)

    processed_counts = _apply_operations(operations_by_skin, skin_cache)

    _finalize_joints(target_joints, joint_parents, operation_counts, processed_counts)

if __name__ == "__main__":
    remove_selected_joint()