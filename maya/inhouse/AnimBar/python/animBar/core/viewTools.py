"""表示・操作の補助(モーショントレイル・細かい移動・選んだものの周りで回すカメラ)。"""

import maya.cmds as cmds

import mlib
from mlib.common import ScriptJob, Time
from mlib.decorator import undoChunk

from . import keys

#: モーショントレイルのノードに付ける目印のアトリビュート名。
TRAIL_ATTRIBUTE = "animBarMotionTrail"

#: 細かい移動の倍率(1回の操作の変化をこの倍率にする)。
MICRO_FACTORS = (0.5, 0.25, 0.1, 0.05)

#: 細かい移動の状態。
_micro = {"job": None, "factor": 0.1, "values": {}, "resetJobs": []}


@undoChunk("animBarCreateMotionTrail")
def createMotionTrails(nodes=None, increment=1.0):
    """選んだノードのモーショントレイルを、再生範囲で作る。

    Args:
        nodes (Iterable[Transform] | None): 対象。Noneは選択。
        increment (float): 点を置く間隔(フレーム)。

    Returns:
        list[Node]: 作ったモーショントレイルのノード。
    """
    nodes = keys.selectedNodes() if nodes is None else list(nodes)
    start, end = Time.getPlaybackRange()
    created = []
    for node in nodes:
        # mlib にはモーショントレイルの作成の入口が無いため、Mayaのコマンドを使う。
        result = cmds.snapshot(node.getFullName(), motionTrail=True, startTime=start, endTime=end,
                               increment=increment, name=node.getNodeName(removeNamespace=True) + "_animBarTrail")
        trail = mlib.nodes.Node(result[0])
        trail.addAttr(longName=TRAIL_ATTRIBUTE, attributeType="bool", defaultValue=True)
        created.append(trail)
    return created


@undoChunk("animBarClearMotionTrails")
def clearMotionTrails():
    """このツールで作ったモーショントレイルを全部消す。

    Returns:
        int: 消した数。
    """
    trails = [node for node in mlib.ls(type="transform") if node.hasAttr(TRAIL_ATTRIBUTE)]
    trails += [node for node in mlib.ls(type="motionTrail") if node.hasAttr(TRAIL_ATTRIBUTE)]
    if trails:
        mlib.delete(trails)
    return len(trails)


def isMicroTransform():
    """細かい移動が有効かを返す。

    Returns:
        bool: 有効ならTrue。
    """
    return _micro["job"] is not None and _micro["job"].exists()


def setMicroFactor(factor):
    """細かい移動の倍率を設定する。

    Args:
        factor (float): 0より大きく1以下の倍率。

    Returns:
        float: 設定した倍率。
    """
    factor = float(factor)
    if not 0 < factor <= 1:
        raise ValueError("Micro transform factor must be in (0, 1]")
    _micro["factor"] = factor
    return factor


def setMicroTransform(enabled):
    """細かい移動を有効・無効にする。

    有効な間は、選んだノードの移動・回転の値が変わるたびに、変化をこの倍率に縮める
    (マニピュレーターでの操作が細かくなる)。値の監視は scriptJob で行う。

    Args:
        enabled (bool): Trueは有効にする。

    Returns:
        bool: 有効ならTrue。
    """
    if not enabled:
        if _micro["job"] is not None:
            _micro["job"].stop()
        for job in _micro.get("resetJobs", []):
            job.stop()
        _micro.update(job=None, values={}, resetJobs=[])
        return False
    if isMicroTransform():
        return True
    _snapshot_micro()
    # 操作の後のidleで縮め、縮めた書込みは直前の操作と同じUndoにまとめる。
    _micro["job"] = ScriptJob(event="idle", callback=_scale_micro, compressUndo=True, killWithScene=True)
    # フレームの移動・Undo・Redo による値の変化は操作ではないため、縮めずに基準を取り直す。
    _micro["resetJobs"] = [ScriptJob(event=event, callback=_snapshot_micro, killWithScene=True)
                           for event in ("timeChanged", "Undo", "Redo")]
    return True


def _snapshot_micro():
    """選んだノードの移動・回転の今の値を覚える。

    Returns:
        None: 値を返さない。
    """
    values = {}
    for node in keys.selectedNodes():
        if isinstance(node, mlib.nodes.Transform):
            values[node] = (tuple(node.getPlug("translate").get()), tuple(node.getPlug("rotate").get()))
    _micro["values"] = values


def _scale_micro():
    """覚えた値からの変化を倍率に縮める(scriptJob の idle から呼ぶ)。

    Returns:
        None: 値を返さない。
    """
    factor = _micro["factor"]
    if cmds.play(query=True, state=True):
        # 再生中の値の変化は縮めない。
        _snapshot_micro()
        return
    selected = set(node for node in keys.selectedNodes() if isinstance(node, mlib.nodes.Transform))
    if selected != set(_micro["values"]):
        _snapshot_micro()
        return
    changed = False
    for node, (translate, rotate) in list(_micro["values"].items()):
        if not node.isValid():
            continue
        for name, before in (("translate", translate), ("rotate", rotate)):
            plug = node.getPlug(name)
            now = tuple(plug.get())
            if any(abs(a - b) > 1e-9 for a, b in zip(now, before)):
                scaled = tuple(b + (a - b) * factor for a, b in zip(now, before))
                plug.set(scaled, safe=True)
                changed = True
    if changed:
        _snapshot_micro()


def setTumbleOnObjects(enabled):
    """カメラの回転(タンブル)を、選んだものの周りで回すかどうかを切り替える。

    Args:
        enabled (bool): Trueは選んだものの周りで回す。

    Returns:
        bool: 設定した値。
    """
    # mlib にはツールコンテキストの入口が無いため、Mayaのコマンドを使う。
    cmds.tumbleCtx("tumbleContext", edit=True, objectTumble=bool(enabled))
    return bool(enabled)


def isTumbleOnObjects():
    """選んだものの周りで回す設定かを返す。

    Returns:
        bool: Trueなら選んだものの周りで回す。
    """
    return bool(cmds.tumbleCtx("tumbleContext", query=True, objectTumble=True))
