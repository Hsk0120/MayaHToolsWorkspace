"""選択メッシュから OBB コリジョンを生成するユーティリティ。"""


import maya.cmds as cmds
import maya.api.OpenMaya as om

from hlib.utils.orientedBounds import computeOrientedBounds, sampleExtremePoints
from hlib.nodes import Mesh


def _selected_mesh_points_world():
	"""現在選択からメッシュ頂点座標（ワールド）を収集します。

	Returns:
		list[maya.api.OpenMaya.MPoint]: 対象ポイント一覧。
	"""
	points = []
	selection = om.MGlobal.getActiveSelectionList()
	iterator = om.MItSelectionList(selection)

	while not iterator.isDone():
		try:
			dag_path, component = iterator.getComponent()
		except RuntimeError:
			dag_path = iterator.getDagPath()
			component = om.MObject.kNullObj

		# Transform が選択されている場合は shape まで降りる。
		if dag_path.apiType() == om.MFn.kTransform:
			dag_path.extendToShape()

		if dag_path.apiType() != om.MFn.kMesh:
			iterator.next()
			continue

		mesh = Mesh(dag_path)

		# 頂点コンポーネント選択時は選択頂点のみを収集する。
		if component and not component.isNull() and component.hasFn(om.MFn.kMeshVertComponent):
			comp_fn = om.MFnSingleIndexedComponent(component)
			mesh_points = mesh.getPoints(ws=True)
			for vertex_id in comp_fn.getElements():
				points.append(om.MPoint(mesh_points[vertex_id]))
		else:
			points.extend(om.MPoint(point) for point in mesh.getPoints(ws=True))

		iterator.next()

	return points


def create_obb_collision_from_selection(name="obbCollision_geo", use_hull_points=True, hull_direction_count=64, return_obb_data=False):
	"""選択から OBB コリジョンメッシュを生成します。

	Args:
		name (str): 生成するコリジョン名。
		use_hull_points (bool): 極値点近似を使うか。
		hull_direction_count (int): 極値抽出の方向サンプル数。
		return_obb_data (bool): OBB 計算結果を辞書で返すか。

	Returns:
		str | dict[str, object] | None: 通常は生成コリジョン名。
		return_obb_data=True 時は OBB 情報辞書。
	"""
	points = _selected_mesh_points_world()
	if len(points) < 3:
		om.MGlobal.displayError("Select mesh object or mesh vertices (3 points minimum).")
		return None

	# 高密度メッシュでは極値点近似を使い、計算量を抑えつつ形状を保持する。
	obb_points = points
	if use_hull_points:
		obb_points = sampleExtremePoints(points, direction_count=hull_direction_count)
		if len(obb_points) < 3:
			obb_points = points

	obb = computeOrientedBounds(obb_points)
	center = obb["center"]
	axis_x, axis_y, axis_z = obb["axes"]
	size_x, size_y, size_z = obb["size"]

	cube_result = cmds.polyCube(
		name=name,
		width=1.0,
		height=1.0,
		depth=1.0,
		constructionHistory=False,
	)
	cube_transform = cube_result[0] if isinstance(cube_result, (list, tuple)) else cube_result
	if not cube_transform:
		om.MGlobal.displayError("Failed to create polyCube for OBB collision.")
		return None

	# 軸方向にサイズを掛けた行列を構築し、位置を中心に合わせる。
	matrix = om.MMatrix([
		axis_x.x * size_x, axis_x.y * size_x, axis_x.z * size_x, 0.0,
		axis_y.x * size_y, axis_y.y * size_y, axis_y.z * size_y, 0.0,
		axis_z.x * size_z, axis_z.y * size_z, axis_z.z * size_z, 0.0,
		center.x, center.y, center.z, 1.0,
	])

	selection = om.MSelectionList()
	selection.add(cube_transform)
	cube_dag = selection.getDagPath(0)
	transform_fn = om.MFnTransform(cube_dag)
	transform_fn.setTransformation(om.MTransformationMatrix(matrix))

	# Keep transform orientation from OBB so pivot orientation follows the collision box.
	# Explicitly place rotate/scale pivots at the OBB center in world space.
	cmds.xform(
		cube_transform,
		worldSpace=True,
		pivots=(center.x, center.y, center.z),
	)

	om.MGlobal.displayInfo(
		"Created OBB collision: {0} (size: {1:.3f}, {2:.3f}, {3:.3f}, points: {4}/{5})".format(
			cube_transform,
			size_x,
			size_y,
			size_z,
			len(obb_points),
			len(points),
		)
	)
	if return_obb_data:
		return {
			"collision": cube_transform,
			"center": center,
			"axes": (axis_x, axis_y, axis_z),
			"size": (size_x, size_y, size_z),
			"obb_points_count": len(obb_points),
			"source_points_count": len(points),
		}
	return cube_transform
if __name__ == "__main__":
	create_obb_collision_from_selection()
