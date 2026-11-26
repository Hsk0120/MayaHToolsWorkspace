"""KawaiiPhysicsを参考にした位置ベースのボーン計算。

上流: pafuhana1213/KawaiiPhysics, feee5fe7272 (MIT)。NOTICE.md参照。
Mayaシーンの読み書きは行わず、所有する位置配列だけを更新する。
距離はcm、時間は秒、角度制限は度。
"""

import math

from mlib.maths import Matrix, Quaternion, Transformation, Vector


EPSILON = 1.0e-9
PARAMETERS = ("damping", "stiffness", "worldDampingLocation", "worldDampingRotation", "radius", "limitAngle")


def position(matrix):
    """マトリクスの移動成分を独立したベクトルで返す。"""
    return Vector(matrix[12], matrix[13], matrix[14])


def direction(vector, fallback=None):
    """ゼロ長の場合に代替方向を使用する単位ベクトルを返す。"""
    if vector.length() > EPSILON:
        return vector.normal()
    return Vector(fallback if fallback is not None else (1, 0, 0)).normal()


def copy_state(state):
    """キャッシュの所有権を分離するため位置と前回位置をコピーする。"""
    return tuple([Vector(value) for value in values] for values in state)


def initial_state(poses):
    """アニメーション姿勢から速度ゼロの状態を作る。"""
    points = [position(matrix) for matrix in poses]
    return points, [Vector(value) for value in points]


def _project_collision(point, radius, collider):
    """球・Y軸カプセル・+Y平面から点を押し出す。"""
    matrix, kind, size, height = collider
    center = position(matrix)
    axis = direction(Vector(0, 1, 0) * matrix)
    scale = Vector(matrix[0], matrix[1], matrix[2]).length()
    size *= scale
    height *= scale
    if kind == 2:
        distance = (point - center) * axis
        return point + axis * max(0.0, radius - distance)
    if kind == 1:
        along = max(-height * 0.5, min(height * 0.5, (point - center) * axis))
        center += axis * along
    delta = point - center
    combined = radius + size
    if delta.length() < combined:
        fallback = direction(Vector(1, 0, 0) * matrix)
        return center + direction(delta, fallback) * combined
    return point


def collision_diagnostics(points, radii, colliders, parents):
    """固定根元以外の最大めり込み量(cm)と、外部衝突面まで1e-5cm以内の粒子数を返す。"""
    tolerance = 1e-5
    maximum = 0.0
    contacts = 0
    for point, radius, parent in zip(points, radii, parents):
        if parent < 0:
            continue
        depth = max(((_project_collision(point, radius + tolerance, collider) - point).length()
                     for collider in colliders), default=0.0)
        contacts += depth > 1e-10
        maximum = max(maximum, depth - tolerance)
    return maximum, contacts


def penetration(points, radii, colliders, parents):
    """固定根元を除いた最大めり込み量をcmで返す。"""
    return collision_diagnostics(points, radii, colliders, parents)[0]


def _restore(points, pose_points, poses, parents, settings, planar):
    """親子長を保ち、ポーズ基準の角度・平面制限を適用する。"""
    for index, parent in enumerate(parents):
        if parent < 0:
            points[index] = Vector(pose_points[index])
            continue
        reference = pose_points[index] - pose_points[parent]
        length = reference.length()
        current = direction(points[index] - points[parent], reference)
        if planar:
            normal = direction(Vector(*(1 if axis == planar - 1 else 0 for axis in range(3))) * poses[parent])
            current = direction(current - normal * (current * normal), reference)
        angle = settings[index]["limitAngle"]
        if angle > 0 and length > EPSILON:
            rest = reference.normal()
            difference = rest.angle(current)
            limit = math.radians(angle)
            if difference > limit:
                rotation = rest.rotateTo(current)
                current = rest.rotateBy(Quaternion().slerp(rotation, limit / difference))
        points[index] = points[parent] + current * length


def _distance_constraints(points, parents, constraints, dt, count):
    """逆質量0の根元を固定したXPBD距離拘束を反復する。"""
    lambdas = [0.0] * len(constraints)
    for _ in range(count):
        for index, (first, second, length, compliance) in enumerate(constraints):
            delta = points[second] - points[first]
            distance = delta.length()
            weight_a = float(parents[first] >= 0)
            weight_b = float(parents[second] >= 0)
            alpha = compliance / (dt * dt)
            denominator = weight_a + weight_b + alpha
            if distance <= EPSILON or denominator <= EPSILON:
                continue
            change = (distance - length - alpha * lambdas[index]) / denominator
            correction = delta * (change / distance)
            points[first] += correction * weight_a
            points[second] -= correction * weight_b
            lambdas[index] += change


