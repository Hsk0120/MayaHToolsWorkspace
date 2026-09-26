"""コントローラ用カーブ形状の生成ライブラリ。

形状はすべて寸法の引数から計算して求め、次数1(折れ線)の nurbsCurve として作成する
(``Planar.circle`` のみ Maya の ``circle`` コマンドで次数3のカーブを作る)。
形状の組み立て方は次の3通り。

* 閉じた輪郭: 外周の点列を1周させる(平面図形、輪郭で描く矢印)。
* ワイヤーフレーム: 線分の集合を :func:`_trace_strokes` で1本の折れ線にまとめる
  (立体、線だけで描く矢印)。
* 巻き付け: 平面上の輪郭を球面へ写す(``Markers.sphere_arrows``)。

座標系は Y 軸が上で、平面図形は XZ 平面に置く。向きを持つ矢印は既定で -Z を指す。

形状は :class:`Shape` を継承したセクションクラスの公開 staticmethod として定義し、
UI(``HTools/rigging/controllerShapeManagerUI.py``)は :func:`get_shape_classes` と
:func:`get_shape_functions` で得た順にタブとボタンを並べる。どの形状関数も、形状ごとの
寸法の引数に加えて次の共通引数を受け取る。

* ``name`` (str): 作成するカーブの名前。
* ``tx``, ``ty``, ``tz`` (float): CV に加える平行移動。
* ``rx``, ``ry``, ``rz`` (float): CV に加える回転(度、X→Y→Z の順に適用)。
* ``sx``, ``sy``, ``sz`` (float): CV に加えるスケール。

戻り値は作成(または形状を差し替え)したカーブの transform 名。ただし ``Planar.circle``
だけは ``cmds.circle`` の戻り値(transform 名を先頭に含むリスト)をそのまま返す。
"""

import inspect
import itertools
import math
import sys
from collections import deque
from importlib import reload

import maya.cmds as cmds

import hlib.decorators.undo as undo
reload(undo)


DEFAULT_SHAPE_NAME = "ctrlCurve"
DEFAULT_DEGREE = 1

# XZ 平面上の角度は +X を 0 として +Z へ向かう向きを正とする(ラジアン)。
_TOWARD_MINUS_Z = -0.5 * math.pi

# 円弧を折れ線で近似するときの1区間の最大角度。
_ARC_STEP = math.radians(10.0)

# 球のワイヤーフレームで、大円1周を分割するときの1区間の角度。
_SPHERE_RING_STEP = math.radians(15.0)

# 放射状の形状で、1本の腕が隣の腕との中間線までの角度のうち、どれだけを使ってよいかの割合。
# 腕の本数が多く外形がこれを超える場合は、腕の幅だけを狭めて隣の腕と重ならないようにする。
_SECTOR_FILL = 0.8

# 球面の矢印: 矢の先端が球の頂点から何度下った位置に来るか。
_SPHERE_ARROW_REACH = math.radians(65.0)


# ---------------------------------------------------------------------------
# 変換
# ---------------------------------------------------------------------------
def _transform_point(point, tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0, sx=1.0, sy=1.0, sz=1.0):
    """1点へスケール→回転→平行移動の順で変換を適用します。

    Args:
        point (tuple[float, float, float]): 入力座標。
        tx, ty, tz (float): 平行移動量。
        rx, ry, rz (float): 回転角(度)。X→Y→Z の順に適用する。
        sx, sy, sz (float): スケール係数。

    Returns:
        tuple[float, float, float]: 変換後の座標。
    """
    x, y, z = point

    x *= sx
    y *= sy
    z *= sz

    if rx or ry or rz:
        cos_x, sin_x = math.cos(math.radians(rx)), math.sin(math.radians(rx))
        cos_y, sin_y = math.cos(math.radians(ry)), math.sin(math.radians(ry))
        cos_z, sin_z = math.cos(math.radians(rz)), math.sin(math.radians(rz))

        y, z = (y * cos_x - z * sin_x), (y * sin_x + z * cos_x)
        x, z = (x * cos_y + z * sin_y), (-x * sin_y + z * cos_y)
        x, y = (x * cos_z - y * sin_z), (x * sin_z + y * cos_z)

    return (x + tx, y + ty, z + tz)


def _transform_points(points, tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0, sx=1.0, sy=1.0, sz=1.0):
    """点列へまとめて変換を適用します。

    Args:
        points (list[tuple[float, float, float]]): 入力点列。
        tx, ty, tz (float): 平行移動量。
        rx, ry, rz (float): 回転角(度)。
        sx, sy, sz (float): スケール係数。

    Returns:
        list[tuple[float, float, float]]: 変換後の点列。変換が無い場合は入力をそのまま返す。
    """
    if (
        (tx, ty, tz, rx, ry, rz) == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        and (sx, sy, sz) == (1.0, 1.0, 1.0)
    ):
        return points
    return [_transform_point(p, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz) for p in points]


