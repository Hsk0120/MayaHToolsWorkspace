"""モデル合わせ、形状転送、ガイドの表示を行う。"""

import math

import mlib
from maya import cmds
from mlib.common.units import convertDistance
from mlib.maths import Matrix, Vector
from mlib import getNode
from mlib.decorator import undoTransaction


def _point(item):
    """コンポーネント位置またはTransformの回転ピボットをワールド座標で返す。"""
    if "." in item:
        return Vector(cmds.pointPosition(item, world=True))
    return Vector(cmds.xform(item, query=True, worldSpace=True, rotatePivot=True))


@undoTransaction("mlrigPositionMarkers")
def markers(items, operation="individual"):
    """選択点に位置マーカーを配置する。"""
    if operation == "surfaceCentroid":
        total = 0.0
        weighted = Vector()
        for item in items:
            mesh = _mesh(item)
            positions = mesh.getPoints(ws=True)
            for triangle in mesh.getTriangles():
                a, b, c = (positions[index] for index in triangle)
                area = ((b - a) ^ (c - a)).length() * 0.5
                weighted += (a + b + c) * (area / 3.0)
                total += area
        if total <= 1e-12:
            raise ValueError("面積を持つメッシュを指定してください")
        factor = convertDistance(1.0, fromUnit="cm")
        points = [weighted * (factor / total)]
    else:
        points = [_point(item) for item in items]
    if not points:
        raise ValueError("マーカーの位置を選択してください")
    if operation == "average":
        points = [sum(points, Vector()) / len(points)]
    elif operation == "sum":
        points = [sum(points, Vector())]
    elif operation in ("boundsMin", "boundsMax", "boundsCenter"):
        low = Vector([min(p[i] for p in points) for i in range(3)])
        high = Vector([max(p[i] for p in points) for i in range(3)])
        points = [{"boundsMin": low, "boundsMax": high, "boundsCenter": (low + high) * 0.5}[operation]]
    elif operation not in ("individual", "surfaceCentroid"):
        raise ValueError("未対応の位置計算法です")
    result = []
    for point in points:
        marker = cmds.spaceLocator(name="positionMarker#")[0]
        cmds.xform(marker, worldSpace=True, translation=list(point))
        result.append(marker)
    return result


@undoTransaction("mlrigMeanPlane")
def meanPlane(items, xPairs, parent=None):
    """始点・終点の組からX・Zの平均方向を求め、中心に平面を置く。"""
    if len(items) % 2 or not 0 < xPairs < len(items) // 2:
        raise ValueError("X方向の点対、Z方向の点対の順に選択してください")
    points = [_point(item) for item in items]
    if parent:
        matrix = Matrix(cmds.xform(parent, query=True, matrix=True, worldSpace=True))
        if matrix.isSingular():
            raise ValueError("親のマトリクスが特異です")
        inverse = matrix.inverse()
        points = [inverse.transformPoint(p) for p in points]
    directions = [b - a for a, b in zip(points[::2], points[1::2])]
    x = sum(directions[:xPairs], Vector()).normal()
    z = sum(directions[xPairs:], Vector()).normal()
    y = (z ^ x).normal()
    if min(x.length(), y.length()) < 1e-8 or (z ^ x).length() < 1e-8:
        raise ValueError("平均方向が平行またはゼロです")
    center = sum(points, Vector()) / len(points)
    plane = cmds.polyPlane(name="guidePlane#", subdivisionsX=1, subdivisionsY=1, constructionHistory=False)[0]
    matrix = list(x) + [0] + list(y) + [0] + list(x ^ y) + [0] + list(center) + [1]
    if parent:
        plane = cmds.parent(plane, parent, relative=True)[0]
    cmds.xform(plane, objectSpace=True, matrix=matrix)
    return plane


