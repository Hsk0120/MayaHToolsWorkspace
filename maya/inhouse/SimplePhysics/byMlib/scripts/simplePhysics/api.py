"""Simple Physicsのセットアップ・プリセット・ベイク操作。

シーン変更はmlibを使用する。出力階層は入力階層から分離し、元のキーを保持する。
"""

from contextlib import contextmanager
import json
import math
from pathlib import Path
import uuid

from maya import cmds

import mlib
from mlib.common import Plugin, Time, units

from .node import DEFAULTS, INTEGERS, SimplePhysicsNode
from .solver import PARAMETERS, position


_ROOT = Path(__file__).resolve().parents[2]
# byMlib/ の下に置いた版でも、元のフォルダーのプラグインをロードする。
if _ROOT.name == "byMlib":
    _ROOT = _ROOT.parent
PLUGIN = _ROOT / "plug-ins" / "simplePhysicsNode.py"
SETTING_NAMES = tuple(DEFAULTS) + tuple(name for name in INTEGERS if name != "resetSerial") + ("planarConstraint",)
COLLIDER_PLUGS = (("worldMatrix[0]", "colliderMatrix"), ("physicsRadius", "colliderRadius"),
                  ("physicsHeight", "colliderHeight"), ("message", "colliderObjects"))


@contextmanager
def _transaction(name):
    """1回のUndoにまとめ、失敗時はこの操作だけを取り消す。"""
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError("Simple PhysicsのセットアップにはUndoを有効にしてください")
    chunk_name = name + " " + uuid.uuid4().hex[:8]
    cmds.undoInfo(openChunk=True, chunkName=chunk_name)
    try:
        yield
    except Exception:
        cmds.undoInfo(closeChunk=True)
        # 最初の編集前に失敗した場合、直前のユーザー操作をUndoしない。
        if cmds.undoInfo(query=True, undoName=True) == chunk_name:
            cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)


def loadPlugin():
    """必要時だけ計算プラグインをロードする。セキュリティ設定は変更しない。"""
    plugin = Plugin(str(PLUGIN))
    if not plugin.isLoaded():
        plugin.load(quiet=True)


def _joint(name):
    """一意なジョイントを、mlibのJointで返す。"""
    matches = mlib.ls(name, long=True, type="joint")
    if len(matches) != 1:
        raise ValueError(f"ジョイントを一意に指定してください: {name}")
    return matches[0]


def _solver_node(node):
    """有効なSimple Physicsノードを検証して、mlibのノードで返す。"""
    if not mlib.objExists(node):
        raise ValueError("Simple PhysicsのSolverを指定してください")
    solver_node = mlib.getNode(node)
    if solver_node.getType() != SimplePhysicsNode.TYPE_NAME:
        raise ValueError("Simple PhysicsのSolverを指定してください")
    return solver_node


def _solver(node):
    """有効なSimple Physicsノード名を検証して返す。"""
    _solver_node(node)
    return node


def _message_array(node, name):
    """シーン内参照の保持用メッセージ配列を作る。"""
    node.addAttr(name, attributeType="message", multi=True, indexMatters=False)


def _connected_nodes(node, attribute):
    """メッセージ配列の接続元のノードを論理番号順に返す。"""
    return list(node.getPlug(attribute).getSourceNodes().values())


def connections(node, attribute):
    """メッセージ配列の接続先を論理番号順に返す。"""
    return [item.getName() for item in _connected_nodes(mlib.getNode(node), attribute)]


