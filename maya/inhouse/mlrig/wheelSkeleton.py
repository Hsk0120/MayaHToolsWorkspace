"""既存の車輪の回転中心に、親の姿勢を継承するベース骨を追加する。"""

from maya import cmds
from mlib.decorator import undoTransaction


_OWNER = "mlrigWheelSource"


@undoTransaction("mlrigWheelSkeleton")
def edit(remove=False):
    """選択車輪の直下に専用骨を作成し、未使用の専用骨だけを削除する。"""
    wheels = cmds.ls(selection=True, long=True, type="transform") or []
    if not wheels:
        raise ValueError("既存の車輪トランスフォームを選択してください")
    result = []
    for wheel in wheels:
        joints = cmds.listRelatives(wheel, children=True, type="joint", fullPath=True) or []
        owned = [joint for joint in joints if cmds.objExists(joint + "." + _OWNER)
                 and cmds.isConnected(wheel + ".message", joint + "." + _OWNER)]
        if remove:
            for joint in owned:
                pairs = cmds.listConnections(joint, source=True, destination=True, connections=True, plugs=True) or []
                if cmds.listRelatives(joint, children=True) or any(plug.rsplit(".", 1)[-1] != _OWNER for plug in pairs[::2]):
                    raise ValueError("接続または子があるため骨を削除できません: " + joint)
                cmds.delete(joint)
        elif owned:
            result.extend(owned)
        else:
            joint = cmds.createNode("joint", parent=wheel, name="wheelBase#", skipSelect=True)
            joint = wheel + "|" + joint.rsplit("|", 1)[-1]
            cmds.addAttr(joint, longName=_OWNER, attributeType="message")
            cmds.connectAttr(wheel + ".message", joint + "." + _OWNER)
            result.append(joint)
    return result
