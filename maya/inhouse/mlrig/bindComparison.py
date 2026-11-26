"""形状をバインドする前に、接続方式による頂点位置の違いを比較する。"""

import math

from maya import cmds
from maya.api import OpenMaya as om2
from mlib.decorator import undoTransaction

from .surfaceGuide import meshPath


def compare(source, destination):
    """同じ面頂点列で、直接接続と座標変換後の最大ワールド距離(cm)を返す。"""
    src, dst = meshPath(source), meshPath(destination)
    first, second = om2.MFnMesh(src), om2.MFnMesh(dst)
    src_topology = tuple(tuple(values) for values in first.getVertices())
    dst_topology = tuple(tuple(values) for values in second.getVertices())
    if first.numVertices != second.numVertices or src_topology != dst_topology:
        raise ValueError("頂点数または面の頂点列が異なります")
    local = first.getPoints()
    target = second.getPoints(om2.MSpace.kWorld)
    src_world = src.inclusiveMatrix()
    dst_world = dst.inclusiveMatrix()
    direct = max(((p * dst_world).distanceTo(q) for p, q in zip(local, target)), default=0.0)
    converted = max(((p * src_world).distanceTo(q) for p, q in zip(local, target)), default=0.0)
    return direct, converted


@undoTransaction("mlrigConnectBindMeshes")
def connect(source, destination, convert):
    """履歴と頂点微調整のないメッシュへ、明示した1方式で入力形状を接続する。"""
    compare(source, destination)
    src, dst = meshPath(source), meshPath(destination)
    first, second = src.fullPathName(), dst.fullPathName()
    plug = second + ".inMesh"
    if src.node() == dst.node() or dst.isInstanced() or cmds.referenceQuery(second, isNodeReferenced=True):
        raise ValueError("独立したローカルの宛先形状を指定してください")
    upstream = cmds.listHistory(first, allConnections=True) or []
    if second in (cmds.ls(upstream, long=True) or []):
        raise ValueError("送り側の入力に宛先があります")
    if cmds.connectionInfo(plug, isDestination=True) or not cmds.getAttr(plug, settable=True):
        raise ValueError("既存の履歴またはロックがある宛先には接続できません")
    for index in cmds.getAttr(second + ".pnts", multiIndices=True) or []:
        tweak = "{}.pnts[{}]".format(second, index)
        if cmds.listConnections(tweak, source=True, destination=False) or any(cmds.getAttr(tweak)[0]):
            raise ValueError("宛先に頂点の微調整があります")
    output = first + ".outMesh"
    if convert:
        graph = cmds.createNode("transformGeometry", name="bindSpaceConversion#", skipSelect=True)
        space = cmds.createNode("multMatrix", name="bindSpaceMatrix#", skipSelect=True)
        cmds.connectAttr("{}.worldMatrix[{}]".format(first, src.instanceNumber()), space + ".matrixIn[0]")
        cmds.connectAttr("{}.worldInverseMatrix[{}]".format(second, dst.instanceNumber()), space + ".matrixIn[1]")
        cmds.connectAttr(output, graph + ".inputGeometry")
        cmds.connectAttr(space + ".matrixSum", graph + ".transform")
        output = graph + ".outputGeometry"
    # inMeshは単純に切断すると最後の評価形状を保持する。元形状をMayaの履歴に記録する。
    cmds.deformableShape(second, createOriginalGeometry=True)
    cmds.connectAttr(output, plug, force=True)
    return second


@undoTransaction("mlrigBindMeshCage")
def bindCage(source, destination):
    """送り側の表示メッシュをケージとして宛先へ標準proximityWrapを追加する。"""
    src, dst = meshPath(source), meshPath(destination)
    first, second = src.fullPathName(), dst.fullPathName()
    if src.node() == dst.node() or src.isInstanced() or dst.isInstanced() or cmds.referenceQuery(second, isNodeReferenced=True):
        raise ValueError("独立したケージとローカルの宛先メッシュを指定してください")
    upstream = cmds.listHistory(first, allConnections=True) or []
    if second in (cmds.ls(upstream, long=True) or []):
        raise ValueError("ケージの入力に宛先があります")
    deformer = cmds.deformer(second, type="proximityWrap", name="meshCageBind#")[0]
    cmds.proximityWrap(deformer, edit=True, addDrivers=[first])
    if not cmds.proximityWrap(deformer, query=True, driverIndices=True):
        raise ValueError("ケージを登録できません")
    return deformer


@undoTransaction("mlrigBindProximityRange")
def bindRange(source, destination, radius):
    """バインド時の送り側の面までの距離(cm)でケージの頂点ウェイトを線形に減衰させる。"""
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("最大距離には正の有限値を指定してください")
    driver = om2.MFnMesh(meshPath(source))
    target = meshPath(destination)
    points = om2.MFnMesh(target).getPoints(om2.MSpace.kWorld)
    weights = []
    for point in points:
        closest, _ = driver.getClosestPoint(point, om2.MSpace.kWorld)
        weights.append(max(0.0, 1.0 - point.distanceTo(closest) / radius))
    deformer = bindCage(source, destination)
    for index, weight in enumerate(weights):
        cmds.percent(deformer, "{}.vtx[{}]".format(target.fullPathName(), index), value=weight)
    return deformer


