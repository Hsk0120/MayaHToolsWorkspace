"""スキン面上の重心座標から、補正値または小物の追従ウェイトを求める。"""

import mlib
from maya import cmds
from mlib import getNode
from mlib.maths import Vector
from mlib.decorator import undoTransaction


def sample(mesh, locator, face=None):
    """最近接三角形の3頂点でスキンウェイトを線形補間する。faceで探索を1面に限定できる。"""
    shape = getNode(mesh)
    if shape.getType() != "mesh":
        raise ValueError("メッシュのシェイプを指定してください")
    skins = [skin for skin in shape.getHistory(type="skinCluster")
             if shape.getUuid() in {target.getUuid() for target in skin.getGeometry(all=True)}]
    if len(skins) != 1:
        raise ValueError("選択メッシュに直接対応するスキンクラスタが1つ必要です")
    skin = skins[0]
    point = getNode(locator).getTranslation(ws=True)
    fn = shape.mfn()
    if face is None:
        matrix = shape.getPlug("worldMatrix")[shape.getInstanceIndex()].get()
        axes = [Vector(*list(matrix)[i:i+3]) for i in (0, 4, 8)]
        squared = [axis * axis for axis in axes]
        tolerance = max(squared) * 1e-12
        # 相似変換ならMayaの最近面をそのまま使える。非一様スケール・シアーでは
        # オブジェクト空間で遠い面がワールド空間で近くなる場合がある。
        if min(squared) > 0 and max(squared) - min(squared) <= tolerance and all(
            abs(axes[i] * axes[j]) <= tolerance for i, j in ((0, 1), (1, 2), (2, 0))
        ):
            _, face = shape.getClosestPoint(point, ws=True)
    if face is not None:
        if not 0 <= face < shape.getNumPolygons():
            raise ValueError("面の番号が範囲外です")
        triangles = [(face, list(fn.getPolygonTriangleVertices(face, i))) for i in range(shape.getFaces(face).getTriangleCount())]
        indices = {i for _, vertices in triangles for i in vertices}
        positions = {i: shape.getVertices(i).getPosition(ws=True) for i in indices}
    else:
        positions = shape.getPoints(ws=True)
        counts, ids = fn.getTriangles()
        indices = iter(ids)
        triangles = ((index, (next(indices), next(indices), next(indices))) for index, count in enumerate(counts) for _ in range(count))

    best = None
    for index, vertices in triangles:
        a, b, c = corners = [positions[i] for i in vertices]
        if best is not None:
            lower_bound = sum(max(min(a[i], b[i], c[i]) - point[i], point[i] - max(a[i], b[i], c[i]), 0.0)**2 for i in range(3))
            if lower_bound >= best[0]:
                continue
        if ((b - a) ^ (c - a)).length() == 0:
            continue
        weights = point.getBarycentricWeights(*corners)
        candidates = [weights] if min(weights) >= 0 else []
        if not candidates:
            for i, j in ((0, 1), (1, 2), (2, 0)):
                t = min(1, max(0, point.getBarycentricWeights(corners[i], corners[j])[1]))
                edge_weights = [0.0, 0.0, 0.0]
                edge_weights[i], edge_weights[j] = 1.0 - t, t
                candidates.append(edge_weights)
        for factors in candidates:
            delta = point - sum((v * w for v, w in zip(corners, factors)), Vector())
            squared_distance = delta * delta
            if best is None or squared_distance < best[0]:
                best = squared_distance, index, vertices, factors
    if best is None:
        raise ValueError("評価できる三角形がありません")
    _, face, vertices, factors = best
    influences = list(skin.getInfluences())
    weights = skin.getWeights(influences, vertices=vertices, rows=True, geometryIndex=skin.getGeometryIndices(shape))
    return face, {joint.getName(full=True): sum(row[i] * w for row, w in zip(weights, factors))
                  for i, joint in enumerate(influences)}


@undoTransaction("mlrigAttachBySkinWeights")
def attach(mesh, target, face):
    """指定面から求めた固定ウェイトで、現在の姿勢を保って小物を親追従させる。"""
    _, weights = sample(mesh, target, face)
    active = [(joint, w) for joint, w in weights.items() if w > 1e-8]
    if not active:
        raise ValueError("指定面に有効なインフルエンスがありません")
    target = getNode(target).getName(full=True)
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
    selection = [item.getName(full=True) for item in mlib.ls(selection=True, long=True, flatten=True)]
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
