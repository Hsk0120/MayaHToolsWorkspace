"""選択したモデルの中間メッシュやカーブを、比較用の独立した形状として取り出す。"""

import maya.api.OpenMaya as om
import maya.cmds as cmds


def candidates(transform):
    """同一Transformの中間メッシュと中間カーブをフルパスで取得する。"""
    shapes = cmds.listRelatives(transform, shapes=True, fullPath=True) or []
    return [shape for shape in shapes if cmds.nodeType(shape) in ("mesh", "nurbsCurve")
            and cmds.getAttr(shape + ".intermediateObject")]


def copyOriginal(shape):
    """指定した中間形状の評価結果を同位置へコピーする。"""
    shape_type = cmds.nodeType(shape)
    if shape_type not in ("mesh", "nurbsCurve") or not cmds.getAttr(shape + ".intermediateObject"):
        raise ValueError("Choose an intermediate mesh or NURBS curve.")
    selected = om.MSelectionList()
    selected.add(shape)
    path = selected.getDagPath(0)
    matrix = list(path.inclusiveMatrix())
    cmds.undoInfo(openChunk=True, chunkName="Copy Original Mesh")
    try:
        output = cmds.createNode("transform", name="originalComparison#", skipSelect=True)
        try:
            cmds.xform(output, worldSpace=True, matrix=matrix)
            parent = om.MSelectionList()
            parent.add(output)
            copier = om.MFnMesh() if shape_type == "mesh" else om.MFnNurbsCurve()
            copier.copy(path.node(), parent.getDependNode(0))
            return output
        except RuntimeError:
            cmds.delete(output)
            raise
    finally:
        cmds.undoInfo(closeChunk=True)


def run():
    """選択モデルの中間メッシュ候補を表示する。"""
    transforms = cmds.ls(selection=True, long=True, transforms=True) or []
    if len(transforms) != 1:
        raise ValueError("Select one mesh or curve transform.")
    shapes = candidates(transforms[0])
    if not shapes:
        raise ValueError("No intermediate meshes or curves found.")
    window = "HToolsCopyOriginalMesh"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Copy Original Shape")
    cmds.columnLayout(adjustableColumn=True)
    listing = cmds.textScrollList(append=shapes, selectIndexedItem=1)
    def copy(*_):
        chosen = cmds.textScrollList(listing, query=True, selectItem=True)
        if chosen:
            copyOriginal(chosen[0])
    cmds.button(label="Copy selected shape", command=copy)
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
