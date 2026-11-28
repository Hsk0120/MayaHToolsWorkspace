"""NURBSのノット範囲をメモリ上のコピーで変更し、形状差を調べる。"""

import math

import maya.api.OpenMaya as om
import maya.cmds as cmds


def preview(shape, u_range, v_range):
    """カーブ・サーフェスを等比で再パラメーター化し、同じ分数位置を比較する。"""
    selection = om.MSelectionList()
    selection.add(shape)
    path = selection.getDagPath(0)
    surface = path.node().hasFn(om.MFn.kNurbsSurface)
    if not surface and not path.node().hasFn(om.MFn.kNurbsCurve):
        raise ValueError("Select a NURBS curve or surface.")
    fn = om.MFnNurbsSurface if surface else om.MFnNurbsCurve
    data = om.MFnNurbsSurfaceData().create() if surface else om.MFnNurbsCurveData().create()
    source = fn(path)
    copy = fn(fn().copy(path.node(), data))
    if surface:
        axes = [(source.knotDomainInU, u_range, copy.knotsInU(), copy.setKnotsInU),
                (source.knotDomainInV, v_range, copy.knotsInV(), copy.setKnotsInV)]
    else:
        axes = [(source.knotDomain, u_range, copy.knots(), copy.setKnots)]
    for (lo, hi), (start, end), knots, setter in axes:
        if not math.isfinite(start) or not math.isfinite(end) or start >= end or hi <= lo:
            raise ValueError("Enter finite, increasing knot ranges.")
        setter([start + (k-lo) * (end-start) / (hi-lo) for k in knots], 0, len(knots)-1)

    def samples(bounds):
        lo, hi = bounds
        return [lo + (hi-lo)*i/8 for i in range(9)]

    distances = []
    matrix = path.inclusiveMatrix()
    for u, new_u in zip(samples(axes[0][0]), samples(u_range)):
        if surface:
            for v, new_v in zip(samples(axes[1][0]), samples(v_range)):
                a = source.getPointAtParam(u, v) * matrix
                b = copy.getPointAtParam(new_u, new_v) * matrix
                distances.append(a.distanceTo(b))
        else:
            distances.append((source.getPointAtParam(u)*matrix).distanceTo(copy.getPointAtParam(new_u)*matrix))
    sinks = cmds.listConnections(shape, source=False, destination=True, plugs=True) or []
    return [axis[0] for axis in axes], max(distances), sorted(set(sinks))


def compareSubdivision(shape, spans_u, spans_v, guide_uv):
    """一時的なDG演算で等間隔に再構築し、境界・法線・ガイド位置の差を返す。"""
    if any(type(value) is not int or value < 1 for value in (spans_u, spans_v)):
        raise ValueError("Enter positive U and V span counts.")
    selected = om.MSelectionList()
    selected.add(shape)
    path = selected.getDagPath(0)
    if not path.node().hasFn(om.MFn.kNurbsSurface):
        raise ValueError("Select one NURBS surface shape.")
    source = om.MFnNurbsSurface(path)
    u_range, v_range = source.knotDomainInU, source.knotDomainInV
    if len(guide_uv) != 2 or not all(bounds[0] <= value <= bounds[1] for bounds, value in zip((u_range, v_range), guide_uv)):
        raise ValueError("Enter a guide UV inside the original knot domain.")
    # 一時DGノードの生成・接続・除去はユーザーのUndoキューに積まない。
    modifier = om.MDGModifier()
    rebuild = om.MFnDependencyNode(modifier.createNode("rebuildSurface"))
    shape_fn = om.MFnDependencyNode(path.node())
    modifier.connect(shape_fn.findPlug("local", False), rebuild.findPlug("inputSurface", False))
    for name, value in (("rebuildType", 0), ("direction", 2), ("keepRange", 1), ("spansU", spans_u),
                        ("spansV", spans_v), ("degreeU", source.degreeInU), ("degreeV", source.degreeInV)):
        modifier.newPlugValueInt(rebuild.findPlug(name, False), value)
    modifier.doIt()
    try:
        output_data = rebuild.findPlug("outputSurface", False).asMObject()
        changed = om.MFnNurbsSurface(output_data)
        matrix = path.inclusiveMatrix()

        def distance(u, v):
            return (source.getPointAtParam(u, v) * matrix).distanceTo(changed.getPointAtParam(u, v) * matrix)

        maximum = boundary = normal_angle = 0.0
        invalid_normals = 0
        for i in range(11):
            u = u_range[0] + (u_range[1] - u_range[0]) * i / 10
            for j in range(11):
                v = v_range[0] + (v_range[1] - v_range[0]) * j / 10
                delta = distance(u, v)
                maximum = max(maximum, delta)
                if i in (0, 10) or j in (0, 10):
                    boundary = max(boundary, delta)
                first, second = (fn.normal(u, v).transformAsNormal(matrix) for fn in (source, changed))
                if first.length() and second.length():
                    normal_angle = max(normal_angle, math.degrees(first.angle(second)))
                else:
                    invalid_normals += 1
        return dict(spans=(changed.numSpansInU, changed.numSpansInV), surfaceCm=maximum, boundaryCm=boundary,
                    normalDegrees=normal_angle, undefinedNormals=invalid_normals, guideCm=distance(*guide_uv))
    finally:
        modifier.undoIt()


