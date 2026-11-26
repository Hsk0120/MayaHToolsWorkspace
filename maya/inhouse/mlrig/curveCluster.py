"""カーブ上の点と接線から、クラスターハンドルをオフセット付きで駆動する。"""

import math

from maya import cmds
from maya.api import OpenMaya as om2
from mlib.decorator import undoTransaction

from .curveLengthTools import _curve


@undoTransaction("mlrigCurveCluster")
def bind(curve, handle, fraction):
    """指定弧長比で接続し、再バインド時も現在のワールド姿勢を保つ。"""
    if not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError("弧長比は0から1で指定してください")
    world, fn = _curve(curve)
    if fn.length() <= 1e-8 or not cmds.listRelatives(handle, shapes=True, type="clusterHandle"):
        raise ValueError("長さのあるカーブとクラスターハンドルを指定してください")
    axis = cmds.upAxis(query=True, axis=True)
    up = (0, 1, 0) if axis == "y" else (0, 0, 1)
    tangent = fn.tangent(fn.findParamFromLength(fraction * fn.length()), om2.MSpace.kWorld)
    if abs(tangent.normal() * om2.MVector(*up)) > .99999:
        raise ValueError("接線がシーンの上軸と平行です")
    marker = handle + ".mlrigCurveConstraint"
    old = cmds.connectionInfo(marker, sourceFromDestination=True).rsplit(".", 1)[0] if cmds.objExists(marker) else ""
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
        plug = handle + "." + attr
        source = cmds.connectionInfo(plug, sourceFromDestination=True)
        if cmds.getAttr(plug, lock=True) or source and source.rsplit(".", 1)[0] != old:
            raise ValueError("ハンドルに別の駆動またはロックがあります: " + plug)
    if old:
        matrix = cmds.xform(handle, query=True, worldSpace=True, matrix=True)
        helper = cmds.connectionInfo(old + ".mlrigCurveGuide", sourceFromDestination=True).rsplit(".", 1)[0]
        path = cmds.connectionInfo(old + ".mlrigMotionPath", sourceFromDestination=True).rsplit(".", 1)[0]
        if not helper or not path or cmds.nodeType(path) != "motionPath":
            raise ValueError("既存のカーブ駆動の構成を確認してください")
        cmds.delete(old, helper, path)
        cmds.xform(handle, worldSpace=True, matrix=matrix)
    elif not cmds.objExists(marker):
        cmds.addAttr(handle, longName="mlrigCurveConstraint", attributeType="message")
    path = cmds.createNode("motionPath", name="clusterCurveSample#")
    cmds.connectAttr(world, path + ".geometryPath")
    cmds.setAttr(path + ".fractionMode", True)
    value = om2.MDistance(fraction, om2.MDistance.kCentimeters).asUnits(om2.MDistance.uiUnit()) if cmds.getAttr(path + ".uValue", type=True) == "doubleLinear" else fraction
    cmds.setAttr(path + ".uValue", value)
    cmds.setAttr(path + ".follow", True)
    cmds.setAttr(path + ".worldUpType", 3)
    cmds.setAttr(path + ".worldUpVector", *up)
    guide = cmds.createNode("transform", name="clusterCurveGuide#")
    cmds.connectAttr(path + ".allCoordinates", guide + ".translate")
    cmds.connectAttr(path + ".rotate", guide + ".rotate")
    constraint = cmds.parentConstraint(guide, handle, maintainOffset=True)[0]
    cmds.addAttr(constraint, longName="mlrigCurveGuide", attributeType="message")
    cmds.connectAttr(guide + ".message", constraint + ".mlrigCurveGuide")
    cmds.addAttr(constraint, longName="mlrigMotionPath", attributeType="message")
    cmds.connectAttr(path + ".message", constraint + ".mlrigMotionPath")
    cmds.connectAttr(constraint + ".message", marker)
    return constraint


def show():
    """カーブとハンドルを選択し、駆動する弧長比を指定する。"""
    nodes = cmds.ls(selection=True, long=True) or []
    if len(nodes) < 2:
        raise ValueError("カーブを先に、次にハンドルを選択してください")
    window = "mlrigCurveCluster"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="カーブでクラスターを駆動")
    cmds.columnLayout(adjustableColumn=True)
    field = cmds.floatFieldGrp(label="弧長比", value1=0.5)

    @undoTransaction("mlrigBindCurveClusters")
    def build(*_):
        fraction = cmds.floatFieldGrp(field, query=True, value1=True)
        for handle in nodes[1:]:
            bind(nodes[0], handle, fraction)

    cmds.button(label="現在姿勢で接続・再バインド", command=build)
    cmds.showWindow(window)
    return window
