import maya.cmds as cmds
import math
import inspect
import sys
from importlib import reload
import HTools.decorator.undo as undo; reload(undo)


DEFAULT_SHAPE_NAME = "controller1"
DEFAULT_DEGREE = 1


def _transform_point(point, tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0, sx=1.0, sy=1.0, sz=1.0):
    """Apply S->R->T transform to a 3D point.

    Note:
        Rotation order is X then Y then Z (xyz).

    Args:
        point: (x, y, z)
        tx,ty,tz: translate offsets
        rx,ry,rz: rotate offsets in degrees
        sx,sy,sz: scale factors
    """
    x, y, z = point

    # Scale
    x *= sx
    y *= sy
    z *= sz

    # Rotate (degrees -> radians)
    if rx or ry or rz:
        rx_r = math.radians(rx)
        ry_r = math.radians(ry)
        rz_r = math.radians(rz)

        cx, sx_sin = math.cos(rx_r), math.sin(rx_r)
        cy, sy_sin = math.cos(ry_r), math.sin(ry_r)
        cz, sz_sin = math.cos(rz_r), math.sin(rz_r)

        # X
        y, z = (y * cx - z * sx_sin), (y * sx_sin + z * cx)
        # Y
        x, z = (x * cy + z * sy_sin), (-x * sy_sin + z * cy)
        # Z
        x, y = (x * cz - y * sz_sin), (x * sz_sin + y * cz)

    # Translate
    x += tx
    y += ty
    z += tz
    return (x, y, z)


def _transform_points(points, tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0, sx=1.0, sy=1.0, sz=1.0):
    if (
        (tx, ty, tz, rx, ry, rz) == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        and (sx, sy, sz) == (1.0, 1.0, 1.0)
    ):
        return points
    return [_transform_point(p, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz) for p in points]


def _apply_trs_to_curve_cvs(curve_transform, tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0, sx=1.0, sy=1.0, sz=1.0):
    """Apply TRS to all CVs of the curve shapes under the given transform."""
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
    """ポイントリストからカーブを生成

    If a transform (or a nurbsCurve shape under it) is currently selected and it already has
    one or more nurbsCurve shapes, this function replaces only those nurbsCurve shapes with
    the newly generated curve shape, keeping the original transform.

    Args:
        points: ポイントリスト
        name: カーブの名前
        degree: カーブの次数
        tx,ty,tz: 位置オフセット
        rx,ry,rz: 回転オフセット（degree）
        sx,sy,sz: スケール係数
    Return:
        str: カーブオブジェクト名
    """
    points = _transform_points(points, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)
    knots = [i for i in range(len(points))]

    # If a transform with existing nurbsCurve shapes is selected, swap only the curve shapes.
    target_transform = None
    selected = cmds.ls(selection=True, long=True)
    print("selected:", selected)
    if selected:
        sel = selected[0]
        sel_type = cmds.nodeType(sel)
        print("sel_type:", sel_type)
        if sel_type == "transform":
            target_transform = sel
        elif sel_type == "nurbsCurve":
            parents = cmds.listRelatives(sel, parent=True, fullPath=True) or []
            print("parents:", parents)
            if parents and cmds.nodeType(parents[0]) == "transform":
                target_transform = parents[0]

    print("target_transform:", target_transform)
    if target_transform and cmds.objExists(target_transform):
        existing_curve_shapes = []
        for shape in (cmds.listRelatives(target_transform, shapes=True, fullPath=True) or []):
            if cmds.nodeType(shape) == "nurbsCurve":
                existing_curve_shapes.append(shape)

        if existing_curve_shapes:
            # Create a temporary curve transform, then parent its shape(s) under target_transform.
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


class Shape:
    """Base class for all shape groups."""
    pass


