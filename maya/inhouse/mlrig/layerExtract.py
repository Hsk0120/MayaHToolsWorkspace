"""選択した骨格・制御の役割を作業用レイヤーに取り出し、編集した役割だけを戻す。"""

from maya import cmds
from mlib.decorator import undoTransaction


def _curves(node):
    return cmds.listRelatives(node, shapes=True, noIntermediate=True, type="nurbsCurve", fullPath=True) or []


def _source(node, attr):
    return (cmds.listConnections(node + "." + attr, source=True, destination=False, shapes=True) or [None])[0]


@undoTransaction("mlrigExtractLayer")
def extract(nodes, kind):
    """役割の実ノードと親をメッセージで記録し、選択した階層と制御形状を複製する。"""
    if not nodes or kind not in ("base", "bind", "control"):
        raise ValueError("取り出すレイヤーの役割を選択してください")
    nodes = cmds.ls(nodes, long=True) or []
    if any(not cmds.objectType(n, isAType="transform") or (kind != "control" and cmds.nodeType(n) != "joint") for n in nodes):
        raise ValueError("骨格レイヤーは骨、制御レイヤーはトランスフォームを指定してください")
    group = cmds.createNode("transform", name=kind + "LayerEdit#")
    copies = {}
    for n in sorted(nodes, key=lambda p: p.count("|")):
        parent = n.rpartition("|")[0]
        copy = cmds.createNode(
            "transform" if kind == "control" else "joint",
            parent=copies.get(parent, group),
            name=n.rpartition("|")[2].split(":")[-1] + "Edit#",
        )
        copy = cmds.ls(copy, long=True)[0]
        copies[n] = copy
        cmds.xform(copy, worldSpace=True, matrix=cmds.xform(n, query=True, worldSpace=True, matrix=True))
        cmds.addAttr(copy, longName="mlrigLayerKind", dataType="string")
        cmds.setAttr(copy + ".mlrigLayerKind", kind, type="string")
        for attr, target in (("mlrigLayerSource", n), ("mlrigLayerParent", parent)):
            cmds.addAttr(copy, longName=attr, attributeType="message")
            if target:
                cmds.connectAttr(target + ".message", copy + "." + attr)
        for shape in _curves(n) if kind == "control" else []:
            temp = cmds.duplicateCurve(shape, constructionHistory=False, local=True)[0]
            child = cmds.listRelatives(temp, shapes=True, fullPath=True)[0]
            edit_shape = cmds.parent(child, copy, shape=True, relative=True)[0]
            cmds.delete(temp)
            cmds.addAttr(edit_shape, longName="mlrigCurveSource", attributeType="message")
            cmds.connectAttr(shape + ".message", edit_shape + ".mlrigCurveSource")
    cmds.select(list(copies.values()))
    return list(copies.values())


@undoTransaction("mlrigMergeLayerRoles")
def merge(nodes):
    """選択した編集用役割の姿勢・CVを元の役割へ適用する。"""
    if not nodes or any(not cmds.objExists(n + ".mlrigLayerSource") for n in nodes):
        raise ValueError("統合する編集用の役割を選択してください")
    for n in sorted(nodes, key=lambda p: p.count("|")):
        src = _source(n, "mlrigLayerSource")
        if not src:
            raise ValueError("元の役割が見つかりません")
        src = cmds.ls(src, long=True)[0]
        parent = _source(n, "mlrigLayerParent")
        if (cmds.ls(parent, long=True)[0] if parent else "") != src.rpartition("|")[0]:
            raise ValueError("元の役割の親が変更されています")
        desired = cmds.xform(n, query=True, worldSpace=True, matrix=True)
        actual = cmds.xform(src, query=True, worldSpace=True, matrix=True)
        if max(abs(a - b) for a, b in zip(actual, desired)) > 1e-7:
            channels = [src + "." + attr + axis for attr in ("translate", "rotate", "scale") for axis in "XYZ"] + [
                src + ".shear" + pair for pair in ("XY", "XZ", "YZ")
            ]
            if cmds.autoKeyframe(query=True, state=True) or any(
                not cmds.getAttr(p, settable=True) or cmds.connectionInfo(p, isDestination=True) for p in channels
            ):
                raise ValueError("姿勢を変更する役割に入力・ロックまたは自動キーがあります: " + src)
            cmds.xform(src, worldSpace=True, matrix=desired)
        for shape in _curves(n):
            original = _source(shape, "mlrigCurveSource") if cmds.objExists(shape + ".mlrigCurveSource") else None
            if not original or cmds.ls(original, long=True)[0] not in _curves(src):
                raise ValueError("元の制御形状を確認してください")
            cvs = cmds.ls(original + ".cv[*]", flatten=True)
            edits = cmds.ls(shape + ".cv[*]", flatten=True)
            if len(cvs) != len(edits):
                raise ValueError("制御形状のCV数が一致しません")
            for i, (cv, edit) in enumerate(zip(cvs, edits)):
                p = cmds.xform(edit, query=True, objectSpace=True, translation=True)
                current = cmds.xform(cv, query=True, objectSpace=True, translation=True)
                if max(abs(a - b) for a, b in zip(current, p)) > 1e-7:
                    cp = "{}.controlPoints[{}]".format(original, i)
                    if cmds.connectionInfo(original + ".create", isDestination=True) or any(
                        cmds.connectionInfo(cp + suffix, isDestination=True) or cmds.getAttr(cp + suffix, lock=True)
                        for suffix in ("", ".xValue", ".yValue", ".zValue")
                    ):
                        raise ValueError("履歴・入力・ロックのある元形状は更新できません")
                    cmds.xform(cv, objectSpace=True, translation=p)
    return nodes