@undoTransaction("mlrigTangentTarget")
def bindTangentTarget(sculpt, base):
    """同じトポロジーのスカルプトを評価済みベースの接線空間ターゲットとして追加する。"""
    compare(sculpt, base)
    target, guide = meshPath(sculpt), meshPath(base)
    if target.node() == guide.node() or guide.isInstanced() or cmds.referenceQuery(guide.fullPathName(), isNodeReferenced=True):
        raise ValueError("独立したスカルプトとローカルのベースを指定してください")
    guide_name = guide.fullPathName().rsplit("|", 1)[0]
    node = cmds.blendShape(guide_name, after=True, name="surfaceCorrection#")[0]
    cmds.blendShape(node, edit=True, target=(guide_name, 0, target.fullPathName().rsplit("|", 1)[0], 1.0), tangentSpace=True)
    if not cmds.getAttr(node + ".weight", multiIndices=True):
        raise ValueError("接線空間の補正ターゲットを登録できません")
    # スカルプトのライブ入力を残すと、その固定位置へ毎回差分を再計算してしまう。
    item = node + ".inputTarget[0].inputTargetGroup[0].inputTargetItem[6000]"
    cmds.getAttr(item + ".inputPointsTarget")
    source = cmds.connectionInfo(item + ".inputGeomTarget", sourceFromDestination=True)
    if source:
        cmds.disconnectAttr(source, item + ".inputGeomTarget")
    return node


@undoTransaction("mlrigSurfaceDifference")
def bindSurfaceDifference(reference, evaluated, destination):
    """同じ面構成の2形状のワールド頂点差を宛先の現在形状へ加える。"""
    compare(reference, destination)
    compare(evaluated, destination)
    ref, live, dst = (meshPath(n) for n in (reference, evaluated, destination))
    if len({path.fullPathName() for path in (ref, live, dst)}) != 3 or any(path.isInstanced() for path in (ref, live, dst)):
        raise ValueError("独立した3つのメッシュを指定してください")
    transform = dst.fullPathName().rpartition("|")[0]
    if cmds.referenceQuery(transform, isNodeReferenced=True):
        raise ValueError("ローカルの宛先メッシュを指定してください")
    candidates = [n for n in cmds.listConnections(transform + ".message", type="blendShape") or [] if cmds.objExists(n + ".mlrigDifferenceBase") and cmds.isConnected(transform + ".message", n + ".mlrigDifferenceBase")]
    for path in (ref, live):
        upstream = cmds.listHistory(path.fullPathName(), allConnections=True) or []
        if dst.fullPathName() in (cmds.ls(upstream, long=True) or []) or set(candidates).intersection(upstream):
            raise ValueError("宛先が送り側の履歴にあります")
    if candidates:
        node, = candidates
    else:
        node = cmds.blendShape(transform, after=True, name="surfaceDifference#")[0]
        cmds.addAttr(node, longName="mlrigDifferenceBase", attributeType="message")
        cmds.connectAttr(transform + ".message", node + ".mlrigDifferenceBase")
        cmds.setAttr(node + ".supportNegativeWeights", True)
    for index, (path, weight) in enumerate(((ref, -1), (live, 1))):
        target = "{}.inputTarget[0].inputTargetGroup[{}].inputTargetItem[6000].inputGeomTarget".format(node, index)
        if not candidates:
            converter = cmds.createNode("transformGeometry", name="surfaceDifferenceSpace#")
            space = cmds.createNode("multMatrix", name="surfaceDifferenceMatrix#")
            cmds.connectAttr(transform + ".worldInverseMatrix[0]", space + ".matrixIn[1]")
            cmds.connectAttr(space + ".matrixSum", converter + ".transform")
            cmds.connectAttr(converter + ".outputGeometry", target)
            cmds.setAttr("{}.weight[{}]".format(node, index), weight)
        else:
            converter = cmds.connectionInfo(target, sourceFromDestination=True).rsplit(".", 1)[0]
            if not converter or cmds.nodeType(converter) != "transformGeometry":
                raise ValueError("既存の面差分の座標変換を確認してください")
            space = cmds.connectionInfo(converter + ".transform", sourceFromDestination=True).rsplit(".", 1)[0]
        cmds.connectAttr(path.fullPathName() + ".worldMatrix[0]", space + ".matrixIn[0]", force=True)
        cmds.connectAttr(path.fullPathName() + ".outMesh", converter + ".inputGeometry", force=True)
    return node


def show():
    """選択した送り側・受け側の形状について、バインド前の比較を表示する。"""
    nodes = cmds.ls(selection=True, long=True) or []
    if len(nodes) != 2:
        raise ValueError("送り側と受け側のメッシュを順に選択してください")
    window = "mlrigBindComparison"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="バインド方式の事前比較")
    cmds.columnLayout(adjustableColumn=True)
    try:
        direct, converted = compare(*nodes)
        cmds.text(label="Connect Only  最大差 {:.6g} cm".format(direct))
        cmds.text(label="Transform Geometry  最大差 {:.6g} cm".format(converted))
        cmds.button(label="Connect Onlyで接続", command=lambda *_: connect(*nodes, False))
        cmds.button(label="Transform Geometryで接続", command=lambda *_: connect(*nodes, True))
        cmds.button(label="接線空間の補正ターゲットを追加", command=lambda *_: bindTangentTarget(*nodes))
    except ValueError as exc:
        cmds.text(label=str(exc))
    cmds.text(label="ケージ方式は送り側の面と現在の姿勢を使用")
    cmds.button(label="ケージでバインド", command=lambda *_: bindCage(*nodes))
    radius = cmds.floatFieldGrp(label="最大距離(cm)", value1=1.0)
    cmds.button(label="近接距離でバインド", command=lambda *_: bindRange(*nodes, cmds.floatFieldGrp(radius, query=True, value1=True)))
    cmds.showWindow(window)
    return window
