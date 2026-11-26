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
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
