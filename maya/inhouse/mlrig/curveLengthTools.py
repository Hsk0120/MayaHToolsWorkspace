"""評価済みカーブの弧長補正と、折れ線に沿うチェーンを生成する。"""

import mlib
from maya import cmds
from mlib.decorator import undoTransaction
from mlib.maths import Vector

from .setups.rotationMinimizingFrames import RotationMinimizingFrames


def _curve(node):
    shapes = [node] if cmds.nodeType(node) == "nurbsCurve" else cmds.listRelatives(node, shapes=True, fullPath=True, noIntermediate=True, type="nurbsCurve") or []
    if len(shapes) != 1:
        raise ValueError("評価対象のカーブを1本指定してください")
    curve = mlib.getNode(shapes[0])
    return "{}.worldSpace[{}]".format(curve.getName(full=True), curve.getInstanceIndex()), curve


def _length_ratio(world, name):
    """現在弧長に対する作成時弧長の比を返す。退化時の除数は作成時の長さ。"""
    info = mlib.createNode("curveInfo", name=name + "Length#", skipSelect=True).getName()
    cmds.connectAttr(world, info + ".inputCurve")
    rest = cmds.getAttr(info + ".arcLength")
    if rest <= 1e-8:
        raise ValueError("カーブの弧長が不足しています")
    safe = mlib.createNode("condition", name=name + "LengthGuard#", skipSelect=True).getName()
    cmds.setAttr(safe + ".operation", 2)
    cmds.setAttr(safe + ".secondTerm", 1e-8)
    cmds.connectAttr(info + ".arcLength", safe + ".firstTerm")
    cmds.connectAttr(info + ".arcLength", safe + ".colorIfTrueR")
    # restとライブ値を同じDG単位で保持する。
    rest = cmds.getAttr(safe + ".firstTerm")
    cmds.setAttr(safe + ".colorIfFalseR", rest)
    divide = mlib.createNode("multiplyDivide", name=name + "Ratio#", skipSelect=True).getName()
    cmds.setAttr(divide + ".operation", 2)
    cmds.setAttr(divide + ".input1X", rest)
    cmds.connectAttr(safe + ".outColorR", divide + ".input2X")
    return divide + ".outputX"


@undoTransaction("mlrigKeepCurveLength")
def keepLength(curve):
    """現在の弧長を記録し、評価後の形状を始点中心に一様補正する出力を作る。"""
    world, _ = _curve(curve)
    ratio = _length_ratio(world, "curveCorrection")
    point = mlib.createNode("pointOnCurveInfo", name="curveCorrectionStart#", skipSelect=True).getName()
    cmds.connectAttr(world, point + ".inputCurve")
    cmds.setAttr(point + ".turnOnPercentage", True)
    scale = mlib.createNode("transform", name="curveLengthScale#", skipSelect=True).getName()
    cmds.connectAttr(point + ".position", scale + ".scalePivot")
    for axis in "XYZ":
        cmds.connectAttr(ratio, scale + ".scale" + axis)
    geometry = mlib.createNode("transformGeometry", name="curveLengthCorrection#", skipSelect=True).getName()
    shape_name, element = world.split(".worldSpace", 1)
    matrix = mlib.createNode("multMatrix", name="curveLengthWorldCorrection#", skipSelect=True).getName()
    cmds.connectAttr(shape_name + ".worldMatrix" + element, matrix + ".matrixIn[0]")
    cmds.connectAttr(scale + ".matrix", matrix + ".matrixIn[1]")
    cmds.connectAttr(matrix + ".matrixSum", geometry + ".transform")
    cmds.connectAttr(shape_name + ".local", geometry + ".inputGeometry")
    output = mlib.createNode("transform", name="fixedLengthCurve#", skipSelect=True).getName()
    shape = mlib.createNode("nurbsCurve", parent=output, skipSelect=True).getName()
    cmds.connectAttr(geometry + ".outputGeometry", shape + ".create")
    mlib.select(output, replace=True)
    return output


@undoTransaction("mlrigPolylineChain")
def polylineChain(curve, count=5):
    """開いた折れ線上を初期の弧長間隔で追従する。全長が短い場合は全区間に等配する。"""
    world, fn = _curve(curve)
    if fn.getPlug("degree").get() != 1 or fn.getPlug("form").get() != 0 or type(count) is not int or count < 3:
        raise ValueError("開いた1次カーブと3以上の点数を指定してください")
    cvs = fn.getPoints(ws=True)
    if any(a.distanceTo(b) <= 1e-7 for a, b in zip(cvs, list(cvs)[1:])):
        raise ValueError("長さゼロの区間があります")
    root = mlib.createNode("transform", name="polylineChain#", skipSelect=True).getName()
    ratio = _length_ratio(world, "polyline")
    clamp = mlib.createNode("clamp", name="polylineRange#", skipSelect=True).getName()
    cmds.setAttr(clamp + ".maxR", 1)
    cmds.connectAttr(ratio, clamp + ".inputR")
    samples = []
    for i in range(count):
        fraction = mlib.createNode("multiplyDivide", name="polylineFraction#", skipSelect=True).getName()
        cmds.connectAttr(clamp + ".outputR", fraction + ".input1X")
        cmds.setAttr(fraction + ".input2X", i / float(count - 1))
        unit = mlib.createNode("unitConversion", name="polylineFractionValue#", skipSelect=True).getName()
        cmds.connectAttr(fraction + ".outputX", unit + ".input")
        cmds.setAttr(unit + ".conversionFactor", 1)
        path = mlib.createNode("motionPath", name="polylineSample#", skipSelect=True).getName()
        cmds.setAttr(path + ".fractionMode", True)
        cmds.connectAttr(world, path + ".geometryPath")
        cmds.connectAttr(unit + ".output", path + ".uValue")
        sample = mlib.createNode("transform", parent=root, name="polylinePosition#", skipSelect=True).getName()
        cmds.setAttr(sample + ".inheritsTransform", False)
        cmds.connectAttr(path + ".allCoordinates", sample + ".translate")
        samples.append(sample)
    first, second = [Vector(*cmds.xform(n, query=True, worldSpace=True, translation=True)) for n in samples[:2]]
    up = "z" if abs((second - first).normal().y) > .95 else "y"
    graph = RotationMinimizingFrames.create(samples, name=root + "_frames", upAxis=up, keepOffset=False)
    joints = []
    for i in range(count):
        joint = mlib.createNode("joint", parent=root, name="polylineJoint#", skipSelect=True).getName()
        cmds.setAttr(joint + ".inheritsTransform", False)
        cmds.connectAttr(graph.container.getName() + ".matrix" + str(i), joint + ".offsetParentMatrix")
        joints.append(joint)
    mlib.select(joints, replace=True)
    return joints
