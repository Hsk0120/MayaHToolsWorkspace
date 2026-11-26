"""元コントローラーのカーブ形状に追従するローカルの表示プロキシ。"""

from maya import cmds
from maya.api import OpenMaya as om2
from mlib.decorator import undoTransaction


_SOURCE = "mlrigProxyController"


@undoTransaction("mlrigControlProxy")
def run(action):
    """選択したカーブコントローラーのプロキシを作成するか、その参照元を選択する。"""
    selected = cmds.ls(selection=True, long=True, type="transform") or []
    if not selected:
        raise ValueError("コントローラーまたはプロキシを選択してください")
    results = []
    for node in selected:
        port = node + "." + _SOURCE
        if action == "proxySource":
            source = cmds.listConnections(port, source=True, destination=False) if cmds.objExists(port) else []
            if not source:
                raise ValueError("プロキシの参照元がありません: " + node)
            results.append(source[0])
            continue
        if cmds.objExists(port):
            raise ValueError("元コントローラーを選択してください: " + node)
        existing = cmds.listConnections(node + ".message", source=False, destination=True, plugs=True) or []
        proxies = [plug.rsplit(".", 1)[0] for plug in existing if plug.endswith("." + _SOURCE)]
        if proxies:
            results.extend(proxies)
            continue
        shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True, type="nurbsCurve") or []
        if not shapes or any(om2.MSelectionList().add(shape).getDagPath(0).isInstanced() for shape in shapes):
            raise ValueError("単一のDAGパスを持つカーブコントローラーを選択してください: " + node)
        proxy = cmds.createNode("transform", name=node.rsplit("|", 1)[-1].replace(":", "_") + "_proxy#", skipSelect=True)
        cmds.addAttr(proxy, longName=_SOURCE, attributeType="message")
        cmds.connectAttr(node + ".message", proxy + "." + _SOURCE)
        cmds.setAttr(proxy + ".inheritsTransform", False, lock=True)
        cmds.connectAttr(node + ".worldMatrix[0]", proxy + ".offsetParentMatrix")
        for attr in ("translate", "rotate", "scale", "shear", "offsetParentMatrix"):
            cmds.setAttr(proxy + "." + attr, lock=True)
        for shape in shapes:
            display = cmds.createNode("nurbsCurve", parent=proxy, skipSelect=True)
            cmds.connectAttr(shape + ".local", display + ".create")
            cmds.setAttr(display + ".overrideEnabled", True)
            cmds.setAttr(display + ".overrideColor", 17)
        results.append(proxy)
    cmds.select(results, replace=True)
    return cmds.ls(selection=True, long=True)
