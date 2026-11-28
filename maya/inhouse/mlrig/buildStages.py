"""ガイド・骨の構築段階に追加する部品を、ユニット内の役割で宣言する。"""

import json
import math
import re

import mlib
from maya import cmds
from mlib.common.units import convertDistance
from mlib.decorator import undoTransaction

from .animalGuides import _member, _record


def declarations(root, roles):
    """工程・役割・型・配置を構築前に検査する。"""
    plug = root + ".mlrigBuildStages"
    entries = json.loads(cmds.getAttr(plug)) if cmds.objExists(plug) else []
    if not isinstance(entries, list):
        raise ValueError("構築拡張は配列で指定してください")
    seen = set()
    for data in entries:
        if not isinstance(data, dict) or set(data) != {"id", "stage", "role", "kind", "offset"}:
            raise ValueError("各構築拡張にid、stage、role、kind、offsetを指定してください")
        key, stage, role = data["id"], data["stage"], data["role"]
        if not isinstance(key, str) or not re.fullmatch("[a-zA-Z][a-zA-Z0-9_]*", key) or key in seen:
            raise ValueError("拡張IDが不正または重複しています")
        seen.add(key)
        if stage not in ("guide", "bone", "finish") or role not in roles or data["kind"] not in ("transform", "joint", "locator"):
            raise ValueError("構築工程・対象・部品型を確認してください: {} / {} / {}".format(stage, role, key))
        v = data["offset"]
        if not isinstance(v, list) or len(v) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) for x in v):
            raise ValueError("配置は有限の3成分で指定してください: " + key)
    existing = {a[len("mlrigStage_") :] for a in cmds.listAttr(root, userDefined=True) or [] if a.startswith("mlrigStage_")}
    if existing - seen:
        raise ValueError("作成済みの拡張IDが宣言から外れています: " + ", ".join(sorted(existing - seen)))
    return entries


def run(root, entries, stage, role, parent):
    """工程と役割が一致する部品の基準位置を更新し、同じ役割の重複を防ぐ。"""
    for entry in entries:
        if (entry["stage"], entry["role"]) != (stage, role):
            continue
        key = entry["id"]
        try:
            attr = "mlrigStage_" + key
            target = _member(root, attr)
            kind = entry["kind"]
            if target is None:
                target = mlib.createNode("transform" if kind == "locator" else kind, parent=parent, name=key + "#").getName()
                if kind == "locator":
                    mlib.createNode("locator", parent=target)
                _record(root, attr, target)
            else:
                actual = "locator" if cmds.listRelatives(target, shapes=True, type="locator") else cmds.nodeType(target)
                if actual != kind or cmds.listRelatives(target, parent=True, fullPath=True) != [item.getName(full=True) for item in mlib.ls(parent, long=True)]:
                    raise ValueError("作成済みの部品型または親が宣言と異なります")
            matrix = [float(i % 5 == 0) for i in range(16)]
            matrix[12:15] = [convertDistance(x, toUnit="cm") for x in entry["offset"]]
            cmds.setAttr(target + ".offsetParentMatrix", *matrix, type="matrix")
        except (ValueError, RuntimeError) as error:
            raise ValueError("構築拡張 {} / {} / {}: {}".format(stage, role, key, error)) from error


def show():
    """選択した非人型プリセットに対して工程の宣言を保存して構築する。"""
    from .animalGuides import build

    nodes = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
    if len(nodes) != 1 or not cmds.objExists(nodes[0] + ".mlrigAnimalPreset"):
        raise ValueError("非人型プリセットのルートを選択してください")
    root = nodes[0]
    plug = root + ".mlrigBuildStages"
    window = "mlrigBuildStages"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="構築工程の拡張")
    cmds.columnLayout(adjustableColumn=True)
    field = cmds.scrollField(text=cmds.getAttr(plug) if cmds.objExists(plug) else "[]", height=160)

    @undoTransaction("mlrigSaveBuildStages")
    def apply(*_):
        value = cmds.scrollField(field, query=True, text=True)
        if not cmds.objExists(plug):
            cmds.addAttr(root, longName="mlrigBuildStages", dataType="string")
        cmds.setAttr(plug, value, type="string")
        build(root)

    cmds.button(label="宣言を保存して構築", command=apply)
    cmds.showWindow(window)
    return window
