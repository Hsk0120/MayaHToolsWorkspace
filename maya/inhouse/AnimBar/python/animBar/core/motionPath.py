"""元のワールド移動距離をカーブ上の距離に置き換え、対象の移動だけをベイクする。"""

import math

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib
from mlib.decorator import undoTransaction


def _position(node, frame):
    """指定時刻のワールド位置をcmで返す。"""
    matrix = cmds.getAttr(node + ".worldMatrix[0]", time=frame)
    return om2.MPoint(*matrix[12:15])


@undoTransaction("animBarBakeMotionPath")
def bakeSelected(distanceScale=1.0, inputOffset=0.0):
    """元・パス・出力の順に選び、半フレームで距離を積算して整数フレームへ書く。

    入力の時刻オフセットはフレーム、距離倍率は無次元。パスは現在の形状を使用する。
    出力は未接続のワールド直下のtransform。返す値は半フレームでの最大位置誤差(cm)。
    """
    nodes = cmds.ls(selection=True, long=True, type="transform") or []
    if len(nodes) != 3 or not math.isfinite(distanceScale) or distanceScale < 0 or not math.isfinite(inputOffset):
        raise ValueError("Select a source, a curve and an output transform. Use a finite nonnegative distance scale.")
    source, path, target = nodes
    shapes = cmds.listRelatives(path, shapes=True, noIntermediate=True, fullPath=True, type="nurbsCurve") or []
    if len(shapes) != 1 or cmds.listRelatives(target, parent=True) or cmds.nodeType(target) != "transform":
        raise ValueError("Choose one NURBS path and a root-level output transform.")
    if cmds.referenceQuery(target, isNodeReferenced=True) or cmds.listConnections(target, source=True, destination=False):
        raise ValueError("Choose an unreferenced output transform without inputs.")
    if tuple(cmds.getAttr(target + ".offsetParentMatrix")) != tuple(om2.MMatrix()):
        raise ValueError("The output must have an identity offset parent matrix.")
    if any(not cmds.getAttr(target + ".t" + axis, settable=True) for axis in "xyz"):
        raise ValueError("Output translations must be writable.")
    start = cmds.playbackOptions(q=True, minTime=True)
    end = cmds.playbackOptions(q=True, maxTime=True)
    if not start.is_integer() or not end.is_integer() or end <= start:
        raise ValueError("Choose a whole-frame playback range.")
    curve = mlib.getNode(shapes[0])
    length = curve.getLength(ws=True)
    if length <= 0:
        raise ValueError("The path length must be positive.")
    positions = []
    previous = _position(source, start + inputOffset)
    distance = 0.0
    for tick in range(int(start * 2), int(end * 2) + 1):
        current = _position(source, tick / 2.0 + inputOffset)
        distance = min(length, distance + current.distanceTo(previous) * distanceScale)
        param = curve.getParam(length=distance, ws=True)
        positions.append(om2.MPoint(curve.getAtParam(param, ws=True)))
        previous = current
    origin = _position(target, start)
    translation = cmds.getAttr(target + ".translate")[0]
    for index in range(0, len(positions), 2):
        delta = positions[index] - origin
        for axis, original, change in zip("xyz", translation, delta):
            value = original + om2.MDistance(change).asUnits(om2.MDistance.uiUnit())
            cmds.setKeyframe(target, attribute="t" + axis, time=start + index // 2, value=value,
                             inTangentType="linear", outTangentType="linear")
    return max(_position(target, start + i / 2.0).distanceTo(positions[i]) for i in range(1, len(positions), 2))
