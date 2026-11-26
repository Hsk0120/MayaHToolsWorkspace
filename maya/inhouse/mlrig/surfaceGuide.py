"""UV位置が一意なメッシュ面に追従するガイドを作成する。"""

import math

from maya import cmds
from maya.api import OpenMaya as om2
from mlib.decorator import undoTransaction


def meshPath(node):
    """単一の表示用メッシュのDAGパスを返す。"""
    if cmds.nodeType(node) != "mesh":
        shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True, type="mesh", fullPath=True) or []
        if len(shapes) != 1:
            raise ValueError("メッシュを1つ持つトランスフォームを指定してください")
        node = shapes[0]
    return om2.MSelectionList().add(node).getDagPath(0)


def _validate_uv(fn, uvSet, shell, u, v):
    if uvSet not in fn.getUVSetNames() or not all(math.isfinite(x) for x in (u, v)):
        raise ValueError("UVセットまたは座標が無効です")
    faces, _ = fn.getPointsAtUV(u, v, om2.MSpace.kObject, uvSet, 1e-7)
    if len(set(faces)) != 1:
        raise ValueError("UV位置の面が見つからないか、複数の面が重なっています")
    face = faces[0]
    ids = [fn.getPolygonUVid(face, i, uvSet) for i in range(fn.polygonVertexCount(face))]
    _, shells = fn.getUvShellsIds(uvSet)
    if any(shells[i] != shell for i in ids):
        raise ValueError("UV位置と指定シェルが一致しません")
    points = [fn.getUV(i, uvSet) for i in ids]
    for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
        dx, dy = bx - ax, by - ay
        length = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((u - ax) * dx + (v - ay) * dy) / length)) if length else 0.0
        if math.hypot(u - ax - t * dx, v - ay - t * dy) <= 1e-7:
            raise ValueError("UVの境界を避けて面の内側を指定してください")


@undoTransaction("mlrigCreateUvSurfaceGuide")
def create(mesh, uvSet, shell, u, v):
    """UVセット・シェルを検査し、面の内側に標準follicleのガイドを作成する。"""
    path = meshPath(mesh)
    _validate_uv(om2.MFnMesh(path), uvSet, shell, u, v)
    node = path.fullPathName()
    guide = cmds.createNode("transform", name="surfaceGuide#", skipSelect=True)
    follicle = cmds.createNode("follicle", parent=guide, skipSelect=True)
    cmds.setAttr(follicle + ".mapSetName", uvSet, type="string")
    cmds.setAttr(follicle + ".parameterU", u)
    cmds.setAttr(follicle + ".parameterV", v)
    cmds.connectAttr(node + ".outMesh", follicle + ".inputMesh")
    cmds.connectAttr("{}.worldMatrix[{}]".format(node, path.instanceNumber()), follicle + ".inputWorldMatrix")
    cmds.setAttr(guide + ".inheritsTransform", False)
    cmds.connectAttr(follicle + ".outTranslate", guide + ".translate")
    cmds.connectAttr(follicle + ".outRotate", guide + ".rotate")
    return guide