def create(roots, excluded=(), dummyLength=0.0, forwardAxis="X", name="simplePhysics"):
    """選択した根元から入力接続と独立した出力ジョイント階層を作る。

    Args:
        roots: ルートジョイント名の列。
        excluded: 除外するジョイント名。子孫も除外する。
        dummyLength: 末端の仮想ボーン長。cm、0で無効。
        forwardAxis: 仮想ボーン方向。X/Y/Z/-X/-Y/-Z。
        name: セットアップの名前。

    Returns:
        str: 設定を保持する計算ノード名。
    """
    if isinstance(roots, str) or not roots:
        raise ValueError("rootsには1個以上のジョイント名の列を指定してください")
    if not math.isfinite(dummyLength) or dummyLength < 0:
        raise ValueError("Dummy Bone Lengthは0以上の有限値です")
    if forwardAxis not in ("X", "Y", "Z", "-X", "-Y", "-Z"):
        raise ValueError("Forward Axisが不正です")
    roots = [_joint(value) for value in roots]
    root_paths = [root.getFullName() for root in roots]
    excluded = {_joint(value).getFullName() for value in excluded}
    if len(set(root_paths)) != len(root_paths) or any(a.startswith(b + "|") for a in root_paths for b in root_paths if a != b):
        raise ValueError("Root Bonesには重複・親子を含めないでください")
    if excluded.intersection(root_paths):
        raise ValueError("ルート自体は除外できません")
    bones = []
    sources = []
    axis = forwardAxis[-1]
    offset = [0.0, 0.0, 0.0]
    offset["XYZ".index(axis)] = dummyLength * (-1 if forwardAxis.startswith("-") else 1)

    def collect(joint, parent, distance, root_index):
        """Mayaの親子順を保ち、骨長に沿うカーブ座標の基礎を作る。"""
        index = len(bones)
        world = joint.getMatrix(ws=True)
        if abs(world.det4x4()) < 1.0e-9:
            raise ValueError(f"ゼロスケールのジョイントは使用できません: {joint.getFullName()}")
        if parent >= 0:
            parent_world = sources[parent].getMatrix(ws=True)
            length = (position(world) - position(parent_world)).length()
            if length <= 1.0e-7:
                raise ValueError(f"長さ0のボーンは除外してください: {joint.getFullName()}")
            distance += length
        bones.append({"parent": parent, "distance": distance, "root": root_index, "rate": 0.0})
        sources.append(joint)
        children = joint.getChildren(type="joint")
        active = [child for child in children if child.getFullName() not in excluded]
        for child in active:
            collect(child, index, distance, root_index)
        if not active and dummyLength > 0:
            bones.append({"parent": index, "distance": distance + dummyLength, "root": root_index,
                          "rate": 0.0, "dummyOffset": offset})
            sources.append(None)

    for root_index, root in enumerate(roots):
        collect(root, -1, 0.0, root_index)
    if all(bone["parent"] < 0 for bone in bones):
        raise ValueError("子ジョイントまたはDummy Bone Lengthが必要です")
    maximum = {index: max(bone["distance"] for bone in bones if bone["root"] == index) for index in range(len(roots))}
    for bone in bones:
        bone["rate"] = bone["distance"] / max(maximum[bone["root"]], 1.0e-7)
    loadPlugin()
    with _transaction("Simple Physics: Create"):
        node = mlib.createNode(SimplePhysicsNode.TYPE_NAME, name=name + "_solver")
        node.getPlug("topology").set(json.dumps(bones))
        node.addAttr("setupInfo", dataType="string").set(json.dumps({"dummyLength": dummyLength, "forwardAxis": forwardAxis,
                                                                     "excluded": sorted(excluded)}))
        for attribute in ("sourceBones", "outputBones", "colliderObjects", "ownedObjects"):
            _message_array(node, attribute)
        mlib.getPlug("time1.outTime").connectTo(node.getPlug("time"))
        node.getPlug("startFrame").set(Time.getPlaybackRange()[0])
        for attribute in PARAMETERS:
            for index, coordinate in enumerate((0.0, 1.0)):
                base = f"{attribute}Curve[{index}].{attribute}Curve_"
                node.getPlug(base + "Position").set(coordinate)
                node.getPlug(base + "FloatValue").set(1.0)
                node.getPlug(base + "Interp").set(1)
        group = mlib.createNode("transform", name=name + "_output")
        group.getPlug("inheritsTransform").set(False)
        group.setAttrFlags(["translate", "rotate", "scale", "shear"], locked=True)
        node.getPlug("ownedObjects[0]").connect(group.getPlug("message"))
        outputs = []
        for index, (bone, source) in enumerate(zip(bones, sources)):
            if source:
                node.getPlug(f"inputMatrix[{index}]").connect(source.getPlug("worldMatrix[0]"))
                node.getPlug(f"sourceBones[{index}]").connect(source.getPlug("message"))
            parent = group if bone["parent"] < 0 else outputs[bone["parent"]]
            leaf = source.getFullName().rsplit("|", 1)[-1].replace(":", "_") if source else "dummy"
            joint = mlib.createNode("joint", name=leaf + "_SP", parent=parent)
            joint.getPlug("segmentScaleCompensate").set(False)
            joint.getPlug("radius").set(0.5)
            joint.setOverrideColor(14)
            joint.getPlug("offsetParentMatrix").connect(node.getPlug(f"outputMatrix[{index}]"))
            joint.setAttrFlags(["translate", "rotate", "scale", "shear", "jointOrient", "rotateAxis"], locked=True)
            node.getPlug(f"outputBones[{index}]").connect(joint.getPlug("message"))
            outputs.append(joint)
        mlib.select(node)
    return node.getName()


