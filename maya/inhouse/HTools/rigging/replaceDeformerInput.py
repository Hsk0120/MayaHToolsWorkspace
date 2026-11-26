"""既存デフォーマーの入力を、同じ面順・UVを持つメッシュに差し替える。"""

import maya.api.OpenMaya as om
import maya.cmds as cmds


def _signature(mesh):
    """頂点番号と全UVセットの値・面頂点対応を比較可能な形で取得する。"""
    counts, vertices = mesh.getVertices()
    uv_sets = []
    for name in sorted(mesh.getUVSetNames()):
        u, v = mesh.getUVs(name)
        face_counts, indices = mesh.getAssignedUVs(name)
        uv_sets.append((name, tuple(u), tuple(v), tuple(face_counts), tuple(indices)))
    return mesh.numVertices, tuple(counts), tuple(vertices), uv_sets


def inspect(replacement, deformer):
    """差し替える接続を返し、循環・参照・形状やUVの不一致を事前に拒否する。"""
    if cmds.nodeType(replacement) != "mesh" or not cmds.objectType(deformer, isAType="geometryFilter"):
        raise ValueError("Choose a replacement mesh and a geometry deformer.")
    indices = cmds.deformer(deformer, query=True, geometryIndices=True) or []
    if len(indices) != 1:
        raise ValueError("Choose a deformer affecting one mesh.")
    plug = f"{deformer}.input[{indices[0]}].inputGeometry"
    if cmds.referenceQuery(deformer, isNodeReferenced=True) or cmds.getAttr(plug, lock=True) or cmds.lockNode(deformer, query=True, lock=True)[0]:
        raise ValueError("The input deformer must be editable and local.")
    old = cmds.connectionInfo(plug, sourceFromDestination=True)
    while old and cmds.nodeType(old.split(".", 1)[0]) == "groupParts":
        parts = old.split(".", 1)[0]
        consumers = cmds.listConnections(old, source=False, destination=True, plugs=True) or []
        if len(consumers) != 1 or cmds.referenceQuery(parts, isNodeReferenced=True):
            raise ValueError("Cannot replace a shared or referenced membership input.")
        plug = parts + ".inputGeometry"
        old = cmds.connectionInfo(plug, sourceFromDestination=True)
    if old and cmds.nodeType(old.split(".", 1)[0]) != "mesh":
        raise ValueError("Only direct mesh inputs and membership groups are supported.")
    if not old:
        raise ValueError("The deformer has no connected input geometry.")
    upstream = cmds.listHistory(replacement, allConnections=True) or []
    if deformer in upstream:
        raise ValueError("The replacement depends on the target deformer.")
    selection = om.MSelectionList()
    selection.add(plug)
    selection.add(replacement)
    original_data = selection.getPlug(0).asMObject()
    if not original_data.hasFn(om.MFn.kMeshData):
        raise ValueError("The input geometry must be a polygon mesh.")
    path = selection.getDagPath(1)
    if _signature(om.MFnMesh(original_data)) != _signature(om.MFnMesh(path)):
        raise ValueError("The vertex count, polygon vertex order, or UV layout differs.")
    # 元シェイプのcomponentTagとworldMesh変換を保ち、頂点データだけを差し替える。
    original = old.split(".", 1)[0]
    if not cmds.getAttr(original + ".intermediateObject"):
        raise ValueError("A dedicated intermediate source mesh is required.")
    outputs = []
    for attribute in ("outMesh", "worldMesh"):
        outputs.extend(cmds.listConnections(original + "." + attribute, source=False, destination=True, plugs=True) or [])
    if set(outputs) - {plug, f"{deformer}.originalGeometry[{indices[0]}]"}:
        raise ValueError("Cannot replace a source mesh shared by several outputs.")
    if cmds.referenceQuery(original, isNodeReferenced=True) or cmds.lockNode(original, query=True, lock=True)[0]:
        raise ValueError("The intermediate source must be local and editable.")
    plug = original + ".inMesh"
    if cmds.getAttr(plug, lock=True) or cmds.ls(original, uuid=True) == cmds.ls(replacement, uuid=True):
        raise ValueError("Choose a different mesh and an unlocked input.")
    history_ids = set(cmds.ls(upstream, uuid=True) or []) if upstream else set()
    if cmds.ls(original, uuid=True)[0] in history_ids:
        raise ValueError("The replacement depends on the original mesh.")
    return cmds.connectionInfo(plug, sourceFromDestination=True), path.fullPathName() + ".outMesh", plug


def run():
    """差し替え元のメッシュと対象デフォーマーを指定して接続を比較する。"""
    window = "HToolsReplaceDeformerInput"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Replace Deformer Input")
    cmds.columnLayout(adjustableColumn=True)
    mesh = cmds.textFieldGrp(label="Replacement mesh shape")
    deformer = cmds.textFieldGrp(label="Deformer")
    status = cmds.scrollField(editable=False, height=100)

    def update(apply):
        old, new, target = inspect(cmds.textFieldGrp(mesh, query=True, text=True),
                                   cmds.textFieldGrp(deformer, query=True, text=True))
        if apply:
            if not cmds.undoInfo(query=True, state=True):
                raise ValueError("Enable Undo before replacing the input.")
            cmds.connectAttr(new, target, force=True)
        cmds.scrollField(status, edit=True, text=f"{target}\nPrevious: {old}\nReplacement (object space): {new}")

    cmds.button(label="Preview input connection", command=lambda *_: update(False))
    cmds.button(label="Replace input connection", command=lambda *_: update(True))
    cmds.showWindow(window)


if __name__ == "__main__":
    run()

