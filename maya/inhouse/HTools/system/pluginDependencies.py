"""シーンまたは選択階層の履歴を調べ、使用中のプラグインを一覧表示する。"""

from pathlib import Path

import maya.cmds as cmds


def dependencies(selectionOnly=False):
    """調査範囲に含まれるプラグイン名、型名、ノード名を取得する。"""
    if selectionOnly:
        selected = cmds.ls(selection=True, objectsOnly=True, long=True) or []
        nodes = set(selected)
        if selected:
            nodes.update(cmds.listRelatives(selected, allDescendents=True, fullPath=True) or [])
            nodes.update(cmds.ls(cmds.listHistory(sorted(nodes)) or [], long=True) or [])
    else:
        nodes = set(cmds.ls(long=True) or [])
    owners = {}
    for plugin in cmds.pluginInfo(query=True, listPlugins=True) or []:
        for node_type in cmds.pluginInfo(plugin, query=True, dependNode=True) or []:
            owners[node_type] = plugin
    result = []
    for node in nodes:
        node_type = cmds.nodeType(node)
        owner = owners.get(node_type)
        if node_type in ("unknown", "unknownDag", "unknownTransform"):
            owner = cmds.unknownNode(node, query=True, plugin=True) or "<unknown>"
        if owner:
            result.append((owner, node_type, node))
    return sorted(result)


def savedRequirements():
    """現在開いているMaya ASCIIのヘッダーから保存済みの依存宣言を読む。"""
    name = cmds.file(query=True, sceneName=True)
    if not name or Path(name).suffix.lower() != ".ma":
        return "Available for saved Maya ASCII scenes."
    declarations = []
    pending = []
    try:
        with Path(name).open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                line = line.strip()
                if pending or line.startswith("requires "):
                    pending.append(line)
                    if line.endswith(";"):
                        declarations.append(" ".join(pending))
                        pending.clear()
                elif line.startswith(("currentUnit ", "fileInfo ", "createNode ")):
                    break
    except OSError as error:
        return f"Cannot read saved scene: {error}"
    return "\n".join(declarations) or "No requires declarations found."


def run():
    """使用プラグインと対象ノードの診断画面を表示する。"""
    window = "HToolsPluginDependencies"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Plug-in Dependencies", widthHeight=(640, 400))
    cmds.columnLayout(adjustableColumn=True)
    scope = cmds.checkBox(label="Selected hierarchy and history", value=True)
    output = cmds.scrollField(editable=False, wordWrap=False, height=320)

    def refresh(*_):
        rows = dependencies(cmds.checkBox(scope, query=True, value=True))
        lines = []
        for owner, node_type, node in rows:
            location = "Local"
            if cmds.referenceQuery(node, isNodeReferenced=True):
                location = "Reference: " + cmds.referenceQuery(node, filename=True)
            if node_type in ("unknown", "unknownDag", "unknownTransform"):
                original = cmds.unknownNode(node, query=True, realClassName=True)
                if original:
                    node_type += " (" + original + ")"
            lines.append("  |  ".join((owner, node_type, node, location)))
        report = "\n".join(lines) or "No plug-in nodes in this scope."
        report += "\n\nSaved file requires (whole scene)\n" + savedRequirements()
        cmds.scrollField(output, edit=True, text=report)

    cmds.checkBox(scope, edit=True, changeCommand=refresh)
    cmds.button(label="Refresh", command=refresh)
    refresh()
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
