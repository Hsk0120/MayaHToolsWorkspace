"""明示した操作Transformの下に、1頂点用のClusterまたはSoftModを作る。"""

import maya.cmds as cmds

from mlib.decorator import undoTransaction


@undoTransaction("Create Vertex Tweak")
def create(control, vertex, kind):
    """頂点の位置を中心にハンドルを作り、既存の操作Transformへ親子付けする。"""
    vertices = cmds.filterExpand(vertex, selectionMask=31, expand=True, fullPath=True) or []
    if len(vertices) != 1 or not cmds.objectType(control, isAType="transform"):
        raise ValueError("Choose one mesh vertex and one control transform.")
    component = vertices[0]
    if kind == "Cluster":
        node, handle = cmds.cluster(component)
    elif kind == "SoftMod":
        position = cmds.pointPosition(component, world=True)
        node, handle = cmds.softMod(component, falloffCenter=position, falloffRadius=1.0)
        cmds.xform(handle, worldSpace=True, pivots=position)
    else:
        raise ValueError("Choose Cluster or SoftMod.")
    handle = cmds.parent(handle, control, absolute=True)[0]
    return node, handle


def run():
    """操作対象と頂点の対応を表示し、選んだ種類の変形を追加する。"""
    window = "HToolsVertexTweak"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Create Vertex Tweak")
    cmds.columnLayout(adjustableColumn=True)
    field = cmds.textFieldGrp(label="Control", editable=False)
    kind = cmds.optionMenu(label="Deformer")
    for label in ("Cluster", "SoftMod"):
        cmds.menuItem(label=label)
    report = cmds.scrollField(editable=False, height=100)

    def pick(*_):
        nodes = cmds.ls(selection=True, transforms=True, long=True) or []
        if len(nodes) != 1:
            raise ValueError("Select one control transform.")
        cmds.textFieldGrp(field, edit=True, text=nodes[0])

    def apply(*_):
        selected = cmds.ls(selection=True, long=True, flatten=True) or []
        if len(selected) != 1:
            raise ValueError("Select one vertex.")
        node, handle = create(cmds.textFieldGrp(field, query=True, text=True), selected[0], cmds.optionMenu(kind, query=True, value=True))
        cmds.scrollField(report, edit=True, text=f"{selected[0]}\n{node}\n{handle}")

    cmds.button(label="Use selected control", command=pick)
    cmds.button(label="Create tweak on selected vertex", command=apply)
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
