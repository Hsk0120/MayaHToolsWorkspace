# -*- coding: utf-8 -*-
import maya.cmds as cmds

import maya.mel as mel
import heapq

import mlib
from mlib.common import units


def _get_influence_names(skin_cluster):
    """skinCluster の influence を Maya の influence 順で最短一意名として返します。

    Args:
        skin_cluster: ウェイトを照会・編集するskinCluster。
    """
    return mlib.getNode(skin_cluster).getInfluences().getNames()


def _to_shape(mesh):
    """transform / shape どちらが来ても mesh shape を返す

    Args:
        mesh: 処理対象のメッシュまたはそのTransform。
    """
    if not mlib.objExists(mesh):
        raise RuntimeError(u'Object does not exist: {}'.format(mesh))

    node = mlib.getNode(mesh)
    if node.getType() == 'mesh':
        return mesh

    if isinstance(node, mlib.Transform):
        for s in node.getShape(all=True):
            if s.getType() == 'mesh':
                return s.getName(full=True)

    raise RuntimeError(u'Mesh shape not found under: {}'.format(mesh))


def _get_mesh(mesh):
    """transform / shape どちらが来ても mesh shape の Mesh オブジェクトを返します。

    Args:
        mesh: 処理対象のメッシュまたはそのTransform。
    """
    return mlib.getNode(_to_shape(mesh))


def _get_skin_cluster(mesh):
    """mesh から関連 skinCluster を取得

    Args:
        mesh: 処理対象のメッシュまたはそのTransform。
    """
    skins = _get_mesh(mesh).getHistory(type='skinCluster')
    if not skins:
        raise RuntimeError(u'skinCluster not found: {}'.format(mesh))
    return skins[0].getName()


def _get_axis_index(axis):
    """軸文字を座標インデックスへ変換します。

    Args:
        axis: 基準軸。x・y・zのいずれか。
    """
    axis = axis.lower()
    table = {'x': 0, 'y': 1, 'z': 2}
    if axis not in table:
        raise RuntimeError(u'axis must be x, y, or z.')
    return table[axis]


def _all_vertices(mesh):
    """メッシュの全頂点コンポーネントを返します。

    Args:
        mesh: 処理対象のメッシュまたはそのTransform。
    """
    shape = _to_shape(mesh)
    # 戻り値の頂点名は cmds.ls と同じ形(Transform の短い名前.vtx[i])にする。番号の順に並ぶ。
    return mlib.getNode(shape).getVertices().getNames()


def _to_ui_point(point):
    """cm の位置を UI の距離単位の [x, y, z] にします。

    Args:
        point: cm の位置。
    """
    return [units.convertDistance(point.x, "cm"), units.convertDistance(point.y, "cm"), units.convertDistance(point.z, "cm")]


def _world_points(mesh):
    """全頂点のワールド座標を、頂点番号の順に UI の距離単位で返します。

    Args:
        mesh: 処理対象のメッシュまたはそのTransform。
    """
    return [_to_ui_point(point) for point in _get_mesh(mesh).getPoints(ws=True)]


def _get_selected_node_names():
    """現在選択の各要素について、それを持つノードの長い名前を選択順に返します。"""
    names = []
    for item in mlib.Selection.capture().getItems():
        if isinstance(item, mlib.Node):
            node = item
        elif isinstance(item, mlib.Plug):
            node = item.getNode()
        else:
            # コンポーネントは cmds.ls(long=True) と同じく、Shape の親の Transform で表す。
            node = item.shape.getParent()
        names.append(node.getName(full=True))
    return names


def _get_selected_mesh():
    """
    現在選択から最初のメッシュ(transform/shape/component)を返す
    """
    for node in _get_selected_node_names():
        if not mlib.objExists(node):
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
    meshes = []
    seen = set()
    for node in _get_selected_node_names():
        if not mlib.objExists(node):
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


