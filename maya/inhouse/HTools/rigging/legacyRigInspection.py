"""旧セットアップの候補を診断し、選んだトップ骨のSSCを個別に更新する。"""

import re
from pathlib import Path

import maya.cmds as cmds


_LEGACY = {
    "eST3vectorUtility": "Utility Node: inspect inputs before mapping to Maya utility nodes.",
    "eST3doubleUtility": "Utility Node: inspect inputs before mapping to Maya utility nodes.",
    "eST3flattenSurface": "Flatten: compare surface CVs and downstream parameters.",
    "eST3fakeRope": "Fake Rope: compare chain dynamics, time history and reset behavior.",
}


def _marker(node, kind):
    """識別可能な型と名前から比較対象を返す。"""
    if kind in _LEGACY:
        return f"{node} ({kind})  |  {_LEGACY[kind]}"
    if kind in ("multMatrix", "eST3decomposeMatrix") and "epConstMat" in node:
        return f"{node}  |  Possible Exclusive Parent. Compare driver-local motion and parent isolation."
    return None


def inspectFile(path):
    """Maya ASCIIのノード宣言を読み、シーンを開かず旧機能の候補を返す。"""
    pattern = re.compile(r'^createNode\s+(\w+)\s+[^;]*?-n\s+"([^"]+)"')
    rows = []
    with Path(path).open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            match = pattern.match(line)
            if match:
                row = _marker(match[2], match[1])
                if row:
                    rows.append(row)
    return sorted(rows)


def inventory():
    """既知の型と名前付き拘束候補を表示し、ベイク済み形状の由来は推測しない。"""
    rows = []
    for node in cmds.ls(long=True) or []:
        kind = cmds.nodeType(node)
        if kind in ("unknown", "unknownDag", "unknownTransform"):
            kind = cmds.unknownNode(node, query=True, realClassName=True) or kind
        row = _marker(node, kind)
        if row:
            rows.append(row)
    rows.append("Uniform: a baked NURBS surface has no unique operation marker. Compare its knot ranges and CVs.")
    return sorted(rows)


def pending(joints):
    """指定トップ骨のうち、スケール評価を変えずSSCを有効にできるものを返す。"""
    changes = []
    for joint in joints:
        if cmds.nodeType(joint) != "joint" or cmds.listRelatives(joint, parent=True, type="joint"):
            raise ValueError("Choose top skeleton joints.")
        plug = joint + ".segmentScaleCompensate"
        if cmds.getAttr(plug):
            continue
        if cmds.referenceQuery(joint, isNodeReferenced=True) or not cmds.getAttr(plug, settable=True) or cmds.connectionInfo(plug, isDestination=True):
            raise ValueError("The SSC plug is referenced, driven or locked: " + joint)
        if cmds.listConnections(joint+".inverseScale", source=True, destination=False) or cmds.getAttr(joint+".inverseScale")[0] != (1,1,1):
            raise ValueError("Validate inverse-scale behavior before migration: " + joint)
        changes.append(plug)
    return changes


def run():
    """旧機能の診断と、選択トップ骨の限定的な更新を表示する。"""
    window = "HToolsLegacyRigInspection"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Inspect Legacy Rig")
    cmds.columnLayout(adjustableColumn=True)
    report = cmds.scrollField(editable=False, height=200)

    def scan(*_):
        cmds.scrollField(report, edit=True, text="\n".join(inventory()))

    def update(apply):
        joints = cmds.ls(selection=True, long=True, type="joint") or []
        if not joints:
            raise ValueError("Select the top skeleton joints to inspect.")
        plugs = pending(joints)
        if apply and plugs:
            from mlib.decorator import undoTransaction

            @undoTransaction("Migrate Top Joint SSC")
            def set_values():
                """事前に確認したSSCのみを更新する。"""
                if cmds.autoKeyframe(query=True, state=True):
                    raise ValueError("Disable Auto Key before migrating SSC.")
                for plug in plugs:
                    cmds.setAttr(plug, True)
            set_values()
        cmds.scrollField(report, edit=True, text="\n".join(plug+"  off -> on" for plug in plugs) or "No changes.")

    def scan_file(*_):
        paths = cmds.fileDialog2(fileMode=1, fileFilter="Maya ASCII (*.ma)")
        if paths:
            rows = inspectFile(paths[0])
            cmds.scrollField(report, edit=True, text="\n".join(rows) or "No recognized legacy node declarations.")

    cmds.button(label="Inspect saved Maya ASCII", command=scan_file)
    cmds.button(label="Inspect legacy setup markers", command=scan)
    cmds.button(label="Preview top joint SSC", command=lambda *_: update(False))
    cmds.button(label="Enable SSC on selected top joints", command=lambda *_: update(True))
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
