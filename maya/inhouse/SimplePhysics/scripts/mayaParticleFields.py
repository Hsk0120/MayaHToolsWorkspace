"""Evaluate connected static Maya fields on solver particle positions using MFnField."""

import hashlib
import json

from maya import cmds
from maya import OpenMaya as om1
from maya import OpenMayaFX as fx
from maya.api import OpenMaya as om


SUPPORTED = ("radialField", "uniformField", "gravityField", "vortexField")


def selected(node, disconnect=False):
    """Attach or detach one static field chosen in the Maya scene."""
    values = cmds.ls(selection=True, long=True) or []
    if len(values) != 1:
        raise ValueError("Select one Maya radial, uniform, gravity or vortex field.")
    field = values[0]
    if cmds.nodeType(field) not in SUPPORTED:
        shapes = cmds.listRelatives(field, shapes=True, fullPath=True) or []
        fields = [shape for shape in shapes if cmds.nodeType(shape) in SUPPORTED]
        if len(fields) != 1:
            raise ValueError("Select one Maya radial, uniform, gravity or vortex field.")
        field = fields[0]
    source = field + ".outputForce[0]"
    destination = node + ".fieldForces"
    array = cmds.getAttr(destination, multiIndices=True) or []
    match = next((i for i in array if cmds.isConnected(source, f"{destination}[{i}]")), None)
    if disconnect:
        if match is None:
            raise ValueError("This field is not attached.")
        cmds.disconnectAttr(source, f"{destination}[{match}]")
    elif match is None:
        selection = om.MSelectionList()
        selection.add(field)
        validate(selection.getDagPath(0))
        cmds.connectAttr(source, f"{destination}[{max(array, default=-1) + 1}]")


def validate(field):
    """Verify the field and its ancestors have fixed parameters and transforms."""
    path = om.MDagPath(field)
    if om.MFnDependencyNode(path.node()).typeName not in SUPPORTED:
        raise ValueError("Unsupported Maya field type.")
    while path.length():
        fn = om.MFnDependencyNode(path.node())
        if any(p.isDestination and not p.attribute().hasFn(om.MFn.kMessageAttribute) for p in fn.getConnections()):
            raise ValueError("Use a stationary Maya field with unconnected settings.")
        path.pop()


def samplers(function):
    """Resolve the registered field function sets. All fields use fixed scene parameters."""
    sources = function.findPlug("fieldForces", False)
    fields = []
    signatures = []
    for index in sources.getExistingArrayAttributeIndices():
        plug = sources.elementByLogicalIndex(index)
        if not plug.isDestination:
            continue
        path = om.MDagPath.getAPathTo(plug.source().node())
        validate(path)
        fn = om.MFnDependencyNode(path.node())
        values = []
        for number in range(fn.attributeCount()):
            obj = fn.attribute(number)
            attr = om.MFnAttribute(obj)
            if attr.storable and attr.writable and attr.parent.isNull() and not obj.hasFn(om.MFn.kMessageAttribute):
                values.extend(fn.findPlug(obj, False).getSetAttrCmds(om.MPlug.kAll))
        digest = hashlib.sha256(json.dumps(values).encode("utf-8")).hexdigest()
        signatures.append((index, fn.uuid().asString(), tuple(path.inclusiveMatrix()), digest))
        selection = om1.MSelectionList()
        selection.add(path.fullPathName())
        obj = om1.MDagPath()
        selection.getDagPath(0, obj)
        fields.append(fx.MFnField(obj))
    return fields, signatures


def accelerations(fields, positions, velocities, mass, dt):
    """Return particle acceleration in world space from native Maya field evaluations."""
    points, speeds = om1.MVectorArray(), om1.MVectorArray()
    masses = om1.MDoubleArray()
    for point, velocity in zip(positions, velocities):
        points.append(om1.MVector(*point))
        speeds.append(om1.MVector(*velocity))
        masses.append(mass)
    total = [om.MVector() for _ in positions]
    for field in fields:
        forces = om1.MVectorArray()
        field.getForceAtPoint(points, speeds, masses, forces, dt)
        for index in range(forces.length()):
            f = forces[index]
            total[index] += om.MVector(f.x, f.y, f.z) / mass
    return total
