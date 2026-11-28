"""選択した設計用ジョイントのローカル基準姿勢をシーン内に記録する。"""

import json
import math

import mlib
from maya import cmds
from mlib.decorator import undoTransaction


_MARKER = "mlrigJointDesignPose"
_CHANNELS = tuple(attr + axis for attr in ("translate", "rotate", "scale", "jointOrient", "rotateAxis") for axis in "XYZ") + ("rotateOrder",)


@undoTransaction("mlrigJointDesignPose")
def apply(action):
    """選択ジョイントごとの記録・復帰・記録削除を1回のUndoにまとめる。"""
    nodes = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
    if not nodes or any(cmds.nodeType(n) != "joint" or cmds.referenceQuery(n, isNodeReferenced=True) for n in nodes):
        raise ValueError("設計するローカルジョイントだけを選択してください")
    if action not in ("save", "restore", "delete"):
        raise ValueError("不明な基準姿勢の操作です")
    units = [cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True)]
    records = {}
    edits = {}
    for node in nodes:
        marker = node + "." + _MARKER
        exists = cmds.objExists(marker)
        if exists:
            record = json.loads(cmds.getAttr(marker))
            if record.get("schema") != "mlrigJointDesignPose/1" or set(record.get("channels", {})) != set(_CHANNELS):
                raise ValueError("基準姿勢の形式を確認してください: " + node)
        elif action != "save":
            raise ValueError("基準姿勢が保存されていません: " + node)
        if action == "save":
            records[marker] = dict(schema="mlrigJointDesignPose/1", units=units,
                                   channels={key: cmds.getAttr(node + "." + key) for key in _CHANNELS})
        elif action == "restore":
            if record["units"] != units or cmds.autoKeyframe(query=True, state=True):
                raise ValueError("保存時の単位に合わせ、自動キーを無効にしてください")
            for key, value in record["channels"].items():
                plug = node + "." + key
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("基準値が無効です: " + plug)
                if cmds.getAttr(plug) != value:
                    if cmds.connectionInfo(plug, isDestination=True) or not cmds.getAttr(plug, settable=True):
                        raise ValueError("入力接続またはロックがあります: " + plug)
                    edits[plug] = value
    if action == "save":
        for marker, record in records.items():
            if not cmds.objExists(marker):
                cmds.addAttr(marker.rsplit(".", 1)[0], longName=_MARKER, dataType="string", hidden=True)
            cmds.setAttr(marker, json.dumps(record), type="string")
    elif action == "delete":
        for node in nodes:
            cmds.deleteAttr(node + "." + _MARKER)
    else:
        for plug, value in edits.items():
            cmds.setAttr(plug, value)
    return nodes