def _influence_position(inf):
    """influence のワールド座標を UI の距離単位で返します(transform でなければ例外)。

    Args:
        inf: インフルエンスの名前。
    """
    # cmds.xform(q=True, ws=True, t=True) と同じく translate の位置を使う。
    return _to_ui_point(mlib.getNode(inf).getTranslation(ws=True, at=1))


def _pick_top_bottom_influences(skin_cluster, axis='y'):
    """skinCluster の influence から軸方向の最下端/最上端を返す
    可能なら joint のみを対象にする

    Args:
        skin_cluster: ウェイトを照会・編集するskinCluster。
        axis: 基準軸。x・y・zのいずれか。
    """
    axis_index = _get_axis_index(axis)
    influences = _get_influence_names(skin_cluster)

    if len(influences) < 2:
        raise RuntimeError(u'Not enough influences in {}.'.format(skin_cluster))

    def _collect(nodes, joints_only):
        pairs = []
        for inf in nodes:
            if not mlib.objExists(inf):
                continue
            if joints_only and mlib.getNode(inf).getType() != 'joint':
                continue
            try:
                pos = _influence_position(inf)
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
    """頂点群のワールド座標中心を返す

    Args:
        vertices: 処理対象の頂点コンポーネント列。
    """
    if not vertices:
        raise RuntimeError(u'No vertices to compute center.')

    return _to_ui_point(mlib.ls(vertices).getCenter(ws=True))


def _collect_influence_positions(skin_cluster, joints_only=True):
    """influence のワールド座標一覧を収集します。

    Args:
        skin_cluster: ウェイトを照会・編集するskinCluster。
        joints_only: Trueはジョイントのインフルエンスだけを対象にする。
    """
    influences = _get_influence_names(skin_cluster)
    pairs = []
    for inf in influences:
        if not mlib.objExists(inf):
            continue
        if joints_only and mlib.getNode(inf).getType() != 'joint':
            continue
        try:
            pairs.append((inf, _influence_position(inf)))
        except Exception:
            continue

    # joint 限定で取れない場合は全 influence へフォールバックする。
    if not pairs and joints_only:
        return _collect_influence_positions(skin_cluster, joints_only=False)
    return pairs