def addCollider(node, kind="sphere", attachTo=None, radius=5.0, height=10.0):
    """ビューポートで移動・回転できるコライダーを作る。寸法はcm。

    Returns:
        str: Radius/Heightを編集できるガイドのトランスフォーム。
    """
    solver_node = _solver_node(node)
    if kind not in ("sphere", "capsule", "plane"):
        raise ValueError("sphere/capsule/planeから選んでください")
    if not all(math.isfinite(value) and value >= 0 for value in (radius, height)):
        raise ValueError("コライダー寸法は0以上の有限値です")
    if attachTo:
        matches = mlib.ls(attachTo, long=True, type="transform")
        if len(matches) != 1:
            raise ValueError("追従先を一意に指定してください")
        attachTo = matches[0]
        attach_path = attachTo.getFullName()
        outputs = [item.getFullName() for item in _connected_nodes(solver_node, "outputBones")]
        if any(attach_path == output or attach_path.startswith(output + "|") for output in outputs):
            raise ValueError("循環を避けるため、出力ジョイントへコライダーを追従させることはできません")
    types = json.loads(solver_node.getPlug("colliderTypes").get())
    with _transaction("Simple Physics: Add Collider"):
        collider = mlib.createNode("transform", name="sp_" + kind, parent=attachTo) if attachTo else mlib.createNode("transform", name="sp_" + kind)
        for attribute, default in (("physicsRadius", radius), ("physicsHeight", height)):
            collider.addAttr(attribute, attributeType="double", defaultValue=default, minValue=0, keyable=True)
        shape_plug = collider.addAttr("physicsShape", attributeType="enum", enumName="Sphere:Capsule:Plane")
        shape_type = ("sphere", "capsule", "plane").index(kind)
        shape_plug.set(shape_type)
        shape_plug.setLocked(True)
        # 元の版の polySphere などと同じく、大きさはシーン表示単位の値として作る。
        if kind == "sphere":
            shape = mlib.createPolySphere(radius=units.distanceFromUi(radius), subdivisions=(16, 8), constructionHistory=True)
            history = shape.getHistory(type="polySphere")[0]
            history.getPlug("radius").connect(collider.getPlug("physicsRadius"))
        elif kind == "capsule":
            shape = mlib.createPolyCylinder(radius=units.distanceFromUi(radius), height=units.distanceFromUi(height + 2 * radius),
                                            subdivisions=(16, 1, 4), roundCap=True, constructionHistory=True)
            history = shape.getHistory(type="polyCylinder")[0]
            history.getPlug("radius").connect(collider.getPlug("physicsRadius"))
            multiply = mlib.createNode("multDoubleLinear", name="sp_capsuleDiameter")
            add = mlib.createNode("addDoubleLinear", name="sp_capsuleHeight")
            multiply.getPlug("input1").connect(collider.getPlug("physicsRadius"))
            multiply.getPlug("input2").set(2)
            add.getPlug("input1").connect(multiply.getPlug("output"))
            add.getPlug("input2").connect(collider.getPlug("physicsHeight"))
            history.getPlug("height").connect(add.getPlug("output"))
            owned = solver_node.getPlug("ownedObjects")
            for utility in (multiply, add):
                owned.connect(utility.getPlug("message"), nextAvailable=True)
        else:
            shape = mlib.createPolyPlane(width=units.distanceFromUi(20), height=units.distanceFromUi(20), subdivisions=(1, 1),
                                         constructionHistory=True)
            history = shape.getHistory(type="polyPlane")[0]
        mesh = shape.getTransform()
        # 元の版の polySphere などと同じく、作った形状を選んだ状態にする。
        mlib.select(mesh)
        mesh.setParent(collider, relative=True)
        mesh.setOverrideColor(18)
        mesh.setShadingOverride(True)
        mesh.setAttrFlags(["translate", "rotate", "scale"], locked=True)
        index = len(types)
        for source, target in COLLIDER_PLUGS:
            solver_node.getPlug(f"{target}[{index}]").connect(collider.getPlug(source))
        solver_node.getPlug("colliderTypes").set(json.dumps([*types, shape_type]))
        mlib.select(collider)
    return collider.getName()