@undoTransaction("mlrigRebindSurfaceGuide")
def rebind(guide, shell, u, v):
    """現在のUVセットと面入力を使い、子の姿勢と変形を保って1点を再登録する。"""
    shapes = cmds.listRelatives(guide, shapes=True, fullPath=True, type="follicle") or []
    if len(shapes) != 1 or cmds.getAttr(guide + ".inheritsTransform") or cmds.autoKeyframe(query=True, state=True):
        raise ValueError("自動キーをオフにし、面追従ガイドを選択してください")
    follicle = shapes[0]
    for attr in ("parameterU", "parameterV"):
        plug = follicle + "." + attr
        if cmds.connectionInfo(plug, isDestination=True) or not cmds.getAttr(plug, settable=True):
            raise ValueError("UVの入力接続またはロックを確認してください")
    fn = om2.MFnMesh(om2.MSelectionList().add(follicle + ".inputMesh").getPlug(0).asMObject())
    _validate_uv(fn, cmds.getAttr(follicle + ".mapSetName"), shell, u, v)
    opm = guide + ".offsetParentMatrix"
    current = om2.MMatrix(cmds.getAttr(guide + ".worldMatrix[0]"))
    marker = guide + ".mlrigUVOffset"
    if cmds.objExists(marker):
        mm = cmds.connectionInfo(marker, sourceFromDestination=True).rsplit(".", 1)[0]
        if not mm or not cmds.isConnected(mm + ".matrixSum", opm):
            raise ValueError("ガイドのオフセット接続が変わっています")
        compose = cmds.connectionInfo(mm + ".matrixIn[1]", sourceFromDestination=True).rsplit(".", 1)[0]
        if not compose or not cmds.isConnected(follicle + ".outTranslate", compose + ".inputTranslate"):
            raise ValueError("ガイドの面入力が変わっています")
    else:
        if cmds.connectionInfo(opm, isDestination=True) or not all(
            cmds.isConnected(follicle + ".out" + a.capitalize(), guide + "." + a) for a in ("translate", "rotate")
        ):
            raise ValueError("面追従の直接接続を確認してください")
        compose = cmds.createNode("composeMatrix", name="uvGuideFrame#")
        mm = cmds.createNode("multMatrix", name="uvGuideOffset#")
        for a in ("translate", "rotate"):
            src = follicle + ".out" + a.capitalize()
            cmds.disconnectAttr(src, guide + "." + a)
            cmds.setAttr(guide + "." + a, 0, 0, 0)
            cmds.connectAttr(src, compose + ".input" + a.capitalize())
        cmds.connectAttr(compose + ".outputMatrix", mm + ".matrixIn[1]")
        cmds.connectAttr(mm + ".matrixSum", opm)
        cmds.addAttr(guide, longName="mlrigUVOffset", attributeType="message")
        cmds.connectAttr(mm + ".message", marker)
    cmds.setAttr(follicle + ".parameterU", u)
    cmds.setAttr(follicle + ".parameterV", v)
    frame = om2.MMatrix(cmds.getAttr(compose + ".outputMatrix"))
    local = om2.MMatrix(cmds.getAttr(guide + ".matrix"))
    if local.isSingular() or frame.isSingular():
        raise ValueError("逆マトリクスを求められない姿勢です")
    cmds.setAttr(mm + ".matrixIn[0]", *list(local.inverse() * current * frame.inverse()), type="matrix")
    return guide


def showRebind():
    """ガイドの現在UVを表示し、新しいシェルと面内座標を指定する。"""
    nodes = cmds.ls(selection=True, long=True, transforms=True) or []
    shapes = cmds.listRelatives(nodes[0], shapes=True, type="follicle", fullPath=True) if len(nodes) == 1 else []
    if not shapes or len(shapes) != 1:
        raise ValueError("対象の面追従ガイドを1点選択してください")
    window = "mlrigRebindSurfaceGuide"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="面追従を現在姿勢で再バインド")
    cmds.columnLayout(adjustableColumn=True)
    shell = cmds.intFieldGrp(label="UVシェル", value1=0)
    uv = cmds.floatFieldGrp(
        label="U / V",
        numberOfFields=2,
        precision=6,
        value1=cmds.getAttr(shapes[0] + ".parameterU"),
        value2=cmds.getAttr(shapes[0] + ".parameterV"),
    )
    cmds.button(
        label="選択ガイドを再バインド",
        command=lambda *_: rebind(
            nodes[0], cmds.intFieldGrp(shell, query=True, value1=True), *cmds.floatFieldGrp(uv, query=True, value=True)[:2]
        ),
    )
    cmds.showWindow(window)
    return window


def show():
    """選択メッシュのUVセット・シェル番号・座標を指定する。"""
    nodes = cmds.ls(selection=True, long=True) or []
    if len(nodes) != 1:
        raise ValueError("メッシュを1つ選択してください")
    path = meshPath(nodes[0])
    window = "mlrigUvSurfaceGuide"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="UV面追従ガイド")
    cmds.columnLayout(adjustableColumn=True)
    menu = cmds.optionMenu(label="UVセット")
    for name in om2.MFnMesh(path).getUVSetNames():
        cmds.menuItem(label=name, parent=menu)
    shell = cmds.intFieldGrp(label="シェル番号", value1=0)
    uv = cmds.floatFieldGrp(label="U・V", numberOfFields=2, precision=6, value1=0.5, value2=0.5)

    def build(*_):
        guide = create(
            path.fullPathName(),
            cmds.optionMenu(menu, query=True, value=True),
            cmds.intFieldGrp(shell, query=True, value1=True),
            cmds.floatFieldGrp(uv, query=True, value1=True),
            cmds.floatFieldGrp(uv, query=True, value2=True),
        )
        cmds.select(guide, replace=True)

    cmds.button(label="追従ガイドを作成", command=build)
    cmds.showWindow(window)
    return window
