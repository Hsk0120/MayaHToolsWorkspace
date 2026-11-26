"""選択したTransformの回転合成に関係する値と接続を読み取る。"""

import maya.cmds as cmds


def inspect(node):
    """回転順・回転角・軸と各プラグに関係する接続を返す。"""
    if not cmds.objectType(node, isAType="transform"):
        raise ValueError("Select a transform or joint.")
    rows = []
    for attr in ("rotateOrder", "rotate", "rotateAxis", "jointOrient", "offsetParentMatrix"):
        if not cmds.attributeQuery(attr, node=node, exists=True):
            continue
        plug = node + "." + attr
        if attr == "rotateOrder":
            value = cmds.getAttr(plug, asString=True)
        else:
            value = cmds.getAttr(plug)
        rows.append(f"{attr} = {value}")
        children = cmds.attributeQuery(attr, node=node, listChildren=True) or []
        for checked in [plug] + [node + "." + child for child in children]:
            for source, label in ((True, "input"), (False, "output")):
                links = cmds.listConnections(checked, source=source, destination=not source, plugs=True) or []
                rows.extend(f"  {label}: {checked} / {remote}" for remote in links)
    return rows


def run():
    """選択したノードの回転設定を表示する。"""
    window = "HToolsRotationInspection"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Inspect Rotation Composition")
    cmds.columnLayout(adjustableColumn=True)
    output = cmds.scrollField(editable=False, height=250)

    def refresh(*_):
        nodes = cmds.ls(selection=True, transforms=True, long=True) or []
        rows = []
        for node in nodes:
            rows.extend([node] + inspect(node))
        cmds.scrollField(output, edit=True, text="\n".join(rows) or "Select transforms or joints.")

    cmds.button(label="Inspect selected transforms", command=refresh)
    refresh()
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
