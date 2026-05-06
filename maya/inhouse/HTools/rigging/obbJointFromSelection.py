"""選択メッシュから OBB ベースのジョイントを作成して再バインドするツール。"""

import maya.cmds as cmds
import maya.api.OpenMaya as om

import HTools.rigging.simpleCollisionFromSelection as simple_collision


def _selected_mesh_transforms():
	"""選択からメッシュ Transform 一覧を重複なしで取得します。

	Returns:
		list[str]: フルパスのメッシュ Transform 名一覧。
	"""
	mesh_transforms = []
	seen = set()
	selection = om.MGlobal.getActiveSelectionList()
	iterator = om.MItSelectionList(selection)

	while not iterator.isDone():
		try:
			dag_path, _component = iterator.getComponent()
		except RuntimeError:
			dag_path = iterator.getDagPath()

		# Transform 選択時は shape へ降りてメッシュ判定する。
		if dag_path.apiType() == om.MFn.kTransform:
			dag_path.extendToShape()

		if dag_path.apiType() != om.MFn.kMesh:
			iterator.next()
			continue

		# shape から親 Transform を復元して結果へ積む。
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
	"""メッシュに接続された最初の skinCluster を取得します。

	Args:
		mesh_transform (str): 対象メッシュ Transform。

	Returns:
		str | None: skinCluster 名。存在しなければ None。
	"""
	history = cmds.listHistory(mesh_transform) or []
	skin_clusters = cmds.ls(history, type="skinCluster") or []
	return skin_clusters[0] if skin_clusters else None


def _bind_mesh_to_single_joint(mesh_transform, joint):
	"""メッシュを単一ジョイント 100% でスキニングします。

	Args:
		mesh_transform (str): 対象メッシュ Transform。
		joint (str): バインド先ジョイント。

	Returns:
		str: 作成された skinCluster 名。
	"""
	existing_skin = _find_skin_cluster(mesh_transform)
	if existing_skin:
		# 既存スキンがある場合は一旦解除して単一影響へ再構築する。
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
	"""複数処理時に連番付き名前を生成します。"""
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
	"""選択メッシュごとに OBB 姿勢のジョイントを作成し単一バインドします。

	Args:
		collision_name (str): 中間コリジョンメッシュ名のベース。
		joint_name (str): 作成ジョイント名のベース。
		use_hull_points (bool): 凸包近似点を使って OBB 計算するか。
		hull_direction_count (int): 凸包近似に使う方向サンプル数。
		delete_collision (bool): 中間コリジョンを処理後に削除するか。

	Returns:
		dict[str, list[str]] | None: 成功時は作成ジョイントと対象メッシュ、
		失敗時は None。
	"""
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

			# OBB 推定は既存ユーティリティに委譲し、結果の軸と中心を利用する。
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

			# OBB の回転軸 + 中心位置でジョイント行列を直接組み立てる。
			joint_matrix = om.MMatrix([
				axis_x.x, axis_x.y, axis_x.z, 0.0,
				axis_y.x, axis_y.y, axis_y.z, 0.0,
				axis_z.x, axis_z.y, axis_z.z, 0.0,
				center.x, center.y, center.z, 1.0,
			])
			joint_fn.setTransformation(om.MTransformationMatrix(joint_matrix))
			# 回転を凍結して jointOrient 側へ焼き込み、扱いやすい状態にする。
			cmds.makeIdentity(joint, apply=True, t=False, r=True, s=True, n=False, pn=True)

			_bind_mesh_to_single_joint(mesh_transform, joint)
			created_joints.append(joint)
			bound_meshes.append(mesh_transform)

			# デバッグ用途が不要なら中間コリジョンは掃除する。
			if delete_collision and cmds.objExists(collision):
				cmds.delete(collision)
				deleted_collisions += 1
	finally:
		# 失敗時でも元の選択状態を戻す。
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
