"""明示したリグ部品の仕上げ設定を個別に診断・適用する。"""

import maya.cmds as cmds
from mlib.decorator import undoTransaction

_RULES = {
    "Hide setup transform": (("visibility", False),),
    "Hide node from channel history": (("isHistoricallyInteresting", 0),),
    "Hide bind joint drawing": (("drawStyle", 2),),
    "Make render mesh unselectable": (("overrideDisplayType", 2), ("overrideEnabled", True)),
    "Inspect bind mesh materials": (),
}


def inspect(node, rule):
    """選んだ部品・規則について現在値と期待値の異なるプラグを列挙する。"""
    if rule == "Hide bind joint drawing" and cmds.nodeType(node) != "joint":
        raise ValueError("Select a bind joint.")
    if rule == "Hide setup transform" and not cmds.objectType(node, isAType="transform"):
        raise ValueError("Select a setup transform.")
    if rule == "Make render mesh unselectable" and cmds.nodeType(node) != "mesh" and not cmds.listRelatives(node, shapes=True, type="mesh"):
        raise ValueError("Choose a render mesh or its transform.")
    changes = []
    for attribute, expected in _RULES[rule]:
        plug = node + "." + attribute
        value = cmds.getAttr(plug)
        if value != expected:
            changes.append((plug, value, expected))
    return changes


def copyPlan(root, rule):
    """複製に適用するルート規則、不要な中間形状と元の材質を列挙する。"""
    paths = cmds.ls(root, long=True, transforms=True) or []
    if len(paths) != 1:
        raise ValueError("Select one transform.")
    root = paths[0]
    shapes = cmds.listRelatives(root, allDescendents=True, shapes=True, fullPath=True) or []
    unused = []
    materials = {}
    for shape in shapes:
        if cmds.getAttr(shape + ".intermediateObject"):
            destinations = cmds.listConnections(shape, source=False, destination=True, plugs=True) or []
            if not destinations and len(cmds.listRelatives(shape, allParents=True) or []) == 1:
                unused.append(shape)
        elif cmds.nodeType(shape) == "mesh":
            materials[shape] = sorted(set(cmds.listConnections(shape, type="shadingEngine") or []))
    return dict(root=root, attributes=inspect(root, rule), intermediates=unused, materials=materials)


@undoTransaction("Create Clean Export Duplicate")
def duplicateForExport(root, rule):
    """選択した枝を複製し、そのコピーにだけ仕上げ規則を適用する。"""
    if not cmds.undoInfo(query=True, state=True) or cmds.autoKeyframe(query=True, state=True):
        raise ValueError("Enable Undo and disable Auto Key.")
    plan = copyPlan(root, rule)
    root = plan["root"]
    parent, leaf = root.rsplit("|", 1)
    duplicate = cmds.duplicate(root, returnRootsOnly=True, renameChildren=False,
                               name=leaf.rsplit(":", 1)[-1] + "_export")[0]
    target = parent + "|" + duplicate.rsplit("|", 1)[-1]
    if not cmds.objExists(target):
        raise RuntimeError("Cannot resolve export duplicate.")
    # 入力グラフを共有しない複製で再診断する。元に履歴がある中間形状も事前表示の範囲だけを処理する。
    copied = copyPlan(target, rule)
    for plug, _, value in copied["attributes"]:
        if not cmds.getAttr(plug, settable=True) or cmds.connectionInfo(plug, isDestination=True):
            raise ValueError("Duplicate attribute cannot be changed: " + plug)
        cmds.setAttr(plug, value)
    # 複製時の子の改名を避けて元との相対パスを保つ場合だけ除去できる。
    for source in plan["intermediates"]:
        child = target + source[len(root):]
        if child in copied["intermediates"]:
            cmds.delete(child)
    return target


def run():
    """選択ノードに対して仕上げ規則を1件ずつ診断し、表示設定を変更する。"""
    window = "HToolsRigFinish"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Inspect Rig Finishing Rules")
    cmds.columnLayout(adjustableColumn=True)
    menu = cmds.optionMenu(label="Rule")
    for name in _RULES:
        cmds.menuItem(label=name)
    report = cmds.scrollField(editable=False, height=180)

    def update(apply):
        nodes = cmds.ls(selection=True, objectsOnly=True, long=True) or []
        if not nodes:
            raise ValueError("Select rig components for the chosen rule.")
        rule = cmds.optionMenu(menu, query=True, value=True)
        if rule == "Inspect bind mesh materials":
            shapes = cmds.ls(nodes, dag=True, type="mesh", noIntermediate=True, long=True) or []
            lines = [shape + "  |  " + ", ".join(sorted(set(cmds.listConnections(shape, type="shadingEngine") or []))) for shape in shapes]
            cmds.scrollField(report, edit=True, text="\n".join(lines) or "No bind meshes selected.")
            return
        changes = [row for node in nodes for row in inspect(node, rule)]
        if apply and changes:
            if not cmds.undoInfo(query=True, state=True) or cmds.autoKeyframe(query=True, state=True):
                raise ValueError("Enable Undo and disable Auto Key before applying a finishing rule.")
            for plug, _, _ in changes:
                if cmds.referenceQuery(plug.split(".",1)[0], isNodeReferenced=True) or not cmds.getAttr(plug, settable=True) or cmds.connectionInfo(plug, isDestination=True):
                    raise ValueError("The plug is referenced, driven, or locked: " + plug)
            cmds.undoInfo(openChunk=True, chunkName="Apply Rig Finish Rule")
            applied = 0
            try:
                try:
                    for plug, _, expected in changes:
                        cmds.setAttr(plug, expected)
                        applied += 1
                finally:
                    cmds.undoInfo(closeChunk=True)
            except RuntimeError:
                if applied:
                    cmds.undo()
                raise
        lines = [f"{plug}: {old} -> {new}" for plug,old,new in changes]
        cmds.scrollField(report, edit=True, text="\n".join(lines) or "No changes.")

    cmds.button(label="Diagnose selected rule", command=lambda *_: update(False))
    cmds.button(label="Apply selected display rule", command=lambda *_: update(True))
    def exportCopy(apply):
        roots = cmds.ls(selection=True, long=True, transforms=True) or []
        if len(roots) != 1:
            raise ValueError("Select one transform to duplicate.")
        rule = cmds.optionMenu(menu, query=True, value=True)
        plan = copyPlan(roots[0], rule)
        rows = ["Source: " + plan["root"]]
        rows.extend(f"{plug}: {old} -> {new}" for plug, old, new in plan["attributes"])
        rows.extend("Unused intermediate: " + path for path in plan["intermediates"])
        rows.extend(f"Materials: {path} {', '.join(sets)}" for path, sets in plan["materials"].items())
        if apply:
            rows.append("Export duplicate: " + duplicateForExport(roots[0], rule))
        cmds.scrollField(report, edit=True, text="\n".join(rows))

    cmds.button(label="Preview export duplicate cleanup", command=lambda *_: exportCopy(False))
    cmds.button(label="Create cleaned export duplicate", command=lambda *_: exportCopy(True))
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
