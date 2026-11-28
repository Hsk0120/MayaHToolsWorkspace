"""モデル改版時に部位ごとの形状と骨を照合する、シーン内の対応表。"""

import json
from collections import defaultdict

import mlib
from maya import cmds
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector


_ATTRIBUTE = "mlrigCharacterMap"
_MODEL_ID = "mlrigCharacterModelId"


def _inspect(root, mapping):
    """名前空間を除いたモデル内パスを照合し、ルート空間の左右・姿勢を読み取る。"""
    roots = mlib.ls(root, long=True, transforms=True).getNames(full=True)
    if len(roots) != 1 or not isinstance(mapping, dict) or not mapping:
        raise ValueError("モデルルートを1つ選び、部位別の対応表を指定してください")
    root = roots[0]
    inverse = Matrix(cmds.getAttr(root + ".worldInverseMatrix[0]"))
    paths = defaultdict(list)
    for node in cmds.listRelatives(root, allDescendents=True, fullPath=True) or []:
        key = "|".join(p.rsplit(":", 1)[-1] for p in node[len(root) + 1:].split("|"))
        paths[key].append(node)
    values, issues = {}, []
    owners = {}
    for role, pair in mapping.items():
        if not isinstance(role, str) or not role.strip() or not isinstance(pair, dict) or set(pair) != {"joint", "mesh"}:
            raise ValueError("各部位にjointとmeshの相対パスを指定してください")
        values[role] = {}
        for kind, key in pair.items():
            if not isinstance(key, str) or not key:
                raise ValueError("jointとmeshには相対パス文字列を指定してください")
            hits = paths.get(key, [])
            if len(hits) != 1:
                issues.append("{} {} {}: {}".format(role, kind, "重名" if hits else "欠損", key))
                continue
            node = hits[0]
            if kind == "mesh":
                if cmds.nodeType(node) != "transform" or not cmds.listRelatives(node, shapes=True, noIntermediate=True, type="mesh"):
                    issues.append(role + " メッシュの形状がありません: " + key)
                else:
                    transform = mlib.getNode(node)
                    center = (transform.getMatrix(ws=True) * inverse).transformPoint(transform.getBoundingBox().center)
                    values[role]["meshSide"] = 1 if center.x > 1e-6 else -1 if center.x < -1e-6 else 0
                continue
            if cmds.nodeType(node) != "joint":
                issues.append(role + " 骨ではありません: " + key)
                continue
            if node in owners:
                issues.append("{} と {} が同じ骨を指定: {}".format(owners[node], role, key))
            owners[node] = role
            matrix = Matrix(cmds.getAttr(node + ".worldMatrix[0]")) * inverse
            x = matrix[12]
            axes = [list(Vector(*list(matrix)[i:i + 3]).normal()) for i in (0, 4, 8)]
            values[role].update(side=1 if x > 1e-6 else -1 if x < -1e-6 else 0, axes=axes)
    return values, issues


@undoTransaction("mlrigRecordCharacterMap")
def record(root, modelId, mapping):
    """元の対応と姿勢を専用networkに保存し、編集用の対応表を別に保持する。"""
    if not isinstance(modelId, str) or not modelId.strip():
        raise ValueError("モデルIDを指定してください")
    if cmds.objExists(root + "." + _MODEL_ID) and cmds.getAttr(root + "." + _MODEL_ID) != modelId:
        raise ValueError("ルートに登録されたモデルIDと一致しません")
    values, issues = _inspect(root, mapping)
    if issues:
        raise ValueError("\n".join(issues))
    node = mlib.createNode("network", name="characterMap#", skipSelect=True).getName()
    cmds.addAttr(node, longName=_ATTRIBUTE, dataType="string")
    data = dict(version=1, modelId=modelId, original=mapping, working=mapping, baseline=values)
    cmds.setAttr(node + "." + _ATTRIBUTE, json.dumps(data, ensure_ascii=False), type="string")
    return node


def _read(node):
    """このツールで記録した対応表を取得する。"""
    if not cmds.objExists(node + "." + _ATTRIBUTE):
        raise ValueError("記録済みの対応表を選択してください")
    data = json.loads(cmds.getAttr(node + "." + _ATTRIBUTE))
    if data.get("version") != 1:
        raise ValueError("未対応の対応表です")
    return data


