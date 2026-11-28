"""Evaluate Skin Weight Kit triangle bindings on polygon mesh vertices."""

import hashlib
import json

from maya import OpenMaya as om
from maya import OpenMayaMPx as mpx


def _signature(fn):
    """Identify mesh connectivity including face order and winding."""
    counts, ids = om.MIntArray(), om.MIntArray()
    fn.getVertices(counts, ids)
    return hashlib.sha256(json.dumps([fn.numVertices(), list(counts), list(ids)], separators=(",", ":")).encode("ascii")).hexdigest()


class TriangleCage(mpx.MPxDeformerNode):
    """Add the motion of each bound cage triangle to the incoming vertex position."""

    type_id = om.MTypeId(0x0007F7A2)
    cage = om.MObject()
    binding = om.MObject()
    cage_matrix = om.MObject()

    def __init__(self):
        super(TriangleCage, self).__init__()
        self._text = None
        self._rows = []

    def deform(self, block, iterator, matrix, geom_index):
        """Evaluate in world space and apply the weighted displacement in target space."""
        text = block.inputValue(self.binding).asString()
        mesh = block.inputValue(self.cage).asMesh()
        if not text or mesh.isNull():
            return
        if self._text != text:
            record = json.loads(text)
            self._rows = record["rows"]
            self._topology = record["cage"], record["target"]
            self._text = text
        points = om.MPointArray()
        # Reject editing/reordering faces in a bound mesh before indexed correspondences can move the wrong vertices.
        inputs = block.inputArrayValue(mpx.cvar.MPxGeometryFilter_input)
        inputs.jumpToElement(geom_index)
        geometry = inputs.inputValue().child(mpx.cvar.MPxGeometryFilter_inputGeom).asMesh()
        driver = om.MFnMesh(mesh)
        if (_signature(driver), _signature(om.MFnMesh(geometry))) != self._topology:
            raise ValueError("Cage or target topology changed after binding.")
        driver.getPoints(points)
        cage_world = block.inputValue(self.cage_matrix).asMatrix()
        inverse = matrix.inverse()
        envelope = block.inputValue(mpx.cvar.MPxGeometryFilter_envelope).asFloat()
        while not iterator.isDone():
            i = iterator.index()
            if i >= len(self._rows):
                raise ValueError("Target topology changed after binding.")
            ids, uv, offset, original = self._rows[i]
            if max(ids) >= points.length():
                raise ValueError("Cage topology changed after binding.")
            a, b, c = (points[j] for j in ids)
            ab, ac = b-a, c-a
            x, z = ab.normal(), (ab ^ ac).normal()
            current = a + ab * uv[0] + ac * uv[1] + x * offset[0] + (z ^ x) * offset[1] + z * offset[2]
            delta = current * cage_world * inverse - om.MPoint(*original)
            iterator.setPosition(iterator.position() + delta * (envelope * self.weightValue(block, geom_index, i)))
            iterator.next()


def _create():
    """Transfer ownership of the deformer instance to Maya."""
    return mpx.asMPxPtr(TriangleCage())


def _initialize():
    """Register the cage input and storable correspondence data."""
    fn = om.MFnTypedAttribute()
    TriangleCage.cage = fn.create("cageMesh", "cgm", om.MFnData.kMesh)
    fn.setStorable(False)
    TriangleCage.binding = fn.create("binding", "bnd", om.MFnData.kString)
    TriangleCage.cage_matrix = om.MFnMatrixAttribute().create("cageMatrix", "cmtx")
    for attr in (TriangleCage.cage, TriangleCage.binding, TriangleCage.cage_matrix):
        TriangleCage.addAttribute(attr)
        TriangleCage.attributeAffects(attr, mpx.cvar.MPxGeometryFilter_outputGeom)


def initializePlugin(obj):
    """Register the deformer when a setup or saved scene requests it."""
    mpx.MFnPlugin(obj, "SkinWeightKit", "1.0", "Any").registerNode(
        "swkTriangleCage", TriangleCage.type_id, _create, _initialize, mpx.MPxNode.kDeformerNode)


def uninitializePlugin(obj):
    """Unregister the node after its scene instances have been released."""
    mpx.MFnPlugin(obj).deregisterNode(TriangleCage.type_id)
