"""スキンの1列を、スキン面に追従する1個以上のクラスターハンドルへ転用する。"""

import json

import mlib
from maya import cmds
from mlib import getNode, getPlug
from mlib.decorator import undoTransaction

from . import surfaceGuide


@undoTransaction("mlrigSurfaceClusters")
def create(mesh, influence, uvSet, regions):
    """重複しない頂点群ごとにUV上のハンドルを作成し、スキン後段で局所差分を加える。"""
    path = surfaceGuide.meshPath(mesh)
    shape = path.getName(full=True)
    parent = shape.rsplit("|", 1)[0]
    skins = mlib.ls(cmds.listHistory(shape, pruneDagObjects=True) or [], type="skinCluster").getNames()
    if len(skins) != 1 or path.isInstanced():
        raise ValueError("1個のスキンクラスタで変形する単一パスのメッシュを選択してください")
    skin = getNode(skins[0])
    outputs = cmds.getAttr(skins[0] + ".outputGeometry", multiIndices=True)
    if len(outputs) != 1:
        raise ValueError("単一形状のスキンクラスタに対応しています")
    skin_output = "{}.outputGeometry[{}]".format(skins[0], outputs[0])
    fn = path.mfn()
    upstream = path.mfn()
    upstream.setObject(getPlug(skin_output).mplug().asMObject())
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


@undoTransaction("mlrigRebindSurfaceCluster")
def rebindHandle(handle, marker, shell, u, v, frames=()):
    """面追従基準とハンドルの回転中心を変更し、現在の頂点位置を保つ。"""
    guides = cmds.listRelatives(handle, parent=True, fullPath=True) or []
    if len(guides) != 1 or not cmds.listRelatives(handle, shapes=True, type="clusterHandle"):
        raise ValueError("面追従クラスターのハンドルを選択してください")
    clusters = cmds.listConnections(handle + ".worldMatrix[0]", type="cluster", destination=True, source=False) or []
    if len(clusters) != 1 or not cmds.isConnected(guides[0] + ".worldInverseMatrix[0]", clusters[0] + ".bindPreMatrix"):
        raise ValueError("面追従ガイドとクラスタの接続を確認してください")
    def sample():
        geometries = cmds.cluster(clusters[0], query=True, geometry=True) or []
        samples = {}
        for mesh in geometries:
            path = surfaceGuide.meshPath(mesh)
            world_matrix = path.getPlug("worldMatrix")[path.getInstanceIndex()]
            # vrtsは評価済み頂点をオブジェクト空間のcmで返す。時刻はそのまま保持する。
            shape = path.getName(full=True)
            for frame in frames:
                matrix = world_matrix.get(time=frame)
                samples[shape, frame] = [matrix.transformPoint(point) for point in cmds.getAttr(shape + ".vrts[*]", time=frame)]
        return samples

    if frames and not cmds.undoInfo(query=True, state=True):
        raise ValueError("既存ポーズを比較するにはUndoを有効にしてください")
    before = sample()
    surfaceGuide.rebind(guides[0], shell, u, v)
    position = cmds.xform(marker, query=True, worldSpace=True, rotatePivot=True)
    cmds.xform(handle, worldSpace=True, pivots=position, preserve=True)
    for key, result in sample().items():
        old = before[key]
        if len(old) != len(result) or any(not p.isEquivalent(q, 1e-5) for p, q in zip(old, result)):
            raise ValueError("既存の頂点位置が変わるため再バインドを取り消しました: {} / {}f".format(*key))
    return handle


def showRebind():
    """面追従ハンドルと新しいピボットのマーカーを指定して再バインドする。"""
    nodes = mlib.ls(selection=True, long=True, transforms=True).getNames(full=True)
    if len(nodes) != 2:
        raise ValueError("ハンドル、新しいピボットの順に選択してください")
    win = "mlrigSurfaceClusterRebind"
    if cmds.window(win, exists=True):
        cmds.deleteUI(win)
    cmds.window(win, title="面追従クラスタの再バインド")
    cmds.columnLayout(adjustableColumn=True)
    shell = cmds.intFieldGrp(label="UVシェル", value1=0)
    uv = cmds.floatFieldGrp(numberOfFields=2, label="UV", value1=0.25, value2=0.25)
    validate = cmds.checkBox(label="再生範囲の6時刻で頂点位置を照合", value=True)
    def apply(*_):
        frames = []
        if cmds.checkBox(validate, query=True, value=True):
            start = cmds.playbackOptions(query=True, minTime=True)
            end = cmds.playbackOptions(query=True, maxTime=True)
            frames = [start + (end - start) * i / 5 for i in range(6)]
        rebindHandle(*nodes, cmds.intFieldGrp(shell, query=True, value1=True),
                     cmds.floatFieldGrp(uv, query=True, value1=True), cmds.floatFieldGrp(uv, query=True, value2=True), frames)
    cmds.button(label="基準UV・ピボットを更新", command=apply)
    cmds.showWindow(win)


def show():
    """メッシュ・インフルエンスの順に選択し、UVと各領域の頂点番号を入力する。"""
    nodes = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
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
        mlib.select([handle for _, handle in pairs], replace=True)

    cmds.button(label="スキン列から面追従クラスターを作成", command=build)
    cmds.showWindow(window)
    return window
