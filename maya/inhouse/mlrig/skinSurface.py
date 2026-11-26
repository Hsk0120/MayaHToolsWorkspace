"""スキン面上の重心座標から、補正値または小物の追従ウェイトを求める。"""

from maya import cmds
from maya.api import OpenMaya as om2
from maya.api import OpenMayaAnim as oma2
from mlib.decorator import undoTransaction


def sample(mesh, locator, face=None):
    """最近接三角形の3頂点でスキンウェイトを線形補間する。faceで探索を1面に限定できる。"""
    path = om2.MSelectionList().add(mesh).getDagPath(0)
    if not path.node().hasFn(om2.MFn.kMesh):
        raise ValueError("メッシュのシェイプを指定してください")
    shape = path.fullPathName()
    skins = []
    for node in cmds.ls(cmds.listHistory(shape, pruneDagObjects=True) or [], type="skinCluster") or []:
        fn = oma2.MFnSkinCluster(om2.MSelectionList().add(node).getDependNode(0))
        if path.node() in fn.getOutputGeometry():
            skins.append(fn)
    if len(skins) != 1:
        raise ValueError("選択メッシュに直接対応するスキンクラスタが1つ必要です")
    fn = skins[0]
    world_mesh = om2.MFnDagNode(path).findPlug("worldMesh", False).elementByLogicalIndex(path.instanceNumber()).asMObject()
    intersector = om2.MMeshIntersector()
    if face is None:
        intersector.create(world_mesh, om2.MMatrix())
    else:
        if face < 0 or face >= om2.MFnMesh(world_mesh).numPolygons:
            raise ValueError("面の番号が範囲外です")
        intersector.create(world_mesh, om2.MMatrix(), [face])
    transform = om2.MSelectionList().add(locator).getDagPath(0)
    point = om2.MPoint() * transform.inclusiveMatrix()
    hit = intersector.getClosestPoint(point)
    indices = om2.MFnMesh(world_mesh).getPolygonTriangleVertices(hit.face, hit.triangle)
    a, b = hit.barycentricCoords
    infs = fn.influenceObjects()
    totals = [0.0] * len(infs)
    for i, factor in zip(indices, (a, b, 1 - a - b)):
        comp = om2.MFnSingleIndexedComponent()
        obj = comp.create(om2.MFn.kMeshVertComponent)
        comp.addElement(i)
        weights, _ = fn.getWeights(path, obj)
        for j, weight in enumerate(weights):
            totals[j] += factor * weight
    return hit.face, {joint.fullPathName(): weight for joint, weight in zip(infs, totals)}


@undoTransaction("mlrigAttachBySkinWeights")
def attach(mesh, target, face):
    """指定面から求めた固定ウェイトで、現在の姿勢を保って小物を親追従させる。"""
    _, weights = sample(mesh, target, face)
    active = [(joint, w) for joint, w in weights.items() if w > 1e-8]
    if not active:
        raise ValueError("指定面に有効なインフルエンスがありません")
    target = om2.MSelectionList().add(target).getDagPath(0).fullPathName()
    if any(joint == target or joint.startswith(target + "|") for joint, _ in active):
        raise ValueError("インフルエンスの祖先に追従を設定できません")
    for attr in ("translate", "rotate"):
        for axis in "XYZ":
            plug = target + "." + attr + axis
            if not cmds.getAttr(plug, settable=True) or cmds.connectionInfo(plug, isDestination=True):
                raise ValueError("小物の移動・回転に入力またはロックがあります: " + plug)
    constraint = cmds.parentConstraint([j for j, _ in active], target, maintainOffset=True)[0]
    aliases = cmds.parentConstraint(constraint, query=True, weightAliasList=True)
    for alias, (_, weight) in zip(aliases, active):
        cmds.setAttr(constraint + "." + alias, weight)
    return constraint


def run(action):
    """メッシュまたは単一面、小物の順に選択して照会または接続する。"""
    selection = cmds.ls(selection=True, long=True, flatten=True) or []
    if len(selection) != 2:
        raise ValueError("メッシュまたは1面、位置を示すトランスフォームを順に選択してください")
    first, target = selection
    node, _, component = first.partition(".")
    shapes = [node] if cmds.nodeType(node) == "mesh" else cmds.listRelatives(node, shapes=True, noIntermediate=True, type="mesh", fullPath=True) or []
    if len(shapes) != 1 or not cmds.objectType(target, isAType="transform"):
        raise ValueError("単一のメッシュと位置を示すトランスフォームを選択してください")
    face = None
    if component:
        if not component.startswith("f[") or not component.endswith("]"):
            raise ValueError("メッシュの面を選択してください")
        face = int(component[2:-1])
    if action == "attach":
        if face is None:
            raise ValueError("小物の追従には1面を明示してください")
        return attach(shapes[0], target, face)
    index, weights = sample(shapes[0], target, face)
    window = "mlrigSkinSurfaceWeights"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="スキン面の補正値")
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label="{}  面 {}".format(shapes[0], index))
    for joint, weight in weights.items():
        cmds.text(label="{}  {:.6f}".format(joint, weight))
    cmds.showWindow(window)
    return window
