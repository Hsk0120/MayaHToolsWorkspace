"""選択したリグの公開チャンネルと接続を役割ごとに比較する。"""

import re

import maya.cmds as cmds


def inspect(roots):
    """公開先・ロック・参照・実際の接続プラグを各個体について列挙する。"""
    from mlrig.publishedChannels import getPorts, resolveChannels

    edits = {}
    records = {}
    for root in roots:
        ports = getPorts(root)
        resolved, missing = resolveChannels(root, {role: (port["path"], port["attribute"]) for role, port in ports.items()})
        records[root] = {}
        for role, plug in resolved.items():
            node = plug.split(".", 1)[0]
            flags = []
            if cmds.getAttr(plug, lock=True):
                flags.append("Locked")
            if cmds.referenceQuery(node, isNodeReferenced=True):
                flags.append("Referenced")
                ref = cmds.referenceQuery(node, referenceNode=True)
                if ref not in edits:
                    edits[ref] = cmds.referenceQuery(ref, editStrings=True, showDagPath=True) or []
                leaf = node.rsplit("|", 1)[-1]
                attr = plug.split(".", 1)[1]
                aliases = set()
                for member in [attr] + (cmds.attributeQuery(attr, node=node, listParent=True) or []):
                    aliases.add(cmds.attributeQuery(member, node=node, longName=True))
                    aliases.add(cmds.attributeQuery(member, node=node, shortName=True))
                for edit in edits[ref]:
                    tokens = re.findall(r'"([^"]*)"|([^\s"]+)', edit)
                    names = {(quoted or bare).rsplit("|", 1)[-1] for quoted, bare in tokens}
                    if any(leaf + "." + alias in names for alias in aliases):
                        flags.append("Reference edit: " + edit)
            for source, label in ((True, "Input"), (False, "Output")):
                neighbors = cmds.listConnections(plug, source=source, destination=not source, plugs=True) or []
                for neighbor in sorted(neighbors):
                    flags.append(f"{label} {neighbor} ({cmds.nodeType(neighbor.split('.', 1)[0])})")
                if len(neighbors) > 1:
                    flags.append(f"{len(neighbors)} {label.lower()} connections")
            if not cmds.listConnections(plug):
                flags.append("Unconnected")
            records[root][role] = "  |  ".join([plug] + flags)
        for role in missing:
            records[root][role] = "Missing target"
    roles = sorted({role for record in records.values() for role in record})
    return [f"{role}  |  {root}  |  {records[root].get(role, 'No published role')}" for role in roles for root in roots]


def run():
    """リグルートを選択して現在の接続状態を確認する。"""
    window = "HToolsPublishedChannelAudit"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Compare Published Channels")
    cmds.columnLayout(adjustableColumn=True)
    output = cmds.scrollField(editable=False, height=240)

    def refresh(*_):
        roots = cmds.ls(selection=True, long=True, transforms=True) or []
        rows = inspect(roots)
        cmds.scrollField(output, edit=True, text="\n".join(rows) or "Select rig roots with published channels.")

    cmds.button(label="Compare selected rigs", command=refresh)
    refresh()
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
