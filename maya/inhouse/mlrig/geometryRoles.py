"""ブロック・バインド・レンダーの3表現を同じ組に登録して表示を切り替える。"""

import mlib
from maya import cmds
from mlib.decorator import undoTransaction


_ROLES = ("block", "bind", "render")


@undoTransaction("mlrigRegisterGeometryRoles")
def register(nodes):
    """指定順の3形状をローカルのnetworkノードにメッセージ接続する。"""
    if len(nodes) != 3 or len(set(nodes)) != 3:
        raise ValueError("ブロック・バインド・レンダーの順に異なる3形状を選択してください")
    for node in nodes:
        if not cmds.listRelatives(node, shapes=True, type="mesh", noIntermediate=True):
            raise ValueError("メッシュ形状を持つトランスフォームを選択してください: " + node)
        if any(other.startswith(node + "|") for other in nodes):
            raise ValueError("親子関係にある表現は切り替えられません")
    group = mlib.createNode("network", name="mlrigGeometryRoles#", skipSelect=True).getName()
    for node, role in zip(nodes, _ROLES):
        cmds.addAttr(group, longName=role + "Geometry", attributeType="message")
        cmds.connectAttr(node + ".message", group + "." + role + "Geometry")
    mlib.select(group, replace=True)
    return group


@undoTransaction("mlrigSwitchGeometryRole")
def switch(group, role):
    """登録した3表現のvisibilityを切り替え、配線済み・ロック済みの変更は事前に拒否する。"""
    if role not in _ROLES or cmds.nodeType(group) != "network":
        raise ValueError("登録した形状グループと有効な役割を指定してください")
    changes = {}
    for member in _ROLES:
        plug = group + "." + member + "Geometry"
        source = cmds.connectionInfo(plug, sourceFromDestination=True) if cmds.objExists(plug) else ""
        if not source:
            raise ValueError("形状の登録が見つかりません: " + member)
        visibility = source.rsplit(".", 1)[0] + ".visibility"
        value = member == role
        if cmds.getAttr(visibility) != value:
            if cmds.autoKeyframe(query=True, state=True) or cmds.connectionInfo(visibility, isDestination=True) or not cmds.getAttr(visibility, settable=True):
                raise ValueError("表示を変更できません: " + visibility)
            changes[visibility] = value
    for plug, value in changes.items():
        cmds.setAttr(plug, value)
    return group
