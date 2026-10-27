"""Simple Physicsのセットアップ・プリセット・ベイク操作。

シーン変更はmaya.cmdsを使用する。出力階層は入力階層から分離し、元のキーを保持する。
"""

from contextlib import contextmanager
import json
import math
from pathlib import Path
import uuid

from maya import cmds
from maya.api import OpenMaya as om

from .node import DEFAULTS, INTEGERS, SimplePhysicsNode
from .solver import PARAMETERS, position


PLUGIN = Path(__file__).resolve().parents[2] / "plug-ins" / "simplePhysicsNode.py"
SETTING_NAMES = tuple(DEFAULTS) + tuple(name for name in INTEGERS if name != "resetSerial") + ("planarConstraint",)


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
    if not cmds.pluginInfo(str(PLUGIN), query=True, loaded=True):
        cmds.loadPlugin(str(PLUGIN), quiet=True)


def _joint(name):
    """一意なジョイントのフルパスを返す。"""
    matches = cmds.ls(name, long=True, type="joint") or []
    if len(matches) != 1:
        raise ValueError(f"ジョイントを一意に指定してください: {name}")
    return matches[0]


def _solver(node):
    """有効なSimple Physicsノード名を検証して返す。"""
    if not cmds.objExists(node) or cmds.nodeType(node) != SimplePhysicsNode.TYPE_NAME:
        raise ValueError("Simple PhysicsのSolverを指定してください")
    return node


def _message_array(node, name):
    """シーン内参照の保持用メッセージ配列を作る。"""
    cmds.addAttr(node, longName=name, attributeType="message", multi=True, indexMatters=False)


def connections(node, attribute):
    """メッセージ配列の接続先を論理番号順に返す。"""
    result = []
    for index in cmds.getAttr(f"{node}.{attribute}", multiIndices=True) or []:
        linked = cmds.listConnections(f"{node}.{attribute}[{index}]", source=True, destination=False) or []
        if linked:
            result.append(linked[0])
    return result


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
    excluded = {_joint(value) for value in excluded}
    if len(set(roots)) != len(roots) or any(a.startswith(b + "|") for a in roots for b in roots if a != b):
        raise ValueError("Root Bonesには重複・親子を含めないでください")
    if excluded.intersection(roots):
        raise ValueError("ルート自体は除外できません")
    bones = []
    sources = []
    axis = forwardAxis[-1]
    offset = [0.0, 0.0, 0.0]
    offset["XYZ".index(axis)] = dummyLength * (-1 if forwardAxis.startswith("-") else 1)

    def collect(joint, parent, distance, root_index):
        """Mayaの親子順を保ち、骨長に沿うカーブ座標の基礎を作る。"""
        index = len(bones)
        world = om.MMatrix(cmds.getAttr(joint + ".worldMatrix[0]"))
        if abs(world.det4x4()) < 1.0e-9:
            raise ValueError(f"ゼロスケールのジョイントは使用できません: {joint}")
        if parent >= 0:
            parent_world = om.MMatrix(cmds.getAttr(sources[parent] + ".worldMatrix[0]"))
            length = (position(world) - position(parent_world)).length()
            if length <= 1.0e-7:
                raise ValueError(f"長さ0のボーンは除外してください: {joint}")
            distance += length
        bones.append({"parent": parent, "distance": distance, "root": root_index, "rate": 0.0})
        sources.append(joint)
        children = cmds.listRelatives(joint, children=True, fullPath=True, type="joint") or []
        active = [child for child in children if child not in excluded]
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
        node = cmds.createNode(SimplePhysicsNode.TYPE_NAME, name=name + "_solver")
        cmds.setAttr(node + ".topology", json.dumps(bones), type="string")
        cmds.addAttr(node, longName="setupInfo", dataType="string")
        cmds.setAttr(node + ".setupInfo", json.dumps({"dummyLength": dummyLength, "forwardAxis": forwardAxis,
                                                     "excluded": sorted(excluded)}), type="string")
        for attribute in ("sourceBones", "outputBones", "colliderObjects", "ownedObjects"):
            _message_array(node, attribute)
        cmds.connectAttr("time1.outTime", node + ".time")
        cmds.setAttr(node + ".startFrame", cmds.playbackOptions(query=True, minTime=True))
        for attribute in PARAMETERS:
            for index, coordinate in enumerate((0.0, 1.0)):
                base = f"{node}.{attribute}Curve[{index}].{attribute}Curve_"
                cmds.setAttr(base + "Position", coordinate)
                cmds.setAttr(base + "FloatValue", 1.0)
                cmds.setAttr(base + "Interp", 1)
        group = cmds.createNode("transform", name=name + "_output")
        cmds.setAttr(group + ".inheritsTransform", False)
        for attribute in ("translate", "rotate", "scale", "shear"):
            cmds.setAttr(group + "." + attribute, lock=True)
        cmds.connectAttr(group + ".message", node + ".ownedObjects[0]")
        outputs = []
        for index, (bone, source) in enumerate(zip(bones, sources)):
            if source:
                cmds.connectAttr(source + ".worldMatrix[0]", f"{node}.inputMatrix[{index}]")
                cmds.connectAttr(source + ".message", f"{node}.sourceBones[{index}]")
            parent = group if bone["parent"] < 0 else outputs[bone["parent"]]
            leaf = source.rsplit("|", 1)[-1].replace(":", "_") if source else "dummy"
            joint = cmds.createNode("joint", name=leaf + "_SP", parent=parent)
            joint = cmds.ls(joint, long=True)[0]
            cmds.setAttr(joint + ".segmentScaleCompensate", False)
            cmds.setAttr(joint + ".radius", 0.5)
            cmds.setAttr(joint + ".overrideEnabled", True)
            cmds.setAttr(joint + ".overrideColor", 14)
            cmds.connectAttr(f"{node}.outputMatrix[{index}]", joint + ".offsetParentMatrix")
            for attribute in ("translate", "rotate", "scale", "shear", "jointOrient", "rotateAxis"):
                cmds.setAttr(joint + "." + attribute, lock=True)
            cmds.connectAttr(joint + ".message", f"{node}.outputBones[{index}]")
            outputs.append(joint)
        cmds.select(node)
    return node