def _apply_trs_to_curve_cvs(curve_transform, tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0, sx=1.0, sy=1.0, sz=1.0):
    """transform 配下の全 nurbsCurve の CV へ変換を適用します。

    Args:
        curve_transform (str): 対象の transform。
        tx, ty, tz (float): 平行移動量。
        rx, ry, rz (float): 回転角(度)。
        sx, sy, sz (float): スケール係数。
    """
    if not curve_transform or not cmds.objExists(curve_transform):
        return
    if (
        (tx, ty, tz, rx, ry, rz) == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        and (sx, sy, sz) == (1.0, 1.0, 1.0)
    ):
        return

    shapes = cmds.listRelatives(curve_transform, shapes=True, fullPath=True) or []
    for shape in shapes:
        if cmds.nodeType(shape) != "nurbsCurve":
            continue
        cvs = cmds.ls(f"{shape}.cv[*]", flatten=True) or []
        for cv in cvs:
            pos = cmds.pointPosition(cv, local=True)
            new_pos = _transform_point(pos, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)
            cmds.xform(cv, objectSpace=True, absolute=True, translation=new_pos)


# ---------------------------------------------------------------------------
# カーブ作成
# ---------------------------------------------------------------------------
@undo.undo_chunk()
def _curve(
    points,
    name=DEFAULT_SHAPE_NAME,
    degree=DEFAULT_DEGREE,
    tx=0.0,
    ty=0.0,
    tz=0.0,
    rx=0.0,
    ry=0.0,
    rz=0.0,
    sx=1.0,
    sy=1.0,
    sz=1.0,
):
    """点列からカーブを作成します。

    transform(またはその配下の nurbsCurve シェイプ)を選択していて、その transform が
    nurbsCurve シェイプを持つ場合は、transform を残したまま nurbsCurve シェイプだけを
    新しい形状へ差し替えます。

    Args:
        points (list[tuple[float, float, float]]): CV の座標列。
        name (str): 新規作成時のカーブ名。
        degree (int): カーブの次数。
        tx, ty, tz (float): 平行移動量。
        rx, ry, rz (float): 回転角(度)。
        sx, sy, sz (float): スケール係数。

    Returns:
        str: 作成した、または形状を差し替えた transform 名。
    """
    points = _transform_points(points, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)
    knots = list(range(len(points)))

    target_transform = None
    selected = cmds.ls(selection=True, long=True)
    if selected:
        sel = selected[0]
        sel_type = cmds.nodeType(sel)
        if sel_type == "transform":
            target_transform = sel
        elif sel_type == "nurbsCurve":
            parents = cmds.listRelatives(sel, parent=True, fullPath=True) or []
            if parents and cmds.nodeType(parents[0]) == "transform":
                target_transform = parents[0]

    if target_transform and cmds.objExists(target_transform):
        existing_curve_shapes = [
            shape
            for shape in (cmds.listRelatives(target_transform, shapes=True, fullPath=True) or [])
            if cmds.nodeType(shape) == "nurbsCurve"
        ]

        if existing_curve_shapes:
            # 一時カーブを作り、そのシェイプを選択中の transform の下へ移す。
            temp_curve_transform = cmds.curve(degree=degree, point=points, knot=knots, name=f"{name}__tmp")
            temp_shapes = [
                s
                for s in (cmds.listRelatives(temp_curve_transform, shapes=True, fullPath=True) or [])
                if cmds.nodeType(s) == "nurbsCurve"
            ]

            for old_shape in existing_curve_shapes:
                if cmds.objExists(old_shape):
                    cmds.delete(old_shape)

            for new_shape in temp_shapes:
                if cmds.objExists(new_shape):
                    cmds.parent(new_shape, target_transform, shape=True, relative=True)

            if cmds.objExists(temp_curve_transform):
                try:
                    cmds.delete(temp_curve_transform)
                except Exception:
                    pass

            return target_transform

    return cmds.curve(degree=degree, point=points, knot=knots, name=name)


# ---------------------------------------------------------------------------
# 幾何ヘルパー
# ---------------------------------------------------------------------------
def _on_xz(radius, angle, y=0.0):
    """XZ 平面上で、原点から距離 radius・角度 angle(ラジアン)の位置を返します。"""
    return (radius * math.cos(angle), y, radius * math.sin(angle))


def _closed(points):
    """始点を末尾に加えて閉じた点列を返します。"""
    points = list(points)
    return points + [points[0]]