def compare(node, root, modelId, mapping=None):
    """基準姿勢で元定義と編集案を比較し、モデルID・対応・左右・軸の不一致を返す。"""
    data = _read(node)
    stored = root + "." + _MODEL_ID
    if modelId != data["modelId"] or (cmds.objExists(stored) and cmds.getAttr(stored) != data["modelId"]):
        return ["モデルIDが一致しません"]
    entries = data["working"] if mapping is None else mapping
    values, issues = _inspect(root, entries)
    for role in sorted(set(data["baseline"]) ^ set(entries)):
        issues.append(role + " 部位の構成が異なります")
    for role in values.keys() & data["baseline"].keys():
        old, new = data["baseline"][role], values[role]
        if "side" in new and old["side"] != new["side"]:
            issues.append(role + " 左右位置が異なります")
        if "meshSide" in new and old.get("meshSide") != new["meshSide"]:
            issues.append(role + " 形状の左右位置が異なります")
        if "axes" in new and any(Vector(*a) * Vector(*b) < 0.99999 for a, b in zip(old["axes"], new["axes"])):
            issues.append(role + " 骨の軸方向が異なります")
    return sorted(issues)


@undoTransaction("mlrigAssignCharacterModelId")
def _assign_id(root, model_id):
    """改版を通して共有するモデルIDを、制作側のルートへ明示登録する。"""
    if not model_id.strip() or not cmds.objectType(root, isAType="transform"):
        raise ValueError("モデルIDとモデルルートを指定してください")
    plug = root + "." + _MODEL_ID
    if cmds.objExists(plug):
        if cmds.getAttr(plug) != model_id:
            raise ValueError("このルートには別のモデルIDが登録されています")
        return
    cmds.addAttr(root, longName=_MODEL_ID, dataType="string")
    cmds.setAttr(plug, model_id, type="string")


def show():
    """元定義の記録、対応案の照合・保存を行う画面を開く。"""
    window = "mlrigCharacterMap"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="キャラクターの部位対応")
    cmds.columnLayout(adjustableColumn=True)
    identifier = cmds.textFieldGrp(label="モデルID")
    mapping = cmds.scrollField(text='{"左手": {"mesh": "handGeo", "joint": "root|hand"}}', height=100)
    status = cmds.scrollField(editable=False, height=90)

    def act(action):
        selected = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
        mid = cmds.textFieldGrp(identifier, query=True, text=True)
        if action == "id" and len(selected) == 1:
            _assign_id(selected[0], mid)
            cmds.scrollField(status, edit=True, text="ルートにモデルIDを登録")
            return
        if action == "load" and len(selected) == 1:
            data = _read(selected[0])
            cmds.textFieldGrp(identifier, edit=True, text=data["modelId"])
            cmds.scrollField(mapping, edit=True, text=json.dumps(data["working"], ensure_ascii=False, indent=2))
            return
        entries = json.loads(cmds.scrollField(mapping, query=True, text=True))
        if action == "record" and len(selected) == 1:
            node = record(selected[0], mid, entries)
            mlib.select(node, replace=True)
            message = "基準を記録: " + node
        elif action in ("compare", "save") and len(selected) == 2:
            node, root = selected
            issues = compare(node, root, mid, entries)
            message = "\n".join(issues) or "差異なし"
            if action == "save" and not issues:
                data = _read(node)
                data["working"] = entries
                cmds.setAttr(node + "." + _ATTRIBUTE, json.dumps(data, ensure_ascii=False), type="string")
                message = "対応案を保存"
        else:
            raise ValueError("記録はルート、読込は対応表、照合と保存は対応表・ルートの順に選択してください")
        cmds.scrollField(status, edit=True, text=message)

    for action, label in (("id", "選択ルートにモデルIDを登録"), ("record", "選択ルートの基準を記録"), ("load", "選択した対応表を読む"), ("compare", "対応案を照合"), ("save", "照合して対応案を保存")):
        cmds.button(label=label, command=lambda *_, action=action: act(action))
    cmds.showWindow(window)
    return window
