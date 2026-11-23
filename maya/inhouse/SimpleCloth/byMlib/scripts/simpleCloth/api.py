"""Simple Clothのセットアップ・頂点マップ・コライダー・保存操作。"""

from contextlib import contextmanager
import json
import math
from pathlib import Path
import uuid

from maya import cmds, mel

import mlib
from mlib.common import Plugin, Time, units

from . import node, solver


_ROOT = Path(__file__).resolve().parents[2]
# byMlib/ の下に置いた版でも、元のフォルダーのプラグインをロードする。
if _ROOT.name == "byMlib":
    _ROOT = _ROOT.parent
PLUGIN = _ROOT / "plug-ins" / "simpleClothNode.py"
SETTINGS = tuple(node.SCALARS) + ("iterations", "maxSteps", "selfCollision", "gravity", "wind")
COLLIDER_PLUGS = (("worldMatrix[0]", "colliderMatrix"), ("clothRadius", "colliderRadius"),
                  ("clothHeight", "colliderHeight"), ("message", "colliderObjects"))


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
    """一意なSimple Clothノードを検証して、mlibのノードで返す。"""
    matches = mlib.ls(value, type=node.SimpleClothNode.TYPE_NAME)
    if len(matches) != 1:
        raise ValueError("Simple ClothのSolverを1個指定してください")
    return matches[0]


def _mesh_node(value):
    """中間シェイプを除く単一の非インスタンスメッシュを、mlibのMeshで返す。"""
    matches = mlib.ls(value, long=True)
    if len(matches) != 1:
        raise ValueError("メッシュを一意に指定してください")
    shape = matches[0]
    if isinstance(shape, mlib.Component):
        shape = shape.shape
    elif not isinstance(shape, mlib.Node):
        shape = shape.getNode()
    if shape.getType() == "transform":
        shapes = [item for item in shape.getShapes() if item.getType() == "mesh"]
        if len(shapes) != 1:
            raise ValueError("1個のメッシュシェイプを持つオブジェクトを指定してください")
        shape = shapes[0]
    if shape.getType() != "mesh":
        raise TypeError("ポリゴンメッシュを指定してください")
    if shape.isInstanced():
        raise ValueError("インスタンスを複製してから使用してください")
    return shape


def _mesh(value):
    """中間シェイプを除く単一の非インスタンスメッシュのDAGパスを返す。"""
    return _mesh_node(value).mpath()


def _own(owner, objects):
    """作成した専用ノードだけを所有物として記録する。"""
    if owner.hasAttr("ownedObjects"):
        plug = owner.getPlug("ownedObjects")
    else:
        plug = owner.addAttr("ownedObjects", attributeType="message", multi=True, indexMatters=True)
    for obj in objects:
        plug.appendMessage(obj)


def _connected_node(solver_node, attribute):
    """sourceMesh/outputMeshObjectのメッセージ接続元のノードを取得する。"""
    if attribute not in ("sourceMesh", "outputMeshObject"):
        raise ValueError("sourceMeshまたはoutputMeshObjectを指定してください")
    matches = solver_node.getPlug(attribute).getConnections(destination=False, asNode=True)
    if len(matches) != 1:
        raise ValueError("セットアップのメッシュ接続が失われています")
    return matches[0]


def getConnection(solverNode, attribute):
    """sourceMesh/outputMeshObject等のメッセージ接続先を取得する。"""
    return _connected_node(_solver(solverNode), attribute).getName()


def loadPlugin():
    """計算プラグインを明示的にロードする。信頼済みパス設定は変更しない。"""
    plugin = Plugin(str(PLUGIN))
    if not plugin.isLoaded():
        plugin.load(quiet=True)


