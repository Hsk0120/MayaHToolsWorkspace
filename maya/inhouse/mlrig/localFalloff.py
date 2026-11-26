"""標準Soft Modificationの球形範囲を確認し、静止姿勢で中心を置き直す。"""

import math

from maya import cmds
from mlib.decorator import undoTransaction


def _range(vertex, radius):
    if not cmds.objExists(vertex) or ".vtx[" not in vertex or not math.isfinite(radius) or radius <= 0:
        raise ValueError("中心にする頂点と正の半径を指定してください")
    mesh = vertex.split(".vtx[")[0]
    center = cmds.pointPosition(vertex, world=True)
    coords = cmds.xform(mesh + ".vtx[*]", query=True, translation=True, worldSpace=True)
    inside = [i for i in range(len(coords) // 3) if sum((coords[3*i+j] - center[j])**2 for j in range(3)) < radius**2]
    return mesh, center, inside


@undoTransaction("mlrigLocalFalloff")
def apply(vertex, radius, deformer=None):
    """新規作成、またはこのツールで作成した同じメッシュの中立ハンドルの再配置を行う。"""
    mesh, center, _ = _range(vertex, radius)
    if deformer is None:
        node, handle = cmds.softMod(mesh, falloffCenter=center, falloffRadius=radius, name="localFalloff#")
        cmds.addAttr(node, longName="mlrigFalloffHandle", attributeType="message")
        cmds.connectAttr(handle + ".message", node + ".mlrigFalloffHandle")
    else:
        node = deformer
        if not cmds.objExists(node + ".mlrigFalloffHandle"):
            raise ValueError("このツールで作成したSoft Modificationを指定してください")
        shapes = cmds.ls(cmds.softMod(node, query=True, geometry=True), long=True) or []
        current = cmds.ls(mesh, long=True)[0]
        if current not in shapes and current not in [s.rpartition("|")[0] for s in shapes]:
            raise ValueError("同じメッシュの頂点を指定してください")
        handle = cmds.connectionInfo(node + ".mlrigFalloffHandle", sourceFromDestination=True).rsplit(".", 1)[0]
        matrix = cmds.xform(handle, query=True, matrix=True, worldSpace=True)
        if any(abs(v - float(i % 5 == 0)) > 1e-7 for i, v in enumerate(matrix)):
            raise ValueError("ハンドルを作成時の静止姿勢へ戻してください")
        cmds.setAttr(node + ".falloffCenter", *center)
        cmds.setAttr(node + ".falloffRadius", radius)
    cmds.xform(handle, worldSpace=True, pivots=center, preserve=True)
    return node, handle


def show():
    """メッシュ頂点と必要なら再配置するデフォーマーを選んで影響範囲を表示する。"""
    vertices = cmds.filterExpand(selectionMask=31, expand=True, fullPath=True) or []
    nodes = cmds.ls(selection=True, type="softMod") or []
    if len(vertices) != 1 or len(nodes) > 1:
        raise ValueError("中心の頂点を1点、再配置時はSoft Modificationも選択してください")
    window = "mlrigLocalFalloff"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="局所変形の範囲")
    cmds.columnLayout(adjustableColumn=True)
    radius = cmds.floatFieldGrp(label="半径（シーン単位）", value1=1)
    report = cmds.scrollField(editable=False, height=90)

    def preview(*_):
        _, _, inside = _range(vertices[0], cmds.floatFieldGrp(radius, query=True, value1=True))
        cmds.scrollField(report, edit=True, text="範囲内の頂点 {}個\n{}".format(len(inside), ", ".join(map(str, inside))))

    def build(*_):
        _, handle = apply(vertices[0], cmds.floatFieldGrp(radius, query=True, value1=True), nodes[0] if nodes else None)
        cmds.select(handle)

    cmds.button(label="範囲を確認", command=preview)
    cmds.button(label="範囲を再配置" if nodes else "局所変形を作成", command=build)
    preview()
    cmds.showWindow(window)
    return window
