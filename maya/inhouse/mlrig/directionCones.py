"""ドライバーのワールドX軸に対する複数の方向の一致度を管理する。"""

import math

from maya import cmds
from maya.api import OpenMaya as om2
from mlib.decorator import undoTransaction


@undoTransaction("mlrigAddDirectionCone")
def add(driver, direction):
    """2つのトランスフォームの正X軸を比較するコーンを追加する。"""
    if driver == direction or not all(cmds.objectType(n, isAType="transform") for n in (driver, direction)):
        raise ValueError("ドライバー、方向の順に別々のトランスフォームを選択してください")
    owner = cmds.container(name="directionCone#")
    cmds.addAttr(owner, longName="mlrigDirectionCone", attributeType="message")
    cmds.connectAttr(direction + ".message", owner + ".mlrigDirectionCone")
    cmds.addAttr(owner, longName="halfAngle", niceName="Half Angle (deg)", attributeType="double", minValue=0.01, maxValue=180, defaultValue=45, keyable=True)
    cmds.addAttr(owner, longName="weight", attributeType="double")
    cmds.setAttr(owner + ".weight", channelBox=True)
    angle = cmds.createNode("angleBetween", name="coneSeparation#")
    members = [angle]
    for i, transform in enumerate((driver, direction), 1):
        vector = cmds.createNode("vectorProduct", name="coneWorldAxis#")
        cmds.setAttr(vector + ".operation", 3)
        cmds.setAttr(vector + ".input1X", 1)
        path = om2.MSelectionList().add(transform).getDagPath(0)
        cmds.connectAttr("{}.worldMatrix[{}]".format(path.fullPathName(), path.instanceNumber()), vector + ".matrix")
        cmds.connectAttr(vector + ".output", angle + ".vector" + str(i))
        members.append(vector)
    ramp = cmds.createNode("remapValue", name="coneFalloff#")
    unit = cmds.createNode("unitConversion", name="coneDegrees#")
    cmds.connectAttr(angle + ".angle", unit + ".input")
    cmds.setAttr(unit + ".conversionFactor", 180 / math.pi)
    cmds.connectAttr(unit + ".output", ramp + ".inputValue")
    members.append(unit)
    cmds.connectAttr(owner + ".halfAngle", ramp + ".inputMax")
    cmds.setAttr(ramp + ".outputMin", 1)
    cmds.setAttr(ramp + ".outputMax", 0)
    cmds.connectAttr(ramp + ".outValue", owner + ".weight")
    cmds.container(owner, edit=True, addNode=members + [ramp], force=True)
    cmds.select(owner)
    return owner


@undoTransaction("mlrigRemoveDirectionCone")
def remove(nodes):
    """選択したコーンの計算ノードを削除し、方向を指定した入力を保持する。"""
    if not nodes or any(cmds.nodeType(n) != "container" or not cmds.attributeQuery("mlrigDirectionCone", node=n, exists=True) for n in nodes):
        raise ValueError("削除する方向コーンを選択してください")
    cmds.delete(nodes)
