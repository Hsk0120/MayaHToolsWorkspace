"""曲げとねじりを別のインフルエンスに分け、適用順を選ぶ。"""

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
    rotation = cmds.createNode("composeMatrix", name="influenceRotation#")
    cmds.setAttr(rotation + ".useEulerRotation", False)
    cmds.connectAttr(dec + ".outputQuat", rotation + ".inputQuat")
    inverse = cmds.createNode("inverseMatrix", name="inverseTwist#")
    twist = owner + ".twistMatrix"
    cmds.connectAttr(twist, inverse + ".inputMatrix")
    swing = cmds.createNode("multMatrix", name="influenceSwing#")
    factors = (rotation + ".outputMatrix", inverse + ".outputMatrix") if before else (inverse + ".outputMatrix", rotation + ".outputMatrix")
    for i, plug in enumerate(factors):
        cmds.connectAttr(plug, "{}.matrixIn[{}]".format(swing, i))
    frame = cmds.createNode("transform", parent=parents[0], name="splitInfluenceOrigin#")
    cmds.connectAttr(dec + ".outputTranslate", frame + ".translate")
    outputs = []
    for name, plug in ((("twist", twist), ("bend", swing + ".matrixSum")) if before else (("bend", swing + ".matrixSum"), ("twist", twist))):
        part = cmds.createNode("joint", parent=frame, name=name + "Influence#")
        cmds.connectAttr(plug, part + ".offsetParentMatrix")
        outputs.append(part)
        frame = part
    cmds.container(owner, edit=True, addNode=[rotation, inverse, swing])
    cmds.select(outputs)
    return outputs
