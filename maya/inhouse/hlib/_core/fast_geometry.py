"""形状座標のOpenMaya一括編集。履歴を持つ形状には直接上書きしない。"""
import maya.api.OpenMaya as om
from .fast_write import writable


def geometry(shape, indices, edit=False):
    path = shape.dag_path()
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
    path, fn, mesh = geometry(shape, indices)
    points = fn.getPoints() if mesh else fn.cvPositions()
    transform = path.inclusiveMatrix() if ws else om.MMatrix()
    scale = om.MDistance(1, om.MDistance.kCentimeters).asUnits(om.MDistance.uiUnit())
    return [tuple(v * scale for v in list(points[i] * transform)[:3]) for i in indices]


def set_positions(shape, indices, values, ws=False):
    if not indices:
        return
    path, fn, mesh = geometry(shape, indices, edit=True)
    points = fn.getPoints() if mesh else fn.cvPositions()
    transform = path.inclusiveMatrix()
    if ws and abs(transform.det4x4()) < 1e-12:
        raise ValueError("Cannot edit in world space with a singular transform")
    inverse = transform.inverse() if ws else om.MMatrix()
    scale = om.MDistance(1, om.MDistance.uiUnit()).asCentimeters()
    for index, value in zip(indices, values):
        point = om.MPoint(*(v * scale for v in value)) * inverse
        point.w = points[index].w
        points[index] = point
    if mesh:
        fn.setPoints(points)
        fn.updateSurface()
    else:
        fn.setCVPositions(points)
        fn.updateCurve()


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
