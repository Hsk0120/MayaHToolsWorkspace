"""選択したClusterの現在のウェイトに球状の静的マスクを掛ける。"""

import math

import maya.api.OpenMaya as om
import maya.cmds as cmds


def preview(cluster, center, radius):
    """単一メッシュのCluster入力位置(cm)と既存ウェイトから変更候補を返す。"""
    if not math.isfinite(radius) or radius <= 0 or len(center) != 3 or not all(math.isfinite(x) for x in center):
        raise ValueError("Enter a finite center and a positive radius in cm.")
    if cmds.nodeType(cluster) != "cluster":
        raise ValueError("Select one cluster deformer.")
    shapes = cmds.deformer(cluster, query=True, geometry=True) or []
    indices = cmds.deformer(cluster, query=True, geometryIndices=True) or []
    if len(shapes) != 1 or len(indices) != 1 or cmds.nodeType(shapes[0]) != "mesh":
        raise ValueError("The cluster must affect one mesh.")
    paths = cmds.ls(shapes[0], allPaths=True, long=True)
    if len(paths) != 1:
        raise ValueError("The mesh must have one DAG path.")
    selection = om.MSelectionList()
    selection.add(paths[0])
    selection.add(f"{cluster}.input[{indices[0]}].inputGeometry")
    matrix = selection.getDagPath(0).inclusiveMatrix()
    points = om.MFnMesh(selection.getPlug(1).asMObject()).getPoints()
    weights = cmds.percent(cluster, paths[0] + ".vtx[*]", query=True, value=True) or []
    if len(weights) != len(points):
        raise ValueError("The cluster must provide a weight for each input vertex.")
    changes = []
    origin = om.MPoint(*center)
    for index, (point, old) in enumerate(zip(points, weights)):
        distance = (point * matrix).distanceTo(origin)
        t = max(0.0, 1.0 - distance / radius)
        new = old * t * t * (3.0 - 2.0 * t)
        if new != old:
            changes.append((f"{paths[0]}.vtx[{index}]", old, new))
    return changes


def run():
    """球の中心と半径を指定して既存ウェイトの差分を確認し適用する。"""
    window = "HToolsClusterSphereMask"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="Static Cluster Sphere Mask")
    cmds.columnLayout(adjustableColumn=True)
    center = cmds.floatFieldGrp(label="World center (cm)", numberOfFields=3)
    radius = cmds.floatFieldGrp(label="Radius (cm)", value1=1)
    report = cmds.scrollField(editable=False, height=160)

    def changes():
        selected = cmds.ls(selection=True, type="cluster") or []
        if len(selected) != 1:
            raise ValueError("Select one cluster deformer in the Node Editor or Outliner.")
        rows = preview(selected[0], cmds.floatFieldGrp(center, query=True, value=True)[:3],
                       cmds.floatFieldGrp(radius, query=True, value1=True))
        return selected[0], rows

    def inspect(*_):
        _, rows = changes()
        lines = [f"{len(rows)} weights would change"]
        lines.extend(f"{vertex}: {old:g} -> {new:g}" for vertex, old, new in rows[:100])
        cmds.scrollField(report, edit=True, text="\n".join(lines))

    def apply(*_):
        cluster, rows = changes()
        if not rows:
            return
        if not cmds.undoInfo(query=True, state=True):
            raise ValueError("Enable Undo to apply the mask.")
        cmds.undoInfo(openChunk=True, chunkName="Apply Cluster Sphere Mask")
        applied = 0
        try:
            try:
                for vertex, _, new in rows:
                    cmds.percent(cluster, vertex, value=new)
                    applied += 1
            finally:
                cmds.undoInfo(closeChunk=True)
        except RuntimeError:
            if applied:
                cmds.undo()
            raise
        cmds.scrollField(report, edit=True, text=f"Masked {applied} weights.")

    cmds.button(label="Preview current weights", command=inspect)
    cmds.button(label="Multiply current weights by mask", command=apply)
    cmds.showWindow(window)


if __name__ == "__main__":
    run()
