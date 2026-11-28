"""Bind selected mesh vertices to explicit triangles on an animated polygon cage."""

import hashlib
import json
import math
from pathlib import Path
from tempfile import NamedTemporaryFile

from maya import cmds
from maya.api import OpenMaya as om
from mlib.decorator import undoTransaction


NODE = "swkTriangleCage"
FORMAT = "SkinWeightKitTriangleCage1"


def _shape(name):
    """Resolve one non-instanced polygon shape to its DAG path."""
    names = cmds.ls(name, long=True) or []
    if len(names) != 1:
        raise ValueError("Choose one unambiguous mesh.")
    shape = names[0]
    if cmds.nodeType(shape) != "mesh":
        shapes = cmds.listRelatives(shape, shapes=True, noIntermediate=True, fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise ValueError("Choose a transform with one visible mesh.")
        shape = shapes[0]
    selection = om.MSelectionList()
    selection.add(shape)
    path = selection.getDagPath(0)
    if path.isInstanced():
        raise ValueError("Choose a mesh without instances.")
    return path


def _signature(fn):
    """Hash ordered polygon sizes and vertex indices independently of the mesh name."""
    counts, ids = fn.getVertices()
    return hashlib.sha256(json.dumps([fn.numVertices, list(counts), list(ids)], separators=(",", ":")).encode("ascii")).hexdigest()


def _existing(path):
    """Find the cage for this target, rejecting stacked cage bindings."""
    matches = cmds.ls(cmds.listHistory(path.fullPathName()) or [], type=NODE) or []
    if len(matches) > 1:
        raise ValueError("Multiple cage bindings found in target history.")
    return matches[0] if matches else None


def _triangle_record(p, triangle, points):
    """Find the closest barycentric point and preserve the offset in the triangle frame."""
    a, b, c = [points[i] for i in triangle]
    ab, ac = b - a, c - a
    normal = ab ^ ac
    denom = normal * normal
    if denom <= 1e-20:
        return None
    u = (((p - a) ^ ac) * normal) / denom
    v = ((ab ^ (p - a)) * normal) / denom
    if min(u, v, 1 - u - v) < 0:
        edges = []
        for start, end, first, second in ((a, b, (0, 0), (1, 0)), (b, c, (1, 0), (0, 1)), (c, a, (0, 1), (0, 0))):
            d = end - start
            t = min(1, max(0, ((p - start) * d) / (d * d)))
            edges.append(((p - (start + d * t)).length(), first[0] + (second[0] - first[0]) * t, first[1] + (second[1] - first[1]) * t))
        _, u, v = min(edges)
    offset = p - (a + ab * u + ac * v)
    x, z = ab.normal(), normal.normal()
    return offset.length(), [list(triangle), [u, v], [offset * x, offset * (z ^ x), offset * z], list(p)[:3]]


def _load_plugin():
    """Load the tool-owned deformer on demand."""
    plugin = Path(__file__).resolve().parents[3] / "plug-ins" / "swkTriangleCage.py"
    if not cmds.pluginInfo(str(plugin), query=True, loaded=True):
        cmds.loadPlugin(str(plugin), quiet=True)


@undoTransaction("Skin Weight Kit cage binding")
def bind(driver, driven, vertices=None, face=None, data=None):
    """Bind a mesh, replace selected correspondences, or restore validated saved rows."""
    _load_plugin()
    src, dst = _shape(driver), _shape(driven)
    history = cmds.ls(cmds.listHistory(src.fullPathName()) or [], long=True) or []
    if src == dst or dst.fullPathName() in history:
        raise ValueError("The cage must be independent from the target mesh.")
    a, b = om.MFnMesh(src), om.MFnMesh(dst)
    node = _existing(dst)
    if node:
        source = cmds.connectionInfo(node + ".cageMesh", sourceFromDestination=True)
        if not source or _shape(source.split(".")[0]) != src:
            raise ValueError("This mesh is already bound to another cage.")
    keys = dict(format=FORMAT, cage=_signature(a), target=_signature(b))
    if data is not None:
        if not isinstance(data, dict) or any(data.get(k) != v for k, v in keys.items()):
            raise ValueError("Cage or target topology differs from the saved binding.")
        rows = data.get("rows")
        if not isinstance(rows, list) or len(rows) != b.numVertices:
            raise ValueError("Unexpected target vertex count.")
        _, triangle_ids = a.getTriangles()
        triangles = {tuple(triangle_ids[i:i+3]) for i in range(0, len(triangle_ids), 3)}
        for row in rows:
            if not isinstance(row, list) or len(row) != 4:
                raise ValueError("Invalid cage record.")
            ids, uv, offset, original = row
            if not isinstance(ids, list) or len(ids) != 3 or any(type(i) != int for i in ids) or tuple(ids) not in triangles:
                raise ValueError("Invalid cage triangle.")
            for values, size in ((uv, 2), (offset, 3), (original, 3)):
                if not isinstance(values, list) or len(values) != size or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
                    raise ValueError("Invalid cage data.")
            if min(uv) < -1e-9 or sum(uv) > 1 + 1e-9:
                raise ValueError("Cage barycentric coordinates are outside their triangle.")
    else:
        indices = list(range(b.numVertices)) if vertices is None else sorted(set(vertices))
        if not indices or any(type(i) != int or not 0 <= i < b.numVertices for i in indices):
            raise ValueError("Choose valid target vertices.")
        if face is not None and (type(face) != int or not 0 <= face < a.numPolygons):
            raise ValueError("Choose one cage face.")
        if node:
            old = json.loads(cmds.getAttr(node + ".binding"))
            if any(old[k] != v for k, v in keys.items()):
                raise ValueError("Mesh topology changed. Restore the original topology.")
            rows = old["rows"]
            plug = om.MFnDependencyNode(_depend(node)).findPlug("input", False).elementByLogicalIndex(0).child(0)
            rest = [p * dst.inclusiveMatrix() for p in om.MFnMesh(plug.asMObject()).getPoints()]
        else:
            if len(indices) != b.numVertices:
                raise ValueError("Bind the complete mesh before repairing selected vertices.")
            rows = [None] * b.numVertices
            rest = b.getPoints(om.MSpace.kWorld)
        points = a.getPoints()
        driver_inverse = src.inclusiveMatrixInverse()
        target_inverse = dst.inclusiveMatrixInverse()
        tri_counts, triangles = a.getTriangles()
        starts = [0]
        for count in tri_counts:
            starts.append(starts[-1] + 3 * count)
        for i in indices:
            p = rest[i]
            polygon = a.getClosestPoint(p, om.MSpace.kWorld)[1] if face is None else face
            records = [_triangle_record(p * driver_inverse, triangles[j:j+3], points) for j in range(starts[polygon], starts[polygon+1], 3)]
            valid = [r for r in records if r is not None]
            if not valid:
                raise ValueError("A selected cage face has no usable triangle.")
            rows[i] = min(valid, key=lambda r: r[0])[1]
            rows[i][3] = list(p * target_inverse)[:3]
    if not node:
        node = cmds.deformer(dst.fullPathName(), type=NODE)[0]
        cmds.connectAttr(src.fullPathName() + ".outMesh", node + ".cageMesh")
        cmds.connectAttr(src.fullPathName() + ".worldMatrix[0]", node + ".cageMatrix")
    cmds.setAttr(node + ".binding", json.dumps(dict(keys, rows=rows), allow_nan=False, separators=(",", ":")), type="string")
    return node


def _depend(node):
    """Resolve the dependency object used to read the deformer input."""
    selection = om.MSelectionList()
    selection.add(node)
    return selection.getDependNode(0)


def save(driven, filename):
    """Atomically save the cage bindings belonging to this target."""
    _load_plugin()
    node = _existing(_shape(driven))
    if not node:
        raise ValueError("Choose a target bound with Triangle Cage.")
    target = Path(filename)
    with NamedTemporaryFile(dir=str(target.parent), delete=False) as stream:
        temp = Path(stream.name)
    try:
        temp.write_text(cmds.getAttr(node + ".binding"), encoding="utf-8")
        temp.replace(target)
    finally:
        if temp.exists():
            temp.unlink()


def restore(driver, driven, filename):
    """Resolve the driver explicitly and reject incompatible ordered topologies."""
    return bind(driver, driven, data=json.loads(Path(filename).read_text(encoding="utf-8")))
