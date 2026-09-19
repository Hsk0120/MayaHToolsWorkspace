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
        failures = self.transfer_weights_batch([
            (source_joint, target_joint)
        ])

        if source_joint in failures:
            raise RuntimeError(failures[source_joint])

    def _transfer_weight_with_api(
        self,
        source_joint,
        target_joint
    ):
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

        new_weights = om.MDoubleArray()

        for vertex_number in range(vertex_count):
            target_weight = weights[
                vertex_number * 2
            ]

            source_weight = weights[
                vertex_number * 2 + 1
            ]

            new_weights.append(
                target_weight + source_weight
            )

            new_weights.append(0.0)

        self.fn.setWeights(
            self.mesh_path,
            all_vertices,
            target_joints,
            new_weights,
            False
        )

    def transfer_weights_batch(self, source_target_pairs):
        original_selection = cmds.ls(sl=True, long=True) or []
        failures = {}

        try:
            for source_joint, target_joint in source_target_pairs:
                try:
                    # transformMoveWeights acts on selected components.
                    cmds.skinCluster(
                        self.name,
                        edit=True,
                        selectInfluenceVerts=source_joint
                    )

                    if not cmds.ls(sl=True):
                        continue

                    cmds.skinPercent(
                        self.name,
                        transformMoveWeights=[
                            source_joint,
                            target_joint,
                        ]
                    )
                except RuntimeError as error:
                    error_message = str(error)

                    if (
                        "skinning layers are present"
                        in error_message.lower()
                    ):
                        try:
                            # Fallback for scenes where cmds skin writes
                            # are blocked by skin layers.
                            self._transfer_weight_with_api(
                                source_joint,
                                target_joint
                            )
                        except RuntimeError as api_error:
                            failures[source_joint] = str(api_error)
                        continue

                    failures[source_joint] = error_message
        finally:
            if original_selection:
                cmds.select(
                    original_selection,
                    replace=True
                )
            else:
                cmds.select(clear=True)

        return failures

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


def _build_joint_jobs(target_joints):
    skin_cache = {}
    joint_jobs = {}
    failed_reasons = {}

    for child_joint in target_joints:
        if not cmds.objExists(child_joint):
            failed_reasons[child_joint] = "Joint does not exist"
            continue

        if cmds.nodeType(child_joint) != "joint":
            failed_reasons[child_joint] = "Node is not a joint"
            continue

        parent_joint = _get_parent_joint(child_joint)

        if not parent_joint:
            failed_reasons[child_joint] = (
                "Selected joint has no parent joint"
            )
            continue

        skin_cluster_names = _find_skin_clusters_using_influence(
            child_joint
        )

        if not skin_cluster_names:
            failed_reasons[child_joint] = (
                "No skinCluster connected to joint"
            )
            continue

        operations = []
        has_plan_failure = False

        for skin_cluster_name in skin_cluster_names:
            skin = skin_cache.get(skin_cluster_name)

            if skin is None:
                try:
                    skin = SkinCluster(skin_cluster_name)
                except RuntimeError as error:
                    cmds.warning(str(error))
                    has_plan_failure = True
                    continue

                skin_cache[skin_cluster_name] = skin

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
                has_plan_failure = True
                continue

            operations.append((skin_cluster_name, target_joint))

        if not operations:
            failed_reasons[child_joint] = "No skinCluster was processed"
            continue

        joint_jobs[child_joint] = {
            "parent_joint": parent_joint,
            "operations": operations,
            "has_plan_failure": has_plan_failure,
        }

    return skin_cache, joint_jobs, failed_reasons


def _group_operations_by_skin(target_joints, joint_jobs):
    operations_by_skin = {}

    for child_joint in target_joints:
        job = joint_jobs.get(child_joint)
        if not job:
            continue

        for skin_cluster_name, target_joint in job["operations"]:
            if skin_cluster_name not in operations_by_skin:
                operations_by_skin[skin_cluster_name] = []

            operations_by_skin[skin_cluster_name].append(
                (child_joint, target_joint)
            )

    return operations_by_skin


def _apply_grouped_operations(operations_by_skin, skin_cache):
    processed_counts = {}
    runtime_failures = {}

    for skin_cluster_name, source_target_pairs in (
        operations_by_skin.items()
    ):
        skin = skin_cache[skin_cluster_name]
        transfer_failures = skin.transfer_weights_batch(
            source_target_pairs
        )

        for source_joint, target_joint in source_target_pairs:
            if source_joint in transfer_failures:
                message = "Failed to process {}: {}".format(
                    skin_cluster_name,
                    transfer_failures[source_joint]
                )
                cmds.warning(message)
                runtime_failures.setdefault(
                    source_joint,
                    []
                ).append(message)
                continue

            try:
                skin.remove_influence(source_joint)
                processed_counts[source_joint] = (
                    processed_counts.get(source_joint, 0) + 1
                )
            except RuntimeError as error:
                message = "Failed to process {}: {}".format(
                    skin_cluster_name,
                    error
                )
                cmds.warning(message)
                runtime_failures.setdefault(
                    source_joint,
                    []
                ).append(message)

    return processed_counts, runtime_failures


def _finalize_joint_deletion(child_joint, parent_joint):
    try:
        _reparent_child_joints(child_joint, parent_joint)
    except RuntimeError as error:
        return False, "Failed to reparent children: {}".format(
            error
        )

    try:
        cmds.delete(child_joint)
    except RuntimeError as error:
        return False, "Failed to delete joint: {}".format(error)

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
    failed_reasons = {}

    chunk_opened = False

    try:
        cmds.undoInfo(
            openChunk=True,
            chunkName="removeSelectedJoints"
        )
        chunk_opened = True

        skin_cache, joint_jobs, planning_failures = (
            _build_joint_jobs(target_joints)
        )
        failed_reasons.update(planning_failures)

        operations_by_skin = _group_operations_by_skin(
            target_joints,
            joint_jobs
        )

        processed_counts, runtime_failures = (
            _apply_grouped_operations(
                operations_by_skin,
                skin_cache
            )
        )

        for child_joint in target_joints:
            if child_joint in failed_reasons:
                continue

            job = joint_jobs.get(child_joint)
            if not job:
                failed_reasons[child_joint] = (
                    "No skinCluster was processed"
                )
                continue

            if processed_counts.get(child_joint, 0) == 0:
                failed_reasons[child_joint] = (
                    "No skinCluster was processed"
                )
                continue

            if (
                job["has_plan_failure"]
                or child_joint in runtime_failures
            ):
                failed_reasons[child_joint] = (
                    "Some skinClusters failed"
                )
                continue

            succeeded, reason = _finalize_joint_deletion(
                child_joint,
                job["parent_joint"]
            )

            if succeeded:
                success_joints.append(child_joint)
                continue

            failed_reasons[child_joint] = reason
    finally:
        if chunk_opened:
            cmds.undoInfo(closeChunk=True)

    if failed_reasons:
        failed_joints = []

        for child_joint in target_joints:
            reason = failed_reasons.get(child_joint)
            if reason is None:
                continue

            failed_joints.append(child_joint)
            cmds.warning(
                "Skipped {}: {}".format(
                    child_joint,
                    reason
                )
            )

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