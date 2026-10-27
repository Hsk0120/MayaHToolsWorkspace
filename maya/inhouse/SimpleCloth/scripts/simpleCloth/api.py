"""Simple Clothのセットアップ・頂点マップ・コライダー・保存操作。"""

from contextlib import contextmanager
import json
import math
from pathlib import Path
import uuid

from maya import cmds, mel
from maya.api import OpenMaya as om

from . import node, solver


PLUGIN = Path(__file__).resolve().parents[2] / "plug-ins" / "simpleClothNode.py"
SETTINGS = tuple(node.SCALARS) + ("iterations", "maxSteps", "selfCollision", "gravity", "wind")


@contextmanager
def _transaction(label):
    """この操作だけを1回のUndoへまとめ、途中失敗時に取り消す。"""
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError("Simple Clothの編集にはUndoを有効にしてください")
    name = label + " " + uuid.uuid4().hex[:8]
    cmds.undoInfo(openChunk=True, chunkName=name)
    try:
        yield
    except Exception:
        cmds.undoInfo(closeChunk=True)
        if cmds.undoInfo(query=True, undoName=True) == name:
            cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)


def _number(value, name, minimum=None, maximum=None):
    """公開入力に対して数値型・有限値・範囲を検査する。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name}には数値を指定してください")
    if not math.isfinite(value) or (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ValueError(f"{name}が範囲外です: {value}")
    return value


def _solver(value):
    """一意なSimple Clothノード名を検証する。"""
    matches = cmds.ls(value, type=node.SimpleClothNode.TYPE_NAME) or []
    if len(matches) != 1:
        raise ValueError("Simple ClothのSolverを1個指定してください")
    return matches[0]


def _mesh(value):
    """中間シェイプを除く単一の非インスタンスメッシュのDAGパスを返す。"""
    matches = cmds.ls(value, long=True) or []
    if len(matches) != 1:
        raise ValueError("メッシュを一意に指定してください")
    shape = matches[0]
    if cmds.nodeType(shape) == "transform":
        shapes = cmds.listRelatives(shape, shapes=True, noIntermediate=True, fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise ValueError("1個のメッシュシェイプを持つオブジェクトを指定してください")
        shape = shapes[0]
    if cmds.nodeType(shape) != "mesh":
        raise TypeError("ポリゴンメッシュを指定してください")
    selection = om.MSelectionList()
    selection.add(shape)
    path = selection.getDagPath(0)
    if path.isInstanced():
        raise ValueError("インスタンスを複製してから使用してください")
    return path


def _own(owner, objects):
    """作成した専用ノードだけを所有物として記録する。"""
    if not cmds.attributeQuery("ownedObjects", node=owner, exists=True):
        cmds.addAttr(owner, longName="ownedObjects", attributeType="message", multi=True, indexMatters=True)
    indices = cmds.getAttr(owner + ".ownedObjects", multiIndices=True) or []
    first = max(indices, default=-1) + 1
    for index, obj in enumerate(objects, start=first):
        cmds.connectAttr(obj + ".message", f"{owner}.ownedObjects[{index}]")


def getConnection(solverNode, attribute):
    """sourceMesh/outputMeshObject等のメッセージ接続先を取得する。"""
    solver_node = _solver(solverNode)
    if attribute not in ("sourceMesh", "outputMeshObject"):
        raise ValueError("sourceMeshまたはoutputMeshObjectを指定してください")
    matches = cmds.listConnections(solver_node + "." + attribute, source=True, destination=False) or []
    if len(matches) != 1:
        raise ValueError("セットアップのメッシュ接続が失われています")
    return matches[0]


def loadPlugin():
    """計算プラグインを明示的にロードする。信頼済みパス設定は変更しない。"""
    if not cmds.pluginInfo(str(PLUGIN), query=True, loaded=True):
        cmds.loadPlugin(str(PLUGIN), quiet=True)


def create(mesh, name="simpleCloth"):
    """現在のメッシュを静止形状として独立した出力を作る。

    Args:
        mesh: 変形済みの入力ポリゴンメッシュ。頂点数1500以下。
        name: Solver名。

    Returns:
        str: 設定と頂点マップを保持するSolver名。
    """
    path = _mesh(mesh)
    function = om.MFnMesh(path)
    if not 3 <= function.numVertices <= 1500:
        raise ValueError("初版は3〜1500頂点のシミュレーションメッシュを使用してください")
    points = [om.MVector(point) for point in function.getPoints(om.MSpace.kWorld)]
    counts, vertices = function.getVertices()
    _, indices = function.getTriangles()
    triangles = [list(indices[index:index + 3]) for index in range(0, len(indices), 3)]
    solver.build_constraints(points, triangles)
    if not triangles or set(vertices) != set(range(len(points))):
        raise ValueError("面のない頂点を除去してください")
    reference = {"points": [list(point) for point in points], "counts": list(counts),
                 "vertices": list(vertices), "triangles": triangles}
    loadPlugin()
    with _transaction("Simple Cloth: Create"):
        result = cmds.createNode(node.SimpleClothNode.TYPE_NAME, name=name)
        cmds.setAttr(result + ".referenceData", json.dumps(reference), type="string")
        cmds.setAttr(result + ".maxDistanceMap", [1.0] * len(points), type="doubleArray")
        cmds.setAttr(result + ".startFrame", cmds.currentTime(query=True))
        cmds.connectAttr("time1.outTime", result + ".time")
        cmds.connectAttr(path.fullPathName() + ".outMesh", result + ".inputMesh")
        cmds.connectAttr(path.fullPathName() + ".worldMatrix[0]", result + ".inputMatrix")
        output = cmds.createNode("transform", name=name + "_output")
        shape = cmds.createNode("mesh", name=output + "Shape", parent=output)
        cmds.connectAttr(result + ".outputMesh", shape + ".inMesh")
        cmds.setAttr(output + ".inheritsTransform", False, lock=True)
        for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
            cmds.setAttr(output + "." + attr, lock=True)
        cmds.sets(output, edit=True, forceElement="initialShadingGroup")
        for attribute, target in (("sourceMesh", path.fullPathName()), ("outputMeshObject", output)):
            cmds.addAttr(result, longName=attribute, attributeType="message")
            cmds.connectAttr(target + ".message", result + "." + attribute)
        cmds.addAttr(result, longName="colliderObjects", attributeType="message", multi=True)
        _own(result, [output])
    return result


def getMap(solverNode):
    """頂点番号順のMax Distance乗数を返す。0は固定、1は最大距離。"""
    return list(cmds.getAttr(_solver(solverNode) + ".maxDistanceMap"))


def setMap(solverNode, values):
    """0〜1の全頂点マップを事前検証し、Undo可能に一括設定する。"""
    solver_node = _solver(solverNode)
    values = list(values)
    if len(values) != len(getMap(solver_node)):
        raise ValueError("マップの要素数が頂点数と一致しません")
    for value in values:
        _number(value, "Map", 0, 1)
    with _transaction("Simple Cloth: Set Map"):
        cmds.setAttr(solver_node + ".maxDistanceMap", values, type="doubleArray")


def setVertexWeights(solverNode, indices, value):
    """指定した頂点番号のMax Distance乗数を変更する。"""
    _number(value, "Map", 0, 1)
    values = getMap(solverNode)
    indices = list(indices)
    if not indices:
        raise ValueError("頂点を1個以上指定してください")
    for index in indices:
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError("頂点番号は整数です")
        if not 0 <= index < len(values):
            raise ValueError("頂点番号が範囲外です")
        values[index] = value
    setMap(solverNode, values)


def paintMap(solverNode):
    """開始フレームで出力を選択し、標準Attribute Paint Toolを開く。"""
    solver_node = _solver(solverNode)
    cmds.currentTime(cmds.getAttr(solver_node + ".startFrame"))
    cmds.select(getConnection(solver_node, "outputMeshObject"), replace=True)
    mel.eval("ArtPaintAttrTool;")
    context = cmds.currentCtx()
    cmds.artAttrCtx(context, edit=True, paintattrselected=f"simpleClothSolver.{solver_node}.maxDistanceMap",
                    minvalue=0, maxvalue=1, clamp="both", clamplower=0, clampupper=1,
                    colorrangelower=0, colorrangeupper=1, value=0, colorfeedback=True)
    return context


def reset(solverNode):
    """キャッシュを無効化して開始フレームへ戻す。"""
    solver_node = _solver(solverNode)
    with _transaction("Simple Cloth: Reset"):
        cmds.setAttr(solver_node + ".resetSerial", cmds.getAttr(solver_node + ".resetSerial") + 1)
    cmds.currentTime(cmds.getAttr(solver_node + ".startFrame"))


def addCollider(solverNode, kind="sphere", radius=3.0, height=6.0, attachTo=None):
    """球・Yカプセル・+Y平面ガイドを作る。寸法はcm、追従先は任意。

    Returns:
        str: 移動・回転とclothRadius/clothHeightを編集するガイド。
    """
    solver_node = _solver(solverNode)
    if kind not in ("sphere", "capsule", "plane"):
        raise ValueError("sphere/capsule/planeを指定してください")
    _number(radius, "Radius", 0)
    _number(height, "Height", 0)
    if attachTo is not None:
        matches = cmds.ls(attachTo, long=True, type="transform") or []
        if len(matches) != 1:
            raise ValueError("追従先Transformを1個指定してください")
        attachTo = matches[0]
        output = cmds.ls(getConnection(solver_node, "outputMeshObject"), long=True)[0]
        if attachTo == output or attachTo.startswith(output + "|"):
            raise ValueError("出力メッシュへの追従は循環するため使用できません")
    kinds = json.loads(cmds.getAttr(solver_node + ".colliderTypes"))
    with _transaction("Simple Cloth: Add Collider"):
        guide = cmds.createNode("transform", name="sc_" + kind, **({"parent": attachTo} if attachTo else {}))
        for attr, default in (("clothRadius", radius), ("clothHeight", height)):
            cmds.addAttr(guide, longName=attr, attributeType="double", defaultValue=default, minValue=0, keyable=True)
        cmds.addAttr(guide, longName="clothKind", attributeType="long")
        kind_index = ("sphere", "capsule", "plane").index(kind)
        cmds.setAttr(guide + ".clothKind", kind_index, lock=True)
        helpers = []
        if kind == "sphere":
            mesh, history = cmds.polySphere(radius=radius, subdivisionsX=20, subdivisionsY=12)
            cmds.connectAttr(guide + ".clothRadius", history + ".radius")
        elif kind == "capsule":
            mesh, history = cmds.polyCylinder(radius=radius, height=height + 2 * radius, roundCap=True,
                                              subdivisionsX=20, subdivisionsCaps=6)
            multiply = cmds.createNode("multDoubleLinear")
            add = cmds.createNode("addDoubleLinear")
            cmds.connectAttr(guide + ".clothRadius", multiply + ".input1")
            cmds.setAttr(multiply + ".input2", 2)
            cmds.connectAttr(multiply + ".output", add + ".input1")
            cmds.connectAttr(guide + ".clothHeight", add + ".input2")
            cmds.connectAttr(add + ".output", history + ".height")
            cmds.connectAttr(guide + ".clothRadius", history + ".radius")
            helpers.extend([multiply, add])
        else:
            mesh, history = cmds.polyPlane(width=20, height=20, subdivisionsX=1, subdivisionsY=1)
        cmds.parent(mesh, guide, relative=True)
        # ガイドの形状は計算単位cm。シーン表示単位によるpolyプリミティブ倍率を打ち消す。
        unit_scale = om.MDistance(1.0, om.MDistance.kCentimeters).asUnits(om.MDistance.uiUnit())
        cmds.setAttr(mesh + ".scale", unit_scale, unit_scale, unit_scale)
        cmds.setAttr(guide + ".overrideEnabled", True)
        cmds.setAttr(guide + ".overrideRGBColors", True)
        cmds.setAttr(guide + ".overrideColorRGB", 0.2, 0.65, 1.0)
        cmds.setAttr(guide + ".overrideShading", False)
        _own(guide, helpers + [history])
        _own(solver_node, [guide] + helpers + [history])
        for source, target in (("worldMatrix[0]", "colliderMatrix"), ("clothRadius", "colliderRadius"),
                               ("clothHeight", "colliderHeight"), ("message", "colliderObjects")):
            cmds.connectAttr(guide + "." + source, f"{solver_node}.{target}[{len(kinds)}]")
        cmds.setAttr(solver_node + ".colliderTypes", json.dumps(kinds + [kind_index]), type="string")
    return guide


def getColliders(solverNode):
    """コライダーを接続インデックス順に返す。"""
    solver_node = _solver(solverNode)
    result = []
    for index in cmds.getAttr(solver_node + ".colliderObjects", multiIndices=True) or []:
        result.extend(cmds.listConnections(f"{solver_node}.colliderObjects[{index}]", source=True, destination=False) or [])
    return result


def removeCollider(solverNode, collider):
    """専用コライダーとその表示用ノードを削除して接続番号を詰める。"""
    solver_node = _solver(solverNode)
    colliders = getColliders(solver_node)
    if collider not in colliders:
        raise ValueError("このSolverに属するコライダーを指定してください")
    with _transaction("Simple Cloth: Remove Collider"):
        colliders.remove(collider)
        for attribute in ("colliderMatrix", "colliderRadius", "colliderHeight", "colliderObjects"):
            for index in cmds.getAttr(solver_node + "." + attribute, multiIndices=True) or []:
                cmds.removeMultiInstance(f"{solver_node}.{attribute}[{index}]", b=True)
        for index, remaining in enumerate(colliders):
            for source, target in (("worldMatrix[0]", "colliderMatrix"), ("clothRadius", "colliderRadius"),
                                   ("clothHeight", "colliderHeight"), ("message", "colliderObjects")):
                cmds.connectAttr(remaining + "." + source, f"{solver_node}.{target}[{index}]")
        kinds = [cmds.getAttr(remaining + ".clothKind") for remaining in colliders]
        cmds.setAttr(solver_node + ".colliderTypes", json.dumps(kinds), type="string")
        owned = cmds.listConnections(collider + ".ownedObjects", source=True, destination=False) or []
        cmds.delete(owned + [collider])


def remove(solverNode):
    """セットアップ所有物だけを削除する。入力とベイク済みメッシュは保持する。"""
    solver_node = _solver(solverNode)
    owned = cmds.listConnections(solver_node + ".ownedObjects", source=True, destination=False) or []
    with _transaction("Simple Cloth: Remove"):
        cmds.delete(owned + [solver_node])


def savePreset(solverNode, path):
    """係数と全頂点マップをUTF-8 JSONへ保存する。接続やアニメーションは含めない。"""
    solver_node = _solver(solverNode)
    reference = json.loads(cmds.getAttr(solver_node + ".referenceData"))
    settings = {name: cmds.getAttr(solver_node + "." + name) for name in SETTINGS}
    for name in ("gravity", "wind"):
        settings[name] = settings[name][0]
    payload = {"format": "SimpleClothPreset", "version": 1, "settings": settings,
               "counts": reference["counts"], "vertices": reference["vertices"], "map": getMap(solver_node)}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def loadPreset(solverNode, path):
    """トポロジー・係数・マップを全件検証してからUndo可能に復元する。"""
    solver_node = _solver(solverNode)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format") != "SimpleClothPreset" or payload.get("version") != 1:
        raise ValueError("Simple Cloth Preset version 1を指定してください")
    reference = json.loads(cmds.getAttr(solver_node + ".referenceData"))
    if payload.get("counts") != reference["counts"] or payload.get("vertices") != reference["vertices"]:
        raise ValueError("プリセットと入力メッシュのトポロジーが異なります")
    values = payload.get("map")
    if not isinstance(values, list) or len(values) != len(reference["points"]):
        raise ValueError("頂点マップの要素数が不正です")
    for value in values:
        _number(value, "Map", 0, 1)
    settings = payload.get("settings")
    if not isinstance(settings, dict) or set(settings) != set(SETTINGS):
        raise ValueError("プリセットの設定項目が一致しません")
    for name, value in settings.items():
        if name in ("gravity", "wind"):
            if not isinstance(value, list) or len(value) != 3:
                raise ValueError(f"{name}は3要素です")
            for item in value:
                _number(item, name)
        elif name == "selfCollision":
            if not isinstance(value, bool):
                raise TypeError("selfCollisionはboolです")
        else:
            _, minimum, maximum = (node.SCALARS if name in node.SCALARS else node.INTEGERS)[name]
            _number(value, name, minimum, maximum)
            if name in node.INTEGERS and not isinstance(value, int):
                raise TypeError(f"{name}は整数です")
    with _transaction("Simple Cloth: Load Preset"):
        for name, value in settings.items():
            if name in ("gravity", "wind"):
                cmds.setAttr(solver_node + "." + name, *value, type="float3")
            else:
                cmds.setAttr(solver_node + "." + name, value)
        cmds.setAttr(solver_node + ".maxDistanceMap", values, type="doubleArray")


def bake(solverNode, start, end):
    """各整数フレームを独立メッシュのblendShapeへベイクする。

    Args:
        solverNode: Simple Cloth Solver。
        start: 開始フレーム。整数。
        end: 終了フレーム。整数、最大1000フレーム。

    Returns:
        str: プラグインに依存しないベイク済みメッシュ。フレーム間は線形補間。
    """
    solver_node = _solver(solverNode)
    for value in (start, end):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("ベイク範囲は整数フレームで指定してください")
    if end < start or end - start >= 1000:
        raise ValueError("ベイク範囲は1〜1000フレームです")
    output = getConnection(solver_node, "outputMeshObject")
    time = cmds.currentTime(query=True)
    selection = cmds.ls(selection=True, long=True) or []

    def duplicate_output(name):
        """複製時にMayaが増やす所有メッセージを外し、独立メッシュを返す。"""
        duplicate = cmds.duplicate(output, name=name, returnRootsOnly=True)[0]
        for destination in cmds.listConnections(duplicate + ".message", source=False, destination=True, plugs=True) or []:
            if destination.startswith(solver_node + "."):
                cmds.disconnectAttr(duplicate + ".message", destination)
        cmds.delete(duplicate, constructionHistory=True)
        return duplicate

    try:
        with _transaction("Simple Cloth: Bake"):
            cmds.currentTime(start)
            baked = duplicate_output(solver_node + "_baked")
            blend = cmds.blendShape(baked, name=solver_node + "_cache", origin="world")[0]
            for index, frame in enumerate(range(start, end + 1)):
                cmds.currentTime(frame)
                snapshot = duplicate_output(solver_node + "_snapshot")
                cmds.blendShape(blend, edit=True, target=(baked, index, snapshot, 1.0))
                cmds.delete(snapshot)
                attr = f"{blend}.weight[{index}]"
                keys = [(frame, 1)]
                if frame > start:
                    keys.insert(0, (frame - 1, 0))
                if frame < end:
                    keys.append((frame + 1, 0))
                for key_time, value in keys:
                    cmds.setKeyframe(attr, time=key_time, value=value, inTangentType="linear", outTangentType="linear")
    finally:
        cmds.currentTime(time)
        cmds.select(selection, replace=True) if selection else cmds.select(clear=True)
    return baked
