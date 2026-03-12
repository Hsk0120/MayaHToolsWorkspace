import maya.cmds as cmds
import maya.api.OpenMaya as om

import HTools.rigging.simpleCollisionFromSelection as simple_collision


def _selected_mesh_transforms():
	mesh_transforms = []
	seen = set()
	selection = om.MGlobal.getActiveSelectionList()
	iterator = om.MItSelectionList(selection)

	while not iterator.isDone():
		try:
			dag_path, _component = iterator.getComponent()
		except RuntimeError:
			dag_path = iterator.getDagPath()

		if dag_path.apiType() == om.MFn.kTransform:
			dag_path.extendToShape()

		if dag_path.apiType() != om.MFn.kMesh:
			iterator.next()
			continue

		shape_path = dag_path.fullPathName()
		parents = cmds.listRelatives(shape_path, parent=True, fullPath=True) or []
		if parents:
			transform = parents[0]
			if transform not in seen:
				seen.add(transform)
				mesh_transforms.append(transform)

		iterator.next()

	return mesh_transforms


def _find_skin_cluster(mesh_transform):
	history = cmds.listHistory(mesh_transform) or []
	skin_clusters = cmds.ls(history, type="skinCluster") or []
	return skin_clusters[0] if skin_clusters else None


def _bind_mesh_to_single_joint(mesh_transform, joint):
	existing_skin = _find_skin_cluster(mesh_transform)
	if existing_skin:
		cmds.skinCluster(existing_skin, edit=True, unbind=True)

	skin_cluster = cmds.skinCluster(
		joint,
		mesh_transform,
		toSelectedBones=True,
		bindMethod=0,
		skinMethod=0,
		normalizeWeights=1,
		maximumInfluences=1,
		obeyMaxInfluences=True,
		removeUnusedInfluence=False,
	)[0]

	cmds.skinPercent(
		skin_cluster,
		"{0}.vtx[*]".format(mesh_transform),
		transformValue=[(joint, 1.0)],
		normalize=True,
	)

	return skin_cluster


def _indexed_name(base_name, index, total_count):
	if total_count <= 1:
		return base_name
	return "{0}_{1:02d}".format(base_name, index + 1)


def create_obb_joint_and_bind_from_selection(
		collision_name="obbCollision_geo",
		joint_name="obbCollision_jnt",
		use_hull_points=True,
		hull_direction_count=64,
		delete_collision=True,
):
	source_meshes = _selected_mesh_transforms()
	if not source_meshes:
		om.MGlobal.displayError("Select mesh object or mesh vertices.")
		return None

	original_selection = cmds.ls(selection=True, long=True) or []
	created_joints = []
	bound_meshes = []
	deleted_collisions = 0
	total_count = len(source_meshes)

	try:
		for index, mesh_transform in enumerate(source_meshes):
			cmds.select(mesh_transform, replace=True)

			collision_name_i = _indexed_name(collision_name, index, total_count)
			joint_name_i = _indexed_name(joint_name, index, total_count)

			obb_data = simple_collision.create_obb_collision_from_selection(
				name=collision_name_i,
				use_hull_points=use_hull_points,
				hull_direction_count=hull_direction_count,
				return_obb_data=True,
			)
			if not obb_data:
				continue

			collision = obb_data["collision"]
			center = obb_data["center"]
			axis_x, axis_y, axis_z = obb_data["axes"]

			joint = cmds.createNode("joint", name=joint_name_i)
			selection = om.MSelectionList()
			selection.add(joint)
			joint_dag = selection.getDagPath(0)
			joint_fn = om.MFnTransform(joint_dag)

			joint_matrix = om.MMatrix([
				axis_x.x, axis_x.y, axis_x.z, 0.0,
				axis_y.x, axis_y.y, axis_y.z, 0.0,
				axis_z.x, axis_z.y, axis_z.z, 0.0,
				center.x, center.y, center.z, 1.0,
			])
			joint_fn.setTransformation(om.MTransformationMatrix(joint_matrix))
			cmds.makeIdentity(joint, apply=True, t=False, r=True, s=True, n=False, pn=True)

			_bind_mesh_to_single_joint(mesh_transform, joint)
			created_joints.append(joint)
			bound_meshes.append(mesh_transform)

			if delete_collision and cmds.objExists(collision):
				cmds.delete(collision)
				deleted_collisions += 1
	finally:
		if original_selection:
			cmds.select(original_selection, replace=True)
		else:
			cmds.select(clear=True)

	if not created_joints:
		om.MGlobal.displayError("No joints were created. Check selected meshes.")
		return None

	om.MGlobal.displayInfo(
		"Created joints: {0} (frozen) / Bound meshes: {1} / Deleted collisions: {2}".format(
			len(created_joints),
			len(bound_meshes),
			deleted_collisions,
		)
	)

	return {
		"joints": created_joints,
		"meshes": bound_meshes,
	}


if __name__ == "__main__":
	create_obb_joint_and_bind_from_selection()
