# -*- coding: utf-8 -*-
import maya.cmds as cmds
import maya.mel as mel
import heapq


def _to_shape(mesh):
    """
    transform / shape どちらが来ても mesh shape を返す
    """
    if not cmds.objExists(mesh):
        raise RuntimeError(u'Object does not exist: {}'.format(mesh))

    if cmds.nodeType(mesh) == 'mesh':
        return mesh

    shapes = cmds.listRelatives(mesh, shapes=True, fullPath=True, noIntermediate=True) or []
    for s in shapes:
        if cmds.nodeType(s) == 'mesh':
            return s

    raise RuntimeError(u'Mesh shape not found under: {}'.format(mesh))


def _get_skin_cluster(mesh):
    """
    mesh から関連 skinCluster を取得
    """
    shape = _to_shape(mesh)
    history = cmds.listHistory(shape, pruneDagObjects=True) or []
    skins = cmds.ls(history, type='skinCluster') or []
    if not skins:
        raise RuntimeError(u'skinCluster not found: {}'.format(mesh))
    return skins[0]


def _get_axis_index(axis):
    axis = axis.lower()
    table = {'x': 0, 'y': 1, 'z': 2}
    if axis not in table:
        raise RuntimeError(u'axis must be x, y, or z.')
    return table[axis]


def _all_vertices(mesh):
    shape = _to_shape(mesh)
    return cmds.ls('{}.vtx[*]'.format(shape), fl=True) or []


def _get_selected_mesh():
    """
    現在選択から最初のメッシュ(transform/shape/component)を返す
    """
    selection = cmds.ls(sl=True, long=True) or []
    for item in selection:
        node = item.split('.')[0]
        if not cmds.objExists(node):
            continue
        try:
            _to_shape(node)
            return node
        except RuntimeError:
            continue

    raise RuntimeError(u'No mesh selected. Please select a mesh object.')


def _get_selected_meshes():
    """
    現在選択からメッシュ(transform/shape/component)を重複なしで返す
    """
    selection = cmds.ls(sl=True, long=True) or []
    meshes = []
    seen = set()
    for item in selection:
        node = item.split('.')[0]
        if not cmds.objExists(node):
            continue
        try:
            _to_shape(node)
        except RuntimeError:
            continue

        if node in seen:
            continue
        seen.add(node)
        meshes.append(node)

    if not meshes:
        raise RuntimeError(u'No mesh selected. Please select at least one mesh object.')

    return meshes


def _pick_top_bottom_influences(skin_cluster, axis='y'):
    """
    skinCluster の influence から軸方向の最下端/最上端を返す
    可能なら joint のみを対象にする
    """
    axis_index = _get_axis_index(axis)
    influences = cmds.skinCluster(skin_cluster, q=True, influence=True) or []

    if len(influences) < 2:
        raise RuntimeError(u'Not enough influences in {}.'.format(skin_cluster))

    def _collect(nodes, joints_only):
        pairs = []
        for inf in nodes:
            if not cmds.objExists(inf):
                continue
            if joints_only and cmds.nodeType(inf) != 'joint':
                continue
            try:
                pos = cmds.xform(inf, q=True, ws=True, t=True)
                pairs.append((inf, pos[axis_index]))
            except Exception:
                continue
        return pairs

    candidates = _collect(influences, joints_only=True)
    if len(candidates) < 2:
        candidates = _collect(influences, joints_only=False)

    if len(candidates) < 2:
        raise RuntimeError(u'Could not determine top/bottom influences from {}'.format(skin_cluster))

    bottom_influence = min(candidates, key=lambda x: x[1])[0]
    top_influence = max(candidates, key=lambda x: x[1])[0]

    if bottom_influence == top_influence:
        raise RuntimeError(u'Failed to resolve distinct top/bottom influences in {}'.format(skin_cluster))

    return bottom_influence, top_influence


def _vertices_center(vertices):
    """
    頂点群のワールド座標中心を返す
    """
    if not vertices:
        raise RuntimeError(u'No vertices to compute center.')

    sx = sy = sz = 0.0
    count = 0
    for vtx in vertices:
        pos = cmds.pointPosition(vtx, world=True)
        sx += pos[0]
        sy += pos[1]
        sz += pos[2]
        count += 1
    inv = 1.0 / float(count)
    return [sx * inv, sy * inv, sz * inv]


def _collect_influence_positions(skin_cluster, joints_only=True):
    influences = cmds.skinCluster(skin_cluster, q=True, influence=True) or []
    pairs = []
    for inf in influences:
        if not cmds.objExists(inf):
            continue
        if joints_only and cmds.nodeType(inf) != 'joint':
            continue
        try:
            pos = cmds.xform(inf, q=True, ws=True, t=True)
            pairs.append((inf, [pos[0], pos[1], pos[2]]))
        except Exception:
            continue

    if not pairs and joints_only:
        return _collect_influence_positions(skin_cluster, joints_only=False)
    return pairs