def run():
    """選択形状の範囲と下流の接続先を確認する。"""
    window = "HToolsKnotRangePreview"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Preview Knot Range")
    cmds.columnLayout(adjustableColumn=True)
    u = cmds.floatFieldGrp(label="New curve / U range", numberOfFields=2, value2=1)
    v = cmds.floatFieldGrp(label="New V range", numberOfFields=2, value2=1)
    report = cmds.scrollField(editable=False, height=180)

    def inspect(*_):
        nodes = cmds.ls(selection=True, long=True) or []
        shapes = cmds.ls(nodes, dag=True, shapes=True, noIntermediate=True, long=True) if nodes else []
        if len(shapes) != 1:
            raise ValueError("Select one NURBS curve or surface.")
        ranges, error, sinks = preview(shapes[0], cmds.floatFieldGrp(u, query=True, value=True)[:2],
                                      cmds.floatFieldGrp(v, query=True, value=True)[:2])
        rows = [f"Current ranges: {ranges}", f"Maximum sampled distance: {error:g} cm", "Downstream inputs:"]
        for sink in sinks:
            rows.append(sink)
            node = sink.rsplit(".", 1)[0]
            for attribute in ("parameter", "parameterU", "parameterV", "turnOnPercentage"):
                if cmds.attributeQuery(attribute, node=node, exists=True):
                    plug = node + "." + attribute
                    source = cmds.connectionInfo(plug, sourceFromDestination=True)
                    value = f"driven by {source}" if source else f"fixed at {cmds.getAttr(plug)}"
                    rows.append(f"  {attribute}: {value}")
        cmds.scrollField(report, edit=True, text="\n".join(rows))

    cmds.button(label="Preview on geometry copy", command=inspect)
    spans = cmds.intFieldGrp(label="Uniform spans U / V", numberOfFields=2, value1=4, value2=4)
    guide = cmds.floatFieldGrp(label="Guide U / V (knot units)", numberOfFields=2, value1=0.5, value2=0.5)

    def subdivision(*_):
        nodes = cmds.ls(selection=True, long=True) or []
        shapes = cmds.ls(nodes, dag=True, type="nurbsSurface", noIntermediate=True, long=True) if nodes else []
        if len(shapes) != 1:
            raise ValueError("Select one NURBS surface.")
        su, sv = cmds.intFieldGrp(spans, query=True, value=True)[:2]
        result = compareSubdivision(shapes[0], su, sv, cmds.floatFieldGrp(guide, query=True, value=True)[:2])
        cmds.scrollField(report, edit=True, text="\n".join(f"{key}: {value}" for key, value in result.items()))

    cmds.button(label="Compare uniform surface subdivision", command=subdivision)
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
