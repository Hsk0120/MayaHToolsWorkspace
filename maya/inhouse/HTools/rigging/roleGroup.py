"""同じ名前のリグを区別して、役割セットの選択とTransform表示を操作する。"""

import maya.api.OpenMaya as om
import maya.cmds as cmds


def members(root, role):
    """選択ルートの名前空間にあるobjectSetからそのルート配下だけを解決する。"""
    if not role or any(char in role for char in ":|*.?[]"):
        raise ValueError("Enter a local object set name.")
    namespace = root.rsplit("|", 1)[-1].rpartition(":")[0]
    group = (namespace + ":" if namespace else "") + role
    if not cmds.objExists(group) or cmds.nodeType(group) != "objectSet":
        raise ValueError("No matching object set: " + group)
    names = cmds.sets(group, query=True) or []
    paths = cmds.ls(names, transforms=True, long=True, allPaths=True) if names else []
    return sorted({p for p in paths or [] if p == root or p.startswith(root + "|")})


def run():
    """現在の個体・役割名に対応するTransformの一覧・選択・表示を操作する。"""
    window = "HToolsRoleGroup"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Rig Role Group")
    cmds.columnLayout(adjustableColumn=True)
    root = cmds.textFieldGrp(label="Rig root", editable=False)
    role = cmds.textFieldGrp(label="Role object set")
    output = cmds.scrollField(editable=False, height=150)

    def pick(*_):
        nodes = cmds.ls(selection=True, long=True, transforms=True) or []
        if len(nodes) != 1:
            raise ValueError("Select one rig root.")
        cmds.textFieldGrp(root, edit=True, text=nodes[0])

    def update(action):
        paths = members(cmds.textFieldGrp(root, query=True, text=True), cmds.textFieldGrp(role, query=True, text=True))
        cmds.scrollField(output, edit=True, text="\n".join(paths))
        if not paths:
            return
        if action == "select":
            cmds.select(paths, replace=True)
        if action in ("show", "hide"):
            plugs = []
            for path in paths:
                plug = path + ".visibility"
                selection = om.MSelectionList()
                selection.add(path)
                if selection.getDagPath(0).isInstanced() or not cmds.getAttr(plug, settable=True) or cmds.connectionInfo(plug, isDestination=True):
                    raise ValueError("Shared or non-editable visibility: " + path)
                if cmds.getAttr(plug) != (action == "show"):
                    plugs.append(plug)
            if not plugs:
                return
            if not cmds.undoInfo(query=True, state=True):
                raise ValueError("Enable Undo to change visibility.")
            cmds.undoInfo(openChunk=True, chunkName="Role Group Visibility")
            applied = 0
            try:
                try:
                    for plug in plugs:
                        cmds.setAttr(plug, action == "show")
                        applied += 1
                finally:
                    cmds.undoInfo(closeChunk=True)
            except RuntimeError:
                if applied:
                    cmds.undo()
                raise

    cmds.button(label="Use selected rig root", command=pick)
    for action in ("inspect", "select", "show", "hide"):
        cmds.button(label=action.title() + " group", command=lambda *_, key=action: update(key))
    cmds.showWindow(window)


if __name__ == "__main__":
    run()