def addCollider(node, kind="sphere", attachTo=None, radius=5.0, height=10.0):
    """ビューポートで移動・回転できるコライダーを作る。寸法はcm。

    Returns:
        str: Radius/Heightを編集できるガイドのトランスフォーム。
    """
    _solver(node)
    if kind not in ("sphere", "capsule", "plane"):
        raise ValueError("sphere/capsule/planeから選んでください")
    if not all(math.isfinite(value) and value >= 0 for value in (radius, height)):
        raise ValueError("コライダー寸法は0以上の有限値です")
    if attachTo:
        matches = cmds.ls(attachTo, long=True, type="transform") or []
        if len(matches) != 1:
            raise ValueError("追従先を一意に指定してください")
        attachTo = matches[0]
        outputs = cmds.ls(connections(node, "outputBones"), long=True) or []
        if any(attachTo == output or attachTo.startswith(output + "|") for output in outputs):
            raise ValueError("循環を避けるため、出力ジョイントへコライダーを追従させることはできません")
    types = json.loads(cmds.getAttr(node + ".colliderTypes"))
    with _transaction("Simple Physics: Add Collider"):
        collider = cmds.createNode("transform", name="sp_" + kind, parent=attachTo) if attachTo else cmds.createNode("transform", name="sp_" + kind)
        for attribute, default in (("physicsRadius", radius), ("physicsHeight", height)):
            cmds.addAttr(collider, longName=attribute, attributeType="double", defaultValue=default, minValue=0, keyable=True)
        cmds.addAttr(collider, longName="physicsShape", attributeType="enum", enumName="Sphere:Capsule:Plane")
        shape_type = ("sphere", "capsule", "plane").index(kind)
        cmds.setAttr(collider + ".physicsShape", shape_type, lock=True)
        if kind == "sphere":
            mesh, history = cmds.polySphere(radius=radius, subdivisionsX=16, subdivisionsY=8)
            cmds.connectAttr(collider + ".physicsRadius", history + ".radius")
        elif kind == "capsule":
            mesh, history = cmds.polyCylinder(radius=radius, height=height + 2 * radius, roundCap=True, subdivisionsX=16, subdivisionsCaps=4)
            cmds.connectAttr(collider + ".physicsRadius", history + ".radius")
            multiply = cmds.createNode("multDoubleLinear", name="sp_capsuleDiameter")
            add = cmds.createNode("addDoubleLinear", name="sp_capsuleHeight")
            cmds.connectAttr(collider + ".physicsRadius", multiply + ".input1")
            cmds.setAttr(multiply + ".input2", 2)
            cmds.connectAttr(multiply + ".output", add + ".input1")
            cmds.connectAttr(collider + ".physicsHeight", add + ".input2")
            cmds.connectAttr(add + ".output", history + ".height")
            for utility in (multiply, add):
                cmds.connectAttr(utility + ".message", node + ".ownedObjects", nextAvailable=True)
        else:
            mesh, history = cmds.polyPlane(width=20, height=20, subdivisionsX=1, subdivisionsY=1)
        mesh = cmds.parent(mesh, collider, relative=True)[0]
        cmds.setAttr(mesh + ".overrideEnabled", True)
        cmds.setAttr(mesh + ".overrideShading", False)
        cmds.setAttr(mesh + ".overrideColor", 18)
        for attribute in ("translate", "rotate", "scale"):
            cmds.setAttr(mesh + "." + attribute, lock=True)
        index = len(types)
        cmds.connectAttr(collider + ".worldMatrix[0]", f"{node}.colliderMatrix[{index}]")
        cmds.connectAttr(collider + ".physicsRadius", f"{node}.colliderRadius[{index}]")
        cmds.connectAttr(collider + ".physicsHeight", f"{node}.colliderHeight[{index}]")
        cmds.connectAttr(collider + ".message", f"{node}.colliderObjects[{index}]")
        cmds.setAttr(node + ".colliderTypes", json.dumps(types + [shape_type]), type="string")
        cmds.select(collider)
    return collider


