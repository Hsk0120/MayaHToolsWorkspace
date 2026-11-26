"""同じ3関節鎖に対して補助骨の追従方式を選択する。"""

import math

from maya import cmds
from mlib.decorator import undoTransaction


MODES = (("weighted", "回転を半分追従"), ("noStretch", "長手Xを伸縮させない"), ("stickOut", "曲げで突出"), ("twoBone", "前後2区間へ配置"))


def _midpoint(a, b, root):
    joint = cmds.createNode("joint", parent=root, name="segmentInfluence#")
    cmds.pointConstraint(a, b, joint)
    cmds.aimConstraint(
        b, joint, aimVector=(1, 0, 0), upVector=(0, 1, 0), worldUpType="objectrotation", worldUpObject=a, worldUpVector=(0, 1, 0)
    )
    return joint


@undoTransaction("mlrigInfluenceMode")
def create(chain, mode):
    """親・中間・末端を指定し、入力骨や既存のスキンに手を加えず補助骨を作る。"""
    if mode not in dict(MODES) or len(chain) != 3 or any(cmds.nodeType(n) != "joint" for n in chain):
        raise ValueError("親、中間、末端の3関節を指定してください")
    a, b, c = cmds.ls(chain, long=True)
    if b.rpartition("|")[0] != a or c.rpartition("|")[0] != b:
        raise ValueError("直接親子になっている3関節を順に指定してください")
    coords = [cmds.xform(n, query=True, worldSpace=True, translation=True) for n in (a, b, c)]
    if min(math.dist(p, q) for p, q in zip(coords, coords[1:])) < 1e-7:
        raise ValueError("骨の区間に長さが必要です")
    root = cmds.createNode("transform", name=mode + "Influences#")
    cmds.setAttr(root + ".inheritsTransform", False)
    if mode == "twoBone":
        return [_midpoint(a, b, root), _midpoint(b, c, root)]
    joint = cmds.createNode("joint", parent=root, name=mode + "Influence#")
    if mode == "weighted":
        cmds.pointConstraint(b, joint)
        constraint = cmds.orientConstraint(a, b, joint)[0]
        cmds.setAttr(constraint + ".interpType", 2)
        attrs = cmds.orientConstraint(constraint, query=True, weightAliasList=True)
        cmds.addAttr(joint, longName="followWeight", attributeType="double", minValue=0, maxValue=1, defaultValue=0.5, keyable=True)
        rev = cmds.createNode("reverse", name="influenceParentWeight#")
        cmds.connectAttr(joint + ".followWeight", rev + ".inputX")
        cmds.connectAttr(rev + ".outputX", constraint + "." + attrs[0])
        cmds.connectAttr(joint + ".followWeight", constraint + "." + attrs[1])
    elif mode == "noStretch":
        dec = cmds.createNode("decomposeMatrix", name="influenceWorldParts#")
        cmds.connectAttr(b + ".worldMatrix[0]", dec + ".inputMatrix")
        for src, dst in (
            ("outputTranslate", "translate"),
            ("outputRotate", "rotate"),
            ("outputScaleY", "scaleY"),
            ("outputScaleZ", "scaleZ"),
        ):
            cmds.connectAttr(dec + "." + src, joint + "." + dst)
    else:
        frame = cmds.createNode("transform", parent=root, name="stickOutFrame#")
        cmds.parentConstraint(b, frame)
        joint = cmds.parent(joint, frame, relative=True)[0]
        angle = cmds.createNode("angleBetween", name="influenceBend#")
        positions = []
        for n in (a, b, c):
            dec = cmds.createNode("decomposeMatrix", name="influencePoint#")
            cmds.connectAttr(n + ".worldMatrix[0]", dec + ".inputMatrix")
            positions.append(dec + ".outputTranslate")
        for i in range(2):
            diff = cmds.createNode("plusMinusAverage", name="influenceSegment#")
            cmds.setAttr(diff + ".operation", 2)
            cmds.connectAttr(positions[i + 1], diff + ".input3D[0]")
            cmds.connectAttr(positions[i], diff + ".input3D[1]")
            cmds.connectAttr(diff + ".output3D", angle + ".vector" + str(i + 1))
        degrees = cmds.createNode("unitConversion", name="influenceBendDegrees#")
        cmds.connectAttr(angle + ".angle", degrees + ".input")
        cmds.setAttr(degrees + ".conversionFactor", 180 / math.pi)
        rest = cmds.getAttr(degrees + ".output")
        if rest >= 179.99:
            raise ValueError("折り返した鎖では曲げの増分を測れません")
        ramp = cmds.createNode("remapValue", name="stickOutDistance#")
        cmds.setAttr(ramp + ".inputMin", rest)
        cmds.setAttr(ramp + ".inputMax", min(180, rest + 90))
        cmds.addAttr(joint, longName="maxOffset", attributeType="doubleLinear", defaultValue=1, keyable=True)
        cmds.connectAttr(joint + ".maxOffset", ramp + ".outputMax")
        cmds.connectAttr(degrees + ".output", ramp + ".inputValue")
        cmds.connectAttr(ramp + ".outValue", joint + ".translateY")
    return [joint]