def create(mesh, name="simpleCloth"):
    """現在のメッシュを静止形状として独立した出力を作る。

    Args:
        mesh: 変形済みの入力ポリゴンメッシュ。頂点数1500以下。
        name: Solver名。

    Returns:
        str: 設定と頂点マップを保持するSolver名。
    """
    source = _mesh_node(mesh)
    if not 3 <= source.getNumVertices() <= 1500:
        raise ValueError("初版は3〜1500頂点のシミュレーションメッシュを使用してください")
    points = source.getPoints(ws=True)
    counts, vertices = source.getTopology()
    triangles = [list(triangle) for triangle in source.getTriangles()]
    solver.build_constraints(points, triangles)
    if not triangles or set(vertices) != set(range(len(points))):
        raise ValueError("面のない頂点を除去してください")
    reference = {"points": [list(point) for point in points], "counts": list(counts),
                 "vertices": list(vertices), "triangles": triangles}
    loadPlugin()
    with _transaction("Simple Cloth: Create"):
        result = mlib.createNode(node.SimpleClothNode.TYPE_NAME, name=name)
        result.getPlug("referenceData").set(json.dumps(reference))
        result.getPlug("maxDistanceMap").set([1.0] * len(points))
        result.getPlug("startFrame").set(Time.getCurrent())
        mlib.getPlug("time1.outTime").connectTo(result.getPlug("time"))
        source.getPlug("outMesh").connectTo(result.getPlug("inputMesh"))
        source.getPlug("worldMatrix[0]").connectTo(result.getPlug("inputMatrix"))
        output = mlib.createNode("transform", name=name + "_output")
        shape = mlib.createNode("mesh", name=output.getName() + "Shape", parent=output)
        result.getPlug("outputMesh").connectTo(shape.getPlug("inMesh"))
        inherits = output.getPlug("inheritsTransform")
        inherits.set(False)
        inherits.setLocked(True)
        output.setAttrFlags(["tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"], locked=True)
        mlib.getNode("initialShadingGroup").assign(output)
        for attribute, target in (("sourceMesh", source), ("outputMeshObject", output)):
            result.addAttr(attribute, attributeType="message").connect(target.getPlug("message"))
        result.addAttr("colliderObjects", attributeType="message", multi=True)
        _own(result, [output])
    return result.getName()


def getMap(solverNode):
    """頂点番号順のMax Distance乗数を返す。0は固定、1は最大距離。"""
    return list(_solver(solverNode).getPlug("maxDistanceMap").get())


def setMap(solverNode, values):
    """0〜1の全頂点マップを事前検証し、Undo可能に一括設定する。"""
    solver_node = _solver(solverNode)
    values = list(values)
    if len(values) != len(getMap(solver_node)):
        raise ValueError("マップの要素数が頂点数と一致しません")
    for value in values:
        _number(value, "Map", 0, 1)
    with _transaction("Simple Cloth: Set Map"):
        solver_node.getPlug("maxDistanceMap").set(values)


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
    Time.setCurrent(solver_node.getPlug("startFrame").get())
    mlib.select(_connected_node(solver_node, "outputMeshObject"), replace=True)
    mel.eval("ArtPaintAttrTool;")
    context = cmds.currentCtx()
    cmds.artAttrCtx(context, edit=True, paintattrselected=f"simpleClothSolver.{solver_node.getName()}.maxDistanceMap",
                    minvalue=0, maxvalue=1, clamp="both", clamplower=0, clampupper=1,
                    colorrangelower=0, colorrangeupper=1, value=0, colorfeedback=True)
    return context


