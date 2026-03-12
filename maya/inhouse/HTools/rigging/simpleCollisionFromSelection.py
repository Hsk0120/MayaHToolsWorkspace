import math

import maya.cmds as cmds
import maya.api.OpenMaya as om


def _safe_normalize(vector, fallback):
	vec = om.MVector(vector)
	if vec.length() < 1e-10:
		return om.MVector(fallback)
	vec.normalize()
	return vec


def _selected_mesh_points_world():
	points = []
	selection = om.MGlobal.getActiveSelectionList()
	iterator = om.MItSelectionList(selection)

	while not iterator.isDone():
		try:
			dag_path, component = iterator.getComponent()
		except RuntimeError:
			dag_path = iterator.getDagPath()
			component = om.MObject.kNullObj

		if dag_path.apiType() == om.MFn.kTransform:
			dag_path.extendToShape()

		if dag_path.apiType() != om.MFn.kMesh:
			iterator.next()
			continue

		mesh_fn = om.MFnMesh(dag_path)

		if component and not component.isNull() and component.hasFn(om.MFn.kMeshVertComponent):
			comp_fn = om.MFnSingleIndexedComponent(component)
			mesh_points = mesh_fn.getPoints(om.MSpace.kWorld)
			for vertex_id in comp_fn.getElements():
				points.append(mesh_points[vertex_id])
		else:
			points.extend(mesh_fn.getPoints(om.MSpace.kWorld))

		iterator.next()

	return points


def _build_sample_directions(count=64):
	directions = [
		om.MVector(1.0, 0.0, 0.0),
		om.MVector(-1.0, 0.0, 0.0),
		om.MVector(0.0, 1.0, 0.0),
		om.MVector(0.0, -1.0, 0.0),
		om.MVector(0.0, 0.0, 1.0),
		om.MVector(0.0, 0.0, -1.0),
	]

	golden_angle = math.pi * (3.0 - math.sqrt(5.0))
	count = max(int(count), 8)

	for i in range(count):
		y = 1.0 - (2.0 * i) / (count - 1)
		radius = math.sqrt(max(0.0, 1.0 - y * y))
		theta = golden_angle * i
		x = math.cos(theta) * radius
		z = math.sin(theta) * radius
		directions.append(om.MVector(x, y, z))

	return directions


def _convex_hull_extreme_points(points, direction_count=64):
	if len(points) <= 8:
		return list(points)

	vectors = [om.MVector(point.x, point.y, point.z) for point in points]
	directions = _build_sample_directions(direction_count)
	hull_indices = set()

	for direction in directions:
		max_dot = float("-inf")
		min_dot = float("inf")
		max_index = -1
		min_index = -1

		for index, vector in enumerate(vectors):
			dot_value = vector * direction
			if dot_value > max_dot:
				max_dot = dot_value
				max_index = index
			if dot_value < min_dot:
				min_dot = dot_value
				min_index = index

		if max_index >= 0:
			hull_indices.add(max_index)
		if min_index >= 0:
			hull_indices.add(min_index)

	if len(hull_indices) < 4:
		return list(points)

	return [points[index] for index in sorted(hull_indices)]


def _refine_minor_axes_by_min_area(points, axis_x, axis_y, axis_z, steps=180):
	best_axis_y = axis_y
	best_axis_z = axis_z
	best_area = float("inf")

	steps = max(int(steps), 8)
	half_pi = math.pi * 0.5

	for i in range(steps):
		theta = (half_pi * i) / float(steps)
		cos_t = math.cos(theta)
		sin_t = math.sin(theta)

		candidate_y = _safe_normalize((axis_y * cos_t) + (axis_z * sin_t), axis_y)
		candidate_z = _safe_normalize((axis_z * cos_t) - (axis_y * sin_t), axis_z)

		min_y = float("inf")
		max_y = float("-inf")
		min_z = float("inf")
		max_z = float("-inf")

		for point in points:
			vec = om.MVector(point.x, point.y, point.z)
			py = vec * candidate_y
			pz = vec * candidate_z
			min_y = min(min_y, py)
			max_y = max(max_y, py)
			min_z = min(min_z, pz)
			max_z = max(max_z, pz)

		extent_y = max_y - min_y
		extent_z = max_z - min_z
		area = extent_y * extent_z

		if area < best_area:
			best_area = area
			best_axis_y = candidate_y
			best_axis_z = candidate_z

	return best_axis_y, best_axis_z