def addConstraint(node, first, second, compliance=0.0001):
    """2本の出力ボーンを現在の距離で結ぶXPBD拘束を追加する。"""
    solver_node = _solver_node(node)
    if not math.isfinite(compliance) or compliance < 0:
        raise ValueError("Complianceは0以上の有限値です")
    outputs = [item.getFullName() for item in _connected_nodes(solver_node, "outputBones")]
    first, second = _joint(first), _joint(second)
    first_path, second_path = first.getFullName(), second.getFullName()
    if first_path not in outputs or second_path not in outputs or first_path == second_path:
        raise ValueError("同じSolverの異なる出力ジョイントを2本指定してください")
    a, b = outputs.index(first_path), outputs.index(second_path)
    length = (position(first.getMatrix(ws=True)) - position(second.getMatrix(ws=True))).length()
    if length < 1.0e-7:
        raise ValueError("同じ位置のジョイントには距離拘束を追加できません")
    plug = solver_node.getPlug("boneConstraints")
    constraints = json.loads(plug.get())
    if any({pair[0], pair[1]} == {a, b} for pair in constraints):
        raise ValueError("この組の距離拘束は登録済みです")
    with _transaction("Simple Physics: Add Constraint"):
        plug.set(json.dumps([*constraints, [a, b, length, compliance]]))


def removeCollider(node, collider):
    """指定コライダーを取り除き、論理番号を詰めて接続し直す。"""
    solver_node = _solver_node(node)
    colliders = _connected_nodes(solver_node, "colliderObjects")
    names = [item.getName() for item in colliders]
    if collider not in names:
        raise ValueError("このSolverのコライダーを選択してください")
    with _transaction("Simple Physics: Remove Collider"):
        removed = colliders.pop(names.index(collider))
        for attribute in ("colliderMatrix", "colliderRadius", "colliderHeight", "colliderObjects"):
            plug = solver_node.getPlug(attribute)
            for index in plug.getIndices():
                plug.removeElement(index, breakConnections=True)
        types = []
        for index, remaining in enumerate(colliders):
            types.append(remaining.getPlug("physicsShape").get())
            for source, target in COLLIDER_PLUGS:
                solver_node.getPlug(f"{target}[{index}]").connect(remaining.getPlug(source))
        solver_node.getPlug("colliderTypes").set(json.dumps(types))
        removed.delete()