def addConstraint(node, first, second, compliance=0.0001):
    """2本の出力ボーンを現在の距離で結ぶXPBD拘束を追加する。"""
    _solver(node)
    if not math.isfinite(compliance) or compliance < 0:
        raise ValueError("Complianceは0以上の有限値です")
    outputs = cmds.ls(connections(node, "outputBones"), long=True) or []
    first, second = _joint(first), _joint(second)
    if first not in outputs or second not in outputs or first == second:
        raise ValueError("同じSolverの異なる出力ジョイントを2本指定してください")
    a, b = outputs.index(first), outputs.index(second)
    length = (position(om.MMatrix(cmds.getAttr(first + ".worldMatrix[0]"))) - position(om.MMatrix(cmds.getAttr(second + ".worldMatrix[0]")))).length()
    if length < 1.0e-7:
        raise ValueError("同じ位置のジョイントには距離拘束を追加できません")
    constraints = json.loads(cmds.getAttr(node + ".boneConstraints"))
    if any({pair[0], pair[1]} == {a, b} for pair in constraints):
        raise ValueError("この組の距離拘束は登録済みです")
    with _transaction("Simple Physics: Add Constraint"):
        cmds.setAttr(node + ".boneConstraints", json.dumps(constraints + [[a, b, length, compliance]]), type="string")


def removeCollider(node, collider):
    """指定コライダーを取り除き、論理番号を詰めて接続し直す。"""
    _solver(node)
    colliders = connections(node, "colliderObjects")
    if collider not in colliders:
        raise ValueError("このSolverのコライダーを選択してください")
    with _transaction("Simple Physics: Remove Collider"):
        colliders.remove(collider)
        for attribute in ("colliderMatrix", "colliderRadius", "colliderHeight", "colliderObjects"):
            for index in cmds.getAttr(node + "." + attribute, multiIndices=True) or []:
                cmds.removeMultiInstance(f"{node}.{attribute}[{index}]", b=True)
        types = []
        for index, remaining in enumerate(colliders):
            types.append(cmds.getAttr(remaining + ".physicsShape"))
            for source, target in (("worldMatrix[0]", "colliderMatrix"), ("physicsRadius", "colliderRadius"),
                                   ("physicsHeight", "colliderHeight"), ("message", "colliderObjects")):
                cmds.connectAttr(remaining + "." + source, f"{node}.{target}[{index}]")
        cmds.setAttr(node + ".colliderTypes", json.dumps(types), type="string")
        cmds.delete(collider)


