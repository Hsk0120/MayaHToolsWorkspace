"""点群の主成分分析と局所探索による有向境界ボックスの近似。"""

import math

import maya.api.OpenMaya as om

from ..maths import Vector


def _safe_normalize(vector, fallback):
    """ベクトルを安全に正規化します。

    Args:
        vector (maya.api.OpenMaya.MVector): 入力ベクトル。
        fallback (maya.api.OpenMaya.MVector): 長さゼロ時の代替ベクトル。

    Returns:
        maya.api.OpenMaya.MVector: 正規化ベクトル。
    """
    vec = om.MVector(vector)
    if vec.length() < 1e-10:
        return om.MVector(fallback)
    vec.normalize()
    return vec


def _build_sample_directions(count=64):
    """凸包近似用の方向ベクトル群を生成します。

    Args:
        count (int): 球面サンプル方向数。

    Returns:
        list[maya.api.OpenMaya.MVector]: サンプル方向一覧。
    """
    directions = [
        om.MVector(1.0, 0.0, 0.0),
        om.MVector(-1.0, 0.0, 0.0),
        om.MVector(0.0, 1.0, 0.0),
        om.MVector(0.0, -1.0, 0.0),
        om.MVector(0.0, 0.0, 1.0),
        om.MVector(0.0, 0.0, -1.0),
    ]

    # Fibonacci sphere に近い分布で方向サンプルを生成する。
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


def sampleExtremePoints(points, direction_count=64):
    """方向サンプルに対する極値点集合を抽出します。

    Args:
        points (list[maya.api.OpenMaya.MPoint]): 入力ポイント群。
        direction_count (int): 方向サンプル数。

    Returns:
        list[maya.api.OpenMaya.MPoint]: OBB 推定に使う代表点集合。
    """
    if len(points) <= 8:
        return list(points)

    vectors = [om.MVector(point.x, point.y, point.z) for point in points]
    directions = _build_sample_directions(direction_count)
    hull_indices = set()

    # 各方向の最大/最小投影点を拾い、外形を近似する。
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
    """主軸固定で YZ 面回転を走査し断面面積最小の副軸を選びます。

    Args:
        points: 計算対象の座標列。
        axis_x: 対象座標系の各基底ベクトル。
        axis_y: 対象座標系の各基底ベクトル。
        axis_z: 対象座標系の各基底ベクトル。
        steps: 角度探索を分割する試行数。
    """
    best_axis_y = axis_y
    best_axis_z = axis_z
    best_area = float("inf")

    steps = max(int(steps), 8)
    half_pi = math.pi * 0.5

    # minor 軸平面内を走査し、投影矩形面積が最小の向きを選択する。
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
    """指定基底へ投影した各軸の最小最大値を返します。

    Args:
        points: 計算対象の座標列。
        axis_x: 対象座標系の各基底ベクトル。
        axis_y: 対象座標系の各基底ベクトル。
        axis_z: 対象座標系の各基底ベクトル。
    """
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
    """基底に対する OBB 体積を計算します。

    Args:
        points: 計算対象の座標列。
        axis_x: 対象座標系の各基底ベクトル。
        axis_y: 対象座標系の各基底ベクトル。
        axis_z: 対象座標系の各基底ベクトル。
    """
    min_x, max_x, min_y, max_y, min_z, max_z = _project_extents(points, axis_x, axis_y, axis_z)
    extent_x = max(max_x - min_x, 1e-6)
    extent_y = max(max_y - min_y, 1e-6)
    extent_z = max(max_z - min_z, 1e-6)
    return extent_x * extent_y * extent_z


def _rotate_basis(axis_x, axis_y, axis_z, rot_axis, angle_radians):
    """基底を任意軸回転し、再直交化した基底を返します。

    Args:
        axis_x: 対象座標系の各基底ベクトル。
        axis_y: 対象座標系の各基底ベクトル。
        axis_z: 対象座標系の各基底ベクトル。
        rot_axis: 基底を回転させる軸ベクトル。
        angle_radians: 回転・配置の角度。radians指定はラジアン。
    """
    quat = om.MQuaternion(angle_radians, rot_axis)
    new_x = _safe_normalize(axis_x.rotateBy(quat), axis_x)
    new_y = _safe_normalize(axis_y.rotateBy(quat), axis_y)
    new_z = _safe_normalize(axis_z.rotateBy(quat), axis_z)
    new_z = _safe_normalize(new_x ^ new_y, new_z)
    new_y = _safe_normalize(new_z ^ new_x, new_y)
    return new_x, new_y, new_z


def _refine_axes_by_volume_local_search(points, axis_x, axis_y, axis_z, initial_deg=10.0, min_deg=0.05, decay=0.5):
    """局所探索で OBB 体積が小さくなる軸向きを探索します。

    Args:
        points: 計算対象の座標列。
        axis_x: 対象座標系の各基底ベクトル。
        axis_y: 対象座標系の各基底ベクトル。
        axis_z: 対象座標系の各基底ベクトル。
        initial_deg: 局所探索の初期角度刻みまたは最小刻み。単位は度。
        min_deg: 局所探索の初期角度刻みまたは最小刻み。単位は度。
        decay: 反復ごとに探索刻みを縮小する係数。
    """
    current_x = axis_x
    current_y = axis_y
    current_z = axis_z
    best_volume = _obb_volume(points, current_x, current_y, current_z)

    step = math.radians(max(initial_deg, 0.1))
    min_step = math.radians(max(min_deg, 0.01))

    # 3 軸まわりの微小回転を繰り返し、改善が止まったらステップを縮小する。
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
    """ポイント群の共分散行列を計算します。

    Args:
        points: 計算対象の座標列。
    """
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
    """3x3 対称行列の固有値/固有ベクトルを Jacobi 法で求めます。

    Args:
        matrix: 変換または数値計算に使う行列。
        max_iter: 反復計算の最大回数。
        epsilon: ゼロ判定・収束判定の許容誤差。
    """
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


def computeOrientedBounds(points):
    """ポイント群から OBB の中心・軸・サイズを推定します。

    Args:
        points (Iterable[MPoint | Sequence[float]]): 入力ポイント群。

    Returns:
        dict[str, object]: centerはVector、axesは3本のVector、sizeは3成分tuple。
        入力と同じ空間・距離単位。最小サイズは1e-6。最小体積の厳密解は保証しない。

    Raises:
        ValueError: 3点未満、または有限でない座標。
    """
    points = [om.MPoint(point) for point in points]
    if len(points) < 3 or any(not math.isfinite(value) for point in points for value in (point.x, point.y, point.z)):
        raise ValueError("有限座標の点を3点以上指定してください。")
    covariance = _covariance_matrix(points)
    eigenvalues, eigenvectors = _jacobi_eigen_decomposition_3x3(covariance)

    # 最大固有値方向を長軸候補として採用する。
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
        "center": Vector(center),
        "axes": (Vector(axis_x), Vector(axis_y), Vector(axis_z)),
        "size": (size_x, size_y, size_z),
    }

