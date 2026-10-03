"""形状座標のOpenMaya一括編集。履歴を持つ形状には直接上書きしない。"""
import maya.api.OpenMaya as om
from .fastWrite import writable


def geometry(shape, indices, edit=False):
    path = shape.dagPath()
    mesh = path.node().hasFn(om.MFn.kMesh)
    fn = om.MFnMesh(path) if mesh else om.MFnNurbsCurve(path)
    if edit:
        if not mesh and fn.form == om.MFnNurbsCurve.kPeriodic:
            raise NotImplementedError("fast edits of periodic curves are not supported")
        dependency = om.MFnDependencyNode(path.node())
        source = dependency.findPlug("inMesh" if mesh else "create", False)
        if source.isDestination:
            raise NotImplementedError("fast geometry edits require a shape without input history")
        if dependency.isLocked:
            raise RuntimeError("Shape node is locked")
        points = dependency.findPlug("pnts" if mesh else "controlPoints", False)
        for index in indices:
            point = points.elementByLogicalIndex(index)
            writable(point)
            for child in range(point.numChildren()):
                writable(point.child(child))
    return path, fn, mesh


def positions(shape, indices, ws=False):
    """指定した点を保持順・cm単位で取得する。

    Args:
        shape (Shape): 有効なMeshまたはNurbsCurve。
        indices (Sequence[int]): 検証済みの点番号。
        ws (bool): Trueならワールド空間へ変換する。

    Returns:
        list[tuple[float, float, float]]: 指定順の座標。単点では全点を取得しない。
    """
    path, fn, mesh = geometry(shape, indices)
    space = om.MSpace.kWorld if ws else om.MSpace.kObject
    if len(indices) == 1:
        points = [fn.getPoint(indices[0], space) if mesh else fn.cvPosition(indices[0], space)]
    else:
        all_points = fn.getPoints(space) if mesh else fn.cvPositions(space)
        points = (all_points[i] for i in indices)
    return [(point.x, point.y, point.z) for point in points]


def setPositions(shape, indices, values, ws=False):
    """検証済みのcm座標を一括設定する。CVのwは変更しない。

    Args:
        shape (Shape): 履歴なしMeshまたは非周期NurbsCurve。
        indices (Sequence[int]): 検証済みの番号。
        values (Sequence[Sequence[float]]): 設定するXYZ。
        ws (bool): TrueならAPIワールド座標、Falseならローカル座標。
    """
    if not indices:
        return
    path, fn, mesh = geometry(shape, indices, edit=True)
    points = fn.getPoints() if mesh else fn.cvPositions()
    transform = path.inclusiveMatrix()
    if ws and abs(transform.det4x4()) < 1e-12:
        raise ValueError("Cannot edit in world space with a singular transform")
    inverse = transform.inverse() if ws else om.MMatrix()
    for index, value in zip(indices, values):
        # cvPositions(kWorld)はCVのwも行列積に使う。同じwで逆変換して往復を保つ。
        point = om.MPoint(value[0], value[1], value[2], points[index].w) * inverse
        point.w = points[index].w
        points[index] = point
    if mesh:
        fn.setPoints(points)
        fn.updateSurface()
    else:
        fn.setCVPositions(points)
        fn.updateCurve()


def object_positions(shape, indices, values):
    """APIのワールド座標を、CVの重みを保持したローカルXYZへ変換する。

    Args:
        shape (Shape): MeshまたはNurbsCurve。
        indices (Sequence[int]): 検証済みの番号。
        values (Sequence[Sequence[float]]): APIのワールドXYZ。距離はcm。

    Returns:
        list[tuple[float, float, float]]: cmdsのobjectSpaceへ渡すcmの座標。

    Raises:
        ValueError: ワールド行列が特異な場合。
    """
    path, fn, mesh = geometry(shape, indices)
    matrix = path.inclusiveMatrix()
    if abs(matrix.det4x4()) < 1e-12:
        raise ValueError("Cannot edit in world space with a singular transform")
    inverse = matrix.inverse()
    if mesh:
        weights = [1.0] * len(indices)
    elif len(indices) == 1:
        weights = [fn.cvPosition(indices[0]).w]
    else:
        cvs = fn.cvPositions()
        weights = [cvs[i].w for i in indices]
    points = [om.MPoint(row[0], row[1], row[2], weight) * inverse
              for row, weight in zip(values, weights)]
    return [(point.x, point.y, point.z) for point in points]


def set_uvs(shape, indices, values):
    if not indices:
        return
    _, fn, _ = geometry(shape, [], edit=True)
    uv_set = fn.currentUVSetName()
    us, vs = fn.getUVs(uvSet=uv_set)
    for index, (u, v) in zip(indices, values):
        us[index], vs[index] = u, v
    fn.setUVs(us, vs, uvSet=uv_set)
    fn.updateSurface()