def reset(solverNode):
    """キャッシュを無効化して開始フレームへ戻す。"""
    solver_node = _solver(solverNode)
    serial = solver_node.getPlug("resetSerial")
    with _transaction("Simple Cloth: Reset"):
        serial.set(serial.get() + 1)
    Time.setCurrent(solver_node.getPlug("startFrame").get())


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
        matches = mlib.ls(attachTo, long=True, type="transform")
        if len(matches) != 1:
            raise ValueError("追従先Transformを1個指定してください")
        attachTo = matches[0]
        output = _connected_node(solver_node, "outputMeshObject").getFullName()
        attach_path = attachTo.getFullName()
        if attach_path == output or attach_path.startswith(output + "|"):
            raise ValueError("出力メッシュへの追従は循環するため使用できません")
    kinds = json.loads(solver_node.getPlug("colliderTypes").get())
    with _transaction("Simple Cloth: Add Collider"):
        guide = mlib.createNode("transform", name="sc_" + kind, **({"parent": attachTo} if attachTo else {}))
        for attr, default in (("clothRadius", radius), ("clothHeight", height)):
            guide.addAttr(attr, attributeType="double", defaultValue=default, minValue=0, keyable=True)
        kind_plug = guide.addAttr("clothKind", attributeType="long")
        kind_index = ("sphere", "capsule", "plane").index(kind)
        kind_plug.set(kind_index)
        kind_plug.setLocked(True)
        helpers = []
        # 元の版の polySphere などと同じく、大きさはシーン表示単位の値として作る(下で表示単位の倍率を打ち消す)。
        if kind == "sphere":
            shape = mlib.createPolySphere(radius=units.distanceFromUi(radius), subdivisions=(20, 12), constructionHistory=True)
            history = shape.getHistory(type="polySphere")[0]
            history.getPlug("radius").connect(guide.getPlug("clothRadius"))
        elif kind == "capsule":
            shape = mlib.createPolyCylinder(radius=units.distanceFromUi(radius), height=units.distanceFromUi(height + 2 * radius),
                                            subdivisions=(20, 1, 6), roundCap=True, constructionHistory=True)
            history = shape.getHistory(type="polyCylinder")[0]
            multiply = mlib.createNode("multDoubleLinear")
            add = mlib.createNode("addDoubleLinear")
            multiply.getPlug("input1").connect(guide.getPlug("clothRadius"))
            multiply.getPlug("input2").set(2)
            add.getPlug("input1").connect(multiply.getPlug("output"))
            add.getPlug("input2").connect(guide.getPlug("clothHeight"))
            history.getPlug("height").connect(add.getPlug("output"))
            history.getPlug("radius").connect(guide.getPlug("clothRadius"))
            helpers.extend([multiply, add])
        else:
            shape = mlib.createPolyPlane(width=units.distanceFromUi(20), height=units.distanceFromUi(20), subdivisions=(1, 1),
                                         constructionHistory=True)
            history = shape.getHistory(type="polyPlane")[0]
        mesh = shape.getTransform()
        # 元の版の polySphere などと同じく、作った形状を選んだ状態にする。
        mlib.select(mesh)
        mesh.setParent(guide, relative=True)
        # ガイドの形状は計算単位cm。シーン表示単位によるpolyプリミティブ倍率を打ち消す。
        unit_scale = units.distanceToUi(1.0)
        mesh.getPlug("scale").set((unit_scale, unit_scale, unit_scale))
        guide.setOverrideColor((0.2, 0.65, 1.0))
        guide.setShadingOverride(True)
        _own(guide, [*helpers, history])
        _own(solver_node, [guide, *helpers, history])
        for source, target in COLLIDER_PLUGS:
            solver_node.getPlug(f"{target}[{len(kinds)}]").connect(guide.getPlug(source))
        solver_node.getPlug("colliderTypes").set(json.dumps([*kinds, kind_index]))
    return guide.getName()


def _collider_nodes(solver_node):
    """コライダーのノードを接続インデックス順に返す。"""
    return list(solver_node.getPlug("colliderObjects").getSourceNodes().values())


def getColliders(solverNode):
    """コライダーを接続インデックス順に返す。"""
    return [collider.getName() for collider in _collider_nodes(_solver(solverNode))]


