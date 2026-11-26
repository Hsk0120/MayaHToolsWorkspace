"""評価済みカーブの弧長補正と、折れ線に沿うチェーンを生成する。"""

from maya import cmds
from maya.api import OpenMaya as om2
from mlib.decorator import undoTransaction

from .setups.rotationMinimizingFrames import RotationMinimizingFrames


def _curve(node):
    shapes = [node] if cmds.nodeType(node) == "nurbsCurve" else cmds.listRelatives(node, shapes=True, fullPath=True, noIntermediate=True, type="nurbsCurve") or []
    if len(shapes) != 1:
        raise ValueError("評価対象のカーブを1本指定してください")
    path = om2.MSelectionList().add(shapes[0]).getDagPath(0)
    return "{}.worldSpace[{}]".format(path.fullPathName(), path.instanceNumber()), om2.MFnNurbsCurve(path)


def _length_ratio(world, name):
    """現在弧長に対する作成時弧長の比を返す。退化時の除数は作成時の長さ。"""
    info = cmds.createNode("curveInfo", name=name + "Length#", skipSelect=True)
    cmds.connectAttr(world, info + ".inputCurve")
    rest = cmds.getAttr(info + ".arcLength")
    if rest <= 1e-8:
        raise ValueError("カーブの弧長が不足しています")
    safe = cmds.createNode("condition", name=name + "LengthGuard#", skipSelect=True)
    cmds.setAttr(safe + ".operation", 2)
    cmds.setAttr(safe + ".secondTerm", 1e-8)
    cmds.connectAttr(info + ".arcLength", safe + ".firstTerm")
    cmds.connectAttr(info + ".arcLength", safe + ".colorIfTrueR")
    # restとライブ値を同じDG単位で保持する。
    rest = cmds.getAttr(safe + ".firstTerm")
    cmds.setAttr(safe + ".colorIfFalseR", rest)
    divide = cmds.createNode("multiplyDivide", name=name + "Ratio#", skipSelect=True)
    cmds.setAttr(divide + ".operation", 2)
    cmds.setAttr(divide + ".input1X", rest)
    cmds.connectAttr(safe + ".outColorR", divide + ".input2X")
    return divide + ".outputX"


@undoTransaction("mlrigKeepCurveLength")
def keepLength(curve):
    """現在の弧長を記録し、評価後の形状を始点中心に一様補正する出力を作る。"""
    world, _ = _curve(curve)
    ratio = _length_ratio(world, "curveCorrection")
    point = cmds.createNode("pointOnCurveInfo", name="curveCorrectionStart#", skipSelect=True)
    cmds.connectAttr(world, point + ".inputCurve")
    cmds.setAttr(point + ".turnOnPercentage", True)
    scale = cmds.createNode("transform", name="curveLengthScale#", skipSelect=True)
    cmds.connectAttr(point + ".position", scale + ".scalePivot")
    for axis in "XYZ":
        cmds.connectAttr(ratio, scale + ".scale" + axis)
    geometry = cmds.createNode("transformGeometry", name="curveLengthCorrection#", skipSelect=True)
    shape_name, element = world.split(".worldSpace", 1)
    matrix = cmds.createNode("multMatrix", name="curveLengthWorldCorrection#", skipSelect=True)
    cmds.connectAttr(shape_name + ".worldMatrix" + element, matrix + ".matrixIn[0]")
    cmds.connectAttr(scale + ".matrix", matrix + ".matrixIn[1]")
    cmds.connectAttr(matrix + ".matrixSum", geometry + ".transform")
    cmds.connectAttr(shape_name + ".local", geometry + ".inputGeometry")
    output = cmds.createNode("transform", name="fixedLengthCurve#", skipSelect=True)
    shape = cmds.createNode("nurbsCurve", parent=output, skipSelect=True)
    cmds.connectAttr(geometry + ".outputGeometry", shape + ".create")
    cmds.select(output, replace=True)
    return output


@undoTransaction("mlrigPolylineChain")
def polylineChain(curve, count=5):
    """開いた折れ線上を初期の弧長間隔で追従する。全長が短い場合は全区間に等配する。"""
    world, fn = _curve(curve)
    if fn.degree != 1 or fn.form != om2.MFnNurbsCurve.kOpen or type(count) is not int or count < 3:
        raise ValueError("開いた1次カーブと3以上の点数を指定してください")
    cvs = fn.cvPositions(om2.MSpace.kWorld)
    if any(a.distanceTo(b) <= 1e-7 for a, b in zip(cvs, list(cvs)[1:])):
        raise ValueError("長さゼロの区間があります")
    root = cmds.createNode("transform", name="polylineChain#", skipSelect=True)
    ratio = _length_ratio(world, "polyline")
    clamp = cmds.createNode("clamp", name="polylineRange#", skipSelect=True)
    cmds.setAttr(clamp + ".maxR", 1)
    cmds.connectAttr(ratio, clamp + ".inputR")
    samples = []
    for i in range(count):
        fraction = cmds.createNode("multiplyDivide", name="polylineFraction#", skipSelect=True)
        cmds.connectAttr(clamp + ".outputR", fraction + ".input1X")
        cmds.setAttr(fraction + ".input2X", i / float(count - 1))
        unit = cmds.createNode("unitConversion", name="polylineFractionValue#", skipSelect=True)
        cmds.connectAttr(fraction + ".outputX", unit + ".input")
        cmds.setAttr(unit + ".conversionFactor", 1)
        path = cmds.createNode("motionPath", name="polylineSample#", skipSelect=True)
        cmds.setAttr(path + ".fractionMode", True)
        cmds.connectAttr(world, path + ".geometryPath")
        cmds.connectAttr(unit + ".output", path + ".uValue")
        sample = cmds.createNode("transform", parent=root, name="polylinePosition#", skipSelect=True)
        cmds.setAttr(sample + ".inheritsTransform", False)
        cmds.connectAttr(path + ".allCoordinates", sample + ".translate")
        samples.append(sample)
    first, second = [om2.MVector(*cmds.xform(n, query=True, worldSpace=True, translation=True)) for n in samples[:2]]
    up = "z" if abs((second - first).normal().y) > .95 else "y"
    graph = RotationMinimizingFrames.create(samples, name=root + "_frames", upAxis=up, keepOffset=False)
    joints = []
    for i in range(count):
        joint = cmds.createNode("joint", parent=root, name="polylineJoint#", skipSelect=True)
        cmds.setAttr(joint + ".inheritsTransform", False)
        cmds.connectAttr(graph.container.getName() + ".matrix" + str(i), joint + ".offsetParentMatrix")
        joints.append(joint)
    cmds.select(joints, replace=True)
    return joints
