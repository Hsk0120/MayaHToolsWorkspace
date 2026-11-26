"""選択したメッシュのシェーダー割り当てを面単位で記録し、比較・復元する。"""

from collections import defaultdict

import maya.api.OpenMaya as om
import maya.cmds as cmds


def _mesh(path):
    """インスタンスを区別できるメッシュパスを取得する。"""
    matches = cmds.ls(path, long=True) or []
    if len(matches) != 1:
        raise ValueError("Select one unambiguous mesh.")
    selection = om.MSelectionList()
    selection.add(matches[0])
    dag = selection.getDagPath(0)
    if not dag.node().hasFn(om.MFn.kMesh):
        raise ValueError("A mesh shape is required.")
    return dag, om.MFnMesh(dag)


def capture(path):
    """トポロジーと各面のシェーディンググループをインスタンス単位で記録する。"""
    dag, mesh = _mesh(path)
    groups, assignments = mesh.getConnectedShaders(dag.instanceNumber())
    names = [om.MFnDependencyNode(group).name() for group in groups]
    counts, ids = mesh.getVertices()
    return dict(path=dag.fullPathName(), uuid=cmds.ls(path, uuid=True)[0],
                topology=(tuple(counts), tuple(ids)),
                shaders=tuple(names[index] if index >= 0 else None for index in assignments) if names else (None,) * mesh.numPolygons)


def differences(snapshot):
    """記録時と異なる面番号、元の割り当て、現在の割り当てを返す。"""
    current = capture(snapshot["path"])
    if current["uuid"] != snapshot["uuid"] or current["topology"] != snapshot["topology"]:
        raise ValueError("The mesh or its topology has changed.")
    return [(index, saved, actual) for index, (saved, actual) in
            enumerate(zip(snapshot["shaders"], current["shaders"])) if saved != actual]


def restore(snapshot):
    """差がある面だけに記録した割り当てを復元する。"""
    path = snapshot["path"]
    changes = differences(snapshot)
    by_shader = defaultdict(list)
    remove = defaultdict(list)
    for index, saved, actual in changes:
        if saved is None:
            remove[actual].append("{}.f[{}]".format(path, index))
            continue
        if not cmds.objExists(saved) or cmds.nodeType(saved) != "shadingEngine":
            raise ValueError("Cannot restore a missing shading group.")
        by_shader[saved].append("{}.f[{}]".format(path, index))
    if not changes:
        return 0
    if not cmds.undoInfo(query=True, state=True):
        raise ValueError("Enable Undo to restore shader assignments.")
    cmds.undoInfo(openChunk=True, chunkName="Restore Shader Assignments")
    applied = False
    try:
        try:
            for group, faces in remove.items():
                # オブジェクト全体の所属から個別の面だけを外すには、残す面を明示し直す。
                if cmds.sets(path, isMember=group):
                    cmds.sets(path, edit=True, remove=group)
                    applied = True
                    retained = [f"{path}.f[{i}]" for i, shader in enumerate(snapshot["shaders"]) if shader == group]
                    if retained:
                        cmds.sets(retained, edit=True, forceElement=group)
                else:
                    cmds.sets(faces, edit=True, remove=group)
                    applied = True
            for group, faces in by_shader.items():
                cmds.sets(faces, edit=True, forceElement=group)
                applied = True
            if differences(snapshot):
                raise RuntimeError("Could not restore all shader assignments.")
        finally:
            cmds.undoInfo(closeChunk=True)
    except RuntimeError:
        if applied:
            cmds.undo()
        raise
    return len(changes)


def run():
    """選択モデルの記録・比較・復元画面を表示する。"""
    nodes = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    shapes = cmds.ls(nodes, dag=True, long=True, shapes=True, type="mesh", noIntermediate=True) if nodes else []
    if len(shapes or []) != 1:
        raise ValueError("Select one mesh.")
    snapshot = capture(shapes[0])
    window = "HToolsShaderAssignments"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Shader Assignments")
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label=snapshot["path"])
    report = cmds.scrollField(editable=False, height=200)

    def compare(*_):
        changes = differences(snapshot)
        text = "\n".join("f[{}]: {} -> {}".format(*change) for change in changes)
        cmds.scrollField(report, edit=True, text=text or "Assignments match the captured mesh.")

    def apply(*_):
        restore(snapshot)
        compare()

    cmds.button(label="Compare with captured assignments", command=compare)
    cmds.button(label="Restore captured assignments", command=apply)
    compare()
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