@undoTransaction("mlrigGuideLine")
def line(nodes):
    """選択順に各Transformの原点を結び、入力に追従するカーブを作る。"""
    if len(nodes) < 2:
        raise ValueError("2つ以上の点を指定してください")
    curve = cmds.curve(degree=1, point=[(0, 0, 0)] * len(nodes), name="guideLine#")
    shape = cmds.listRelatives(curve, shapes=True, fullPath=True)[0]
    for i, item in enumerate(nodes):
        source = None
        fixed = None
        if "." in item and cmds.attributeQuery(item.split(".", 1)[1].partition("[")[0], node=item.split(".", 1)[0], exists=True) and cmds.getAttr(item, type=True, silent=True) in ("double3", "float3"):
            source = item
        elif "." in item:
            fixed = _point(item)
        else:
            dag = getNode(item)
            if not cmds.objectType(item, isAType="transform"):
                raise ValueError("トランスフォーム、点、ワールド位置Plugを指定してください")
            pos = mlib.createNode("decomposeMatrix", name="guideLinePosition#").getName()
            cmds.connectAttr("{}.worldMatrix[{}]".format(item, dag.getInstanceIndex()), pos + ".inputMatrix")
            source = pos + ".outputTranslate"
        local = mlib.createNode("pointMatrixMult", name="guideLineSpace#").getName()
        if source:
            cmds.connectAttr(source, local + ".inPoint")
        else:
            factor = convertDistance(1.0, toUnit="cm")
            cmds.setAttr(local + ".inPoint", *list(fixed * factor))
        cmds.connectAttr(curve + ".worldInverseMatrix[0]", local + ".inMatrix")
        cmds.connectAttr(local + ".output", "{}.controlPoints[{}]".format(shape, i))
    return curve


def _mesh(item):
    """単一の表示メッシュを解決する。"""
    if cmds.nodeType(item) != "mesh":
        shapes = cmds.listRelatives(item, shapes=True, noIntermediate=True, type="mesh", fullPath=True) or []
        if len(shapes) != 1:
            raise ValueError("単一のメッシュを指定してください: " + item)
        item = shapes[0]
    return getNode(item)


@undoTransaction("mlrigTransferRbf")
def transfer(source, deformed, target, scale, kernelName="gaussian", metric="euclidean"):
    """対応頂点の変位を選択したRBFで補間し、対象の静的な複製に転送する。"""
    # Mayaの数値ライブラリは形状転送時のみ使用する。
    import numpy as np

    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("半径は正の有限値で指定してください")
    base, end, dst = map(_mesh, (source, deformed, target))
    if base.getTopology() != end.getTopology():
        raise ValueError("基準と変形後の面・頂点順が異なります")
    def coords(fn):
        return np.asarray([list(p) for p in fn.getPoints(ws=True)])
    a, b, c = map(coords, (base, end, dst))
    if not 1 <= len(a) <= 1500:
        raise ValueError("基準形状は1〜1500頂点に対応しています")
    def kernel(points):
        delta = points[:, None] - a
        if metric == "angular":
            magnitude = np.linalg.norm(points, axis=1)[:, None] * np.linalg.norm(a, axis=1)
            if (magnitude == 0).any():
                raise ValueError("角距離では原点の入力を扱えません")
            distance = np.arccos(np.clip(points @ a.T / magnitude, -1, 1))
        elif metric == "euclidean":
            distance = np.sqrt(np.einsum("ijk,ijk->ij", delta, delta))
        elif metric == "manhattan":
            distance = np.abs(delta).sum(axis=2)
        elif metric == "chebyshev":
            distance = np.abs(delta).max(axis=2)
        else:
            raise ValueError("未対応の距離尺度です")
        r = distance / scale
        functions = {
            "gaussian": lambda: np.exp(-r*r),
            "exponential": lambda: np.exp(-r),
            "linear": lambda: r,
            "multiquadratic": lambda: np.sqrt(1 + r*r),
            "inverseQuadratic": lambda: 1 / (1 + r*r),
            "inverseMultiquadratic": lambda: 1 / np.sqrt(1 + r*r),
            "cubic": lambda: r**3,
            "thinPlate": lambda: r*r * np.log(np.maximum(r, np.finfo(float).tiny)),
        }
        return functions[kernelName]()
    weights, _, rank, _ = np.linalg.lstsq(kernel(a), b - a, rcond=1e-12)
    if rank != len(a):
        raise ValueError("基準点が重複または半径に対して密集しています")
    output = c.copy()
    for i in range(0, len(c), 128):
        output[i:i + 128] += kernel(c[i:i + 128]) @ weights
    source_transform = dst.getName(full=True).rsplit("|", 1)[0]
    copy = mlib.duplicate(source_transform, name="rbfTransfer#", returnRootsOnly=True).getName()
    cmds.delete(copy, constructionHistory=True)
    result = _mesh(copy)
    result.setPoints(output.tolist(), ws=True)
    return copy
