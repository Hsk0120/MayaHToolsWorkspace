"""スキンの1列を、スキン面に追従する1個以上のクラスターハンドルへ転用する。"""

import json

from maya import cmds
from maya.api import OpenMaya as om2
from mlib import getNode
from mlib.decorator import undoTransaction

from . import surfaceGuide


@undoTransaction("mlrigSurfaceClusters")
def create(mesh, influence, uvSet, regions):
    """重複しない頂点群ごとにUV上のハンドルを作成し、スキン後段で局所差分を加える。"""
    path = surfaceGuide.meshPath(mesh)
    shape = path.fullPathName()
    parent = shape.rsplit("|", 1)[0]
    skins = cmds.ls(cmds.listHistory(shape, pruneDagObjects=True) or [], type="skinCluster") or []
    if len(skins) != 1 or path.isInstanced():
        raise ValueError("1個のスキンクラスタで変形する単一パスのメッシュを選択してください")
    skin = getNode(skins[0])
    outputs = cmds.getAttr(skins[0] + ".outputGeometry", multiIndices=True)
    if len(outputs) != 1:
        raise ValueError("単一形状のスキンクラスタに対応しています")
    skin_output = "{}.outputGeometry[{}]".format(skins[0], outputs[0])
    fn = om2.MFnMesh(path)
    upstream = om2.MFnMesh(om2.MSelectionList().add(skin_output).getPlug(0).asMObject())
    if [list(a) for a in fn.getVertices()] != [list(a) for a in upstream.getVertices()] or uvSet not in upstream.getUVSetNames():
        raise ValueError("スキン出力と現在形状のトポロジーまたはUVセットが一致しません")
    if uvSet not in fn.getUVSetNames() or any(
        [list(a) for a in getattr(fn, method)(uvSet)] != [list(a) for a in getattr(upstream, method)(uvSet)]
        for method in ("getUVs", "getAssignedUVs")
    ):
        raise ValueError("スキン出力と現在形状のUV座標または面への割り当てが異なります")
    if not isinstance(regions, list) or not regions:
        raise ValueError("1つ以上の領域を指定してください")
    plans = []
    used = set()
    for region in regions:
        if not isinstance(region, dict) or not {"u", "v", "shell"} <= region.keys():
            raise ValueError("各領域にu、v、shellを指定してください")
        indices = list(region.get("vertices", range(fn.numVertices)))
        if not indices or any(type(i) is not int or not 0 <= i < fn.numVertices for i in indices):
            raise ValueError("領域の頂点番号を確認してください")
        if len(set(indices)) != len(indices) or used.intersection(indices):
            raise ValueError("領域間または領域内で頂点が重複しています")
        used.update(indices)
        weights = skin.getWeights([influence], vertices=indices)
        members = [(i, w) for i, w in zip(indices, weights) if w > 0]
        if not members:
            raise ValueError("領域に指定インフルエンスのウェイトがありません")
        guide = surfaceGuide.create(shape, uvSet, region["shell"], region["u"], region["v"])
        follicle = cmds.listRelatives(guide, shapes=True, type="follicle", fullPath=True)[0]
        # ハンドルが自身の変形結果を読み戻さないよう、スキン直後の形状で評価する。
        cmds.connectAttr(skin_output, follicle + ".inputMesh", force=True)
        plans.append((guide, members))
    results = []
    for guide, members in plans:
        cluster, handle = cmds.cluster(["{}.vtx[{}]".format(parent, i) for i, _ in members], after=True, name="surfaceCluster#")
        handle = cmds.parent(handle, guide, relative=True)[0]
        cmds.xform(handle, objectSpace=True, pivots=(0, 0, 0), preserve=False)
        cmds.setAttr(handle + ".translate", 0, 0, 0)
        handle_shape = cmds.listRelatives(handle, shapes=True, type="clusterHandle", fullPath=True)[0]
        cmds.setAttr(handle_shape + ".origin", 0, 0, 0)
        cmds.connectAttr(guide + ".worldInverseMatrix[0]", cluster + ".bindPreMatrix")
        index, = cmds.cluster(cluster, query=True, geometryIndices=True)
        for vertex, value in members:
            cmds.setAttr("{}.weightList[{}].weights[{}]".format(cluster, index, vertex), value)
        results.append((cluster, handle))
    return results


def show():
    """メッシュ・インフルエンスの順に選択し、UVと各領域の頂点番号を入力する。"""
    nodes = cmds.ls(selection=True, long=True) or []
    if len(nodes) != 2:
        raise ValueError("メッシュとスキンインフルエンスを順に選択してください")
    window = "mlrigSurfaceClusters"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="面追従クラスター")
    cmds.columnLayout(adjustableColumn=True)
    uv = cmds.textFieldGrp(label="UVセット", text="map1")
    cmds.text(label="領域ごとにUVとシェルを指定。verticesを省略すると全頂点。")
    field = cmds.scrollField(text='[{"u":0.25,"v":0.25,"shell":0}]', height=110)

    @undoTransaction("mlrigCreateSurfaceClusterControls")
    def build(*_):
        pairs = create(*nodes, cmds.textFieldGrp(uv, query=True, text=True), json.loads(cmds.scrollField(field, query=True, text=True)))
        cmds.select([handle for _, handle in pairs], replace=True)

    cmds.button(label="スキン列から面追従クラスターを作成", command=build)
    cmds.showWindow(window)
    return window