def savePreset(node, path):
    """係数・カーブをUTF-8 JSONへ保存する。シーン固有の接続は保存しない。"""
    solver_node = _solver_node(node)
    payload = {"format": "SimplePhysicsPreset", "version": 1, "settings": {}, "curves": {}}
    for name in SETTING_NAMES:
        payload["settings"][name] = solver_node.getPlug(name).get()
    for name in ("gravity", "wind"):
        payload["settings"][name] = solver_node.getPlug(name).get()
    for name in PARAMETERS:
        curve = name + "Curve"
        payload["curves"][name] = [
            [solver_node.getPlug(f"{curve}[{index}].{curve}_{suffix}").get() for suffix in ("Position", "FloatValue", "Interp")]
            for index in solver_node.getPlug(curve).getIndices()]
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def loadPreset(node, path):
    """既存Solverへ係数プリセットを適用する。読み取り値を先に検証する。"""
    solver_node = _solver_node(node)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("プリセットはJSONオブジェクトで指定してください")
    if payload.get("format") != "SimplePhysicsPreset" or payload.get("version") != 1:
        raise ValueError("未対応のプリセットです")
    settings = payload.get("settings", {})
    curves = payload.get("curves", {})
    if not isinstance(settings, dict) or not isinstance(curves, dict):
        raise TypeError("settings/curvesはJSONオブジェクトで指定してください")
    if set(settings) != set(SETTING_NAMES) | {"gravity", "wind"} or set(curves) != set(PARAMETERS):
        raise ValueError("プリセットの項目が不足しているか、未対応の項目があります")
    for name, value in settings.items():
        values = value if name in ("gravity", "wind") else [value]
        if not isinstance(values, (list, tuple)) or (name in ("gravity", "wind") and len(values) != 3):
            raise ValueError(f"値の形式が不正です: {name}")
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in values):
            raise ValueError(f"有限数値を指定してください: {name}")
        if name in INTEGERS or name == "planarConstraint":
            if not isinstance(value, int):
                raise TypeError(f"整数を指定してください: {name}")
        if name not in ("gravity", "wind"):
            plug = solver_node.getPlug(name)
            minimum, maximum = plug.getRange()
            if (minimum is not None and value < minimum) or (maximum is not None and value > maximum) or (name == "planarConstraint" and value not in range(4)):
                raise ValueError(f"設定範囲外です: {name}")
    for name, entries in curves.items():
        if not isinstance(entries, list) or not entries or len(entries) > 256:
            raise ValueError(f"カーブの要素数が不正です: {name}")
        for entry in entries:
            if not isinstance(entry, list) or len(entry) != 3 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in entry):
                raise ValueError(f"カーブ値が不正です: {name}")
            if not 0 <= entry[0] <= 1 or entry[1] < 0 or entry[2] not in (0, 1, 2, 3):
                raise ValueError(f"カーブの範囲が不正です: {name}")
    with _transaction("Simple Physics: Load Preset"):
        for name, value in settings.items():
            solver_node.getPlug(name).set(tuple(value) if name in ("gravity", "wind") else value)
        for name, entries in curves.items():
            curve = name + "Curve"
            curve_plug = solver_node.getPlug(curve)
            for index in curve_plug.getIndices():
                curve_plug.removeElement(index, breakConnections=True)
            for index, entry in enumerate(entries):
                for suffix, value in zip(("Position", "FloatValue", "Interp"), entry):
                    solver_node.getPlug(f"{curve}[{index}].{curve}_{suffix}").set(value)


def bake(node, start, end):
    """出力を独立したキー付き階層へベイクし、プラグイン依存を取り除く。

    Args:
        node: Solver名。
        start: 開始フレーム（整数）。
        end: 終了フレーム（整数、開始以上）。

    Returns:
        str: ベイク結果のグループ名。
    """
    solver_node = _solver_node(node)
    if not isinstance(start, int) or not isinstance(end, int) or end < start:
        raise ValueError("開始・終了フレームは昇順の整数で指定してください")
    topology = json.loads(solver_node.getPlug("topology").get())
    outputs = _connected_nodes(solver_node, "outputBones")
    if len(outputs) != len(topology):
        raise ValueError("出力ジョイントが欠けています。セットアップを作り直してください")
    current = Time.getCurrent()
    try:
        with _transaction("Simple Physics: Bake"):
            group = mlib.createNode("transform", name="simplePhysics_baked")
            baked = []
            for index, bone in enumerate(topology):
                parent = group if bone["parent"] < 0 else baked[bone["parent"]]
                joint = mlib.createNode("joint", name=outputs[index].getName().rsplit("|", 1)[-1] + "_baked", parent=parent)
                joint.getPlug("segmentScaleCompensate").set(False)
                baked.append(joint)
            for frame in range(start, end + 1):
                Time.setCurrent(frame)
                for output, target in zip(outputs, baked):
                    target.setMatrix(output.getMatrix(ws=True), ws=True)
                    target.setKey(["translate", "rotate", "scale"], time=frame)
            for target in baked:
                target.eulerFilter()
            mlib.select(group)
    finally:
        Time.setCurrent(current)
    return group.getName()


def remove(node):
    """このセットアップが所有する出力・コライダー・補助ノードだけを削除する。"""
    solver_node = _solver_node(node)
    owned = _connected_nodes(solver_node, "ownedObjects") + _connected_nodes(solver_node, "colliderObjects")
    with _transaction("Simple Physics: Remove"):
        mlib.delete([*(item for item in owned if item.isValid()), solver_node])
