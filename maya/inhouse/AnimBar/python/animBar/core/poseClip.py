"""シーン内のポーズクリップを作成・再構築・復元する。"""

import json

import maya.cmds as cmds
from mlib.decorator import undoChunk
from mlib.json import NodeRef, PoseSnapshot

_ATTRIBUTE = "animBarPoseSnapshotV1"
_WEIGHT = "animBarPoseWeight"


def _node_ref(data):
    """保存データのノードの参照(``name``・``path``・``type`` の辞書)から NodeRef を作る。"""
    return NodeRef(data["name"], data.get("path"), data.get("type"))


def _selection():
    """選択したtransformをクリップと記録対象に分ける。"""
    clips, targets = [], []
    for node in cmds.ls(selection=True, long=True, objectsOnly=True) or []:
        if not cmds.objectType(node, isAType="transform"):
            raise ValueError("Select controls or pose clip transforms.")
        if cmds.attributeQuery(_ATTRIBUTE, node=node, exists=True):
            clips.append(node)
        else:
            targets.append(node)
    return clips, targets


@undoChunk("animBarCapturePoseClip")
def captureSelected():
    """選択したコントローラーの値を新しいクリップに保存する。

    Returns:
        str: 作成したクリップ名。
    """
    clips, targets = _selection()
    if clips or not targets:
        raise ValueError("Select only the controls to capture.")
    payload = json.dumps(PoseSnapshot.capture(targets).toData(), allow_nan=False)
    clip = cmds.createNode("transform", name="animBarPoseClip#", skipSelect=True)
    cmds.addAttr(clip, longName=_ATTRIBUTE, dataType="string")
    cmds.setAttr(f"{clip}.{_ATTRIBUTE}", payload, type="string")
    cmds.addAttr(clip, longName=_WEIGHT, attributeType="double", minValue=0, maxValue=1, defaultValue=1)
    cmds.setAttr(f"{clip}.{_WEIGHT}", channelBox=True)
    return clip


@undoChunk("animBarRebuildPoseClip")
def rebuildSelected():
    """選択した1クリップの内容を、一緒に選んだコントローラーの現在値で置き換える。"""
    clips, targets = _selection()
    if len(clips) != 1 or not targets:
        raise ValueError("Select one pose clip and the controls to capture.")
    payload = json.dumps(PoseSnapshot.capture(targets).toData(), allow_nan=False)
    cmds.setAttr(f"{clips[0]}.{_ATTRIBUTE}", payload, type="string")


def _read_clip(node):
    """保存データと適用ウェイトを読む。以前のクリップは全量を適用する。"""
    snapshot = PoseSnapshot(json.loads(cmds.getAttr(f"{node}.{_ATTRIBUTE}")))
    weight = cmds.getAttr(f"{node}.{_WEIGHT}") if cmds.attributeQuery(_WEIGHT, node=node, exists=True) else 1
    if not 0 <= weight <= 1:
        raise ValueError("Pose clip weight must be between 0 and 1.")
    return snapshot, weight


def _apply_clip(snapshot, weight):
    """現在値から記録値へ各軸を線形補間する。整数・boolは半分で切り替える。"""
    if weight == 0:
        return None
    if weight == 1:
        return snapshot.apply()
    data = snapshot.toData()
    for entry in data["nodes"]:
        node = _node_ref(entry["node"]).resolve()
        if node is None:
            continue
        for name, value in list(entry["attrs"].items()):
            if isinstance(value, int):
                if weight < 0.5:
                    del entry["attrs"][name]
            elif node.hasAttr(name):
                current = node.getPlug(name).get()
                entry["attrs"][name] = current + (value - current) * weight
    return PoseSnapshot(data).apply()


def restoreSelected():
    """選択した1クリップの保存値を記録元へ復元する。"""
    clips, targets = _selection()
    if len(clips) != 1 or targets:
        raise ValueError("Select one pose clip to restore.")
    return _apply_clip(*_read_clip(clips[0]))


@undoChunk("animBarRestorePoseGroup")
def restoreSelectedGroup():
    """選んだグループのDAG子順に深さ優先で、直前の結果へ各クリップを混合する。"""
    clips, groups = _selection()
    if clips or len(groups) != 1:
        raise ValueError("Select one group containing pose clips.")
    pending = [groups[0]]
    snapshots = []
    while pending:
        node = pending.pop()
        if cmds.attributeQuery(_ATTRIBUTE, node=node, exists=True):
            snapshots.append(_read_clip(node))
        children = cmds.listRelatives(node, children=True, type="transform", fullPath=True) or []
        pending.extend(reversed(children))
    if not snapshots:
        raise ValueError("The selected group contains no pose clips.")
    for snapshot, weight in snapshots:
        _apply_clip(snapshot, weight)

def previewSelectedBlend(confirm):
    """1つまたは2つのクリップを名前順に混合し、確認中だけシーンに表示する。

    元の値から各クリップのウェイトで順に各軸を線形補間する。
    確定時は元の値へ戻してから、同じ処理を1回のUndoで適用する。
    """
    clips, targets = _selection()
    if targets or len(clips) not in (1, 2):
        raise ValueError("Select one or two pose clips to preview.")
    if not cmds.undoInfo(query=True, state=True):
        raise ValueError("Enable Undo before previewing a pose.")
    clips.sort()
    snapshots = [_read_clip(clip) for clip in clips]
    originals = []
    for snapshot, _ in snapshots:
        for entry in snapshot.toData()["nodes"]:
            node = _node_ref(entry["node"]).resolve()
            if node is None:
                continue
            attrs = {name: node.getPlug(name).get() for name in entry["attrs"] if node.hasAttr(name)}
            originals.append({"node": entry["node"], "attrs": attrs})
    baseline = PoseSnapshot({"nodes": originals})
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        for snapshot, weight in snapshots:
            _apply_clip(snapshot, weight)
        cmds.undoInfo(stateWithoutFlush=True)
        cmds.refresh()
        accepted = confirm([(clip, weight) for clip, (_, weight) in zip(clips, snapshots)])
    finally:
        try:
            cmds.undoInfo(stateWithoutFlush=False)
            baseline.apply()
        finally:
            cmds.undoInfo(stateWithoutFlush=True)
    if accepted:
        with undoChunk("animBarBlendPoseClips"):
            for snapshot, weight in snapshots:
                _apply_clip(snapshot, weight)


def restoreShortcut():
    """選択クリップのポーズを全量復元する。対象も選んだ場合は記録元との共通部分だけを戻す。"""
    clips, targets = _selection()
    if len(clips) != 1:
        raise ValueError("Select one pose clip, optionally with some of its recorded controls.")
    snapshot, _ = _read_clip(clips[0])
    if not targets:
        return snapshot.apply()
    data = snapshot.toData()
    selected = set(targets)
    entries = []
    for entry in data["nodes"]:
        node = _node_ref(entry["node"]).resolve()
        if node is not None and node.getName(full=True) in selected:
            entries.append(entry)
    if not entries:
        raise ValueError("No selected control matches a recorded control in its original namespace.")
    return PoseSnapshot({"nodes": entries}).apply()