def _nearest_influence(influence_positions, target_pos, exclude=None):
    exclude = set(exclude or [])
    best_name = None
    best_dist = None
    for name, pos in influence_positions:
        if name in exclude:
            continue
        dx = pos[0] - target_pos[0]
        dy = pos[1] - target_pos[1]
        dz = pos[2] - target_pos[2]
        dist2 = dx * dx + dy * dy + dz * dz
        if best_dist is None or dist2 < best_dist:
            best_dist = dist2
            best_name = name
    return best_name


def _pick_top_bottom_influences_from_end_rings(skin_cluster, top_vertices, bottom_vertices, axis='y'):
    """
    上端/下端リングの中心に最も近い influence を選ぶ
    """
    influence_positions = _collect_influence_positions(skin_cluster, joints_only=True)
    if len(influence_positions) < 2:
        raise RuntimeError(u'Not enough influences in {}.'.format(skin_cluster))

    top_center = _vertices_center(top_vertices)
    bottom_center = _vertices_center(bottom_vertices)

    top_influence = _nearest_influence(influence_positions, top_center)
    bottom_influence = _nearest_influence(influence_positions, bottom_center)

    if top_influence is None or bottom_influence is None:
        raise RuntimeError(u'Could not resolve top/bottom influences from {}'.format(skin_cluster))

    if top_influence == bottom_influence:
        axis_index = _get_axis_index(axis)
        bottom_influence = min(influence_positions, key=lambda x: x[1][axis_index])[0]
        top_influence = max(influence_positions, key=lambda x: x[1][axis_index])[0]

    if top_influence == bottom_influence:
        raise RuntimeError(u'Failed to resolve distinct top/bottom influences in {}'.format(skin_cluster))

    return bottom_influence, top_influence


def get_vertices_by_world_band(mesh, axis='y', top_range=1.0, bottom_range=1.0):
    """
    ワールド座標の高さ帯で上端・下端・中間頂点を返す
    """
    axis_index = _get_axis_index(axis)
    vtx_list = _all_vertices(mesh)

    if not vtx_list:
        raise RuntimeError(u'No vertices found: {}'.format(mesh))

    values = []
    for vtx in vtx_list:
        pos = cmds.pointPosition(vtx, world=True)
        values.append((vtx, pos[axis_index]))

    min_val = min(v for _, v in values)
    max_val = max(v for _, v in values)

    bottom_limit = min_val + bottom_range
    top_limit = max_val - top_range

    if bottom_limit >= top_limit:
        raise RuntimeError(
            u'top_range + bottom_range is too large. '
            u'No middle band remains. '
            u'(min={:.6f}, max={:.6f}, bottom_limit={:.6f}, top_limit={:.6f})'.format(
                min_val, max_val, bottom_limit, top_limit
            )
        )

    bottom_vertices = [vtx for vtx, v in values if v <= bottom_limit]
    top_vertices = [vtx for vtx, v in values if v >= top_limit]
    middle_vertices = [vtx for vtx, v in values if bottom_limit < v < top_limit]

    return {
        'top': top_vertices,
        'bottom': bottom_vertices,
        'middle': middle_vertices,
        'min_val': min_val,
        'max_val': max_val,
        'bottom_limit': bottom_limit,
        'top_limit': top_limit,
    }


