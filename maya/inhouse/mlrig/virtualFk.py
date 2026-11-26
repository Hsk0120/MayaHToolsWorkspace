"""同じ親の下の独立した制御列から、選択順の仮想FKの出力を生成する。"""

from maya import cmds
from maya.api import OpenMaya as om2
from mlib.decorator import undoTransaction


@undoTransaction("mlrigVirtualFk")
def create(controls):
    """入力を再親子化せず、直前の入力の基準姿勢に対する変化を順に合成する。"""
    paths = [cmds.ls(node, long=True, transforms=True) or [] for node in controls]
    if len(paths) < 2 or any(len(matches) != 1 for matches in paths):
        raise ValueError("2つ以上の実在する入力を一意に指定してください")
    nodes = [matches[0] for matches in paths]
    parents = {node.rpartition("|")[0] for node in nodes}
    if len(set(nodes)) != len(nodes) or len(parents) != 1:
        raise ValueError("重複しない同一親の入力を仮想FK順に選択してください")
    if cmds.cycleCheck(nodes, list=True, dag=True):
        raise ValueError("入力に依存サイクルがあります")
    parent = parents.pop()
    rest = []
    for node in nodes:
        path = om2.MSelectionList().add(node).getDagPath(0)
        if path.isInstanced() or not cmds.getAttr(node + ".inheritsTransform"):
            raise ValueError("親を継承する単一パスの入力を指定してください")
        local = path.inclusiveMatrix() * path.exclusiveMatrixInverse()
        if local.isSingular():
            raise ValueError("入力の基準マトリクスを反転できません")
        rest.append(local)
    root = cmds.createNode("transform", name="virtualFk#", skipSelect=True, **({"parent": parent} if parent else {}))
    previous = None
    for i, node in enumerate(nodes):
        product = cmds.createNode("multMatrix", name="virtualFkMatrix#", skipSelect=True)
        cmds.connectAttr(node + ".matrix", product + ".matrixIn[0]")
        cmds.connectAttr(node + ".offsetParentMatrix", product + ".matrixIn[1]")
        if previous:
            cmds.setAttr(product + ".matrixIn[2]", *rest[i-1].inverse(), type="matrix")
            cmds.connectAttr(previous, product + ".matrixIn[3]")
        output = cmds.createNode("transform", name="virtualFkOutput#", parent=root, skipSelect=True)
        previous = product + ".matrixSum"
        cmds.connectAttr(previous, output + ".offsetParentMatrix")
        cmds.addAttr(output, longName="mlrigFkInput", attributeType="message")
        cmds.connectAttr(node + ".message", output + ".mlrigFkInput")
    return root
