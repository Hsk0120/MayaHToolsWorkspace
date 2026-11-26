"""4点から右手座標系を作り、親のスケールに依存しない補助ガイドを配置する。"""

from maya import cmds
from maya.api import OpenMaya as om2
from mlib.decorator import undoTransaction


@undoTransaction("mlrigFourPointGuide")
def create(tips, parent=None):
    """X先端・原点・Y先端・Z先端から直交軸を求め、補助トランスフォームを返す。"""
    if len(tips) != 4 or len(set(tips)) != 4 or not all(cmds.objectType(n, isAType="transform") for n in tips):
        raise ValueError("X先端、原点、Y先端、Z先端の異なる4点を選択してください")
    paths = [om2.MSelectionList().add(n).getDagPath(0) for n in tips]
    points = [om2.MPoint() * p.inclusiveMatrix() for p in paths]
    axes = [(points[i] - points[1]).normal() for i in (0, 2, 3)]
    if (axes[0] ^ axes[1]) * axes[2] <= 1e-6:
        raise ValueError("ガイドが同一点・共線・同一平面または反転しています")
    owner = cmds.container(name="fourPointFrame#")
    members = []

    def node(kind):
        name = cmds.createNode(kind, name="fourPoint" + kind[0].upper() + kind[1:] + "#", skipSelect=True)
        members.append(name)
        return name

    def vector(operation, a, b=None, normalize=False):
        op = node("vectorProduct")
        cmds.setAttr(op + ".operation", operation)
        cmds.setAttr(op + ".normalizeOutput", normalize)
        cmds.connectAttr(a, op + ".input1")
        if b:
            cmds.connectAttr(b, op + ".input2")
        return op + ".output"

    coords = []
    for path in paths:
        dec = node("decomposeMatrix")
        cmds.connectAttr("{}.worldMatrix[{}]".format(path.fullPathName(), path.instanceNumber()), dec + ".inputMatrix")
        coords.append(dec + ".outputTranslate")
    directions = []
    for i in (0, 2, 3):
        diff = node("plusMinusAverage")
        cmds.setAttr(diff + ".operation", 2)
        cmds.connectAttr(coords[i], diff + ".input3D[0]")
        cmds.connectAttr(coords[1], diff + ".input3D[1]")
        directions.append(vector(0, diff + ".output3D", normalize=True))
    x, y_tip, z_tip = directions
    normal = vector(2, x, y_tip)
    valid = vector(1, normal, z_tip)
    z = vector(0, normal, normalize=True)
    y = vector(2, z, x, normalize=True)
    rotation = node("fourByFourMatrix")
    for i, row in enumerate((x, y, z)):
        for j, axis in enumerate("XYZ"):
            cmds.connectAttr(row + axis, "{}.in{}{}".format(rotation, i, j))
    gate = node("condition")
    cmds.connectAttr(valid + "X", gate + ".firstTerm")
    cmds.setAttr(gate + ".operation", 2)
    cmds.setAttr(gate + ".secondTerm", 1e-6)
    cmds.setAttr(gate + ".colorIfTrueR", 1)
    cmds.setAttr(gate + ".colorIfFalseR", 0)
    choice = node("choice")
    # 無効姿勢では作成時の回転を保持し、位置だけは引き続き追従する。
    cmds.connectAttr(rotation + ".output", choice + ".input[1]")
    frozen = node("holdMatrix")
    cmds.setAttr(frozen + ".inMatrix", *cmds.getAttr(rotation + ".output"), type="matrix")
    cmds.connectAttr(frozen + ".outMatrix", choice + ".input[0]")
    cmds.connectAttr(gate + ".outColorR", choice + ".selector")
    position = node("composeMatrix")
    cmds.connectAttr(coords[1], position + ".inputTranslate")
    result = node("multMatrix")
    cmds.connectAttr(choice + ".output", result + ".matrixIn[0]")
    cmds.connectAttr(position + ".outputMatrix", result + ".matrixIn[1]")
    output = cmds.createNode("transform", name="fourPointGuide#", **({"parent": parent} if parent else {}))
    if parent:
        path = om2.MSelectionList().add(parent).getDagPath(0)
        cmds.connectAttr("{}.worldInverseMatrix[{}]".format(path.fullPathName(), path.instanceNumber()), result + ".matrixIn[2]")
    cmds.connectAttr(result + ".matrixSum", output + ".offsetParentMatrix")
    cmds.container(owner, edit=True, addNode=members)
    cmds.addAttr(output, longName="mlrigFourPointFrame", attributeType="message")
    cmds.connectAttr(owner + ".message", output + ".mlrigFourPointFrame")
    cmds.select(output)
    return output


@undoTransaction("mlrigReleaseFourPointGuide")
def release(output):
    """現在のローカルマトリクスを保持し、4点追従を解除する。"""
    marker = output + ".mlrigFourPointFrame"
    if not cmds.objExists(marker):
        raise ValueError("4点追従ガイドを選択してください")
    owner = cmds.connectionInfo(marker, sourceFromDestination=True).rpartition(".")[0]
    plug = output + ".offsetParentMatrix"
    source = cmds.connectionInfo(plug, sourceFromDestination=True)
    if not owner or source.rpartition(".")[0] not in (cmds.container(owner, query=True, nodeList=True) or []):
        raise ValueError("4点追従の接続を確認してください")
    matrix = cmds.getAttr(plug)
    cmds.disconnectAttr(source, plug)
    cmds.setAttr(plug, *matrix, type="matrix")
    cmds.delete(owner)
    cmds.deleteAttr(marker)
    return output
