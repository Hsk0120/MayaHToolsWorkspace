"""1本のカーブの回転最小フレームから、対応点を持つ平行な2列を生成する。"""

import math

import mlib
from maya import cmds
from mlib.decorator import undoTransaction

from .setups.rotationMinimizingFrames import RotationMinimizingFrames


@undoTransaction("mlrigParallelStrands")
def create(curve, count, spacing):
    """カーブのパラメーターを等分し、共有するフレームの±Yへ半間隔ずつ配置する。"""
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError("列の間隔は正の有限値で指定してください")
    root = mlib.createNode("transform", name="parallelStrands#", skipSelect=True).getName()
    graph = RotationMinimizingFrames.fromCurve(curve, count, name=root + "_frames")
    rows = [], []
    for index in range(count):
        station = mlib.createNode("transform", parent=root, name=root + "_frame" + str(index), skipSelect=True).getName()
        cmds.setAttr(station + ".inheritsTransform", False)
        cmds.connectAttr(graph.container.getName() + ".matrix" + str(index), station + ".offsetParentMatrix")
        for row, sign, side in zip(rows, (-1, 1), ("A", "B")):
            node = mlib.createNode("transform", parent=station, name=root + "_" + side + str(index), skipSelect=True).getName()
            cmds.setAttr(node + ".ty", sign * spacing / 2)
            row.append(node)
    return rows


def show():
    """選択カーブの列数2、点数と間隔を指定して配置する。"""
    curves = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
    if len(curves) != 1:
        raise ValueError("カーブを1本選択してください")
    window = "mlrigParallelStrands"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="カーブから平行な2列を作成")
    cmds.columnLayout(adjustableColumn=True)
    count = cmds.intFieldGrp(label="各列の点数", value1=5)
    spacing = cmds.floatFieldGrp(label="列の間隔（シーン単位）", value1=2)

    def build(*_):
        rows = create(curves[0], cmds.intFieldGrp(count, query=True, value1=True), cmds.floatFieldGrp(spacing, query=True, value1=True))
        mlib.select(rows[0] + rows[1], replace=True)

    cmds.button(label="2列を作成", command=build)
    cmds.showWindow(window)
    return window