def _polygon(radius, sides, start_angle=0.0, y=0.0):
    """XZ 平面に平行な正多角形の頂点列(閉じていない)を返します。

    Args:
        radius (float): 外接円の半径。
        sides (int): 頂点数。
        start_angle (float): 最初の頂点の角度(ラジアン)。
        y (float): 多角形を置く高さ。
    """
    step = 2.0 * math.pi / sides
    return [_on_xz(radius, start_angle + step * i, y) for i in range(sides)]


def _arc(radius, start, end, max_step=_ARC_STEP, y=0.0):
    """XZ 平面上の円弧を折れ線で近似した点列(両端を含む)を返します。

    Args:
        radius (float): 半径。
        start (float): 開始角(ラジアン)。
        end (float): 終了角(ラジアン)。
        max_step (float): 1区間の最大角度(ラジアン)。
        y (float): 円弧を置く高さ。
    """
    count = max(1, int(math.ceil(abs(end - start) / max_step - 1e-9)))
    angles = [start + (end - start) * i / float(count) for i in range(count)] + [end]
    return [_on_xz(radius, angle, y) for angle in angles]


def _subdivide(points, max_length):
    """各区間の長さが max_length 以下になるよう、線分の途中へ点を補います。"""
    result = [tuple(points[0])]
    for a, b in zip(points, points[1:]):
        length = math.sqrt(sum((q - p) ** 2 for p, q in zip(a, b)))
        count = max(1, int(math.ceil(length / max_length - 1e-9)))
        for i in range(1, count + 1):
            t = i / float(count)
            result.append(tuple(p + (q - p) * t for p, q in zip(a, b)))
    return result


def _arm_point(angle, along, across):
    """向き angle の腕に沿った局所座標を XZ 平面上の位置へ変換します。

    Args:
        angle (float): 腕の向き(ラジアン)。
        along (float): 腕の向きへの距離。
        across (float): 腕の向きから +90 度回した向きへの距離。
    """
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return (along * cos_a - across * sin_a, 0.0, along * sin_a + across * cos_a)


def _sector_slope(arms):
    """放射状に並ぶ腕1本の外形に許す、幅方向と長さ方向の比の上限を返します。

    隣の腕との中間線までの角度に :data:`_SECTOR_FILL` を掛けた角度の正接を上限とします。

    Args:
        arms (int): 腕の本数。

    Returns:
        float or None: ``across / along`` の上限。腕が2本以下なら隣の腕と向き合わないため ``None``。
    """
    if arms <= 2:
        return None
    return math.tan(math.pi / arms * _SECTOR_FILL)


def _radial_outline(arms, profile, root_half_width, start_angle=_TOWARD_MINUS_Z):
    """原点から等間隔に伸びる腕の外周を、閉じた点列で返します。

    腕が1本の場合は付け根側を直線で閉じます。腕が3本以上の場合は、隣り合う腕の付け根の
    辺どうしが交わる点を内側の角にします(2本の場合は辺が一直線につながるため角を置かない)。
    腕の外形が :func:`_sector_slope` の上限より広がる場合は、幅方向だけを一律に縮めて
    隣の腕と重ならないようにします。

    Args:
        arms (int): 腕の本数(1以上)。
        profile (list[tuple[float, float]]): 腕1本の外形を、across が負の側から先端を
            回って正の側へ向かう順に並べた局所座標 ``(along, across)`` の列。
        root_half_width (float): 腕の付け根の半幅。
        start_angle (float): 最初の腕の向き(ラジアン)。

    Returns:
        list[tuple[float, float, float]]: 閉じた点列。
    """
    slope_limit = _sector_slope(arms)
    if slope_limit is not None:
        slopes = [abs(across) / along for along, across in profile if along > 1e-9]
        widest = max(slopes) if slopes else 0.0
        if widest > slope_limit:
            narrow = slope_limit / widest
            profile = [(along, across * narrow) for along, across in profile]
            root_half_width *= narrow

    step = 2.0 * math.pi / arms
    points = []
    for index in range(arms):
        angle = start_angle + step * index
        if arms == 1:
            points.append(_arm_point(angle, 0.0, -root_half_width))
        points.extend(_arm_point(angle, along, across) for along, across in profile)
        if arms == 1:
            points.append(_arm_point(angle, 0.0, root_half_width))
        elif arms > 2:
            points.append(_on_xz(root_half_width / math.sin(step * 0.5), angle + step * 0.5))
    return _closed(points)


def _arrow_profile(length, head_length, head_width, shaft_width):
    """輪郭で描く矢印1本分の外形を、腕の局所座標で返します。

    Args:
        length (float): 付け根から先端までの長さ。
        head_length (float): 矢じりの長さ(length を上限とする)。
        head_width (float): 矢じりの幅。
        shaft_width (float): 軸の幅。
    """
    neck = length - min(max(head_length, 0.0), length)
    return [
        (neck, -shaft_width * 0.5),
        (neck, -head_width * 0.5),
        (length, 0.0),
        (neck, head_width * 0.5),
        (neck, shaft_width * 0.5),
    ]