def savePreset(node, path):
    """係数・カーブをUTF-8 JSONへ保存する。シーン固有の接続は保存しない。"""
    _solver(node)
    payload = {"format": "SimplePhysicsPreset", "version": 1, "settings": {}, "curves": {}}
    for name in SETTING_NAMES:
        payload["settings"][name] = cmds.getAttr(node + "." + name)
    for name in ("gravity", "wind"):
        payload["settings"][name] = cmds.getAttr(node + "." + name)[0]
    for name in PARAMETERS:
        curve = name + "Curve"
        payload["curves"][name] = [
            [cmds.getAttr(f"{node}.{curve}[{index}].{curve}_{suffix}") for suffix in ("Position", "FloatValue", "Interp")]
            for index in cmds.getAttr(node + "." + curve, multiIndices=True) or []]
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def loadPreset(node, path):
    """既存Solverへ係数プリセットを適用する。読み取り値を先に検証する。"""
    _solver(node)
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
            minimum = cmds.attributeQuery(name, node=node, minimum=True) if cmds.attributeQuery(name, node=node, minExists=True) else None
            maximum = cmds.attributeQuery(name, node=node, maximum=True) if cmds.attributeQuery(name, node=node, maxExists=True) else None
            if (minimum and value < minimum[0]) or (maximum and value > maximum[0]) or (name == "planarConstraint" and value not in range(4)):
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
            if name in ("gravity", "wind"):
                cmds.setAttr(node + "." + name, *value, type="float3")
            else:
                cmds.setAttr(node + "." + name, value)
        for name, entries in curves.items():
            curve = name + "Curve"
            for index in cmds.getAttr(node + "." + curve, multiIndices=True) or []:
                cmds.removeMultiInstance(f"{node}.{curve}[{index}]", b=True)
            for index, entry in enumerate(entries):
                for suffix, value in zip(("Position", "FloatValue", "Interp"), entry):
                    cmds.setAttr(f"{node}.{curve}[{index}].{curve}_{suffix}", value)


def bake(node, start, end):
    """出力を独立したキー付き階層へベイクし、プラグイン依存を取り除く。

    Args:
        node: Solver名。
        start: 開始フレーム（整数）。
        end: 終了フレーム（整数、開始以上）。

    Returns:
        str: ベイク結果のグループ名。
    """
    _solver(node)
    if not isinstance(start, int) or not isinstance(end, int) or end < start:
        raise ValueError("開始・終了フレームは昇順の整数で指定してください")
    topology = json.loads(cmds.getAttr(node + ".topology"))
    outputs = connections(node, "outputBones")
    if len(outputs) != len(topology):
        raise ValueError("出力ジョイントが欠けています。セットアップを作り直してください")
    current = cmds.currentTime(query=True)
    try:
        with _transaction("Simple Physics: Bake"):
            group = cmds.createNode("transform", name="simplePhysics_baked")
            baked = []
            for index, bone in enumerate(topology):
                parent = group if bone["parent"] < 0 else baked[bone["parent"]]
                joint = cmds.createNode("joint", name=outputs[index].rsplit("|", 1)[-1] + "_baked", parent=parent)
                cmds.setAttr(joint + ".segmentScaleCompensate", False)
                baked.append(cmds.ls(joint, long=True)[0])
            for frame in range(start, end + 1):
                cmds.currentTime(frame, edit=True)
                for output, target in zip(outputs, baked):
                    matrix = cmds.xform(output, query=True, worldSpace=True, matrix=True)
                    cmds.xform(target, worldSpace=True, matrix=matrix)
                    cmds.setKeyframe(target, attribute=("translate", "rotate", "scale"), time=frame)
            curves = cmds.listConnections(baked, type="animCurveTA") or []
            if curves:
                cmds.filterCurve(curves)
            cmds.select(group)
    finally:
        cmds.currentTime(current, edit=True)
    return group


def remove(node):
    """このセットアップが所有する出力・コライダー・補助ノードだけを削除する。"""
    _solver(node)
    owned = connections(node, "ownedObjects") + connections(node, "colliderObjects")
    with _transaction("Simple Physics: Remove"):
        cmds.delete([item for item in owned if cmds.objExists(item)] + [node])
