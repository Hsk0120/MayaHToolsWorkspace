"""曲げとねじりを別のインフルエンスに分け、適用順を選ぶ。"""

import mlib
from maya import cmds
from mlib.decorator import undoTransaction

from .setups.twistDistribution import TwistDistribution


@undoTransaction("mlrigSplitTwistInfluences")
def create(joint, before, axis="x"):
    """親空間の回転を分解し、指定軸のねじりを親側または子側で受ける補助骨を作る。"""
    parents = cmds.listRelatives(joint, parent=True, fullPath=True) or []
    if cmds.nodeType(joint) != "joint" or len(parents) != 1:
        raise ValueError("親のあるジョイントを選択してください")
    graph = TwistDistribution.create(parents[0], joint, name="splitInfluence#", axis=axis)
    owner = graph.container.getName()
    dec = cmds.connectionInfo(owner + ".relativeDecompose", sourceFromDestination=True).rsplit(".", 1)[0]
    rotation = mlib.createNode("composeMatrix", name="influenceRotation#").getName()
    cmds.setAttr(rotation + ".useEulerRotation", False)
    cmds.connectAttr(dec + ".outputQuat", rotation + ".inputQuat")
    inverse = mlib.createNode("inverseMatrix", name="inverseTwist#").getName()
    twist = owner + ".twistMatrix"
    cmds.connectAttr(twist, inverse + ".inputMatrix")
    swing = mlib.createNode("multMatrix", name="influenceSwing#").getName()
    factors = (rotation + ".outputMatrix", inverse + ".outputMatrix") if before else (inverse + ".outputMatrix", rotation + ".outputMatrix")
    for i, plug in enumerate(factors):
        cmds.connectAttr(plug, "{}.matrixIn[{}]".format(swing, i))
    frame = mlib.createNode("transform", parent=parents[0], name="splitInfluenceOrigin#").getName()
    cmds.connectAttr(dec + ".outputTranslate", frame + ".translate")
    outputs = []
    for name, plug in ((("twist", twist), ("bend", swing + ".matrixSum")) if before else (("bend", swing + ".matrixSum"), ("twist", twist))):
        part = mlib.createNode("joint", parent=frame, name=name + "Influence#").getName()
        cmds.connectAttr(plug, part + ".offsetParentMatrix")
        outputs.append(part)
        frame = part
    cmds.container(owner, edit=True, addNode=[rotation, inverse, swing])
    mlib.select(outputs)
    return outputs
