"""機能ルート・配下のDAGと登録された補助ノードの共有先を確認する。"""

import maya.api.OpenMaya as om
import maya.cmds as cmds


def _members(root):
    """所有範囲の候補と外部への接続を表示し、選択外への依存を明示する。"""
    matches = cmds.ls(root, long=True, transforms=True) or []
    if len(matches) != 1:
        raise ValueError("Select one feature root.")
    root = matches[0]
    members = {root, *(cmds.listRelatives(root, allDescendents=True, fullPath=True) or [])}
    if cmds.attributeQuery("graph", node=root, exists=True) and cmds.getAttr(root + ".graph", type=True) == "message":
        helpers = cmds.listConnections(root + ".graph", source=True, destination=False) or []
        if helpers:
            members.update(cmds.ls(helpers, long=True) or [])
    return members


def inspect(root):
    """機能範囲と外部への接続を表示する。"""
    members = _members(root)
    rows = []
    for node in sorted(members):
        reference = cmds.referenceQuery(node, isNodeReferenced=True)
        rows.append(node + ("  [Referenced]" if reference else ""))
        for source, label in ((True, "External input"), (False, "External output")):
            links = cmds.listConnections(node, source=source, destination=not source, plugs=True, connections=True) or []
            for local, remote in zip(links[::2], links[1::2]):
                owner = remote.split(".", 1)[0]
                paths = cmds.ls(owner, long=True) or []
                if len(paths) != 1 or paths[0] not in members:
                    rows.append(f"  {label}: {local} / {remote}")
    return rows


def run():
    """選択した機能範囲と、削除時に切れる可能性のある接続を表示する。"""
    window = "HToolsFeatureRemovalPreview"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Preview Feature Removal")
    cmds.columnLayout(adjustableColumn=True)
    output = cmds.scrollField(editable=False, height=280)

    captured = []

    def refresh(*_):
        selected = cmds.ls(selection=True, transforms=True, long=True) or []
        rows = inspect(selected[0]) if len(selected) == 1 else ["Select one feature root."]
        cmds.scrollField(output, edit=True, text="\n".join(rows))

    def capture(*_):
        selected = cmds.ls(selection=True, transforms=True, long=True) or []
        if len(selected) != 1:
            raise ValueError("Select one feature root.")
        objects = []
        for name in sorted(_members(selected[0])):
            selection = om.MSelectionList()
            selection.add(name)
            objects.append((name, om.MObjectHandle(selection.getDependNode(0))))
        captured[:] = objects
        refresh()

    def compare(*_):
        if not captured:
            raise ValueError("Capture a feature before checking survivors.")
        rows = []
        for name, handle in captured:
            state = "Remaining" if handle.isValid() and handle.isAlive() else "Removed"
            rows.append(f"{state}: {name}")
        cmds.scrollField(output, edit=True, text="\n".join(rows))

    cmds.button(label="Capture feature before removal", command=capture)
    cmds.button(label="Check surviving feature nodes", command=compare)
    cmds.button(label="Inspect hierarchy and registered graph", command=refresh)
    refresh()
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
