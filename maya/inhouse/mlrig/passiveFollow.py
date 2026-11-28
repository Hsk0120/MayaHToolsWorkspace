"""専用バッファの行列追従を作成し、現在の親空間姿勢を保持して抑制する。"""

import mlib
from maya import cmds
from mlib.decorator import undoTransaction

from .setups.matrixFollow import MatrixFollow


_GRAPH = "mlrigPassiveFollowGraph"


@undoTransaction("mlrigPassiveFollow")
def run(action):
    """作成時は送り・受け側の順に選択し、切り替え時は受け側だけを選択する。"""
    selected = mlib.ls(selection=True, long=True, type="transform").getNames(full=True)
    if action == "create":
        if len(selected) != 2:
            raise ValueError("送り側と専用バッファを順に選択してください")
        source, target = selected
        if cmds.objExists(target + "." + _GRAPH):
            raise ValueError("すでに受動接続が登録されています")
        graph = MatrixFollow.create(source, target, maintain_offset=False)
        cmds.addAttr(target, longName=_GRAPH, attributeType="message", hidden=True)
        cmds.connectAttr(graph.getName() + ".message", target + "." + _GRAPH)
        return target
    if len(selected) != 1 or not cmds.objExists(selected[0] + "." + _GRAPH):
        raise ValueError("受動接続を登録したバッファを1つ選択してください")
    target = selected[0]
    message = cmds.connectionInfo(target + "." + _GRAPH, sourceFromDestination=True)
    if not message or cmds.nodeType(message.rsplit(".", 1)[0]) != "multMatrix":
        raise ValueError("登録された行列ノードがありません")
    source = message.rsplit(".", 1)[0] + ".matrixSum"
    dest = target + ".offsetParentMatrix"
    active = cmds.isConnected(source, dest)
    if not active and cmds.connectionInfo(dest, isDestination=True):
        raise ValueError("別の入力が接続されています")
    if action == "suppress" and active:
        value = cmds.getAttr(dest)
        cmds.disconnectAttr(source, dest)
        cmds.setAttr(dest, *value, type="matrix")
    elif action == "resume" and not active:
        cmds.connectAttr(source, dest)
    elif action == "inspect":
        cmds.confirmDialog(title="受動接続の状態", message=target + ("  追従中" if active else "  抑制中") + "\n" + source, button=["閉じる"])
    return target
