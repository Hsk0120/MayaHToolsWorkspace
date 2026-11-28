"""選択TransformとShapeの命名変更候補と名前依存を表示する。"""

import re

import maya.cmds as cmds
from mlib.decorator import undoTransaction


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


def shapeNames(nodes):
    """形状の用途から候補を作成し、参照・ロック・衝突を報告する。"""
    rows = {}
    for path in cmds.ls(nodes, long=True) if nodes else []:
        shapes = cmds.listRelatives(path, shapes=True, fullPath=True) if cmds.objectType(path, isAType="transform") else [path]
        for shape in shapes or []:
            if not cmds.objectType(shape, isAType="shape"):
                continue
            parent = shape.rsplit("|", 1)[0]
            base = parent.rsplit("|", 1)[-1]
            intermediate = cmds.getAttr(shape + ".intermediateObject")
            new = base + ("ShapeOrig" if intermediate else "Shape")
            status = []
            if cmds.referenceQuery(shape, isNodeReferenced=True):
                status.append("Referenced")
            if cmds.lockNode(shape, query=True, lock=True)[0]:
                status.append("Locked")
            if len(cmds.listRelatives(shape, allParents=True, fullPath=True) or []) > 1:
                status.append("Instanced")
            if shape == parent + "|" + new:
                status.append("Unchanged")
            elif cmds.objExists(parent + "|" + new):
                status.append("Name collision")
            rows[shape] = (new, status)
    targets = [path.rsplit("|", 1)[0] + "|" + row[0] for path, row in rows.items()]
    for path, (new, status) in rows.items():
        if targets.count(path.rsplit("|", 1)[0] + "|" + new) > 1 and "Name collision" not in status:
            status.append("Name collision")
    return rows


@undoTransaction("Rename Shapes by Purpose")
def renameShapes(plan):
    """表示した候補のうち選択された行を、再検査してから適用する。"""
    if not plan or not cmds.undoInfo(query=True, state=True):
        raise ValueError("Select preview rows and enable Undo.")
    for path, expected in plan.items():
        if not cmds.objExists(path):
            raise ValueError("Shape was removed: " + path)
        siblings = shapeNames([path.rsplit("|", 1)[0]])
        if path not in siblings or siblings[path] != (expected, []):
            raise ValueError("Refresh the preview: " + path)
    for path, new in plan.items():
        cmds.rename(path, ":" + new)


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
    listing = cmds.textScrollList(allowMultiSelection=True, height=130)
    plan = {}

    def shapePreview(*_):
        plan.clear()
        plan.update(shapeNames(cmds.ls(selection=True, long=True) or []))
        cmds.textScrollList(listing, edit=True, removeAll=True)
        for path, (new, flags) in plan.items():
            cmds.textScrollList(listing, edit=True, append="{} -> {}  {}".format(path, new, ", ".join(flags)))

    def applyRows(*_):
        picks = cmds.textScrollList(listing, query=True, selectIndexedItem=True) or []
        chosen = [list(plan)[i - 1] for i in picks]
        if any(plan[path][1] for path in chosen):
            raise ValueError("Select editable rows without collisions.")
        renameShapes({path: plan[path][0] for path in chosen})
        shapePreview()

    cmds.button(label="Preview selected shapes by purpose", command=shapePreview)
    cmds.button(label="Rename selected preview rows", command=applyRows)
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