def removeCollider(solverNode, collider):
    """専用コライダーとその表示用ノードを削除して接続番号を詰める。"""
    solver_node = _solver(solverNode)
    colliders = _collider_nodes(solver_node)
    names = [item.getName() for item in colliders]
    if collider not in names:
        raise ValueError("このSolverに属するコライダーを指定してください")
    with _transaction("Simple Cloth: Remove Collider"):
        removed = colliders.pop(names.index(collider))
        for attribute in ("colliderMatrix", "colliderRadius", "colliderHeight", "colliderObjects"):
            plug = solver_node.getPlug(attribute)
            for index in plug.getIndices():
                plug.removeElement(index, breakConnections=True)
        for index, remaining in enumerate(colliders):
            for source, target in COLLIDER_PLUGS:
                solver_node.getPlug(f"{target}[{index}]").connect(remaining.getPlug(source))
        kinds = [remaining.getPlug("clothKind").get() for remaining in colliders]
        solver_node.getPlug("colliderTypes").set(json.dumps(kinds))
        owned = removed.getPlug("ownedObjects").getConnections(destination=False, asNode=True)
        mlib.delete([*owned, removed])


def remove(solverNode):
    """セットアップ所有物だけを削除する。入力とベイク済みメッシュは保持する。"""
    solver_node = _solver(solverNode)
    owned = solver_node.getPlug("ownedObjects").getConnections(destination=False, asNode=True)
    with _transaction("Simple Cloth: Remove"):
        mlib.delete([*owned, solver_node])


def savePreset(solverNode, path):
    """係数と全頂点マップをUTF-8 JSONへ保存する。接続やアニメーションは含めない。"""
    solver_node = _solver(solverNode)
    reference = json.loads(solver_node.getPlug("referenceData").get())
    settings = {name: solver_node.getPlug(name).get() for name in SETTINGS}
    for name in ("gravity", "wind"):
        settings[name] = list(settings[name])
    payload = {"format": "SimpleClothPreset", "version": 1, "settings": settings,
               "counts": reference["counts"], "vertices": reference["vertices"], "map": getMap(solver_node)}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def loadPreset(solverNode, path):
    """トポロジー・係数・マップを全件検証してからUndo可能に復元する。"""
    solver_node = _solver(solverNode)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format") != "SimpleClothPreset" or payload.get("version") != 1:
        raise ValueError("Simple Cloth Preset version 1を指定してください")
    reference = json.loads(solver_node.getPlug("referenceData").get())
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
            solver_node.getPlug(name).set(tuple(value) if name in ("gravity", "wind") else value)
        solver_node.getPlug("maxDistanceMap").set(values)


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
    output = _connected_node(solver_node, "outputMeshObject")
    time = Time.getCurrent()
    selection = mlib.ls(selection=True, long=True)

    def duplicate_output(name):
        """複製時にMayaが増やす所有メッセージを外し、独立メッシュを返す。"""
        duplicate = mlib.duplicate(output, name=name, returnRootsOnly=True)
        message = duplicate.getPlug("message")
        for destination in message.getConnections(outputs=True):
            if destination.getNode() == solver_node:
                destination.disconnect(message)
        duplicate.deleteHistory(keepDeformers=False)
        return duplicate

    try:
        with _transaction("Simple Cloth: Bake"):
            Time.setCurrent(start)
            baked = duplicate_output(solver_node.getName() + "_baked")
            # 元の版の cmds.blendShape と同じく、変形の最後に置く(frontOfChain=False)。
            blend = mlib.createBlendShape(baked, name=solver_node.getName() + "_cache", frontOfChain=False, origin="world")
            for index, frame in enumerate(range(start, end + 1)):
                Time.setCurrent(frame)
                snapshot = duplicate_output(solver_node.getName() + "_snapshot")
                weight = blend.addTarget(snapshot, base=baked, index=index, fullWeight=1.0)
                snapshot.delete()
                keys = [(frame, 1)]
                if frame > start:
                    keys.insert(0, (frame - 1, 0))
                if frame < end:
                    keys.append((frame + 1, 0))
                for key_time, value in keys:
                    weight.setKey(time=key_time, value=value, inTangentType="linear", outTangentType="linear")
    finally:
        Time.setCurrent(time)
        mlib.select(selection, replace=True) if selection else mlib.select(clear=True)
    return baked.getName()