def _arrow_strokes(arms, length, head_length, head_width, start_angle=_TOWARD_MINUS_Z):
    """線で描く矢印(軸線と V 字の矢じり)を、原点から放射状にストロークで返します。

    矢じりが :func:`_sector_slope` の上限より開く場合は、隣の矢じりと交わらないよう
    矢じりの幅を狭めます。

    Args:
        arms (int): 矢印の本数(1以上)。
        length (float): 原点から先端までの長さ。
        head_length (float): 矢じりの長さ(length を上限とする)。
        head_width (float): 矢じりの幅。
        start_angle (float): 最初の矢印の向き(ラジアン)。

    Returns:
        list[list[tuple[float, float, float]]]: ストロークの一覧。
    """
    neck = length - min(max(head_length, 0.0), length)
    half_head = head_width * 0.5
    slope_limit = _sector_slope(arms)
    if slope_limit is not None:
        half_head = min(half_head, neck * slope_limit)
    step = 2.0 * math.pi / arms
    strokes = []
    for index in range(arms):
        angle = start_angle + step * index
        tip = _arm_point(angle, length, 0.0)
        strokes.append([(0.0, 0.0, 0.0), tip])
        strokes.append([_arm_point(angle, neck, -half_head), tip, _arm_point(angle, neck, half_head)])
    return strokes


def _shift_z(points, offset):
    """点列を Z 方向へ offset だけ移動します。"""
    return [(x, y, z + offset) for x, y, z in points]


def _arc_span(radius, sweep, head_length):
    """-X 方向を中心にした円弧の開始角・終了角と、矢じり1つ分の角度を返します。

    Args:
        radius (float): 円弧の半径。
        sweep (float): 円弧の角度(度)。1〜360 に収める。
        head_length (float): 矢じりの長さ(円弧に沿った長さ)。

    Returns:
        tuple[float, float, float]: ``(開始角, 終了角, 矢じりの角度)``(ラジアン)。
            矢じりの角度は円弧の半分を上限とする。
    """
    span = math.radians(min(max(float(sweep), 1.0), 360.0))
    start = math.pi - span * 0.5
    end = math.pi + span * 0.5
    head_angle = max(head_length, 0.0) / radius if radius > 0.0 else 0.0
    return start, end, min(head_angle, span * 0.5)


def _wrap_onto_sphere(points, radius, angle_per_unit):
    """XZ 平面上の点を、原点からの距離に比例した角度だけ球の頂点から下った球面上へ写します。

    原点は球の頂点 ``(0, radius, 0)`` へ写り、原点から距離 d の点は元の方位を保ったまま
    頂点から ``d * angle_per_unit`` ラジアン下った位置へ写ります。

    Args:
        points (list[tuple[float, float, float]]): XZ 平面上の点列(Y は無視する)。
        radius (float): 球の半径。
        angle_per_unit (float): 平面上の距離1あたりの角度(ラジアン)。
    """
    wrapped = []
    for x, _y, z in points:
        planar = math.hypot(x, z)
        if planar < 1e-12:
            wrapped.append((0.0, radius, 0.0))
            continue
        polar = planar * angle_per_unit
        ring = radius * math.sin(polar) / planar
        wrapped.append((x * ring, radius * math.cos(polar), z * ring))
    return wrapped


def _bipyramid_strokes(radius, height, sides):
    """Y=0 の正多角形と、その各頂点から上下の頂点へ向かう稜線をストロークで返します。

    Args:
        radius (float): 中央の多角形の外接円の半径。
        height (float): 原点から上下それぞれの頂点までの距離。
        sides (int): 中央の多角形の頂点数(3以上)。

    Returns:
        list[list[tuple[float, float, float]]]: ストロークの一覧。
    """
    ring = _polygon(radius, sides)
    top = (0.0, height, 0.0)
    bottom = (0.0, -height, 0.0)
    return [_closed(ring)] + [[top, corner, bottom] for corner in ring]


def _shortest_route(links, source, targets):
    """幅優先探索で source から targets のいずれかへ至る最短の頂点列を返します。"""
    previous = {source: None}
    queue = deque([source])
    while queue:
        current = queue.popleft()
        if current in targets:
            route = []
            while current is not None:
                route.append(current)
                current = previous[current]
            return route[::-1]
        for neighbor, _edge in links[current]:
            if neighbor not in previous:
                previous[neighbor] = current
                queue.append(neighbor)
    raise ValueError("形状の線分がつながっていません。")


