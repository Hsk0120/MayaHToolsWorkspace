"""選択TransformとShapeの命名変更候補と名前依存を表示する。"""

import re

import maya.cmds as cmds


def preview(nodes, search, replacement):
    """選択範囲の新旧パス・兄弟名の衝突・参照・リグ内保存文字列を確認する。"""
    if not search:
        raise ValueError("Enter the text to find.")
    names = {}
    for node in nodes:
        for path in [node] + (cmds.listRelatives(node, shapes=True, fullPath=True) or []):
            leaf = path.rsplit("|", 1)[1]
            namespace, colon, local = leaf.rpartition(":")
            new = local.replace(search, replacement)
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", new):
                raise ValueError("Invalid resulting name: " + new)
            names[path] = namespace + colon + new
    planned = {}
    for path in names:
        prefix = ""
        parts = []
        for part in path.split("|")[1:]:
            prefix += "|" + part
            parts.append(names.get(prefix, part))
        planned[path] = "|" + "|".join(parts)
    rows = []
    changed = {}
    for path, new in names.items():
        leaf = path.rsplit("|", 1)[1]
        if leaf != new:
            changed[path] = leaf.rsplit(":", 1)[-1]
    data = {}
    for root in {path.split("|")[1] for path in nodes}:
        base = "|" + root
        for owner in [base] + (cmds.listRelatives(base, allDescendents=True, fullPath=True) or []):
            for attr in cmds.listAttr(owner, userDefined=True) or []:
                plug = owner + "." + attr
                if cmds.getAttr(plug, type=True) == "string":
                    data[plug] = cmds.getAttr(plug) or ""
    for path, new_path in planned.items():
        flags = []
        sibling = path.rsplit("|", 1)[0] + "|" + names[path]
        if list(planned.values()).count(new_path) > 1 or (sibling not in planned and cmds.objExists(sibling)):
            flags.append("Name collision")
        if cmds.referenceQuery(path, isNodeReferenced=True):
            flags.append("Referenced")
        if path in changed:
            token = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(changed[path]) + r"(?![A-Za-z0-9_])")
            for plug, value in data.items():
                if token.search(value):
                    flags.append("Stored name in " + plug)
        rows.append(f"{path} -> {new_path}" + ("  |  " + ", ".join(flags) if flags else ""))
    return rows


def run():
    """文字列置換を適用した場合のパスと参照先を表示する。"""
    window = "HToolsRenamePreview"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Preview Rig Names")
    cmds.columnLayout(adjustableColumn=True)
    search = cmds.textFieldGrp(label="Find in local name")
    replacement = cmds.textFieldGrp(label="Replace with")
    report = cmds.scrollField(editable=False, height=200)

    def inspect(*_):
        nodes = cmds.ls(selection=True, transforms=True, long=True) or []
        rows = preview(nodes, cmds.textFieldGrp(search, query=True, text=True),
                       cmds.textFieldGrp(replacement, query=True, text=True))
        cmds.scrollField(report, edit=True, text="\n".join(rows) or "Select rig transforms.")

    cmds.button(label="Preview names and dependencies", command=inspect)
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