def get_vertices_by_axis_equal_count(mesh, axis='y', segment_count=3):
    """
    軸方向に頂点を並べ、上端/中間/下端を頂点数ベースで均等分割する
    例: 12頂点 -> 下4 / 中4 / 上4
    """
    if int(segment_count) < 3:
        raise RuntimeError(u'segment_count must be >= 3.')

    axis_index = _get_axis_index(axis)
    all_vertices = _all_vertices(mesh)
    if not all_vertices:
        raise RuntimeError(u'No vertices found: {}'.format(mesh))

    values = [(vtx, cmds.pointPosition(vtx, world=True)[axis_index]) for vtx in all_vertices]
    values = sorted(values, key=lambda x: x[1])

    total = len(values)
    if total < 3:
        raise RuntimeError(u'Not enough vertices for equal count split: {}'.format(mesh))

    # 少頂点でも端点を確保できるように 3分割の端点数を丸めで決定
    # 例: 5頂点 -> end_count=2 => 下2 / 中1 / 上2
    end_count = int(round(float(total) / float(segment_count)))
    end_count = max(1, min(end_count, (total - 1) // 2))

    bottom_vertices = [vtx for vtx, _ in values[:end_count]]
    top_vertices = [vtx for vtx, _ in values[-end_count:]]
    middle_vertices = [vtx for vtx, _ in values[end_count:-end_count]]

    if not middle_vertices:
        raise RuntimeError(u'No middle vertices found in equal count split: {}'.format(mesh))

    min_val = values[0][1]
    max_val = values[-1][1]

    return {
        'top': top_vertices,
        'bottom': bottom_vertices,
        'middle': middle_vertices,
        'min_val': min_val,
        'max_val': max_val,
        'bottom_limit': None,
        'top_limit': None,
        'method': 'axis_equal_count',
    }


def _get_strict_border_edges(mesh):
    """
    face数1の厳密な境界エッジを返す
    """
    shape = _to_shape(mesh)
    all_edges = cmds.ls('{}.e[*]'.format(shape), fl=True) or []
    border_edges = cmds.ls(
        cmds.polyListComponentConversion(all_edges, fromEdge=True, toEdge=True, border=True),
        fl=True,
    ) or []

    if not border_edges:
        border_edges = cmds.ls(
            cmds.polyListComponentConversion(shape, toEdge=True, border=True),
            fl=True,
        ) or []

    border_edges = list(set(border_edges))
    strict_border = []
    for edge in border_edges:
        faces = cmds.ls(
            cmds.polyListComponentConversion(edge, fromEdge=True, toFace=True),
            fl=True,
        ) or []
        if len(faces) == 1:
            strict_border.append(edge)
    return strict_border


def _get_border_vertex_groups(mesh):
    """
    境界頂点の連結グループを返す
    """
    all_vertices = _all_vertices(mesh)
    all_vertex_set = set(all_vertices)
    border_edges = _get_strict_border_edges(mesh)
    if not border_edges:
        return []

    adjacency = {}
    for edge in border_edges:
        edge_vertices = cmds.ls(
            cmds.polyListComponentConversion(edge, fromEdge=True, toVertex=True),
            fl=True,
        ) or []
        edge_vertices = [v for v in edge_vertices if v in all_vertex_set]
        if len(edge_vertices) < 2:
            continue
        v0, v1 = edge_vertices[0], edge_vertices[1]
        adjacency.setdefault(v0, set()).add(v1)
        adjacency.setdefault(v1, set()).add(v0)

    groups = []
    visited = set()
    for start in adjacency.keys():
        if start in visited:
            continue
        stack = [start]
        group = []
        visited.add(start)
        while stack:
            cur = stack.pop()
            group.append(cur)
            for nxt in adjacency.get(cur, []):
                if nxt in visited:
                    continue
                visited.add(nxt)
                stack.append(nxt)
        groups.append(group)
    return groups


def get_vertices_by_axis_apex(mesh, axis='y', expected_top_count=1):
    """
    軸方向の極値から、先端(top)が少数(通常1)の形状を優先抽出する
    例: コーン形状で top=1 を強制
    """
    axis_index = _get_axis_index(axis)
    all_vertices = _all_vertices(mesh)
    if not all_vertices:
        raise RuntimeError(u'No vertices found: {}'.format(mesh))

    border_groups = _get_border_vertex_groups(mesh)
    if len(border_groups) != 1:
        raise RuntimeError(u'Axis apex requires exactly one border ring: {}'.format(mesh))
    border_vertices = set(border_groups[0])

    values = [(vtx, cmds.pointPosition(vtx, world=True)[axis_index]) for vtx in all_vertices]
    min_val = min(v for _, v in values)
    max_val = max(v for _, v in values)
    span = max(1e-8, max_val - min_val)
    tol = span * 1e-5

    top_vertices = [vtx for vtx, v in values if abs(v - max_val) <= tol]

    if len(top_vertices) != int(expected_top_count):
        raise RuntimeError(u'Apex top count mismatch: {} (expected {})'.format(len(top_vertices), expected_top_count))

    # 開口側が先端扱いされる誤判定を防ぐ
    if any(vtx in border_vertices for vtx in top_vertices):
        raise RuntimeError(u'Apex top vertex is on border ring: {}'.format(mesh))

    # bottom は唯一の境界リング全体を採用
    bottom_vertices = list(border_vertices)
    if not bottom_vertices:
        raise RuntimeError(u'No bottom vertices from axis apex: {}'.format(mesh))

    top_set = set(top_vertices)
    bottom_set = set(bottom_vertices)
    middle_vertices = [vtx for vtx in all_vertices if vtx not in top_set and vtx not in bottom_set]
    if not middle_vertices:
        raise RuntimeError(u'No middle vertices from axis apex: {}'.format(mesh))

    return {
        'top': top_vertices,
        'bottom': bottom_vertices,
        'middle': middle_vertices,
        'min_val': min_val,
        'max_val': max_val,
        'bottom_limit': None,
        'top_limit': None,
        'method': 'axis_apex',
    }


def _build_vertex_graph(mesh):
    vertices = _all_vertices(mesh)
    if not vertices:
        raise RuntimeError(u'No vertices found: {}'.format(mesh))

    positions = [cmds.pointPosition(vtx, world=True) for vtx in vertices]
    vtx_to_idx = {vtx: i for i, vtx in enumerate(vertices)}

    shape = _to_shape(mesh)
    edges = cmds.ls('{}.e[*]'.format(shape), fl=True) or []
    adjacency = [[] for _ in vertices]

    for edge in edges:
        edge_vertices = cmds.ls(
            cmds.polyListComponentConversion(edge, fromEdge=True, toVertex=True),
            fl=True,
        ) or []
        if len(edge_vertices) < 2:
            continue
        v0, v1 = edge_vertices[0], edge_vertices[1]
        if v0 not in vtx_to_idx or v1 not in vtx_to_idx:
            continue

        i0 = vtx_to_idx[v0]
        i1 = vtx_to_idx[v1]
        p0 = positions[i0]
        p1 = positions[i1]
        dx = p0[0] - p1[0]
        dy = p0[1] - p1[1]
        dz = p0[2] - p1[2]
        w = (dx * dx + dy * dy + dz * dz) ** 0.5

        adjacency[i0].append((i1, w))
        adjacency[i1].append((i0, w))

    return vertices, positions, adjacency


def _dijkstra_distances(adjacency, start_index):
    inf = float('inf')
    dist = [inf] * len(adjacency)
    dist[start_index] = 0.0
    queue = [(0.0, start_index)]

    while queue:
        cur_dist, node = heapq.heappop(queue)
        if cur_dist > dist[node]:
            continue
        for nxt, w in adjacency[node]:
            nd = cur_dist + w
            if nd < dist[nxt]:
                dist[nxt] = nd
                heapq.heappush(queue, (nd, nxt))

    return dist


def _argmax_finite(values):
    best_idx = None
    best_val = None
    for i, v in enumerate(values):
        if v == float('inf'):
            continue
        if best_val is None or v > best_val:
            best_val = v
            best_idx = i
    return best_idx


def get_vertices_by_geodesic_band(mesh, axis='y', endpoint_count_priority=True):
    """
    ジオデシック距離で top/middle/bottom を分割
    endpoint_count_priority=True の場合は top/bottom 同数を優先
    """
    axis_index = _get_axis_index(axis)
    vertices, positions, adjacency = _build_vertex_graph(mesh)
    if len(vertices) < 3:
        raise RuntimeError(u'Not enough vertices for geodesic split: {}'.format(mesh))

    seed = min(range(len(vertices)), key=lambda i: positions[i][axis_index])
    dist_seed = _dijkstra_distances(adjacency, seed)
    end_a = _argmax_finite(dist_seed)
    if end_a is None:
        raise RuntimeError(u'Failed to resolve geodesic endpoint A: {}'.format(mesh))

    dist_a = _dijkstra_distances(adjacency, end_a)
    end_b = _argmax_finite(dist_a)
    if end_b is None:
        raise RuntimeError(u'Failed to resolve geodesic endpoint B: {}'.format(mesh))

    if positions[end_a][axis_index] <= positions[end_b][axis_index]:
        bottom_end = end_a
        top_end = end_b
    else:
        bottom_end = end_b
        top_end = end_a

    dist_bottom = _dijkstra_distances(adjacency, bottom_end)
    dist_top = _dijkstra_distances(adjacency, top_end)

    scored = []
    for i, vtx in enumerate(vertices):
        db = dist_bottom[i]
        dt = dist_top[i]
        if db == float('inf') or dt == float('inf'):
            continue
        denom = db + dt
        t = 0.5 if denom <= 1e-8 else db / denom
        scored.append((vtx, t))

    if len(scored) < 3:
        raise RuntimeError(u'Not enough reachable vertices in geodesic split: {}'.format(mesh))

    scored.sort(key=lambda x: x[1])
    total = len(scored)

    if endpoint_count_priority:
        end_count = max(1, min((total - 1) // 2, int(round(total / 3.0))))
        bottom_count = end_count
        top_count = end_count
    else:
        bottom_count = max(1, int(round(total / 3.0)))
        top_count = max(1, int(round(total / 3.0)))
        bottom_count = min(bottom_count, total - 2)
        top_count = min(top_count, total - bottom_count - 1)

    bottom_vertices = [vtx for vtx, _ in scored[:bottom_count]]
    top_vertices = [vtx for vtx, _ in scored[-top_count:]]
    middle_vertices = [vtx for vtx, _ in scored[bottom_count:-top_count]]

    if not middle_vertices:
        raise RuntimeError(u'No middle vertices found in geodesic split: {}'.format(mesh))

    axis_values = [pos[axis_index] for pos in positions]
    return {
        'top': top_vertices,
        'bottom': bottom_vertices,
        'middle': middle_vertices,
        'min_val': min(axis_values),
        'max_val': max(axis_values),
        'bottom_limit': None,
        'top_limit': None,
        'method': 'geodesic',
    }


def get_vertices_by_end_rings(mesh, axis='y'):
    """
    開口境界リングから上端・下端・中間頂点を返す
    上端/下端は同頂点数を想定
    """
    axis_index = _get_axis_index(axis)
    shape = _to_shape(mesh)
    all_vertices = _all_vertices(mesh)
    all_vertex_set = set(all_vertices)

    all_edges = cmds.ls('{}.e[*]'.format(shape), fl=True) or []

    # Maya バージョンや履歴状態で border 変換結果が変わるため複数手段で取得する
    border_edges = cmds.ls(
        cmds.polyListComponentConversion(all_edges, fromEdge=True, toEdge=True, border=True),
        fl=True,
    ) or []

    if not border_edges:
        border_edges = cmds.ls(
            cmds.polyListComponentConversion(shape, toEdge=True, border=True),
            fl=True,
        ) or []

    if not border_edges:
        # 最後の手段: edge -> face 数が 1 のエッジを境界とみなす
        manual_border = []
        for edge in all_edges:
            faces = cmds.ls(
                cmds.polyListComponentConversion(edge, fromEdge=True, toFace=True),
                fl=True,
            ) or []
            if len(faces) == 1:
                manual_border.append(edge)
        border_edges = manual_border

    border_edges = list(set(border_edges))

    # 取得結果に内部エッジが混ざるケースがあるため、face数1のものだけを境界として採用
    strict_border = []
    for edge in border_edges:
        faces = cmds.ls(
            cmds.polyListComponentConversion(edge, fromEdge=True, toFace=True),
            fl=True,
        ) or []
        if len(faces) == 1:
            strict_border.append(edge)
    border_edges = strict_border

    if not border_edges:
        raise RuntimeError(u'No border edges found: {}'.format(mesh))

    def _groups_from_edges(edges):
        adjacency = {}
        for edge in edges:
            edge_vertices = cmds.ls(
                cmds.polyListComponentConversion(edge, fromEdge=True, toVertex=True),
                fl=True,
            ) or []
            edge_vertices = [v for v in edge_vertices if v in all_vertex_set]
            if len(edge_vertices) < 2:
                continue
            v0, v1 = edge_vertices[0], edge_vertices[1]
            adjacency.setdefault(v0, set()).add(v1)
            adjacency.setdefault(v1, set()).add(v0)

        if not adjacency:
            return []

        groups = []
        visited = set()
        for start in adjacency.keys():
            if start in visited:
                continue
            stack = [start]
            group = []
            visited.add(start)
            while stack:
                cur = stack.pop()
                group.append(cur)
                for nxt in adjacency.get(cur, []):
                    if nxt in visited:
                        continue
                    visited.add(nxt)
                    stack.append(nxt)
            groups.append(group)
        return groups

    rings = _groups_from_edges(border_edges)

    # 1つの境界リングしかない場合(例: 先端が1頂点でクローズ)、
    # 反対端は軸方向の極値頂点群から復元する
    if len(rings) == 1:
        ring = rings[0]

        def _avg_axis(verts):
            return sum(cmds.pointPosition(vtx, world=True)[axis_index] for vtx in verts) / float(len(verts))

        ring_avg = _avg_axis(ring)
        all_axis_values = [cmds.pointPosition(vtx, world=True)[axis_index] for vtx in all_vertices]
        min_axis = min(all_axis_values)
        max_axis = max(all_axis_values)

        # メッシュサイズに応じた許容幅で極値頂点群を抽出
        axis_span = max(1e-8, max_axis - min_axis)
        tol = axis_span * 1e-5

        min_group = [vtx for vtx in all_vertices if abs(cmds.pointPosition(vtx, world=True)[axis_index] - min_axis) <= tol]
        max_group = [vtx for vtx in all_vertices if abs(cmds.pointPosition(vtx, world=True)[axis_index] - max_axis) <= tol]

        # ring が下側なら反対端は max_group、ring が上側なら min_group
        if abs(ring_avg - min_axis) <= abs(ring_avg - max_axis):
            rings = [ring, max_group]
        else:
            rings = [min_group, ring]

    # 境界情報が取れない場合のみ、境界頂点を軸方向で2分割して復元
    if len(rings) < 2:
        # border変換が不安定なため、確定した境界エッジから頂点を復元する
        boundary_vertices = cmds.ls(
            cmds.polyListComponentConversion(border_edges, fromEdge=True, toVertex=True),
            fl=True,
        ) or []
        boundary_vertices = list(set(v for v in boundary_vertices if v in all_vertex_set))

        if len(boundary_vertices) < 2:
            raise RuntimeError(u'Need at least two border rings: {}'.format(mesh))

        values = [(vtx, cmds.pointPosition(vtx, world=True)[axis_index]) for vtx in boundary_vertices]
        min_v = min(v for _, v in values)
        max_v = max(v for _, v in values)
        mid = (min_v + max_v) * 0.5

        bottom_candidates = [vtx for vtx, val in values if val <= mid]
        top_candidates = [vtx for vtx, val in values if val > mid]

        if not bottom_candidates or not top_candidates:
            values_sorted = sorted(values, key=lambda x: x[1])
            half = len(values_sorted) // 2
            if half <= 0:
                raise RuntimeError(u'Need at least two border rings: {}'.format(mesh))
            bottom_candidates = [vtx for vtx, _ in values_sorted[:half]]
            top_candidates = [vtx for vtx, _ in values_sorted[-half:]]

        rings = [bottom_candidates, top_candidates]

    def _avg_axis(verts):
        return sum(cmds.pointPosition(vtx, world=True)[axis_index] for vtx in verts) / float(len(verts))

    rings = sorted(rings, key=_avg_axis)
    bottom_vertices = rings[0]
    top_vertices = rings[-1]

    if not bottom_vertices or not top_vertices:
        raise RuntimeError(u'Could not resolve top/bottom vertices: {}'.format(mesh))

    top_set = set(top_vertices)
    bottom_set = set(bottom_vertices)
    middle_vertices = [vtx for vtx in all_vertices if vtx not in top_set and vtx not in bottom_set]

    if not middle_vertices:
        raise RuntimeError(u'No middle vertices found after ring extraction: {}'.format(mesh))

    min_val = min(cmds.pointPosition(vtx, world=True)[axis_index] for vtx in all_vertices)
    max_val = max(cmds.pointPosition(vtx, world=True)[axis_index] for vtx in all_vertices)

    return {
        'top': top_vertices,
        'bottom': bottom_vertices,
        'middle': middle_vertices,
        'min_val': min_val,
        'max_val': max_val,
        'bottom_limit': None,
        'top_limit': None,
        'method': 'end_rings',
    }


def set_two_influence_weights(skin_cluster, vertices, bottom_influence, top_influence,
                              bottom_weight, top_weight, normalize=True):
    """
    2インフルエンス分のウェイトを明示設定
    """
    if not vertices:
        return

    for vtx in vertices:
        cmds.skinPercent(
            skin_cluster,
            vtx,
            transformValue=[
                (bottom_influence, float(bottom_weight)),
                (top_influence, float(top_weight)),
            ],
            normalize=normalize
        )


def smooth_skincluster_weights(skin_cluster, smooth_weights=0.0, max_iterations=5,
                               obey_max_influences=2, normalize_after_change=True,
                               preserve_maintain_max_influences=True):
    """
    SIWeightEditor と同系統の skinCluster 平滑化を実行
    smooth_weights: weightChangeTolerance (sw)
    max_iterations: numIterations (swi)
    obey_max_influences: obeyMaxInfluences (omi)
    """
    mmi = None
    has_mmi = cmds.attributeQuery('maintainMaxInfluences', node=skin_cluster, exists=True)
    if preserve_maintain_max_influences and has_mmi:
        mmi = cmds.getAttr(skin_cluster + '.maintainMaxInfluences')

    try:
        cmds.skinCluster(
            skin_cluster,
            edit=True,
            sw=float(smooth_weights),
            swi=int(max_iterations),
            omi=int(obey_max_influences),
        )
        if normalize_after_change:
            cmds.skinCluster(skin_cluster, edit=True, fnw=True)
    finally:
        if preserve_maintain_max_influences and has_mmi and mmi is not None:
            cmds.setAttr(skin_cluster + '.maintainMaxInfluences', mmi)


def open_paint_skin_weights_tool():
    """
    任意: Paint Skin Weights Tool を開く
    UI確認用。バッチ本処理には不要。
    """
    try:
        mel.eval('ArtPaintSkinWeightsToolOptions;')
    except Exception:
        # Maya バージョン差の保険
        try:
            mel.eval('ArtPaintSkinWeightsTool;')
        except Exception:
            cmds.warning(u'Could not open Paint Skin Weights Tool.')


def auto_two_influence_band_smooth(
        mesh=None,
        bottom_influence=None,
        top_influence=None,
        skin_cluster=None,
        axis='y',
        bottom_range=1.0,
        top_range=1.0,
        smooth_weights=0.0,
        smooth_iterations=5,
        smooth_passes=1,
        reselect_middle=True,
        verbose=True):
    """
    2インフルエンス前提:
      1) ワールド座標で上端帯・下端帯を抽出
      2) 下端=bottom 100%, 上端=top 100% を設定
      3) skinCluster の標準 smooth を実行
      4) 最後に上下端を再固定

    Parameters
    ----------
    mesh : str or list[str]
        メッシュ transform または shape。None なら選択から自動取得
    bottom_influence : str
        下端側インフルエンス。None なら skinCluster から自動推定
    top_influence : str
        上端側インフルエンス。None なら skinCluster から自動推定
    skin_cluster : str or None
        指定しなければ mesh から自動取得
    axis : str
        'x' / 'y' / 'z'
    bottom_range : float
        最下点からこの距離以内を下端帯にする
    top_range : float
        最上点からこの距離以内を上端帯にする
    smooth_weights : float
        skinCluster -sw (weightChangeTolerance) 値
    smooth_iterations : int
        skinCluster -swi (numIterations) 値
    smooth_passes : int
        上記 smooth を何回回すか
    reselect_middle : bool
        終了時に middle 頂点を選択し直す
    verbose : bool
        ログ出力
    """
    if mesh is None:
        mesh_list = _get_selected_meshes()
    elif isinstance(mesh, (list, tuple)):
        mesh_list = list(mesh)
    else:
        mesh_list = [mesh]

    if len(mesh_list) > 1 and skin_cluster is not None:
        raise RuntimeError(
            u'When processing multiple meshes, skin_cluster must be None.'
        )

    all_middle_vertices = []
    results = []

    for target_mesh in mesh_list:
        target_skin_cluster = skin_cluster or _get_skin_cluster(target_mesh)

        # 5頂点ケース(2/1/2想定)は geodesic を優先
        vtx_count = len(_all_vertices(target_mesh))
        if vtx_count == 5:
            try:
                band = get_vertices_by_geodesic_band(target_mesh, axis=axis, endpoint_count_priority=True)
                band_method = band.get('method', 'geodesic')
            except RuntimeError as exc:
                band = get_vertices_by_world_band(
                    mesh=target_mesh,
                    axis=axis,
                    top_range=top_range,
                    bottom_range=bottom_range
                )
                band_method = 'world_band_fallback'
                if verbose:
                    cmds.warning(u'Geodesic split failed on {}: {}. Fallback to world band.'.format(target_mesh, exc))
        else:
            try:
                band = get_vertices_by_end_rings(mesh=target_mesh, axis=axis)
                band_method = band.get('method', 'end_rings')
            except RuntimeError as exc:
                # end-ring判定が不成立なメッシュは従来の帯域判定にフォールバック
                band = get_vertices_by_world_band(
                    mesh=target_mesh,
                    axis=axis,
                    top_range=top_range,
                    bottom_range=bottom_range
                )
                band_method = 'world_band_fallback'
                if verbose:
                    cmds.warning(u'End-ring detection failed on {}: {}. Fallback to world band.'.format(target_mesh, exc))

        top_vertices = band['top']
        bottom_vertices = band['bottom']
        middle_vertices = band['middle']

        # end_rings が極端に偏る場合は、軸方向の均等分割にフォールバック
        if band_method == 'end_rings':
            top_count = len(top_vertices)
            bottom_count = len(bottom_vertices)
            middle_count = len(middle_vertices)
            min_end = min(top_count, bottom_count)
            max_end = max(top_count, bottom_count)
            if min_end <= 0 or max_end > (min_end * 2) or middle_count < min_end:
                try:
                    # コーンのように先端が1頂点のケースを優先
                    band = get_vertices_by_axis_apex(mesh=target_mesh, axis=axis, expected_top_count=1)
                    band_method = band.get('method', 'axis_apex')
                    top_vertices = band['top']
                    bottom_vertices = band['bottom']
                    middle_vertices = band['middle']
                except RuntimeError:
                    try:
                        band = get_vertices_by_axis_equal_count(mesh=target_mesh, axis=axis, segment_count=3)
                        band_method = band.get('method', 'axis_equal_count')
                        top_vertices = band['top']
                        bottom_vertices = band['bottom']
                        middle_vertices = band['middle']
                    except RuntimeError:
                        pass

        target_bottom_influence = bottom_influence
        target_top_influence = top_influence
        if target_bottom_influence is None or target_top_influence is None:
            if band_method in ('end_rings', 'axis_equal_count', 'axis_apex'):
                auto_bottom, auto_top = _pick_top_bottom_influences_from_end_rings(
                    target_skin_cluster,
                    top_vertices=top_vertices,
                    bottom_vertices=bottom_vertices,
                    axis=axis,
                )
            else:
                auto_bottom, auto_top = _pick_top_bottom_influences(target_skin_cluster, axis=axis)
            if target_bottom_influence is None:
                target_bottom_influence = auto_bottom
            if target_top_influence is None:
                target_top_influence = auto_top

        if not cmds.objExists(target_bottom_influence):
            raise RuntimeError(u'Bottom influence does not exist: {}'.format(target_bottom_influence))
        if not cmds.objExists(target_top_influence):
            raise RuntimeError(u'Top influence does not exist: {}'.format(target_top_influence))

        influences = cmds.skinCluster(target_skin_cluster, q=True, influence=True) or []
        if target_bottom_influence not in influences:
            raise RuntimeError(u'{} is not connected to {}'.format(target_bottom_influence, target_skin_cluster))
        if target_top_influence not in influences:
            raise RuntimeError(u'{} is not connected to {}'.format(target_top_influence, target_skin_cluster))

        if not top_vertices:
            raise RuntimeError(u'No top vertices found: {}'.format(target_mesh))
        if not bottom_vertices:
            raise RuntimeError(u'No bottom vertices found: {}'.format(target_mesh))
        if not middle_vertices:
            raise RuntimeError(u'No middle vertices found: {}'.format(target_mesh))

        # 1. 端部をベタ固定
        set_two_influence_weights(
            target_skin_cluster, bottom_vertices,
            target_bottom_influence, target_top_influence,
            bottom_weight=0.0, top_weight=1.0,
            normalize=True
        )
        set_two_influence_weights(
            target_skin_cluster, top_vertices,
            target_bottom_influence, target_top_influence,
            bottom_weight=1.0, top_weight=0.0,
            normalize=True
        )

        # 2. middle を選択しておく
        cmds.select(middle_vertices, r=True)

        # 3. Maya 標準 smooth 実行
        for _ in range(max(1, int(smooth_passes))):
            smooth_skincluster_weights(
                skin_cluster=target_skin_cluster,
                smooth_weights=smooth_weights,
                max_iterations=smooth_iterations
            )

        # 4. 端部を再固定
        set_two_influence_weights(
            target_skin_cluster, bottom_vertices,
            target_bottom_influence, target_top_influence,
            bottom_weight=0.0, top_weight=1.0,
            normalize=True
        )
        set_two_influence_weights(
            target_skin_cluster, top_vertices,
            target_bottom_influence, target_top_influence,
            bottom_weight=1.0, top_weight=0.0,
            normalize=True
        )

        all_middle_vertices.extend(middle_vertices)

        result = {
            'mesh': target_mesh,
            'skinCluster': target_skin_cluster,
            'bottomInfluence': target_bottom_influence,
            'topInfluence': target_top_influence,
            'topVertices': top_vertices,
            'bottomVertices': bottom_vertices,
            'middleVertices': middle_vertices,
            'minVal': band['min_val'],
            'maxVal': band['max_val'],
            'bottomLimit': band['bottom_limit'],
            'topLimit': band['top_limit'],
            'bandMethod': band_method,
        }
        results.append(result)

        if verbose:
            print(u'=== auto_two_influence_band_smooth done ===')
            print(u'mesh           : {}'.format(target_mesh))
            print(u'skinCluster    : {}'.format(target_skin_cluster))
            print(u'bottom influence: {}'.format(target_bottom_influence))
            print(u'top influence   : {}'.format(target_top_influence))
            print(u'axis           : {}'.format(axis))
            print(u'band method    : {}'.format(band_method))
            print(u'min/max        : {:.6f} / {:.6f}'.format(result['minVal'], result['maxVal']))
            if result['bottomLimit'] is None or result['topLimit'] is None:
                print(u'bottom/top lim : N/A ({})'.format(band_method))
            else:
                print(u'bottom/top lim : {:.6f} / {:.6f}'.format(result['bottomLimit'], result['topLimit']))
            print(u'bottom count   : {}'.format(len(bottom_vertices)))
            print(u'top count      : {}'.format(len(top_vertices)))
            print(u'middle count   : {}'.format(len(middle_vertices)))

    if reselect_middle and all_middle_vertices:
        cmds.select(all_middle_vertices, r=True)

    if len(results) == 1:
        return results[0]
    return results

if __name__ == '__main__':
    auto_two_influence_band_smooth(
        # mesh / skin_cluster / influence 未指定時は選択とskinClusterから自動推定
        axis='y',
        bottom_range=9.0,
        top_range=3.0,
        smooth_weights=0.0,
        smooth_iterations=5,
        smooth_passes=2
    )