class Flat(Shape):
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
        """正三角形を計算で生成

        Args:
            side_length: 一辺の長さ
            name: カーブの名前
        """
        base_half = side_length * 0.5  # 底辺の半分
        height = side_length * math.sqrt(3) / 2  # 高さ
        height_front = height / 3  # 底辺のZ座標（前方）
        height_back = -height * 2 / 3  # 頂点のZ座標（後方）

        points = [
            (-base_half, 0, height_front),
            (base_half, 0, height_front),
            (0, 0, height_back),
            (-base_half, 0, height_front),
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

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
        """正方形を計算で生成

        Args:
            side_length: 一辺の長さ
            name: カーブの名前
        """
        half = side_length * 0.5
        points = [
            (half, 0, -half),  # 右下
            (-half, 0, -half),  # 左下
            (-half, 0, half),  # 左上
            (half, 0, half),  # 右上
            (half, 0, -half),  # 閉じる
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

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
        """十字形状を計算で生成

        Args:
            axis_length: 中心軸の全長
            line_width_ratio: 線幅の割合（中心軸に対する比率）
            name: カーブの名前
        """
        line_width = axis_length * line_width_ratio
        half_length = axis_length * 0.5
        half_width = line_width * 0.5
        points = [
            (half_width, 0, -half_width),
            (half_width, 0, -half_length),
            (-half_width, 0, -half_length),
            (-half_width, 0, -half_width),
            (-half_length, 0, -half_width),
            (-half_length, 0, half_width),
            (-half_width, 0, half_width),
            (-half_width, 0, half_length),
            (half_width, 0, half_length),
            (half_width, 0, half_width),
            (half_length, 0, half_width),
            (half_length, 0, -half_width),
            (half_width, 0, -half_width),
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

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
        """円を生成

        Args:
            diameter: 円の直径
            name: カーブの名前
        """
        radius = diameter / 2.0
        created = cmds.circle(c=(0, 0, 0), nr=(0, 1, 0), sw=360, r=radius, d=3, ut=0, tol=0.01, s=8, ch=0, n=name)
        curve_transform = created[0] if isinstance(created, (list, tuple)) and created else created
        _apply_trs_to_curve_cvs(curve_transform, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)
        return created


class Prisms(Shape):
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
        """正四角錐を計算で生成

        Args:
            base_side_length: 底面の一辺の長さ
            apex_height: 頂点の高さ
            name: カーブの名前
        """
        half = base_side_length * 0.5
        apex = (0, apex_height, 0)
        # 底面の4つの頂点（右後、左後、左前、右前）
        base_br = (half, 0, -half)  # 右後
        base_bl = (-half, 0, -half)  # 左後
        base_fl = (-half, 0, half)  # 左前
        base_fr = (half, 0, half)  # 右前

        points = [
            apex,
            base_br,
            base_bl,
            apex,
            base_fl,
            base_fr,
            apex,
            base_br,  # 底面の描画開始
            base_fr,
            base_fl,
            base_bl,
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def spear(
        length=1.0,
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
        """3D槍型を計算で生成

        Args:
            length: 各方向の長さ
            name: カーブの名前
        """
        points = [
            (0, length, 0),
            (0, 0, length),
            (0, -length, 0),
            (0, 0, -length),
            (0, length, 0),
            (0, -length, 0),
            (0, 0, 0),
            (0, 0, length),
            (0, 0, -length),
            (length, 0, 0),
            (0, 0, length),
            (-length, 0, 0),
            (0, 0, -length),
            (0, 0, length),
            (0, 0, 0),
            (-length, 0, 0),
            (length, 0, 0),
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def half_spear(
        length=1.0,
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
        """半分の槍型（上半球のみ）を計算で生成

        Args:
            length: 各方向の長さ
            name: カーブの名前
        """
        points = [
            (0, length, 0),
            (0, 0, length),
            (0, 0, -length),
            (0, length, 0),
            (-length, 0, 0),
            (length, 0, 0),
            (0, length, 0),
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

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
        """立方体を計算で生成

        Args:
            side_length: 立方体の一辺の長さ
            name: カーブの名前
        """
        half = side_length * 0.5
        points = [
            (half, half, half),
            (half, half, -half),
            (-half, half, -half),
            (-half, -half, -half),
            (half, -half, -half),
            (half, half, -half),
            (-half, half, -half),
            (-half, half, half),
            (half, half, half),
            (half, -half, half),
            (half, -half, -half),
            (-half, -half, -half),
            (-half, -half, half),
            (half, -half, half),
            (-half, -half, half),
            (-half, half, half),
        ]
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
        """ワイヤーフレーム球を計算で生成

        Args:
            diameter: 球の直径
            name: カーブの名前
        """
        radius = diameter / 2.0
        sqrt3_2 = radius * math.sqrt(3) / 2  # 0.866025
        sqrt1_2 = radius * math.sqrt(2) / 2  # 0.707107

        points = [
            (0, 0, radius),
            (0, radius * 0.5, sqrt3_2),
            (0, sqrt3_2, radius * 0.5),
            (0, radius, 0),
            (0, sqrt3_2, -radius * 0.5),
            (0, radius * 0.5, -sqrt3_2),
            (0, 0, -radius),
            (0, -radius * 0.5, -sqrt3_2),
            (0, -sqrt3_2, -radius * 0.5),
            (0, -radius, 0),
            (0, -sqrt3_2, radius * 0.5),
            (0, -radius * 0.5, sqrt3_2),
            (0, 0, radius),
            (sqrt1_2, 0, sqrt1_2),
            (radius, 0, 0),
            (sqrt1_2, 0, -sqrt1_2),
            (0, 0, -radius),
            (-sqrt1_2, 0, -sqrt1_2),
            (-radius, 0, 0),
            (-sqrt3_2, radius * 0.5, 0),
            (-radius * 0.5, sqrt3_2, 0),
            (0, radius, 0),
            (radius * 0.5, sqrt3_2, 0),
            (sqrt3_2, radius * 0.5, 0),
            (radius, 0, 0),
            (sqrt3_2, -radius * 0.5, 0),
            (radius * 0.5, -sqrt3_2, 0),
            (0, -radius, 0),
            (-radius * 0.5, -sqrt3_2, 0),
            (-sqrt3_2, -radius * 0.5, 0),
            (-radius, 0, 0),
            (-sqrt1_2, 0, sqrt1_2),
            (0, 0, radius),
        ]
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
        """多角柱を計算で生成

        Args:
            diameter: 底面の多角形の直径
            length: 多角柱の全長
            sides: 底面の頂点数
            name: カーブの名前
        """
        radius = diameter / 2.0
        height = length / 2.0  # 高さの半分

        # 底面の頂点を計算
        angle_step = 2.0 * math.pi / sides
        top_vertices = []
        bottom_vertices = []
        for i in range(sides):
            angle = i * angle_step
            x = radius * math.cos(angle)
            z = radius * math.sin(angle)
            top_vertices.append((x, height, z))
            bottom_vertices.append((x, -height, z))

        # 多角柱の辺を描画
        points = []

        # 上面と下面、側面の縦線を交互に描画
        for i in range(sides):
            current_top = top_vertices[i]
            next_top = top_vertices[(i + 1) % sides]
            current_bottom = bottom_vertices[i]
            next_bottom = bottom_vertices[(i + 1) % sides]

            # 上面の辺 → 縦線（下へ） → 下面の辺 → 縦線（上へ）
            points.extend([current_top, next_top, next_bottom, current_bottom, current_top])

        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def hexagon(
        diameter=1.0,
        length=1.0,
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
        """六角柱を生成（互換性のためprismを呼び出し）

        Args:
            diameter: 六角形の直径
            length: 六角柱の全長
            name: カーブの名前
        """
        return Prisms.prism(
            diameter=diameter,
            length=length,
            sides=6,
            name=name,
            tx=tx,
            ty=ty,
            tz=tz,
            rx=rx,
            ry=ry,
            rz=rz,
            sx=sx,
            sy=sy,
            sz=sz,
        )

    @staticmethod
    def rombus(
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
        """菱形（3D八面体）を計算で生成

        Args:
            edge_length: 八面体の一辺の長さ
            name: カーブの名前
        """
        # 八面体の辺の長さから中心から頂点までの距離を計算
        # edge_length = size * √2 なので size = edge_length / √2
        size = edge_length / math.sqrt(2)
        points = [
            (0, size, 0),
            (size, 0, 0),
            (0, 0, size),
            (-size, 0, 0),
            (0, 0, -size),
            (0, size, 0),
            (0, 0, size),
            (0, -size, 0),
            (0, 0, -size),
            (size, 0, 0),
            (0, size, 0),
            (-size, 0, 0),
            (0, -size, 0),
            (size, 0, 0),
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def cone(
        diameter=1.0,
        height=1.0,
        sides=10,
        name="helperCone",
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
        """多角錐を計算で生成

        Args:
            diameter: 底面の多角形の直径
            height: 錐の高さ（底面から頂点まで）
            sides: 底面の頂点数
            name: カーブの名前
        """
        base_radius = diameter / 2.0
        apex = (0, height, 0)

        # 底面の頂点を計算（角度ずつ）
        angle_step = 2.0 * math.pi / sides
        base_vertices = []
        for i in range(sides):
            angle = i * angle_step
            x = base_radius * math.cos(angle)
            z = base_radius * math.sin(angle)
            base_vertices.append((x, 0, z))

        # 錐の辺を描画（各底面の辺から頂点へ）
        points = []
        for i in range(sides):
            current = base_vertices[i]
            next_vertex = base_vertices[(i + 1) % sides]
            points.extend([current, next_vertex, apex])

        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)


class Direction(Shape):
    @staticmethod
    def dir_single_thin(
        length=1.0,
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
        """方向矢印（単一・細）を計算で生成

        Args:
            length: 矢印の全長（先端から後端まで）
            name: カーブの名前
        """
        # 全長に対する各部分の比率（元の値: tip=1.0, shaft=1.0, 合計=2.0）
        tip_length = length * 0.5  # 1.0 / 2.0
        shaft_length = length * 0.5  # 1.0 / 2.0
        head_width = length * 0.5  # 1.0 / 2.0

        points = [
            (0, 0, shaft_length),  # 後端
            (0, 0, -tip_length),  # 先端
            (-head_width, 0, 0),  # 頭部左
            (0, 0, -tip_length),  # 先端
            (head_width, 0, 0),  # 頭部右
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def dir_single_normal(
        length=1.0,
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
        """方向矢印（単一・通常）を計算で生成

        Args:
            length: 矢印の全長（先端から後端まで）
            name: カーブの名前
        """
        # 全長に対する各部分の比率（元の値: tip=1.0, shaft=1.0, 合計=2.0）
        # single_thinと同じ長さ比率で、軸の幅を追加
        tip_length = length * 0.5  # 1.0 / 2.0
        shaft_length = length * 0.5  # 1.0 / 2.0
        head_width = length * 0.5  # 1.0 / 2.0
        shaft_width = length * 0.166667  # head_widthの1/3

        points = [
            (0, 0, -tip_length),  # 矢印の先端
            (-head_width, 0, 0),  # 頭部左
            (-shaft_width, 0, 0),  # 軸の左
            (-shaft_width, 0, shaft_length),  # 軸の後端左
            (shaft_width, 0, shaft_length),  # 軸の後端右
            (shaft_width, 0, 0),  # 軸の右
            (head_width, 0, 0),  # 頭部右
            (0, 0, -tip_length),  # 閉じる
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def dir_double_thin(
        length=1.0,
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
        """方向矢印（両方向・細）を計算で生成

        Args:
            length: 矢印の全長（先端から先端まで）
            name: カーブの名前
        """
        # 全長に対する各部分の比率（元の値: tip=2.0, shaft_end=1.0, 片側合計=2.0）
        tip_length = length * 0.5  # 2.0 / 4.0（両側合計）
        shaft_end = length * 0.25  # 1.0 / 4.0
        head_width = length * 0.25  # 1.0 / 4.0

        points = [
            (head_width, 0, shaft_end),
            (0, 0, tip_length),
            (-head_width, 0, shaft_end),
            (0, 0, tip_length),
            (0, 0, -tip_length),
            (-head_width, 0, -shaft_end),
            (0, 0, -tip_length),
            (head_width, 0, -shaft_end),
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def dir_double_normal(
        length=1.0,
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
        """方向矢印（両方向・通常）を計算で生成

        Args:
            length: 矢印の全長（先端から先端まで）
            name: カーブの名前
        """
        # 全長に対する各部分の比率（元の値: tip=2.31, shaft=0.99, 片側合計=2.31）
        tip_length = length * 0.5  # 2.31 / 4.62（両側合計）
        shaft_length = length * 0.214286  # 0.99 / 4.62
        head_width = length * 0.214286  # 0.99 / 4.62
        shaft_width = length * 0.071429  # 0.33 / 4.62

        points = [
            (0, 0, -tip_length),  # 前方先端
            (-head_width, 0, -shaft_length),  # 前方頭部左
            (-shaft_width, 0, -shaft_length),  # 前方軸左
            (-shaft_width, 0, shaft_length),  # 後方軸左
            (-head_width, 0, shaft_length),  # 後方頭部左
            (0, 0, tip_length),  # 後方先端
            (head_width, 0, shaft_length),  # 後方頭部右
            (shaft_width, 0, shaft_length),  # 後方軸右
            (shaft_width, 0, -shaft_length),  # 前方軸右
            (head_width, 0, -shaft_length),  # 前方頭部右
            (0, 0, -tip_length),  # 閉じる
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def dir_four_thin(
        length=1.0,
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
        """方向矢印（4方向・細）を計算で生成

        Args:
            length: 矢印1本の全長（中心から先端まで）
            name: カーブの名前
        """
        # 全長に対する各部分の比率（元の値: tip=1.75, shaft_end=1.25）
        tip_length = length  # 中心から先端まで
        shaft_end = length * 0.714286  # 1.25 / 1.75
        head_width = length * 0.285714  # 0.5 / 1.75

        points = [
            (shaft_end, 0, -head_width),  # +X矢印開始
            (tip_length, 0, 0),
            (shaft_end, 0, head_width),
            (tip_length, 0, 0),
            (-tip_length, 0, 0),  # -X矢印
            (-shaft_end, 0, -head_width),
            (-tip_length, 0, 0),
            (-shaft_end, 0, head_width),
            (-tip_length, 0, 0),
            (0, 0, 0),  # 中心に戻る
            (0, 0, tip_length),  # +Z矢印
            (-head_width, 0, shaft_end),
            (0, 0, tip_length),
            (head_width, 0, shaft_end),
            (0, 0, tip_length),
            (0, 0, -tip_length),  # -Z矢印
            (head_width, 0, -shaft_end),
            (0, 0, -tip_length),
            (-head_width, 0, -shaft_end),
            (0, 0, -tip_length),
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def dir_four_normal(
        length=1.0,
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
        """方向矢印（4方向・通常）を計算で生成

        Args:
            length: 矢印1本の全長（中心から先端まで）
            name: カーブの名前
        """
        # 全長に対する各部分の比率（元の値: tip=1.98, shaft=1.32）
        tip_length = length  # 中心から先端まで
        shaft_length = length * 0.666667  # 1.32 / 1.98
        head_width = length * 0.25  # 0.495 / 1.98
        shaft_width = length * 0.083333  # 0.165 / 1.98

        points = [
            (0, 0, -tip_length),  # -Z先端
            (-head_width, 0, -shaft_length),  # -Z頭部左
            (-shaft_width, 0, -shaft_length),  # -Z軸左
            (-shaft_width, 0, -shaft_width),  # クロス中心左下
            (-shaft_length, 0, -shaft_width),  # -X軸下
            (-shaft_length, 0, -head_width),  # -X頭部下
            (-tip_length, 0, 0),  # -X先端
            (-shaft_length, 0, head_width),  # -X頭部上
            (-shaft_length, 0, shaft_width),  # -X軸上
            (-shaft_width, 0, shaft_width),  # クロス中心左上
            (-shaft_width, 0, shaft_length),  # +Z軸左
            (-head_width, 0, shaft_length),  # +Z頭部左
            (0, 0, tip_length),  # +Z先端
            (head_width, 0, shaft_length),  # +Z頭部右
            (shaft_width, 0, shaft_length),  # +Z軸右
            (shaft_width, 0, shaft_width),  # クロス中心右上
            (shaft_length, 0, shaft_width),  # +X軸上
            (shaft_length, 0, head_width),  # +X頭部上
            (tip_length, 0, 0),  # +X先端
            (shaft_length, 0, -head_width),  # +X頭部下
            (shaft_length, 0, -shaft_width),  # +X軸下
            (shaft_width, 0, -shaft_width),  # クロス中心右下
            (shaft_width, 0, -shaft_length),  # -Z軸右
            (head_width, 0, -shaft_length),  # -Z頭部右
            (0, 0, -tip_length),  # 閉じる
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)


class Rotation(Shape):
    @staticmethod
    def rot_180_thin(
        diameter=1.0,
        arrow_offset=0.35,
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
        """回転矢印（180度・細）を計算で生成

        Args:
            diameter: 円弧の直径
            arrow_offset: 矢印の突出量
            name: カーブの名前
        """
        # 直径から半径を計算
        radius = diameter / 2.0

        # 矢印の先端・羽の計算
        arrow_tip_offset = arrow_offset * 1.351664  # 0.446514 = 0.35 * 1.276
        arrow_wing_x = arrow_offset * 0.0305837  # 0.0107043
        arrow_wing_z_outer = radius * 1.001418
        arrow_wing_z_inner = radius * 0.5442

        # 円弧上の点（180度の円弧）
        # 角度を使って計算
        points = [
            (-arrow_offset - arrow_tip_offset, 0, -radius * 1.351664),  # 上側矢印先端
            (arrow_wing_x, 0, -arrow_wing_z_outer),  # 上側矢印羽外
            (-arrow_offset + 0.106972, 0, -arrow_wing_z_inner),  # 上側矢印羽内
            (arrow_wing_x, 0, -arrow_wing_z_outer),  # 上側矢印羽外に戻る
            (-radius * 0.13006, 0, -radius),  # 円弧開始
            (-radius * 0.393028, 0, -radius * 0.947932),
            (-radius * 0.725413, 0, -radius * 0.725516),
            (-radius * 0.947961, 0, -radius * 0.392646),
            (-radius * 1.026019, 0, 0),  # 円弧中心
            (-radius * 0.947961, 0, radius * 0.392646),
            (-radius * 0.725413, 0, radius * 0.725516),
            (-radius * 0.393028, 0, radius * 0.947932),
            (-radius * 0.13006, 0, radius),  # 円弧終了
            (0, 0, radius),  # 下側矢印軸
            (-arrow_offset + 0.106972, 0, arrow_wing_z_inner),  # 下側矢印羽内
            (0, 0, radius),  # 下側矢印軸に戻る
            (-arrow_offset - arrow_tip_offset, 0, radius * 1.351664),  # 下側矢印先端
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def rot_180_normal(
        outer_radius=1.063053,
        inner_radius=0.961797,
        arrow_width=0.251045,
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
        """回転矢印（180度・通常）を計算で生成

        Args:
            outer_radius: 外側円弧の半径
            inner_radius: 内側円弧の半径
            arrow_width: 矢印の幅
            name: カーブの名前
        """
        points = [
            (-arrow_width, 0, -outer_radius * 1.015808),  # 上側矢印先端(外)
            (-arrow_width - 0.510789, 0, -outer_radius * 0.979696),  # 上側矢印羽(外)
            (-arrow_width - 0.235502, 0, -outer_radius * 0.930468),  # 上側矢印(外)
            (-arrow_width - 0.319691, 0, -outer_radius * 0.886448),  # 上側(外)
            (-arrow_width - 0.476815, 0, -outer_radius * 0.774834),
            (-arrow_width - 0.658256, 0, -outer_radius * 0.550655),
            (-arrow_width - 0.772854, 0, -outer_radius * 0.285854),
            (-outer_radius, 0, 0),  # 外側円弧中心
            (-arrow_width - 0.772854, 0, outer_radius * 0.285854),
            (-arrow_width - 0.658256, 0, outer_radius * 0.550655),
            (-arrow_width - 0.476815, 0, outer_radius * 0.774834),
            (-arrow_width - 0.319691, 0, outer_radius * 0.886448),
            (-arrow_width - 0.235502, 0, outer_radius * 0.930468),
            (-arrow_width - 0.510789, 0, outer_radius * 0.979696),
            (-arrow_width, 0, outer_radius * 1.015808),  # 下側矢印先端(外)
            (-arrow_width - 0.247870, 0, inner_radius * 0.567734),  # 下側矢印(内)
            (-arrow_width - 0.189157, 0, inner_radius * 0.841857),
            (-arrow_width - 0.265310, 0, inner_radius * 0.802034),
            (-arrow_width - 0.407533, 0, inner_radius * 0.701014),
            (-arrow_width - 0.571631, 0, inner_radius * 0.498232),
            (-arrow_width - 0.675354, 0, inner_radius * 0.258619),
            (-inner_radius, 0, 0),  # 内側円弧中心
            (-arrow_width - 0.675354, 0, -inner_radius * 0.258619),
            (-arrow_width - 0.571631, 0, -inner_radius * 0.498232),
            (-arrow_width - 0.407533, 0, -inner_radius * 0.701014),
            (-arrow_width - 0.265310, 0, -inner_radius * 0.802034),
            (-arrow_width - 0.189157, 0, -inner_radius * 0.841857),
            (-arrow_width - 0.247870, 0, -inner_radius * 0.567734),
            (-arrow_width, 0, -outer_radius * 1.015808),  # 閉じる
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)


class Special(Shape):
    @staticmethod
    def arrows_on_ball(
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
        """球面上の矢印（4方向）を計算で生成

        Args:
            diameter: 仕上がり直径
            name: カーブの名前
        """
        # 直径指定に合わせてスケール
        base_radius = 1.001567
        base_depth = 0.954001
        base_arrow_base_height = 0.35
        base_arrow_width = 0.0959835

        radius = diameter / 2.0
        scale = radius / base_radius
        depth = base_depth * scale
        arrow_base_height = base_arrow_base_height * scale
        arrow_width = base_arrow_width * scale

        # 比率の計算（元の値から）
        mid_height = arrow_base_height + (depth - arrow_base_height) * 0.5  # ≈ 0.677886
        high_height = mid_height + (depth - mid_height) * 0.5  # ≈ 0.850458

        # 矢印の羽の外側距離 (336638 / 1.001567 ≈ 0.3359)
        arrow_outer_offset = radius * 0.3359
        # 矢印の羽の内側距離 (500783 / 1.001567 ≈ 0.4995)
        arrow_inner_offset = radius * 0.4995
        # 矢印の側面矢印 (751175 / 1.001567 ≈ 0.7499)
        arrow_side = radius * 0.7499

        points = [
            (0, arrow_base_height, -radius),
            (-arrow_outer_offset, mid_height, -arrow_side),
            (-arrow_width, mid_height, -arrow_side),
            (-arrow_width, high_height, -arrow_inner_offset),
            (-arrow_width, depth, -arrow_width),
            (-arrow_inner_offset, high_height, -arrow_width),
            (-arrow_side, mid_height, -arrow_width),
            (-arrow_side, mid_height, -arrow_outer_offset),
            (-radius, arrow_base_height, 0),
            (-arrow_side, mid_height, arrow_outer_offset),
            (-arrow_side, mid_height, arrow_width),
            (-arrow_inner_offset, high_height, arrow_width),
            (-arrow_width, depth, arrow_width),
            (-arrow_width, high_height, arrow_inner_offset),
            (-arrow_width, mid_height, arrow_side),
            (-arrow_outer_offset, mid_height, arrow_side),
            (0, arrow_base_height, radius),
            (arrow_outer_offset, mid_height, arrow_side),
            (arrow_width, mid_height, arrow_side),
            (arrow_width, high_height, arrow_inner_offset),
            (arrow_width, depth, arrow_width),
            (arrow_inner_offset, high_height, arrow_width),
            (arrow_side, mid_height, arrow_width),
            (arrow_side, mid_height, arrow_outer_offset),
            (radius, arrow_base_height, 0),
            (arrow_side, mid_height, -arrow_outer_offset),
            (arrow_side, mid_height, -arrow_width),
            (arrow_inner_offset, high_height, -arrow_width),
            (arrow_width, depth, -arrow_width),
            (arrow_width, high_height, -arrow_inner_offset),
            (arrow_width, mid_height, -arrow_side),
            (arrow_outer_offset, mid_height, -arrow_side),
            (0, arrow_base_height, -radius),
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)

    @staticmethod
    def aim2(
        arrow_length=1.0,
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
        """Aim用マーカー（十字形）を計算で生成

        Args:
            arrow_length: 矢印の長さ
            name: カーブの名前
        """
        half = arrow_length * 0.5
        points = [
            (0, 0, half),
            (0, 0, -half),
            (0, half, 0),
            (0, -half, 0),
            (0, 0, -half),
            (half, 0, 0),
            (-half, 0, 0),
            (0, 0, -half),
        ]
        return _curve(points, name, tx=tx, ty=ty, tz=tz, rx=rx, ry=ry, rz=rz, sx=sx, sy=sy, sz=sz)
    

def get_shape_classes():
    """モジュール内のすべてのシェイプクラスを取得

    Returns:
        {section_key: class} 形式の辞書
    """
    classes = {}
    for name, cls in inspect.getmembers(sys.modules[__name__], inspect.isclass):
        if name in {"Shape"}:
            continue
        if not name.startswith('_'):  # private classを除外
            classes[name.lower()] = cls
    return classes