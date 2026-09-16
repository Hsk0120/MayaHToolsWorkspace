import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma


class SkinCluster:

    def __init__(self, skin_cluster):
        self.name = skin_cluster
        self.mesh = self._find_mesh()

        self.mesh_path = self._get_dag_path(self.mesh)
        self.fn = oma.MFnSkinCluster(
            self._get_mobject(self.name)
        )

    # --------------------------------------------------
    # private
    # --------------------------------------------------

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
        geometries = cmds.skinCluster(
            self.name,
            query=True,
            geometry=True
        ) or []

        if not geometries:
            raise RuntimeError(
                "No geometry found for skinCluster: {}".format(
                    self.name
                )
            )

        return geometries[0]

    def _get_joint_number(self, joint):
        target_uuid = self._get_uuid(joint)
        joints = self.fn.influenceObjects()

        for number, path in enumerate(joints):
            influence_name = path.fullPathName()

            if target_uuid:
                influence_uuid = self._get_uuid(
                    influence_name
                )

                if influence_uuid == target_uuid:
                    return number

            if path.partialPathName() == joint:
                return number

        raise RuntimeError(
            "Influence not found in skinCluster {}: {}".format(
                self.name,
                joint
            )
        )

    def _get_all_vertices(self):
        vertex_count = om.MFnMesh(
            self.mesh_path
        ).numVertices

        component_fn = om.MFnSingleIndexedComponent()

        all_vertices = component_fn.create(
            om.MFn.kMeshVertComponent
        )

        component_fn.addElements(
            range(vertex_count)
        )

        return all_vertices, vertex_count

    def _get_target_joints(self, joints):
        return om.MIntArray([
            self._get_joint_number(joint)
            for joint in joints
        ])

    # --------------------------------------------------
    # public
    # --------------------------------------------------

    def influences(self):
        return [
            path.partialPathName()
            for path in self.fn.influenceObjects()
        ]

    def has_influence(self, joint):
        target_uuid = self._get_uuid(joint)

        if not target_uuid:
            return False

        for path in self.fn.influenceObjects():
            influence_uuid = self._get_uuid(
                path.fullPathName()
            )

            if influence_uuid == target_uuid:
                return True

        return False

    def get_weights(self, joints):
        all_vertices, vertex_count = (
            self._get_all_vertices()
        )

        target_joints = self._get_target_joints(
            joints
        )

        return self.fn.getWeights(
            self.mesh_path,
            all_vertices,
            target_joints
        )

    def set_weights(self, joints, weights):
        all_vertices, vertex_count = (
            self._get_all_vertices()
        )

        target_joints = self._get_target_joints(
            joints
        )

        self.fn.setWeights(
            self.mesh_path,
            all_vertices,
            target_joints,
            om.MDoubleArray(weights),
            False
        )

    def transfer_weight(self, source_joint, target_joint):
        all_vertices, vertex_count = (
            self._get_all_vertices()
        )

        target_joints = self._get_target_joints([
            target_joint,
            source_joint
        ])

        weights = self.fn.getWeights(
            self.mesh_path,
            all_vertices,
            target_joints
        )

        # Apply with cmds so this transfer is captured by Maya undo.
        for vertex_number in range(vertex_count):
            target_weight = weights[
                vertex_number * 2
            ]

            source_weight = weights[
                vertex_number * 2 + 1
            ]

            if source_weight <= 0.0:
                continue

            component = "{}.vtx[{}]".format(
                self.mesh,
                vertex_number
            )

            cmds.skinPercent(
                self.name,
                component,
                transformValue=[
                    (target_joint, target_weight + source_weight),
                    (source_joint, 0.0),
                ],
                normalize=False
            )

    def remove_influence(self, joint):
        cmds.skinCluster(
            self.name,
            edit=True,
            removeInfluence=joint
        )


def _get_parent_joint(joint):
    parents = cmds.listRelatives(
        joint,
        parent=True,
        type="joint",
        fullPath=True
    ) or []

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

    return sorted(
        unique_joints,
        key=_get_joint_depth,
        reverse=True
    )


def _find_skin_clusters_using_influence(joint):
    skin_clusters = cmds.listConnections(
        joint,
        type="skinCluster"
    ) or []

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
    child_joints = cmds.listRelatives(
        child_joint,
        children=True,
        type="joint"
    ) or []

    for joint in child_joints:
        cmds.parent(joint, parent_joint)


def _process_single_joint(child_joint):
    if not cmds.objExists(child_joint):
        return False, "Joint does not exist"

    if cmds.nodeType(child_joint) != "joint":
        return False, "Node is not a joint"

    parent_joint = _get_parent_joint(child_joint)

    if not parent_joint:
        return False, "Selected joint has no parent joint"

    skin_cluster_names = _find_skin_clusters_using_influence(
        child_joint
    )

    if not skin_cluster_names:
        return False, "No skinCluster connected to joint"

    has_failure = False
    processed_count = 0

    for skin_cluster_name in skin_cluster_names:
        try:
            skin = SkinCluster(skin_cluster_name)
        except RuntimeError as error:
            cmds.warning(str(error))
            has_failure = True
            continue

        target_joint = _find_target_influence_joint(
            skin,
            child_joint
        )

        if not target_joint:
            cmds.warning(
                "No ancestor influence found in {} for {}".format(
                    skin_cluster_name,
                    child_joint
                )
            )
            has_failure = True
            continue

        try:
            skin.transfer_weight(child_joint, target_joint)
            skin.remove_influence(child_joint)
            processed_count += 1
        except RuntimeError as error:
            cmds.warning(
                "Failed to process {}: {}".format(
                    skin_cluster_name,
                    error
                )
            )
            has_failure = True

    if processed_count == 0:
        return False, "No skinCluster was processed"

    if has_failure:
        return False, "Some skinClusters failed"

    try:
        _reparent_child_joints(child_joint, parent_joint)
    except RuntimeError as error:
        return False, "Failed to reparent children: {}".format(
            error
        )

    cmds.delete(child_joint)
    return True, ""


def remove_selected_joint():
    selected_joints = cmds.ls(
        sl=True,
        type="joint",
        long=True
    ) or []

    if not selected_joints:
        cmds.warning("Select one or more joints.")
        return

    target_joints = _sorted_unique_joints(selected_joints)
    success_joints = []
    failed_joints = []

    chunk_opened = False

    try:
        cmds.undoInfo(
            openChunk=True,
            chunkName="removeSelectedJoints"
        )
        chunk_opened = True

        for child_joint in target_joints:
            succeeded, reason = _process_single_joint(
                child_joint
            )

            if succeeded:
                success_joints.append(child_joint)
                continue

            failed_joints.append(child_joint)
            cmds.warning(
                "Skipped {}: {}".format(
                    child_joint,
                    reason
                )
            )
    finally:
        if chunk_opened:
            cmds.undoInfo(closeChunk=True)

    if failed_joints:
        cmds.warning(
            "Completed with failures. Success: {}, Failed: {} ({})"
            .format(
                len(success_joints),
                len(failed_joints),
                ", ".join(failed_joints)
            )
        )
        return

    print(
        "Processed {} joint(s).".format(
            len(success_joints)
        )
    )

if __name__ == "__main__":
    remove_selected_joint()