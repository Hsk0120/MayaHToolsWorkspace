"""ドライバーのワールドX軸に対する複数の方向の一致度を管理する。"""

import math

import mlib
from maya import cmds
from mlib import getNode
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
    angle = mlib.createNode("angleBetween", name="coneSeparation#").getName()
    members = [angle]
    for i, transform in enumerate((driver, direction), 1):
        vector = mlib.createNode("vectorProduct", name="coneWorldAxis#").getName()
        cmds.setAttr(vector + ".operation", 3)
        cmds.setAttr(vector + ".input1X", 1)
        node = getNode(transform)
        cmds.connectAttr("{}.worldMatrix[{}]".format(node.getName(full=True), node.getInstanceIndex()), vector + ".matrix")
        cmds.connectAttr(vector + ".output", angle + ".vector" + str(i))
        members.append(vector)
    ramp = mlib.createNode("remapValue", name="coneFalloff#").getName()
    unit = mlib.createNode("unitConversion", name="coneDegrees#").getName()
    cmds.connectAttr(angle + ".angle", unit + ".input")
    cmds.setAttr(unit + ".conversionFactor", 180 / math.pi)
    cmds.connectAttr(unit + ".output", ramp + ".inputValue")
    members.append(unit)
    cmds.connectAttr(owner + ".halfAngle", ramp + ".inputMax")
    cmds.setAttr(ramp + ".outputMin", 1)
    cmds.setAttr(ramp + ".outputMax", 0)
    cmds.connectAttr(ramp + ".outValue", owner + ".weight")
    cmds.container(owner, edit=True, addNode=members + [ramp], force=True)
    mlib.select(owner)
    return owner


@undoTransaction("mlrigRemoveDirectionCone")
def remove(nodes):
    """選択したコーンの計算ノードを削除し、方向を指定した入力を保持する。"""
    if not nodes or any(cmds.nodeType(n) != "container" or not cmds.attributeQuery("mlrigDirectionCone", node=n, exists=True) for n in nodes):
        raise ValueError("削除する方向コーンを選択してください")
    mlib.delete(nodes)
