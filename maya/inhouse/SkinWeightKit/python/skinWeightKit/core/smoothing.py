"""ウェイトのスムーズの計算(隣の頂点への重みの付け方と、ロック・最大数を守った1回の平滑化)。

ツールによってスムーズの考え方が違うため、重みの付け方を選べるようにする。

- ``uniform``: 辺でつながった隣の頂点の単純な平均(Maya の Smooth Skin Weights や、隣の頂点へブレンドする方式)。
- ``distance``: 辺の長さの逆数で重み付けする(細かく分割された側に引っ張られにくい)。
- ``cotangent``: 三角形の角度から求めるコタンジェントの重み(メッシュの形に沿った平滑化。三角形の歪みに強い)。

``radius`` を指定すると、辺でつながっていなくても半径内にある頂点も平均に含める(指の間・重なったパーツ・
別のシェルの間でもウェイトがなじむ)。
"""

import math

from . import weights as weights_module

#: 重みの付け方の名前。
METHODS = ("uniform", "distance", "cotangent")

#: コタンジェントの重みの下限(鈍角の三角形で負になるのを防ぐ)。
MIN_COTANGENT = 1e-3


def _cotangent_weights(mesh, points):
    """辺ごとのコタンジェントの重みを {(小さい番号, 大きい番号): 重み} で返す。"""
    result = {}
    for triangle in mesh.getTriangles():

        for corner in range(3):
            a, b, c = triangle[corner], triangle[(corner + 1) % 3], triangle[(corner + 2) % 3]
            # 頂点 c の角は、辺 a-b の向かいの角。
            u = [points[a][axis] - points[c][axis] for axis in range(3)]
            v = [points[b][axis] - points[c][axis] for axis in range(3)]
            dot = sum(u[axis] * v[axis] for axis in range(3))
            cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            length = math.sqrt(sum(value * value for value in cross))
            if length <= 1e-12:
                continue
            key = (a, b) if a < b else (b, a)
            result[key] = result.get(key, 0.0) + 0.5 * dot / length
    return result


def _gap_links(points, radius, existing):
    """半径内にある、辺でつながっていない頂点を {頂点: [(相手, 距離)]} で返す。"""
    size = radius
    grid = {}
    for index, point in enumerate(points):
        grid.setdefault(tuple(int(math.floor(value / size)) for value in point), []).append(index)
    links = {}
    for index, point in enumerate(points):
        base = tuple(int(math.floor(value / size)) for value in point)
        found = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for other in grid.get((base[0] + dx, base[1] + dy, base[2] + dz), ()):
                        if other == index or other in existing[index]:
                            continue
                        distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(points[other], point)))
                        if distance <= radius:
                            found.append((other, distance))
        if found:
            links[index] = found
    return links


def neighborWeights(mesh, method="uniform", radius=0.0):
    """頂点ごとの隣の頂点と、合計1の重みを返す。

    Args:
        mesh (mlib.Mesh): メッシュ。
        method (str): :data:`METHODS` の名前。
        radius (float): 0より大きければ、辺でつながっていなくても半径内(cm、ワールド空間)の頂点も含める。

    Returns:
        list[list[tuple[int, float]]]: 頂点ごとの (隣の頂点, 重み)。重みの合計は1(隣が無ければ空)。

    Raises:
        ValueError: method が不正、または radius が負の場合。
    """
    if method not in METHODS:
        raise ValueError("method must be one of " + ", ".join(METHODS))
    if radius < 0:
        raise ValueError("radius must be 0 or more")
    adjacency = mesh.getVertexAdjacency(worldSpace=True)
    points = None
    if method == "cotangent" or radius > 0:
        points = [(point.x, point.y, point.z) for point in mesh.getPoints(worldSpace=True)]
    cotangents = _cotangent_weights(mesh, points) if method == "cotangent" else {}
    result = []
    existing = []
    for vertex, neighbors in enumerate(adjacency):
        weighted = {}
        for neighbor, length in neighbors:
            if neighbor == vertex:
                continue
            if method == "uniform":
                weight = 1.0
            elif method == "distance":
                weight = 1.0 / max(length, 1e-6)
            else:
                key = (vertex, neighbor) if vertex < neighbor else (neighbor, vertex)
                weight = max(MIN_COTANGENT, cotangents.get(key, 1.0))
            weighted[neighbor] = weighted.get(neighbor, 0.0) + weight
        result.append(weighted)
        existing.append(set(weighted))
    if radius > 0:
        for vertex, links in _gap_links(points, radius, existing).items():
            base = (sum(result[vertex].values()) / len(result[vertex])) if result[vertex] else 1.0
            for other, distance in links:
                # 近いほど強く、半径の端で0になるようにする。
                result[vertex][other] = result[vertex].get(other, 0.0) + base * (1.0 - distance / radius)
    normalized = []
    for weighted in result:
        total = sum(weighted.values())
        normalized.append([(neighbor, weight / total) for neighbor, weight in weighted.items()] if total > 0 else [])
    return normalized


def limitRow(row, locked, maxInfluences):
    """ロックしていない値のうち大きい順に、ロックを含めて最大数までを残した行を返す(合計は戻さない)。

    Args:
        row (list[float]): 行。
        locked (list[bool]): 列ごとのロック。
        maxInfluences (int | None): 最大数。Noneは制限しない。

    Returns:
        list[float]: 制限した行。
    """
    if not maxInfluences:
        return list(row)
    locked_used = sum(1 for index, value in enumerate(row) if locked[index] and value > 0.0)
    allowed = max(1, maxInfluences - locked_used)
    free = sorted((index for index in range(len(row)) if not locked[index] and row[index] > 0.0),
                  key=lambda index: -row[index])
    kept = set(free[:allowed])
    return [value if locked[index] or index in kept else 0.0 for index, value in enumerate(row)]


def smoothRow(row, neighbor_rows, strength, locked, maxInfluences=None):
    """1頂点の行を、隣の行の重み付き平均へ strength だけ近づけた行を返す(ロックを保ち合計1)。

    strength が負なら隣の平均から遠ざける(くっきりさせる)。

    Args:
        row (list[float]): 今の行。
        neighbor_rows (list[tuple[list[float], float]]): (隣の行, 重み) の組。重みの合計は1。
        strength (float): 近づける割合(-1〜1)。
        locked (list[bool]): 列ごとのロック。
        maxInfluences (int | None): 最大数を保つならその数。

    Returns:
        list[float]: 新しい行。隣が無ければ元の行。
    """
    if not neighbor_rows:
        return list(row)
    average = [0.0] * len(row)
    for other, weight in neighbor_rows:
        for column, value in enumerate(other):
            average[column] += value * weight
    blended = [max(0.0, own + strength * (other - own)) for own, other in zip(row, average)]
    blended = limitRow(blended, locked, maxInfluences)
    return weights_module.fitRow(blended, row, locked)