def _project_extents(points, axis_x, axis_y, axis_z):
	min_x = float("inf")
	min_y = float("inf")
	min_z = float("inf")
	max_x = float("-inf")
	max_y = float("-inf")
	max_z = float("-inf")

	for point in points:
		vec = om.MVector(point.x, point.y, point.z)
		px = vec * axis_x
		py = vec * axis_y
		pz = vec * axis_z

		min_x = min(min_x, px)
		min_y = min(min_y, py)
		min_z = min(min_z, pz)
		max_x = max(max_x, px)
		max_y = max(max_y, py)
		max_z = max(max_z, pz)

	return min_x, max_x, min_y, max_y, min_z, max_z


def _obb_volume(points, axis_x, axis_y, axis_z):
	min_x, max_x, min_y, max_y, min_z, max_z = _project_extents(points, axis_x, axis_y, axis_z)
	extent_x = max(max_x - min_x, 1e-6)
	extent_y = max(max_y - min_y, 1e-6)
	extent_z = max(max_z - min_z, 1e-6)
	return extent_x * extent_y * extent_z


def _rotate_basis(axis_x, axis_y, axis_z, rot_axis, angle_radians):
	quat = om.MQuaternion(angle_radians, rot_axis)
	new_x = _safe_normalize(axis_x.rotateBy(quat), axis_x)
	new_y = _safe_normalize(axis_y.rotateBy(quat), axis_y)
	new_z = _safe_normalize(axis_z.rotateBy(quat), axis_z)
	new_z = _safe_normalize(new_x ^ new_y, new_z)
	new_y = _safe_normalize(new_z ^ new_x, new_y)
	return new_x, new_y, new_z


def _refine_axes_by_volume_local_search(points, axis_x, axis_y, axis_z, initial_deg=10.0, min_deg=0.05, decay=0.5):
	current_x = axis_x
	current_y = axis_y
	current_z = axis_z
	best_volume = _obb_volume(points, current_x, current_y, current_z)

	step = math.radians(max(initial_deg, 0.1))
	min_step = math.radians(max(min_deg, 0.01))

	while step >= min_step:
		improved = False
		for rot_axis in (current_x, current_y, current_z):
			for direction in (-1.0, 1.0):
				candidate_x, candidate_y, candidate_z = _rotate_basis(
					current_x,
					current_y,
					current_z,
					rot_axis,
					step * direction,
				)
				candidate_volume = _obb_volume(points, candidate_x, candidate_y, candidate_z)
				if candidate_volume < best_volume:
					current_x, current_y, current_z = candidate_x, candidate_y, candidate_z
					best_volume = candidate_volume
					improved = True

		if not improved:
			step *= decay

	return current_x, current_y, current_z


def _covariance_matrix(points):
	count = float(len(points))
	centroid = om.MVector()
	for point in points:
		centroid += om.MVector(point.x, point.y, point.z)
	centroid /= count

	covariance = [[0.0, 0.0, 0.0],
				  [0.0, 0.0, 0.0],
				  [0.0, 0.0, 0.0]]

	for point in points:
		dx = point.x - centroid.x
		dy = point.y - centroid.y
		dz = point.z - centroid.z
		covariance[0][0] += dx * dx
		covariance[0][1] += dx * dy
		covariance[0][2] += dx * dz
		covariance[1][1] += dy * dy
		covariance[1][2] += dy * dz
		covariance[2][2] += dz * dz

	inv_count = 1.0 / count
	covariance[0][0] *= inv_count
	covariance[0][1] *= inv_count
	covariance[0][2] *= inv_count
	covariance[1][1] *= inv_count
	covariance[1][2] *= inv_count
	covariance[2][2] *= inv_count

	covariance[1][0] = covariance[0][1]
	covariance[2][0] = covariance[0][2]
	covariance[2][1] = covariance[1][2]

	return covariance


