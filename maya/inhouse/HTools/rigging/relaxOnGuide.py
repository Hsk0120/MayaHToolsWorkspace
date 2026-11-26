"""選択した頂点領域の外周を固定し、内側をガイドメッシュに沿って平滑化する。"""

import maya.api.OpenMaya as om
import maya.cmds as cmds


def _path(shape):
    """メッシュへの一意なDAGパスを返す。"""
    selection = om.MSelectionList()
    selection.add(shape)
    path = selection.getDagPath(0)
    if not path.node().hasFn(om.MFn.kMesh):
        raise ValueError("A polygon mesh is required.")
    return path


def relax(shape, indices, guide):
    """選択領域の内点を隣接点の平均からガイド面へ射影し、一度だけ移動する。"""
    path, guide_path = _path(shape), _path(guide)
    if path.node() == guide_path.node() or path.isInstanced() or cmds.referenceQuery(shape, isNodeReferenced=True):
        raise ValueError("Use a local, non-instanced mesh and a separate guide.")
    mesh, target = om.MFnMesh(path), om.MFnMesh(guide_path)
    points = mesh.getPoints(om.MSpace.kWorld)
    indices = set(indices)
    if not indices or min(indices) < 0 or max(indices) >= len(points):
        raise ValueError("Choose vertices on a single mesh.")
    iterator = om.MItMeshVertex(path)
    changes = []
    for index in sorted(indices):
        iterator.setIndex(index)
        adjacent = iterator.getConnectedVertices()
        if iterator.onBoundary() or not adjacent or any(neighbor not in indices for neighbor in adjacent):
            continue
        center = om.MVector()
        for neighbor in adjacent:
            center += om.MVector(points[neighbor])
        proposed, _ = target.getClosestPoint(om.MPoint(center / len(adjacent)), om.MSpace.kWorld)
        if not points[index].isEquivalent(proposed, 1e-10):
            changes.append((index, proposed))
    if not changes:
        return 0
    if not cmds.undoInfo(query=True, state=True):
        raise ValueError("Enable Undo before relaxing vertices.")
    unit = om.MDistance.uiUnit()
    cmds.undoInfo(openChunk=True, chunkName="Relax on Guide Mesh")
    applied = 0
    try:
        try:
            for index, point in changes:
                position = [om.MDistance(x, om.MDistance.kCentimeters).asUnits(unit) for x in (point.x, point.y, point.z)]
                cmds.xform(f"{path.fullPathName()}.vtx[{index}]", worldSpace=True, translation=position)
                applied += 1
        finally:
            cmds.undoInfo(closeChunk=True)
    except RuntimeError:
        if applied:
            cmds.undo()
        raise
    return applied


def run():
    """ガイド形状を指定し、選択中の頂点へ平滑化を適用する。"""
    window = "HToolsRelaxOnGuide"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Relax on Guide Mesh")
    cmds.columnLayout(adjustableColumn=True)
    field = cmds.textField(editable=False)
    status = cmds.text(label="")

    def pick(*_):
        selected = cmds.ls(selection=True, long=True) or []
        shapes = cmds.ls(selected, dag=True, shapes=True, type="mesh", noIntermediate=True, long=True) if selected else []
        if len(shapes) != 1:
            raise ValueError("Select one guide mesh.")
        cmds.textField(field, edit=True, text=shapes[0])

    def apply(*_):
        selection = om.MGlobal.getActiveSelectionList()
        if selection.length() != 1:
            raise ValueError("Select vertices on one mesh.")
        path, component = selection.getComponent(0)
        if component.isNull() or component.apiType() != om.MFn.kMeshVertComponent:
            raise ValueError("Select mesh vertices.")
        indices = om.MFnSingleIndexedComponent(component).getElements()
        count = relax(path.fullPathName(), indices, cmds.textField(field, query=True, text=True))
        cmds.text(status, edit=True, label=f"Moved {count} interior vertices.")

    cmds.button(label="Use selected guide mesh", command=pick)
    cmds.button(label="Relax selected vertices once", command=apply)
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
