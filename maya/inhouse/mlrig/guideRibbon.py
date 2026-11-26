"""2本の既存ガイドに沿う面を作り、メッシュと小物を同じ面座標で駆動する。"""

from maya import cmds
from maya.api import OpenMaya as om2
from mlib.decorator import undoTransaction

from .curveLengthTools import _curve
from .surfaceGuide import meshPath


@undoTransaction("mlrigGuideRibbon")
def bind(first, second, mesh, attachments):
    """各頂点と小物の最近接面座標を記録し、作成時のオフセットを保って接続する。"""
    a, b = _curve(first), _curve(second)
    dst = meshPath(mesh)
    if a[0] == b[0] or dst.isInstanced() or cmds.ls(cmds.listHistory(mesh), type="skinCluster"):
        raise ValueError("別々のガイドとスキン設定前のメッシュを指定してください")
    curves = (a[1], b[1])
    if any(c.form != om2.MFnNurbsCurve.kOpen for c in curves) or a[1].degree != b[1].degree or list(a[1].knots()) != list(b[1].knots()):
        raise ValueError("次数とノット列が一致する開いたカーブを指定してください")
    for i in range(33):
        u, v = a[1].knotDomain
        points = [c.getPointAtParam(u + (v - u) * i / 32, om2.MSpace.kWorld) for c in curves]
        if points[0].distanceTo(points[1]) < 1e-7:
            raise ValueError("ガイド間の幅が不足しています")
    for item in attachments:
        if not cmds.objectType(item, isAType="transform") or any(
            cmds.connectionInfo(item + "." + k, isDestination=True) or cmds.getAttr(item + "." + k, lock=True)
            for k in ("tx", "ty", "tz", "rx", "ry", "rz")
        ):
            raise ValueError("小物の移動と回転を編集できません: " + item)
        if any(n == item or n.startswith(item + "|") for n in (a[0], b[0], dst.fullPathName())):
            raise ValueError("ガイドやメッシュの祖先を小物には指定できません")
    loft = cmds.createNode("loft", name="guideRibbonLoft#")
    cmds.setAttr(loft + ".degree", 1)
    cmds.setAttr(loft + ".autoReverse", False)
    for i, (world, _) in enumerate((a, b)):
        cmds.connectAttr(world, "{}.inputCurve[{}]".format(loft, i))
    group = cmds.createNode("transform", name="guideRibbon#")
    cmds.setAttr(group + ".inheritsTransform", False)
    shape = cmds.createNode("nurbsSurface", parent=group)
    cmds.connectAttr(loft + ".outputSurface", shape + ".create")
    cmds.setAttr(shape + ".visibility", False)
    surface = om2.MFnNurbsSurface(om2.MSelectionList().add(shape).getDagPath(0))
    pin = cmds.createNode("uvPin", name="guideRibbonPin#")
    cmds.connectAttr(loft + ".outputSurface", pin + ".deformedGeometry")
    cmds.setAttr(pin + ".normalizedIsoParms", False)
    mesh_points = list(om2.MFnMesh(dst).getPoints(om2.MSpace.kWorld))
    points = mesh_points + [om2.MFnTransform(om2.MSelectionList().add(n).getDagPath(0)).rotatePivot(om2.MSpace.kWorld) for n in attachments]
    joints = []
    for i, point in enumerate(points):
        _, u, v = surface.closestPoint(point, space=om2.MSpace.kWorld)
        cmds.setAttr("{}.coordinate[{}]".format(pin, i), u, v)
        joint = cmds.createNode("joint", parent=group, name="guideRibbonJoint#")
        cmds.connectAttr("{}.outputMatrix[{}]".format(pin, i), joint + ".offsetParentMatrix")
        if i < len(mesh_points):
            joints.append(joint)
        else:
            cmds.parentConstraint(joint, attachments[i - len(mesh_points)], maintainOffset=True)
    skin = cmds.skinCluster(joints, mesh, toSelectedBones=True, maximumInfluences=1, name="guideRibbonSkin#")[0]
    for i, joint in enumerate(joints):
        cmds.skinPercent(skin, "{}.vtx[{}]".format(mesh, i), transformValue=[(joint, 1)], zeroRemainingInfluences=True)
    return skin