def _jacobi_eigen_decomposition_3x3(matrix, max_iter=32, epsilon=1e-10):
	a = [row[:] for row in matrix]
	v = [[1.0, 0.0, 0.0],
		 [0.0, 1.0, 0.0],
		 [0.0, 0.0, 1.0]]

	for _ in range(max_iter):
		p = 0
		q = 1
		max_val = abs(a[0][1])
		for i in range(3):
			for j in range(i + 1, 3):
				value = abs(a[i][j])
				if value > max_val:
					max_val = value
					p = i
					q = j

		if max_val < epsilon:
			break

		app = a[p][p]
		aqq = a[q][q]
		apq = a[p][q]

		if abs(apq) < epsilon:
			continue

		tau = (aqq - app) / (2.0 * apq)
		t = math.copysign(1.0, tau) / (abs(tau) + math.sqrt(1.0 + tau * tau))
		c = 1.0 / math.sqrt(1.0 + t * t)
		s = t * c

		for k in range(3):
			if k == p or k == q:
				continue
			aik = a[k][p]
			akq = a[k][q]
			a[k][p] = c * aik - s * akq
			a[p][k] = a[k][p]
			a[k][q] = s * aik + c * akq
			a[q][k] = a[k][q]

		a[p][p] = c * c * app - 2.0 * s * c * apq + s * s * aqq
		a[q][q] = s * s * app + 2.0 * s * c * apq + c * c * aqq
		a[p][q] = 0.0
		a[q][p] = 0.0

		for k in range(3):
			vip = v[k][p]
			viq = v[k][q]
			v[k][p] = c * vip - s * viq
			v[k][q] = s * vip + c * viq

	eigenvalues = [a[0][0], a[1][1], a[2][2]]
	eigenvectors = [
		om.MVector(v[0][0], v[1][0], v[2][0]),
		om.MVector(v[0][1], v[1][1], v[2][1]),
		om.MVector(v[0][2], v[1][2], v[2][2]),
	]
	return eigenvalues, eigenvectors


def _compute_obb_from_points(points):
	covariance = _covariance_matrix(points)
	eigenvalues, eigenvectors = _jacobi_eigen_decomposition_3x3(covariance)

	order = sorted(range(3), key=lambda i: eigenvalues[i], reverse=True)
	axis_x = _safe_normalize(eigenvectors[order[0]], om.MVector.kXaxisVector)
	axis_y = _safe_normalize(eigenvectors[order[1]], om.MVector.kYaxisVector)

	axis_z = axis_x ^ axis_y
	axis_z = _safe_normalize(axis_z, om.MVector.kZaxisVector)
	axis_y = _safe_normalize(axis_z ^ axis_x, om.MVector.kYaxisVector)

	# minor axes が近接する形状（正方断面など）での回転不安定を抑える
	axis_y, axis_z = _refine_minor_axes_by_min_area(points, axis_x, axis_y, axis_z, steps=180)

	# PCA 初期解から体積最小方向へ局所探索して、フィット精度を上げる
	axis_x, axis_y, axis_z = _refine_axes_by_volume_local_search(points, axis_x, axis_y, axis_z)

	min_x, max_x, min_y, max_y, min_z, max_z = _project_extents(points, axis_x, axis_y, axis_z)

	center_x = (min_x + max_x) * 0.5
	center_y = (min_y + max_y) * 0.5
	center_z = (min_z + max_z) * 0.5

	center = (axis_x * center_x) + (axis_y * center_y) + (axis_z * center_z)
	size_x = max(max_x - min_x, 1e-6)
	size_y = max(max_y - min_y, 1e-6)
	size_z = max(max_z - min_z, 1e-6)

	return {
		"center": center,
		"axes": (axis_x, axis_y, axis_z),
		"size": (size_x, size_y, size_z),
	}


def create_obb_collision_from_selection(name="obbCollision_geo", use_hull_points=True, hull_direction_count=64, return_obb_data=False):
	points = _selected_mesh_points_world()
	if len(points) < 3:
		om.MGlobal.displayError("Select mesh object or mesh vertices (3 points minimum).")
		return None

	obb_points = points
	if use_hull_points:
		obb_points = _convex_hull_extreme_points(points, direction_count=hull_direction_count)
		if len(obb_points) < 3:
			obb_points = points

	obb = _compute_obb_from_points(obb_points)
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