def step(state, previous_poses, poses, parents, settings, colliders, constraints, options, dt):
    """固定時間の1ステップを実行し、独立した次の状態を返す。

    Args:
        state: 位置と前回位置の配列。
        previous_poses: 前ステップの入力ワールドマトリクス。
        poses: 現ステップの入力ワールドマトリクス。
        parents: 親番号。根元は-1、親は子より先。
        settings: ボーン別の係数。
        colliders: マトリクス・形状番号・半径・円柱部長の配列。
        constraints: 両端番号・自然長・complianceの配列。
        options: 重力、風、反復、平面指定など。
        dt: 秒。正の値。

    Returns:
        tuple: 次の位置と前回位置。
    """
    points, previous = copy_state(state)
    pose_points = [position(matrix) for matrix in poses]
    roots = []
    for index, parent in enumerate(parents):
        roots.append(index if parent < 0 else roots[parent])
    for index, parent in enumerate(parents):
        if parent < 0:
            previous[index] = Vector(points[index])
            points[index] = Vector(pose_points[index])
            continue
        params = settings[index]
        root = roots[index]
        old_root = position(previous_poses[root])
        new_root = pose_points[root]
        old_rotation = Matrix(previous_poses[root]).quaternion
        new_rotation = Matrix(poses[root]).quaternion
        rotation = old_rotation.inverse() * new_rotation
        old_point = Vector(points[index])
        # 過去位置から再構成した速度へ減衰を適用。非整数時刻の末尾dtにも正規化する。
        damping = (1.0 - params["damping"]) ** (options["targetFramerate"] * dt)
        velocity = (points[index] - previous[index]) / options["previousDt"] * damping
        points[index] += velocity * dt + Vector(options["gravity"]) * dt * dt
        points[index] += Vector(options["wind"]) * dt
        points[index] += (new_root - old_root) * (1.0 - params["worldDampingLocation"])
        relative = old_point - old_root
        points[index] += (relative.rotateBy(rotation) - relative) * (1.0 - params["worldDampingRotation"])
        target = points[parent] + pose_points[index] - pose_points[parent]
        strength = 1.0 - (1.0 - params["stiffness"]) ** (options["targetFramerate"] * dt)
        points[index] += (target - points[index]) * strength
        previous[index] = old_point
    _distance_constraints(points, parents, constraints, dt, options["iterationsBefore"])
    # 最後に長さを復元するため、拘束が両立しない場合の残留貫通は別出力で通知する。
    for _ in range(options["collisionIterations"]):
        for index, parent in enumerate(parents):
            if parent >= 0:
                for collider in colliders:
                    points[index] = _project_collision(points[index], settings[index]["radius"], collider)
        _restore(points, pose_points, poses, parents, settings, options["planarConstraint"])
    _distance_constraints(points, parents, constraints, dt, options["iterationsAfter"])
    _restore(points, pose_points, poses, parents, settings, options["planarConstraint"])
    return points, previous


def output_matrices(poses, points, parents, blend):
    """ポーズの捻りを保持し、揺れた子の方向へ向けたローカルマトリクスを返す。"""
    children = [[] for _ in parents]
    for index, parent in enumerate(parents):
        if parent >= 0:
            children[parent].append(index)
    worlds = []
    for index, pose in enumerate(poses):
        transform = Transformation(pose)
        rotation = transform.quaternion
        if children[index]:
            # 分岐では最初の子を回転基準とし、他の枝の位置は個別の長さ拘束で維持する。
            child = children[index][0]
            original = position(poses[child]) - position(pose)
            simulated = points[child] - points[index]
            if original.length() > EPSILON and simulated.length() > EPSILON:
                correction = original.rotateTo(simulated)
                rotation = rotation * Quaternion().slerp(correction, blend)
        transform.quaternion = rotation
        transform.translate = position(pose) * (1.0 - blend) + points[index] * blend
        worlds.append(transform.matrix)
    return [world if parents[index] < 0 else world * worlds[parents[index]].inverse() for index, world in enumerate(worlds)]
