"""XYの操作位置から中心・四方向・四隅の補正ウェイトを作る。"""

import mlib
from maya import cmds
from mlib.common.units import convertDistance
from mlib.decorator import undoTransaction


@undoTransaction("mlrigDirectionPad")
def create():
    """選択した親の下に2Dコントローラーを生成し、9個の非負ウェイトを公開する。"""
    parents = mlib.ls(selection=True, long=True, transforms=True).getNames(full=True)
    if len(parents) > 1:
        raise ValueError("配置先を1つ選択するか、選択を解除してください")
    frame = cmds.curve(name="directionPad#", degree=1, point=[(-1,-1,0), (1,-1,0), (1,1,0), (-1,1,0), (-1,-1,0)])
    if parents:
        frame = cmds.parent(frame, parents[0], relative=True)[0]
    control = cmds.circle(name="directionControl#", normal=(0,0,1), radius=.12, constructionHistory=False)[0]
    control = cmds.parent(control, frame, relative=True)[0]
    cmds.transformLimits(control, tx=(-1,1), ty=(-1,1), etx=(True,True), ety=(True,True))
    for attr in ("tz","rx","ry","rz","sx","sy","sz"):
        cmds.setAttr(control + "." + attr, lock=True, keyable=False)
    factors = []
    for axis in ("X", "Y"):
        # 距離単位と無関係に操作範囲の両端を±1として読む。
        conv = mlib.createNode("unitConversion", name="directionInput#", skipSelect=True).getName()
        cmds.connectAttr(control + ".translate" + axis, conv + ".input")
        cmds.setAttr(conv + ".conversionFactor", convertDistance(1, fromUnit="cm"))
        positive = mlib.createNode("clamp", name="directionHalves#", skipSelect=True).getName()
        cmds.setAttr(positive + ".maxR", 1)
        cmds.setAttr(positive + ".minG", -1)
        cmds.setAttr(positive + ".maxG", 0)
        for c in "RG":
            cmds.connectAttr(conv + ".output", positive + ".input" + c)
        # clamp・multiplyDivideのスカラーは距離変換を介さずに扱う。
        negative = mlib.createNode("multiplyDivide", name="directionNegative#", skipSelect=True).getName()
        cmds.connectAttr(positive + ".outputG", negative + ".input1X")
        cmds.setAttr(negative + ".input2X", -1)
        center = mlib.createNode("plusMinusAverage", name="directionCenter#", skipSelect=True).getName()
        cmds.setAttr(center + ".operation", 2)
        cmds.setAttr(center + ".input1D[0]", 1)
        cmds.connectAttr(positive + ".outputR", center + ".input1D[1]")
        cmds.connectAttr(negative + ".outputX", center + ".input1D[2]")
        factors.append((negative + ".outputX", center + ".output1D", positive + ".outputR"))
    for row, names in enumerate((("downLeft","down","downRight"),("left","center","right"),("upLeft","up","upRight"))):
        multiply = mlib.createNode("multiplyDivide", name="directionWeights#", skipSelect=True).getName()
        for col, (axis, name) in enumerate(zip("XYZ", names)):
            name = "weight" + name[0].upper() + name[1:]
            cmds.connectAttr(factors[0][col], multiply + ".input1" + axis)
            cmds.connectAttr(factors[1][row], multiply + ".input2" + axis)
            cmds.addAttr(control, longName=name, attributeType="double")
            cmds.connectAttr(multiply + ".output" + axis, control + "." + name)
            cmds.setAttr(control + "." + name, channelBox=True)
    mlib.select(control, replace=True)
    return control