def _trace_strokes(strokes, precision=6):
    """複数の折れ線を、全ての線分を通る1本の連続した点列にまとめます。

    座標を precision 桁で丸めて一致する点は同じ頂点とみなし、重なる線分は1本にまとめます。
    一筆書きできない形は、次数が奇数の頂点を近いものどうしで組にし、その間の最短経路の線分を
    複製してから辿ります。複製した区間は同じ線分上を往復するだけなので、見た目は変わりません。

    Args:
        strokes (list[list[tuple[float, float, float]]]): 折れ線の一覧。
        precision (int): 頂点を同一視するときの丸め桁数。

    Returns:
        list[tuple[float, float, float]]: 連続した点列。寸法が0で全ての点が重なる場合は、
            その点を2つ並べた点列(長さ0のカーブになる)。

    Raises:
        ValueError: 点が無い、または線分が1つにつながっていない場合。
    """
    vertices = []
    index_by_key = {}

    def vertex_index(point):
        key = tuple(round(value, precision) for value in point)
        if key not in index_by_key:
            index_by_key[key] = len(vertices)
            vertices.append(tuple(point))
        return index_by_key[key]

    segments = []
    registered = set()
    for stroke in strokes:
        indices = [vertex_index(point) for point in stroke]
        for a, b in zip(indices, indices[1:]):
            key = (min(a, b), max(a, b))
            if a != b and key not in registered:
                registered.add(key)
                segments.append(key)
    if not segments:
        if not vertices:
            raise ValueError("形状に点がありません。")
        return [vertices[0], vertices[0]]

    links = [[] for _ in vertices]
    edge_total = [0]

    def link(a, b):
        edge = edge_total[0]
        edge_total[0] += 1
        links[a].append((b, edge))
        links[b].append((a, edge))

    for a, b in segments:
        link(a, b)

    # 奇数次数の頂点が2つ以下になるまで、近い組の間の経路を往復分として足す。
    odd = [v for v in range(len(vertices)) if len(links[v]) % 2]
    while len(odd) > 2:
        source = odd.pop(0)
        route = _shortest_route(links, source, set(odd))
        odd.remove(route[-1])
        for a, b in zip(route, route[1:]):
            link(a, b)

    # 各辺を1度ずつ通る経路を、行き止まりで巻き戻しながら組み立てる。
    used = [False] * edge_total[0]
    cursor = [0] * len(vertices)
    stack = [odd[0] if odd else segments[0][0]]
    walk = []
    while stack:
        current = stack[-1]
        options = links[current]
        while cursor[current] < len(options) and used[options[cursor[current]][1]]:
            cursor[current] += 1
        if cursor[current] == len(options):
            walk.append(stack.pop())
            continue
        neighbor, edge = options[cursor[current]]
        used[edge] = True
        stack.append(neighbor)

    if not all(used):
        raise ValueError("形状の線分がつながっていません。")
    walk.reverse()
    return [vertices[i] for i in walk]


# ---------------------------------------------------------------------------
# 形状
# ---------------------------------------------------------------------------
class Shape:
    """形状セクションの基底クラス。

    サブクラスの公開 staticmethod が1つの形状に対応します。``order`` は UI のタブの並び順です。
    """

    order = 0


