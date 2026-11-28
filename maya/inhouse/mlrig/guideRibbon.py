"""2本の既存ガイドに沿う面を作り、メッシュと小物を同じ面座標で駆動する。"""

import mlib
from maya import cmds
from mlib.decorator import undoTransaction

from .curveLengthTools import _curve
from .surfaceGuide import meshPath


@undoTransaction("mlrigGuideRibbon")
def bind(first, second, mesh, attachments):
    """各頂点と小物の最近接面座標を記録し、作成時のオフセットを保って接続する。"""
    a, b = _curve(first), _curve(second)
    dst = meshPath(mesh)
    if a[0] == b[0] or dst.isInstanced() or mlib.ls(cmds.listHistory(mesh), type="skinCluster").getNames():
        raise ValueError("別々のガイドとスキン設定前のメッシュを指定してください")
    curves = (a[1], b[1])
    if (any(c.getPlug("form").get() != 0 for c in curves)
            or a[1].getPlug("degree").get() != b[1].getPlug("degree").get()
            or a[1].getKnots() != b[1].getKnots()):
        raise ValueError("次数とノット列が一致する開いたカーブを指定してください")
    u, v = a[1].getParamRange()
    for i in range(33):
        points = [c.getAtParam(u + (v - u) * i / 32, ws=True) for c in curves]
        if points[0].distanceTo(points[1]) < 1e-7:
            raise ValueError("ガイド間の幅が不足しています")
    for item in attachments:
        if not cmds.objectType(item, isAType="transform") or any(
            cmds.connectionInfo(item + "." + k, isDestination=True) or cmds.getAttr(item + "." + k, lock=True)
            for k in ("tx", "ty", "tz", "rx", "ry", "rz")
        ):
            raise ValueError("小物の移動と回転を編集できません: " + item)
        if any(n == item or n.startswith(item + "|") for n in (a[0], b[0], dst.getName(full=True))):
            raise ValueError("ガイドやメッシュの祖先を小物には指定できません")
    loft = mlib.createNode("loft", name="guideRibbonLoft#").getName()
    cmds.setAttr(loft + ".degree", 1)
    cmds.setAttr(loft + ".autoReverse", False)
    for i, (world, _) in enumerate((a, b)):
        cmds.connectAttr(world, "{}.inputCurve[{}]".format(loft, i))
    group = mlib.createNode("transform", name="guideRibbon#").getName()
    cmds.setAttr(group + ".inheritsTransform", False)
    shape = mlib.createNode("nurbsSurface", parent=group).getName()
    cmds.connectAttr(loft + ".outputSurface", shape + ".create")
    cmds.setAttr(shape + ".visibility", False)
    surface = mlib.getNode(shape)
    pin = mlib.createNode("uvPin", name="guideRibbonPin#").getName()
    cmds.connectAttr(loft + ".outputSurface", pin + ".deformedGeometry")
    cmds.setAttr(pin + ".normalizedIsoParms", False)
    mesh_points = dst.getPoints(ws=True)
    points = mesh_points + [mlib.getNode(n).getPivot(ws=True) for n in attachments]
    joints = []
    for i, point in enumerate(points):
        _, u, v = surface.getClosestPoint(point, ws=True)
        cmds.setAttr("{}.coordinate[{}]".format(pin, i), u, v)
        joint = mlib.createNode("joint", parent=group, name="guideRibbonJoint#").getName()
        cmds.connectAttr("{}.outputMatrix[{}]".format(pin, i), joint + ".offsetParentMatrix")
        if i < len(mesh_points):
            joints.append(joint)
        else:
            cmds.parentConstraint(joint, attachments[i - len(mesh_points)], maintainOffset=True)
    skin = cmds.skinCluster(joints, mesh, toSelectedBones=True, maximumInfluences=1, name="guideRibbonSkin#")[0]
    for i, joint in enumerate(joints):
        cmds.skinPercent(skin, "{}.vtx[{}]".format(mesh, i), transformValue=[(joint, 1)], zeroRemainingInfluences=True)
    return skin
