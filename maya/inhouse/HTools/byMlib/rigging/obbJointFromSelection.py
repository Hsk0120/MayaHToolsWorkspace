"""選択メッシュから OBB ベースのジョイントを作成して再バインドするツール。"""

import maya.api.OpenMaya as om

import mlib
from mlib.common import Selection
from mlib.decorator import undoChunk

import HTools.rigging.simpleCollisionFromSelection as simple_collision


def _selected_mesh_transforms():
	"""選択からメッシュ Transform 一覧を重複なしで取得します。

	Returns:
		list[mlib.Transform]: メッシュ Transform 一覧(選択の順)。
	"""
	mesh_transforms = []
	seen = set()

	for item in Selection.capture().getItems():
		# コンポーネント選択時は、それを持つ shape を使う。
		node = item.shape if isinstance(item, mlib.Component) else item

		# Transform 選択時は shape へ降りてメッシュ判定する。
		if isinstance(node, mlib.Transform):
			node = node.getShape()

		if not isinstance(node, mlib.Mesh):
			continue

		# shape から親 Transform を復元して結果へ積む。
		transform = node.getParent()
		if transform is not None:
			key = transform.getName(full=True)
			if key not in seen:
				seen.add(key)
				mesh_transforms.append(transform)

	return mesh_transforms


def _find_skin_cluster(mesh_transform):
	"""メッシュに接続された最初の skinCluster を取得します。

	Args:
		mesh_transform (mlib.Transform): 対象メッシュ Transform。

	Returns:
		mlib.SkinCluster | None: skinCluster。存在しなければ None。
	"""
	skin_clusters = mesh_transform.getHistory(type="skinCluster")
	return skin_clusters[0] if skin_clusters else None


def _bind_mesh_to_single_joint(mesh_transform, joint):
	"""メッシュを単一ジョイント 100% でスキニングします。

	Args:
		mesh_transform (mlib.Transform): 対象メッシュ Transform。
		joint (mlib.Joint): バインド先ジョイント。

	Returns:
		mlib.SkinCluster: 作成された skinCluster。
	"""
	existing_skin = _find_skin_cluster(mesh_transform)
	if existing_skin:
		# 既存スキンがある場合は一旦解除して単一影響へ再構築する。
		existing_skin.unbind()

	skin_cluster = mlib.bindSkin(
		joint,
		mesh_transform,
		maximumInfluences=1,
		bindMethod=0,
		skinMethod=0,
		normalizeWeights=1,
		obeyMaxInfluences=True,
		removeUnusedInfluence=False,
	)

	skin_cluster.setWeights(joint, [1.0], broadcast=True, normalize=True)

	return skin_cluster


def _indexed_name(base_name, index, total_count):
	"""複数処理時に連番付き名前を生成します。

	Args:
	    base_name: 重複回避や連番付加に使う元の名前。
	    index: 対象要素の番号または探索開始番号。
	    total_count: 作成または処理する対象の総数。
	"""
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

	original_selection = Selection.capture()
	created_joints = []
	bound_meshes = []
	deleted_collisions = 0
	total_count = len(source_meshes)

	# 全メッシュ分の作成・バインドを1回の Undo で戻せるようにまとめる。
	with undoChunk("createObbJointAndBindFromSelection"):
		try:
			for index, mesh_transform in enumerate(source_meshes):
				mlib.select(mesh_transform, replace=True)

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

				joint = mlib.createNode("joint", name=joint_name_i)

				# OBB の回転軸 + 中心位置でジョイント行列を直接組み立てる。
				joint.setMatrix(mlib.Matrix.fromAxes(axis_x, axis_y, axis_z, position=center), fast=True)
				# 回転を凍結して jointOrient 側へ焼き込み、扱いやすい状態にする。
				joint.makeIdentity(apply=True, t=False, r=True, s=True, n=False, pn=True)

				_bind_mesh_to_single_joint(mesh_transform, joint)
				created_joints.append(joint.getName())
				bound_meshes.append(mesh_transform.getName(full=True))

				# デバッグ用途が不要なら中間コリジョンは掃除する。
				if delete_collision and mlib.objExists(collision):
					mlib.delete(collision)
					deleted_collisions += 1
		finally:
			# 失敗時でも元の選択状態を戻す(空なら選択を解除する)。
			original_selection.select()

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