class Planar(Shape):
    """XZ 平面に置く平面図形。"""

    order = 10

    @staticmethod
    def circle(
        diameter=1.0,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """円(Maya の circle コマンドによる次数3のカーブ)を作成します。

        選択中のカーブの形状を差し替える動作には対応しません。

        Args:
            diameter (float): 直径。

        Returns:
            list[str]: ``cmds.circle`` の戻り値(先頭が transform 名)。
        """
        # 法線を +Y にして XZ 平面に置く。次数・分割数などは circle コマンドの既定値を使う。
        created = cmds.circle(normal=(0, 1, 0), radius=diameter * 0.5, constructionHistory=False, name=name)
        curve_transform = created[0] if isinstance(created, (list, tuple)) and created else created
        _apply_trs_to_curve_cvs(curve_transform, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)
        return created

    @staticmethod
    def square(
        side_length=1.0,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """辺が X・Z 軸に平行な正方形を作成します。

        Args:
            side_length (float): 一辺の長さ。
        """
        corners = _polygon(side_length / math.sqrt(2.0), 4, math.radians(45.0))
        return _curve(_closed(corners), name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def triangle(
        side_length=1.0,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """重心が原点で、頂点の1つが -Z を指す正三角形を作成します。

        Args:
            side_length (float): 一辺の長さ。
        """
        corners = _polygon(side_length / math.sqrt(3.0), 3, _TOWARD_MINUS_Z)
        return _curve(_closed(corners), name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def cross(
        axis_length=1.0,
        line_width_ratio=0.3,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """X・Z 軸に沿った十字(プラス記号)の外形を作成します。

        Args:
            axis_length (float): 腕の端から反対側の端までの長さ。
            line_width_ratio (float): 腕の幅の axis_length に対する比率。
        """
        half_length = axis_length * 0.5
        half_width = axis_length * line_width_ratio * 0.5
        profile = [(half_length, -half_width), (half_length, half_width)]
        points = _radial_outline(4, profile, half_width)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)


class Solids(Shape):
    """立体のワイヤーフレーム。"""

    order = 20

    @staticmethod
    def cube(
        side_length=1.0,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """原点を中心とする立方体を作成します。

        Args:
            side_length (float): 一辺の長さ。
        """
        half = side_length * 0.5
        signs = list(itertools.product((-1.0, 1.0), repeat=3))
        # 符号が1成分だけ異なる頂点の組が立方体の辺になる。
        strokes = [
            [tuple(half * c for c in a), tuple(half * c for c in b)]
            for a, b in itertools.combinations(signs, 2)
            if sum(1 for p, q in zip(a, b) if p != q) == 1
        ]
        points = _trace_strokes(strokes)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def sphere(
        diameter=1.0,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """XY・YZ・XZ 平面の3つの大円で表した球を作成します。

        Args:
            diameter (float): 直径。
        """
        ring = _arc(diameter * 0.5, 0.0, 2.0 * math.pi, max_step=_SPHERE_RING_STEP)
        strokes = [
            ring,
            [(x, z, 0.0) for x, _y, z in ring],
            [(0.0, x, z) for x, _y, z in ring],
        ]
        points = _trace_strokes(strokes)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def pyramid(
        base_side_length=1.0,
        apex_height=1.0,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """底面が Y=0 にある正四角錐を作成します。

        Args:
            base_side_length (float): 底面の一辺の長さ。
            apex_height (float): 頂点の高さ。
        """
        base = _polygon(base_side_length / math.sqrt(2.0), 4, math.radians(45.0))
        apex = (0.0, apex_height, 0.0)
        strokes = [_closed(base)] + [[corner, apex] for corner in base]
        points = _trace_strokes(strokes)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def cone(
        diameter=1.0,
        height=1.0,
        sides=10,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """底面が Y=0 にある角錐を作成します。

        Args:
            diameter (float): 底面の外接円の直径。
            height (float): 頂点の高さ。
            sides (int): 底面の頂点数(3未満は3として扱う)。
        """
        base = _polygon(diameter * 0.5, max(3, int(sides)))
        apex = (0.0, height, 0.0)
        strokes = [_closed(base)] + [[corner, apex] for corner in base]
        points = _trace_strokes(strokes)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def prism(
        diameter=1.0,
        length=1.0,
        sides=6,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """Y 軸に沿った角柱を作成します。

        Args:
            diameter (float): 断面の外接円の直径。
            length (float): 全長。
            sides (int): 断面の頂点数(3未満は3として扱う)。
        """
        sides = max(3, int(sides))
        top = _polygon(diameter * 0.5, sides, y=length * 0.5)
        bottom = _polygon(diameter * 0.5, sides, y=-length * 0.5)
        strokes = [_closed(top), _closed(bottom)] + [[a, b] for a, b in zip(top, bottom)]
        points = _trace_strokes(strokes)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def octahedron(
        edge_length=1.0,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """頂点が各軸上にある正八面体を作成します。

        正八面体を、XZ 平面上の正方形と上下(±Y)の頂点からなる双角錐として組み立てます。

        Args:
            edge_length (float): 辺の長さ。
        """
        # 各軸上の頂点までの距離。隣り合う2頂点の間隔が edge_length になる。
        reach = edge_length / math.sqrt(2.0)
        points = _trace_strokes(_bipyramid_strokes(reach, reach, 4))
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def bipyramid(
        radius=0.4,
        height=1.0,
        sides=4,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """Y=0 の多角形から上下へ尖る双角錐を作成します。

        Args:
            radius (float): 中央の多角形の外接円の半径。
            height (float): 原点から上下それぞれの頂点までの距離。
            sides (int): 中央の多角形の頂点数(3未満は3として扱う)。
        """
        points = _trace_strokes(_bipyramid_strokes(radius, height, max(3, int(sides))))
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)


class Arrows(Shape):
    """XZ 平面に置く直線の矢印。1方向の矢印は -Z を指す。

    既定の寸法は、矢印1本(付け根から先端まで)の長さを1としたとき、矢じりの長さ 0.44・
    矢じりの幅 0.5・軸の幅 0.16 になるようにそろえている(矢じりの開き角は片側約30度)。
    """

    order = 30

    @staticmethod
    def arrow_thin(
        length=1.0,
        head_length=0.44,
        head_width=0.5,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """線で描く1方向の矢印を、全長の中点が原点に来るよう作成します。

        Args:
            length (float): 後端から先端までの長さ。
            head_length (float): 矢じりの長さ。
            head_width (float): 矢じりの幅。
        """
        strokes = [_shift_z(stroke, length * 0.5) for stroke in _arrow_strokes(1, length, head_length, head_width)]
        points = _trace_strokes(strokes)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def arrow(
        length=1.0,
        head_length=0.44,
        head_width=0.5,
        shaft_width=0.16,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """輪郭で描く1方向の矢印を、全長の中点が原点に来るよう作成します。

        Args:
            length (float): 後端から先端までの長さ。
            head_length (float): 矢じりの長さ。
            head_width (float): 矢じりの幅。
            shaft_width (float): 軸の幅。
        """
        profile = _arrow_profile(length, head_length, head_width, shaft_width)
        points = _shift_z(_radial_outline(1, profile, shaft_width * 0.5), length * 0.5)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def double_arrow_thin(
        length=1.0,
        head_length=0.22,
        head_width=0.25,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """線で描く、Z 軸の両方向を指す矢印を作成します。

        Args:
            length (float): 先端から反対側の先端までの長さ。
            head_length (float): 矢じりの長さ。
            head_width (float): 矢じりの幅。
        """
        points = _trace_strokes(_arrow_strokes(2, length * 0.5, head_length, head_width))
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def double_arrow(
        length=1.0,
        head_length=0.22,
        head_width=0.25,
        shaft_width=0.08,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """輪郭で描く、Z 軸の両方向を指す矢印を作成します。

        Args:
            length (float): 先端から反対側の先端までの長さ。
            head_length (float): 矢じりの長さ。
            head_width (float): 矢じりの幅。
            shaft_width (float): 軸の幅。
        """
        profile = _arrow_profile(length * 0.5, head_length, head_width, shaft_width)
        points = _radial_outline(2, profile, shaft_width * 0.5)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def radial_arrow_thin(
        length=1.0,
        arms=4,
        head_length=0.44,
        head_width=0.5,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """線で描く、原点から等間隔に広がる複数の矢印を作成します。

        Args:
            length (float): 原点から各先端までの長さ。
            arms (int): 矢印の本数(1未満は1として扱う)。本数が多く隣の矢印と重なる場合は、
                矢印の幅を自動で狭める。
            head_length (float): 矢じりの長さ。
            head_width (float): 矢じりの幅。
        """
        strokes = _arrow_strokes(max(1, int(arms)), length, head_length, head_width)
        points = _trace_strokes(strokes)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def radial_arrow(
        length=1.0,
        arms=4,
        head_length=0.44,
        head_width=0.5,
        shaft_width=0.16,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """輪郭で描く、原点から等間隔に広がる複数の矢印を作成します。

        Args:
            length (float): 原点から各先端までの長さ。
            arms (int): 矢印の本数(1未満は1として扱う)。本数が多く隣の矢印と重なる場合は、
                矢印の幅を自動で狭める。
            head_length (float): 矢じりの長さ。
            head_width (float): 矢じりの幅。
            shaft_width (float): 軸の幅。
        """
        profile = _arrow_profile(length, head_length, head_width, shaft_width)
        points = _radial_outline(max(1, int(arms)), profile, shaft_width * 0.5)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)


class Arcs(Shape):
    """XZ 平面に置く、両端に矢じりのある円弧(回転方向の表示用)。円弧は -X 側に置く。"""

    order = 40

    @staticmethod
    def arc_arrow_thin(
        radius=0.7,
        sweep=180,
        head_length=0.3,
        head_width=0.3,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """線で描く円弧の矢印を作成します。

        Args:
            radius (float): 円弧の半径。
            sweep (int): 円弧の角度(度、1〜360)。
            head_length (float): 矢じりの長さ(円弧に沿った長さ)。
            head_width (float): 矢じりの幅。
        """
        start, end, head_angle = _arc_span(radius, sweep, head_length)
        half_head = min(head_width * 0.5, radius * 0.95)
        strokes = [_arc(radius, start, end)]
        for tip_angle, neck_angle in ((start, start + head_angle), (end, end - head_angle)):
            strokes.append([
                _on_xz(radius + half_head, neck_angle),
                _on_xz(radius, tip_angle),
                _on_xz(radius - half_head, neck_angle),
            ])
        points = _trace_strokes(strokes)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def arc_arrow(
        radius=1.0,
        sweep=180,
        head_length=0.4,
        head_width=0.45,
        band_width=0.16,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """輪郭で描く円弧の矢印を作成します。

        Args:
            radius (float): 帯の中心線の半径。
            sweep (int): 先端から先端までの角度(度、1〜360)。
            head_length (float): 矢じりの長さ(中心線に沿った長さ)。
            head_width (float): 矢じりの幅。
            band_width (float): 円弧の帯の幅。
        """
        start, end, head_angle = _arc_span(radius, sweep, head_length)
        half_head = min(head_width * 0.5, radius * 0.95)
        half_band = min(band_width * 0.5, radius * 0.95)
        neck_start = start + head_angle
        neck_end = end - head_angle

        points = [_on_xz(radius, start), _on_xz(radius + half_head, neck_start)]
        points += _arc(radius + half_band, neck_start, neck_end)
        points += [
            _on_xz(radius + half_head, neck_end),
            _on_xz(radius, end),
            _on_xz(radius - half_head, neck_end),
        ]
        points += _arc(radius - half_band, neck_end, neck_start)
        points.append(_on_xz(radius - half_head, neck_start))
        return _curve(_closed(points), name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)


class Markers(Shape):
    """用途を表す目印の形状。"""

    order = 50

    @staticmethod
    def sphere_arrows(
        diameter=1.0,
        arms=4,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """球の上側に沿って曲がる、放射状の矢印の輪郭を作成します。

        平面上で作った放射状の矢印の輪郭を、中心が球の頂点(+Y)に来るよう球面へ巻き付けます。
        矢の先端は頂点から 65 度下った位置になります。

        Args:
            diameter (float): 巻き付ける球の直径。
            arms (int): 矢印の本数(1未満は1として扱う)。本数が多く隣の矢印と重なる場合は、
                矢印の幅を自動で狭める。
        """
        # 矢の長さを1とした平面上の輪郭(比率は Arrows の既定値と同じ)。区間を細かく分けてから
        # 巻き付け、球面に沿わせる。
        profile = _arrow_profile(1.0, 0.44, 0.5, 0.16)
        outline = _subdivide(_radial_outline(max(1, int(arms)), profile, 0.08), 0.2)
        points = _wrap_onto_sphere(outline, diameter * 0.5, _SPHERE_ARROW_REACH)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def aim(
        length=1.0,
        head_length=0.25,
        head_width=0.2,
        name=DEFAULT_SHAPE_NAME,
        tx=0.0,
        ty=0.0,
        tz=0.0,
        rx=0.0,
        ry=0.0,
        rz=0.0,
        sx=1.0,
        sy=1.0,
        sz=1.0,
    ):
        """3軸の線と、-Z 側の端に付けた四角錐の矢じりでエイム方向を示す目印を作成します。

        Args:
            length (float): 各軸の線の全長。
            head_length (float): 矢じりの長さ。
            head_width (float): 矢じりの底面の対角線の長さ。
        """
        half = length * 0.5
        origin = (0.0, 0.0, 0.0)
        strokes = [
            [(-half, 0.0, 0.0), origin, (half, 0.0, 0.0)],
            [(0.0, -half, 0.0), origin, (0.0, half, 0.0)],
            [(0.0, 0.0, half), origin, (0.0, 0.0, -half)],
        ]
        tip = (0.0, 0.0, -half)
        neck_z = -half + min(max(head_length, 0.0), length)
        spread = head_width * 0.5
        base = [(spread, 0.0, neck_z), (0.0, spread, neck_z), (-spread, 0.0, neck_z), (0.0, -spread, neck_z)]
        strokes.append(_closed(base))
        strokes.extend([corner, tip] for corner in base)
        points = _trace_strokes(strokes)
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)


# ---------------------------------------------------------------------------
# 形状の列挙
# ---------------------------------------------------------------------------
def get_shape_classes():
    """形状セクションのクラスを表示順に返します。

    Returns:
        dict[str, type]: ``{セクション名(クラス名の小文字): クラス}``。``order`` の昇順。
    """
    module = sys.modules[__name__]
    sections = [
        cls
        for _name, cls in inspect.getmembers(module, inspect.isclass)
        if issubclass(cls, Shape) and cls is not Shape and cls.__module__ == module.__name__
    ]
    sections.sort(key=lambda cls: (cls.order, cls.__name__))
    return {cls.__name__.lower(): cls for cls in sections}


def get_shape_functions(section_class):
    """セクションクラスに定義された形状関数を定義順に返します。

    Args:
        section_class (type): :func:`get_shape_classes` が返すクラス。

    Returns:
        list[tuple[str, callable]]: ``(形状名, 形状関数)`` のリスト。
    """
    return [
        (attr_name, getattr(section_class, attr_name))
        for attr_name, value in vars(section_class).items()
        if not attr_name.startswith("_") and isinstance(value, staticmethod)
    ]


def find_shape(name):
    """形状名から形状関数を返します。

    Args:
        name (str): 形状名(例: ``"cube"``、``"arc_arrow"``)。

    Returns:
        callable: 形状関数。

    Raises:
        KeyError: 該当する形状が無い場合。
    """
    for section_class in get_shape_classes().values():
        for shape_name, func in get_shape_functions(section_class):
            if shape_name == name:
                return func
    raise KeyError(f"形状が見つかりません: {name}")
