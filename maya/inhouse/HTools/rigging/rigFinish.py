"""明示したリグ部品の仕上げ設定を個別に診断・適用する。"""

import maya.cmds as cmds

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
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