def _nearest_influence(influence_positions, target_pos, exclude=None):
    """目標座標に最も近い influence を返します。

    Args:
        influence_positions: インフルエンスごとのワールド座標。
        target_pos: 最近傍を探索するワールド座標。
        exclude: 候補から除外する対象。
    """
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
    """上端/下端リングの中心に最も近い influence を選ぶ

    Args:
        skin_cluster: ウェイトを照会・編集するskinCluster。
        top_vertices: 処理対象の頂点コンポーネント列。
        bottom_vertices: 処理対象の頂点コンポーネント列。
        axis: 基準軸。x・y・zのいずれか。
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
    """ワールド座標の高さ帯で上端・下端・中間頂点を返す

    Args:
        mesh: 処理対象のメッシュまたはそのTransform。
        axis: 基準軸。x・y・zのいずれか。
        top_range: 最上点から上端帯に含めるワールド空間の距離。
        bottom_range: 最下点から下端帯に含めるワールド空間の距離。
    """
    axis_index = _get_axis_index(axis)
    vtx_list = _all_vertices(mesh)

    if not vtx_list:
        raise RuntimeError(u'No vertices found: {}'.format(mesh))

    points = _world_points(mesh)
    values = [(vtx, points[i][axis_index]) for i, vtx in enumerate(vtx_list)]

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
    """軸方向に頂点を並べ、上端/中間/下端を頂点数ベースで均等分割する
    例: 12頂点 -> 下4 / 中4 / 上4

    Args:
        mesh: 処理対象のメッシュまたはそのTransform。
        axis: 基準軸。x・y・zのいずれか。
        segment_count: 頂点を分割する区分数。
    """
    if int(segment_count) < 3:
        raise RuntimeError(u'segment_count must be >= 3.')

    axis_index = _get_axis_index(axis)
    all_vertices = _all_vertices(mesh)
    if not all_vertices:
        raise RuntimeError(u'No vertices found: {}'.format(mesh))

    points = _world_points(mesh)
    values = [(vtx, points[i][axis_index]) for i, vtx in enumerate(all_vertices)]
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
    """face数1の厳密な境界エッジを返す

    Args:
        mesh: 処理対象のメッシュまたはそのTransform。

    Returns:
        Edges: 接している面が1つだけのエッジ。
    """
    return _get_mesh(mesh).getBorder()


def _vertex_groups_from_edges(vertex_names, edges):
    """エッジでつながった頂点のグループを、頂点名のリストで返します。

    Args:
        vertex_names: 頂点番号の順に並んだ頂点名。
        edges: 対象のエッジ。
    """
    adjacency = {}
    for edge in edges:
        edge_vertices = [vertex_names[vertex.index] for vertex in edge.getVertices()]
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


def _get_border_vertex_groups(mesh):
    """境界頂点の連結グループを返す

    Args:
        mesh: 処理対象のメッシュまたはそのTransform。
    """
    all_vertices = _all_vertices(mesh)
    border_edges = _get_strict_border_edges(mesh)
    if not border_edges:
        return []
    return _vertex_groups_from_edges(all_vertices, border_edges)


def get_vertices_by_axis_apex(mesh, axis='y', expected_top_count=1):
    """軸方向の極値から、先端(top)が少数(通常1)の形状を優先抽出する
    例: コーン形状で top=1 を強制

    Args:
        mesh: 処理対象のメッシュまたはそのTransform。
        axis: 基準軸。x・y・zのいずれか。
        expected_top_count: 先端側で優先する頂点数。
    """
    axis_index = _get_axis_index(axis)
    all_vertices = _all_vertices(mesh)
    if not all_vertices:
        raise RuntimeError(u'No vertices found: {}'.format(mesh))

    border_groups = _get_border_vertex_groups(mesh)
    if len(border_groups) != 1:
        raise RuntimeError(u'Axis apex requires exactly one border ring: {}'.format(mesh))
    border_vertices = set(border_groups[0])

    points = _world_points(mesh)
    values = [(vtx, points[i][axis_index]) for i, vtx in enumerate(all_vertices)]
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
    """メッシュ頂点の隣接グラフを構築します。

    Args:
        mesh: 処理対象のメッシュまたはそのTransform。
    """
    vertices = _all_vertices(mesh)
    if not vertices:
        raise RuntimeError(u'No vertices found: {}'.format(mesh))

    # mlib は内部単位(cm)を返すため、cmds と揃えて UI 単位へ変換する。
    mesh_node = _get_mesh(mesh)
    positions = _world_points(mesh)

    # 頂点ID順の隣接リスト。各要素は(隣接頂点ID, UI 単位のエッジ長)で、
    # エッジID順に格納する。孤立頂点は空リスト、重複エッジは別々に保持する。
    adjacency = [
        [(neighbor, units.convertDistance(length, "cm")) for neighbor, length in row]
        for row in mesh_node.getVertexAdjacency(ws=True)
    ]

    return vertices, positions, adjacency


def _dijkstra_distances(adjacency, start_index):
    """始点からの最短距離配列を Dijkstra で計算します。

    Args:
        adjacency: 隣接頂点と接続情報を保持するグラフ。
        start_index: 対象要素の番号または探索開始番号。
    """
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
    """有限値のみ対象に最大値インデックスを返します。

    Args:
        values: 計算対象の数値列。
    """
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
    """ジオデシック距離で top/middle/bottom を分割
    endpoint_count_priority=True の場合は top/bottom 同数を優先

    Args:
        mesh: 処理対象のメッシュまたはそのTransform。
        axis: 基準軸。x・y・zのいずれか。
        endpoint_count_priority: 端点の数による優先順位を考慮するか。
    """
    axis_index = _get_axis_index(axis)
    vertices, positions, adjacency = _build_vertex_graph(mesh)
    if len(vertices) < 3:
        raise RuntimeError(u'Not enough vertices for geodesic split: {}'.format(mesh))

    # 軸下端付近を seed にし、直径端点を2回の最遠探索で推定する。
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

    # 各頂点を bottom->top の相対位置 t(0..1) に写像する。
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
    """開口境界リングから上端・下端・中間頂点を返す
    上端/下端は同頂点数を想定

    Args:
        mesh: 処理対象のメッシュまたはそのTransform。
        axis: 基準軸。x・y・zのいずれか。
    """
    axis_index = _get_axis_index(axis)
    all_vertices = _all_vertices(mesh)
    points = _world_points(mesh)
    axis_value = {vtx: points[i][axis_index] for i, vtx in enumerate(all_vertices)}

    # 接している面が1つだけのエッジを境界とする(内部エッジ・非多様体のエッジは含まない)。
    border_edges = _get_strict_border_edges(mesh)

    if not border_edges:
        raise RuntimeError(u'No border edges found: {}'.format(mesh))

    rings = _vertex_groups_from_edges(all_vertices, border_edges)

    # 1つの境界リングしかない場合(例: 先端が1頂点でクローズ)、
    # 反対端は軸方向の極値頂点群から復元する
    if len(rings) == 1:
        ring = rings[0]

        def _avg_axis(verts):
            return sum(axis_value[vtx] for vtx in verts) / float(len(verts))

        ring_avg = _avg_axis(ring)
        all_axis_values = [axis_value[vtx] for vtx in all_vertices]
        min_axis = min(all_axis_values)
        max_axis = max(all_axis_values)

        # メッシュサイズに応じた許容幅で極値頂点群を抽出
        axis_span = max(1e-8, max_axis - min_axis)
        tol = axis_span * 1e-5

        min_group = [vtx for vtx in all_vertices if abs(axis_value[vtx] - min_axis) <= tol]
        max_group = [vtx for vtx in all_vertices if abs(axis_value[vtx] - max_axis) <= tol]

        # ring が下側なら反対端は max_group、ring が上側なら min_group
        if abs(ring_avg - min_axis) <= abs(ring_avg - max_axis):
            rings = [ring, max_group]
        else:
            rings = [min_group, ring]

    # 境界情報が取れない場合のみ、境界頂点を軸方向で2分割して復元
    if len(rings) < 2:
        # 確定した境界エッジから頂点を復元する
        boundary_vertices = list(set(all_vertices[vertex.index] for vertex in border_edges.getVertices()))

        if len(boundary_vertices) < 2:
            raise RuntimeError(u'Need at least two border rings: {}'.format(mesh))

        values = [(vtx, axis_value[vtx]) for vtx in boundary_vertices]
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
        return sum(axis_value[vtx] for vtx in verts) / float(len(verts))

    rings = sorted(rings, key=_avg_axis)
    bottom_vertices = rings[0]
    top_vertices = rings[-1]

    if not bottom_vertices or not top_vertices:
        raise RuntimeError(u'Could not resolve top/bottom vertices: {}'.format(mesh))

    top_set = set(top_vertices)
    bottom_set = set(bottom_vertices)
    middle_vertices = [vtx for vtx in all_vertices if vtx not in top_set and vtx not in bottom_set]

    min_val = min(axis_value[vtx] for vtx in all_vertices)
    max_val = max(axis_value[vtx] for vtx in all_vertices)

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
    """2インフルエンス分のウェイトを明示設定

    Args:
        skin_cluster: ウェイトを照会・編集するskinCluster。
        vertices: 処理対象の頂点コンポーネント列。
        bottom_influence: ウェイトを割り当てる、または移管するインフルエンス。
        top_influence: ウェイトを割り当てる、または移管するインフルエンス。
        bottom_weight: 設定するウェイト値。
        top_weight: 設定するウェイト値。
        normalize: 変更後にウェイトを正規化するか。
    """
    if not vertices:
        return

    skin = mlib.getNode(skin_cluster)
    components = mlib.ls(vertices)
    # 全頂点へ同じ2つの値を書く(指定しなかった influence は normalize で 0 になる)。
    # skinCluster が複数の形状を変形するときは、頂点の形状の番号を渡す。
    skin.setWeights(
        [bottom_influence, top_influence],
        [float(bottom_weight), float(top_weight)],
        vertices=components,
        normalize=normalize,
        broadcast=True,
        geometryIndex=skin.getGeometryIndices(components.shape),
    )


def smooth_skincluster_weights(skin_cluster, smooth_weights=0.0, max_iterations=5,
                               obey_max_influences=2, normalize_after_change=True,
                               preserve_maintain_max_influences=True):
    """skinClusterの標準コマンドでウェイトを平滑化する。

    Args:
        skin_cluster: 編集するskinCluster。
        smooth_weights (float): skinClusterのswへ渡す平滑化の許容値。
        max_iterations (int): skinClusterのswiへ渡す最大反復数。
        obey_max_influences (int): skinClusterのomiへ渡す値。
        normalize_after_change (bool): 平滑化後にウェイトを正規化するか。
        preserve_maintain_max_influences (bool): maintainMaxInfluencesの値を保存・復元するか。
    """
    skin = mlib.getNode(skin_cluster)
    mmi = None
    has_mmi = skin.hasAttr('maintainMaxInfluences')
    if preserve_maintain_max_influences and has_mmi:
        mmi = skin.getPlug('maintainMaxInfluences').get()

    try:
        # 選択中の頂点だけを平滑化する(何も選んでいなければメッシュ全体)。
        selected = mlib.ls(selection=True, type='vertex')
        # skinCluster が複数の形状を変形するときは、選んだ頂点の形状の番号を渡す
        # (複数の形状の頂点を選ぶと、元の cmds.skinCluster と同じく失敗する)。
        index = skin.getGeometryIndices(selected.shape) if isinstance(selected, mlib.Vertices) else None
        skin.smoothWeights(
            tolerance=float(smooth_weights),
            iterations=int(max_iterations),
            vertices=selected if len(selected) else None,
            obeyMaxInfluences=bool(obey_max_influences),
            geometryIndex=index,
        )
        if normalize_after_change:
            skin.normalizeWeights(force=True)
    finally:
        if preserve_maintain_max_influences and has_mmi and mmi is not None:
            skin.getPlug('maintainMaxInfluences').set(mmi)


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
    """上下端を2つのインフルエンスへ固定し、中間のウェイトを平滑化する。

    境界や頂点数に応じて端部の抽出方法を選ぶ。ワールド座標の帯を使う場合は
    bottom_rangeとtop_rangeを用いる。平滑化後に両端を再固定する。

    Args:
        mesh (str | list[str] | None): メッシュのTransformまたはShape。省略時は選択から取得。
        bottom_influence (str | None): 下端側のインフルエンス。省略時は自動推定。
        top_influence (str | None): 上端側のインフルエンス。省略時は自動推定。
        skin_cluster (str | None): 編集するskinCluster。省略時はメッシュから取得。
        axis (str): 基準軸。x・y・zのいずれか。
        bottom_range (float): ワールド座標の最下点から下端帯に含める距離。
        top_range (float): ワールド座標の最上点から上端帯に含める距離。
        smooth_weights (float): skinClusterのswへ渡す平滑化の許容値。
        smooth_iterations (int): 1回の平滑化での最大反復数。
        smooth_passes (int): 平滑化の実行回数。1未満も1回として扱う。
        reselect_middle (bool): 完了時に中間頂点を選択するか。
        verbose (bool): 処理結果をログへ出力するか。

    Returns:
        dict | list[dict]: メッシュ・インフルエンス・頂点帯・抽出方式などの処理結果。
            結果が1件なら辞書、それ以外は辞書のリスト。

    Raises:
        RuntimeError: 複数メッシュにskin_clusterを指定した場合や端部を解決できない場合。
    """
    # 平滑化のために選択を変えるため、中間頂点を選び直さない場合は元の選択へ戻す。
    original_selection = mlib.Selection.capture()
    reselected = False
    # 全メッシュ分のウェイト編集を1回の Undo で戻せるようにまとめる。
    cmds.undoInfo(openChunk=True, chunkName='autoTwoInfluenceBandSmooth')
    try:
        result, reselected = _auto_two_influence_band_smooth(
            mesh=mesh,
            bottom_influence=bottom_influence,
            top_influence=top_influence,
            skin_cluster=skin_cluster,
            axis=axis,
            bottom_range=bottom_range,
            top_range=top_range,
            smooth_weights=smooth_weights,
            smooth_iterations=smooth_iterations,
            smooth_passes=smooth_passes,
            reselect_middle=reselect_middle,
            verbose=verbose,
        )
    finally:
        if not reselected:
            # 空なら選択を解除する。
            original_selection.select()
        cmds.undoInfo(closeChunk=True)
    return result


def _auto_two_influence_band_smooth(
        mesh,
        bottom_influence,
        top_influence,
        skin_cluster,
        axis,
        bottom_range,
        top_range,
        smooth_weights,
        smooth_iterations,
        smooth_passes,
        reselect_middle,
        verbose):
    """auto_two_influence_band_smooth の本体です。

    Args:
        mesh: auto_two_influence_band_smooth と同じ。
        bottom_influence: auto_two_influence_band_smooth と同じ。
        top_influence: auto_two_influence_band_smooth と同じ。
        skin_cluster: auto_two_influence_band_smooth と同じ。
        axis: auto_two_influence_band_smooth と同じ。
        bottom_range: auto_two_influence_band_smooth と同じ。
        top_range: auto_two_influence_band_smooth と同じ。
        smooth_weights: auto_two_influence_band_smooth と同じ。
        smooth_iterations: auto_two_influence_band_smooth と同じ。
        smooth_passes: auto_two_influence_band_smooth と同じ。
        reselect_middle: auto_two_influence_band_smooth と同じ。
        verbose: auto_two_influence_band_smooth と同じ。

    Returns:
        tuple[dict | list[dict], bool]: 処理結果と、中間頂点を選択し直したかどうか。
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
        vtx_count = _get_mesh(target_mesh).getNumVertices()
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

        if not mlib.objExists(target_bottom_influence):
            raise RuntimeError(u'Bottom influence does not exist: {}'.format(target_bottom_influence))
        if not mlib.objExists(target_top_influence):
            raise RuntimeError(u'Top influence does not exist: {}'.format(target_top_influence))

        influences = _get_influence_names(target_skin_cluster)
        if target_bottom_influence not in influences:
            raise RuntimeError(u'{} is not connected to {}'.format(target_bottom_influence, target_skin_cluster))
        if target_top_influence not in influences:
            raise RuntimeError(u'{} is not connected to {}'.format(target_top_influence, target_skin_cluster))

        if not top_vertices:
            raise RuntimeError(u'No top vertices found: {}'.format(target_mesh))
        if not bottom_vertices:
            raise RuntimeError(u'No bottom vertices found: {}'.format(target_mesh))

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

        # 2. middle がある場合のみ smooth 実行
        if middle_vertices:
            mlib.select(middle_vertices)
            for _ in range(max(1, int(smooth_passes))):
                smooth_skincluster_weights(
                    skin_cluster=target_skin_cluster,
                    smooth_weights=smooth_weights,
                    max_iterations=smooth_iterations
                )
        elif verbose:
            cmds.warning(u'No middle vertices on {}. Skip smooth pass and keep endpoints fixed.'.format(target_mesh))

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

    reselected = False
    if reselect_middle and all_middle_vertices:
        mlib.select(all_middle_vertices)
        reselected = True

    if len(results) == 1:
        return results[0], reselected
    return results, reselected

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