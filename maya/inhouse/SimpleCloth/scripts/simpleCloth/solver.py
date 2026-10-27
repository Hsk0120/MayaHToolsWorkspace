"""Mayaシーンへアクセスしない、独立した粒子ベースXPBD布計算。

距離の単位はcm、時刻は秒。曲げは隣接三角形の対向頂点間スプリングで
近似する。UEの実装・バイナリは使用しない。
"""

import itertools
import math

from maya.api import OpenMaya as om


def build_constraints(points, triangles):
    """三角形の辺と隣接面の対向頂点から静止距離と近接除外を作る。"""
    edges = {}
    for a, b, c in triangles:
        if ((points[b] - points[a]) ^ (points[c] - points[a])).length() <= 1.0e-10:
            raise ValueError("Simple Cloth: 面積0の三角形を除去してください")
        for i, j, opposite in ((a, b, c), (b, c, a), (c, a, b)):
            edges.setdefault(tuple(sorted((i, j))), []).append(opposite)
    if any(len(values) > 2 for values in edges.values()):
        raise ValueError("Simple Cloth: 非多様体の辺は使用できません")
    stretch = [(i, j, (points[i] - points[j]).length()) for i, j in sorted(edges)]
    bend_pairs = {tuple(sorted(values)) for values in edges.values() if len(values) == 2}
    bend = [(i, j, (points[i] - points[j]).length()) for i, j in sorted(bend_pairs) if i != j]
    if any(length <= 1.0e-8 for _, _, length in stretch):
        raise ValueError("Simple Cloth: 長さ0の辺を除去してください")
    return stretch, bend, set(edges) | bend_pairs


def _distance(points, inverse_mass, constraints, compliance, dt, multipliers):
    """XPBDの距離拘束をGauss-Seidel順で解く。λは各ステップ内で保持する。"""
    alpha = compliance / (dt * dt)
    for index, (i, j, rest) in enumerate(constraints):
        wi, wj = inverse_mass[i], inverse_mass[j]
        delta = points[i] - points[j]
        length = delta.length()
        if wi + wj <= 0 or length < 1.0e-10:
            continue
        change = (-(length - rest) - alpha * multipliers[index]) / (wi + wj + alpha)
        multipliers[index] += change
        correction = delta * (change / length)
        points[i] += correction * wi
        points[j] -= correction * wj


def project_collider(point, collider, thickness):
    """球・Y軸カプセル・ローカル+Y半空間の外へ点を投影する。"""
    matrix, kind, radius, height = collider
    transform = om.MTransformationMatrix(matrix)
    scale = transform.scale(om.MSpace.kTransform)[0]
    local = om.MPoint(point) * matrix.inverse()
    padding = thickness / scale
    if kind == 2:
        local.y = max(local.y, padding)
    else:
        center = om.MVector(0, max(-height * 0.5, min(height * 0.5, local.y)), 0) if kind == 1 else om.MVector()
        delta = om.MVector(local) - center
        length = delta.length()
        if length < radius + padding:
            direction = delta / length if length > 1.0e-10 else om.MVector(1, 0, 0)
            local = om.MPoint(center + direction * (radius + padding))
    return om.MVector(local * matrix)


def _self_collide(points, inverse_mass, excluded, diameter):
    """空間ハッシュで近傍粒子だけを探索する。辺・面の連続衝突ではない。"""
    if diameter <= 0:
        return
    grid = {}
    for i, point in enumerate(points):
        cell = tuple(math.floor(value / diameter) for value in point)
        for offset in itertools.product((-1, 0, 1), repeat=3):
            key = tuple(value + step for value, step in zip(cell, offset))
            for j in grid.get(key, ()):
                if (j, i) in excluded:
                    continue
                mass = inverse_mass[i] + inverse_mass[j]
                delta = points[i] - points[j]
                length = delta.length()
                if mass > 0 and length < diameter:
                    direction = delta / length if length > 1.0e-10 else om.MVector(0, 1, 0)
                    correction = direction * ((diameter - length) / mass)
                    points[i] += correction * inverse_mass[i]
                    points[j] -= correction * inverse_mass[j]
        grid.setdefault(cell, []).append(i)


def _limits(points, targets, normals, weights, settings):
    """Max Distance球・Backstop球・固定頂点を適用する。固定を最優先する。"""
    for index, target in enumerate(targets):
        limit = settings["maxDistance"] * weights[index]
        if limit <= 1.0e-9:
            points[index] = om.MVector(target)
            continue
        radius = settings["backstopRadius"]
        if radius > 0:
            center = target - normals[index] * (radius + settings["backstopDistance"])
            delta = points[index] - center
            length = delta.length()
            if length < radius:
                direction = delta / length if length > 1.0e-10 else normals[index]
                points[index] = center + direction * radius
        delta = points[index] - target
        length = delta.length()
        if length > limit:
            points[index] = target + delta * (limit / length)


def step(state, targets, normals, weights, constraints, colliders, settings, dt):
    """1ステップ進め、新しい位置と速度を返す。入力stateは変更しない。"""
    old_points, velocities = state
    decay = math.exp(-settings["damping"] * dt)
    acceleration = om.MVector(settings["gravity"]) + om.MVector(settings["wind"])
    points = [point + velocity * (decay * dt) + acceleration * (dt * dt)
              for point, velocity in zip(old_points, velocities)]
    inverse_mass = [1.0 / settings["particleMass"] if weight * settings["maxDistance"] > 1.0e-9 else 0.0
                    for weight in weights]
    drive = 1 - math.exp(-settings["animDrive"] * dt)
    for index, target in enumerate(targets):
        points[index] += (target - points[index]) * drive
    stretch, bend, excluded = constraints
    stretch_lambda = [0.0] * len(stretch)
    bend_lambda = [0.0] * len(bend)
    contacts = set()
    _limits(points, targets, normals, weights, settings)
    for _ in range(settings["iterations"]):
        _distance(points, inverse_mass, stretch, settings["stretchCompliance"], dt, stretch_lambda)
        _distance(points, inverse_mass, bend, settings["bendCompliance"], dt, bend_lambda)
        if settings["selfCollision"]:
            _self_collide(points, inverse_mass, excluded, settings["selfCollisionThickness"] * 2)
        for index, point in enumerate(points):
            if inverse_mass[index] == 0:
                continue
            for collider in colliders:
                projected = project_collider(point, collider, settings["collisionThickness"])
                if (projected - point).length() > 1.0e-9:
                    contacts.add(index)
                    point = projected
            points[index] = point
        _limits(points, targets, normals, weights, settings)
    velocities = [(point - old) / dt for point, old in zip(points, old_points)]
    for index in contacts:
        velocities[index] *= 1 - settings["friction"]
    return points, velocities


def diagnostics(points, targets, weights, constraints, colliders, settings):
    """収束残差を返す。固定とコリジョン等の競合を隠さない。"""
    stretch_error = max((abs((points[i] - points[j]).length() / length - 1)
                         for i, j, length in constraints[0]), default=0.0)
    penetration = max(((project_collider(point, collider, settings["collisionThickness"]) - point).length()
                       for point in points for collider in colliders), default=0.0)
    max_error = max(((point - target).length() - settings["maxDistance"] * weight
                     for point, target, weight in zip(points, targets, weights)), default=0.0)
    return stretch_error, penetration, max(0.0, max_error)
