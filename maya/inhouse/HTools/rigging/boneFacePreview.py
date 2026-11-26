"""ポリゴン面の中心と骨区間の距離で分割候補を分類する。"""

import maya.api.OpenMaya as om
import maya.cmds as cmds


def classify(shape, joints):
    """各面を最近の親子区間へ割り当てる。同距離の場合は子のフルパス順を使う。"""
    selection = om.MSelectionList()
    selection.add(shape)
    mesh = om.MFnMesh(selection.getDagPath(0))
    segments = []
    for child in sorted(set(joints)):
        parents = cmds.listRelatives(child, parent=True, type="joint", fullPath=True) or []
        if not parents:
            continue
        endpoints = []
        for node in (parents[0], child):
            path = om.MSelectionList()
            path.add(node)
            endpoints.append(om.MPoint(0, 0, 0) * path.getDagPath(0).inclusiveMatrix())
        a, b = endpoints
        delta = b-a
        length2 = delta*delta
        if length2:
            segments.append((child, a, delta, length2))
    if not segments:
        raise ValueError("Select joints with nonzero parent-to-child segments.")
    groups = {child: [] for child, _, _, _ in segments}
    points = mesh.getPoints(om.MSpace.kWorld)
    for face in range(mesh.numPolygons):
        vertices = mesh.getPolygonVertices(face)
        total = om.MVector()
        for vertex in vertices:
            total += om.MVector(points[vertex])
        center = om.MPoint(total / len(vertices))
        distances = []
        for child, anchor, delta, length2 in segments:
            fraction = max(0, min(1, ((center-anchor)*delta)/length2))
            distances.append((center.distanceTo(anchor + delta*fraction), child))
        groups[min(distances)[1]].append(face)
    return groups


def extract(shape, indices):
    """評価済みメッシュと面材質を独立コピーし、対象外の面を除く。"""
    selection = om.MSelectionList()
    selection.add(shape)
    path = selection.getDagPath(0)
    mesh = om.MFnMesh(path)
    keep = set(indices)
    if not keep or min(keep) < 0 or max(keep) >= mesh.numPolygons:
        raise ValueError("Choose a nonempty group of existing faces.")
    if not cmds.undoInfo(query=True, state=True):
        raise ValueError("Enable Undo to extract geometry.")
    shaders, materials = mesh.getConnectedShaders(path.instanceNumber())
    cmds.undoInfo(openChunk=True, chunkName="Extract Bone Faces")
    try:
        transform = cmds.createNode("transform", name="boneFaces#", skipSelect=True)
        try:
            cmds.xform(transform, matrix=list(path.inclusiveMatrix()), worldSpace=True)
            dest = om.MSelectionList()
            dest.add(transform)
            obj = om.MFnMesh().copy(path.node(), dest.getDependNode(0))
            output = om.MDagPath.getAPathTo(obj).fullPathName()
            for index, shader in enumerate(shaders):
                faces = [f"{output}.f[{face}]" for face in sorted(keep) if materials[face] == index]
                if faces:
                    cmds.sets(faces, edit=True, forceElement=om.MFnDependencyNode(shader).name())
            discard = [f"{output}.f[{face}]" for face in range(mesh.numPolygons) if face not in keep]
            if discard:
                cmds.polyDelFacet(discard, constructionHistory=False)
            return transform
        except (RuntimeError, ValueError):
            cmds.delete(transform)
            raise
    finally:
        cmds.undoInfo(closeChunk=True)


def run():
    """選択モデルと子ジョイントから面グループを作り、選んだ範囲を表示する。"""
    window = "HToolsBoneFacePreview"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Preview Faces by Bone Segment")
    cmds.columnLayout(adjustableColumn=True)
    report = cmds.textScrollList()
    groups = {}
    source = []
    bones = {}

    def refresh(*_):
        nodes = cmds.ls(selection=True, objectsOnly=True, long=True) or []
        joints = cmds.ls(nodes, type="joint", long=True) if nodes else []
        shapes = []
        for node in nodes:
            if cmds.nodeType(node) == "mesh":
                shapes.append(node)
            elif cmds.nodeType(node) == "transform":
                shapes.extend(cmds.listRelatives(node, shapes=True, noIntermediate=True, type="mesh", fullPath=True) or [])
        if len(shapes) != 1:
            raise ValueError("Select one mesh and the child joint of each candidate segment.")
        fractions = classify(shapes[0], joints or [])
        bones.clear()
        bones.update(fractions)
        groups.clear()
        source[:] = shapes
        cmds.textScrollList(report, edit=True, removeAll=True)
        for child, indices in fractions.items():
            label = f"{child} ({len(indices)} faces)"
            groups[label] = indices
            cmds.textScrollList(report, edit=True, append=label)

    def select(*_):
        chosen = cmds.textScrollList(report, query=True, selectItem=True) or []
        if chosen:
            components = [f"{source[0]}.f[{i}]" for i in groups[chosen[0]]]
            if components:
                cmds.select(components, replace=True)
            else:
                cmds.select(clear=True)

    def copy(*_):
        chosen = cmds.textScrollList(report, query=True, selectItem=True) or []
        if chosen:
            # 新しい形状を作る直前に骨と面を再照合し、古い面番号を適用しない。
            current = classify(source[0], list(bones))
            if current != bones:
                raise ValueError("The face classification changed. Refresh the groups.")
            extract(source[0], groups[chosen[0]])

    cmds.button(label="Classify selected mesh and bones", command=refresh)
    cmds.button(label="Select faces in highlighted group", command=select)
    cmds.button(label="Copy highlighted faces", command=copy)
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
