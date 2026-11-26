"""ワールド直下の専用バッファで基準の移動を複数リグから引く。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds
from mlib.decorator import undoTransaction

from .motionPath import _position

_CURVES = "animBarCounterCurves"


@undoTransaction("animBarCounterMotion")
def applySelected():
    """基準と各リグの未使用バッファを順に選び、再生範囲の平行移動を打ち消す。"""
    selected = cmds.ls(selection=True, long=True, type="transform") or []
    if len(selected) < 2:
        raise ValueError("Select the reference control followed by root-level rig buffers.")
    reference, buffers = selected[0], selected[1:]
    for node in buffers:
        if (cmds.nodeType(node) != "transform" or cmds.listRelatives(node, parent=True)
                or cmds.referenceQuery(node, isNodeReferenced=True) or cmds.listConnections(node, source=True, destination=False)
                or cmds.attributeQuery(_CURVES, node=node, exists=True)
                or tuple(cmds.getAttr(node + ".matrix")) != tuple(om2.MMatrix())
                or tuple(cmds.getAttr(node + ".offsetParentMatrix")) != tuple(om2.MMatrix())
                or any(not cmds.getAttr(node + ".t" + axis, settable=True) for axis in "xyz")):
            raise ValueError("Choose unreferenced, unused identity buffers at the scene root: " + node)
    start = cmds.playbackOptions(q=True, minTime=True)
    end = cmds.playbackOptions(q=True, maxTime=True)
    if end < start or not start.is_integer() or not end.is_integer():
        raise ValueError("Choose a whole-frame playback range.")
    origin = _position(reference, start)
    samples = [(t, origin - _position(reference, t)) for t in range(int(start), int(end) + 1)]
    for node in buffers:
        cmds.addAttr(node, longName=_CURVES, attributeType="message", multi=True)
        for index, axis in enumerate("xyz"):
            attr = node + ".t" + axis
            for frame, offset in samples:
                value = om2.MDistance(offset[index]).asUnits(om2.MDistance.uiUnit())
                cmds.setKeyframe(attr, time=frame, value=value, inTangentType="linear", outTangentType="linear")
            curve, = cmds.listConnections(attr, source=True, destination=False, type="animCurve")
            cmds.connectAttr(curve + ".message", f"{node}.{_CURVES}[{index}]")
    return len(buffers)


@undoTransaction("animBarRemoveCounterMotion")
def removeSelected():
    """選択バッファから作成時に記録したカーブだけを取り除く。"""
    buffers = cmds.ls(selection=True, long=True, type="transform") or []
    if not buffers:
        raise ValueError("Select the counter motion buffers to restore.")
    curves = []
    for node in buffers:
        if not cmds.attributeQuery(_CURVES, node=node, exists=True):
            raise ValueError("Select only counter motion buffers.")
        for index, axis in enumerate("xyz"):
            curve = cmds.listConnections(f"{node}.{_CURVES}[{index}]", source=True, destination=False) or []
            if len(curve) != 1 or cmds.listConnections(node + ".t" + axis, source=True, destination=False) != curve:
                raise ValueError("The buffer animation connections have changed.")
            outputs = cmds.listConnections(curve[0] + ".output", source=False, destination=True, plugs=True) or []
            if len(outputs) != 1:
                raise ValueError("The counter curve has other consumers.")
            curves.append(curve[0])
    cmds.delete(curves)
    for node in buffers:
        cmds.setAttr(node + ".translate", 0, 0, 0)
        cmds.deleteAttr(node + "." + _CURVES)
