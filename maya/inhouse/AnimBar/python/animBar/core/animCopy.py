"""アニメーションのコピーと貼付け(別のノード・別のキャラクター・現在時刻へずらす・繰り返しの反転)。

コピーしたアニメーションは、アトリビュートごとのキー(時刻・値・接線の型・角度・ウェイト・ロック)と
インフィニティを :func:`keys.curveSnapshot` の形でメモリに持つ。貼付けは貼る範囲の既存のキーだけを置き換え、
範囲の外のキーは残す。キャラクターの間の貼付けは、名前空間を除いた名前で対応を取る。
"""

import json
import tempfile
from pathlib import Path

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from mlib.common import Time
from mlib.decorator import undoChunk

import mlib

from . import keys, mirror

#: コピーした内容。{名前空間を除いたノード名: {アトリビュート名: keys.curveSnapshot の辞書}}。
#: start・end はコピーしたキーの最初と最後の時刻。
_clipboard = {"order": [], "data": {}, "start": None, "end": None}


def copyAnimation(nodes=None, timeRange=None):
    """選んだノードのアニメーションをコピーする。

    Args:
        nodes (Iterable[Node] | None): 対象。Noneは選択。
        timeRange (tuple[float, float] | None): コピーする範囲。Noneはタイムスライダーで選んだ範囲、
            選んでいなければ全キー。

    Returns:
        int: コピーしたカーブの数。
    """
    nodes = keys.selectedNodes() if nodes is None else list(nodes)
    if timeRange is None:
        timeRange = keys.timelineRange()
    order, data, count, times = [], {}, 0, []
    for node in nodes:
        name = node.getName(node=True, removeNamespace=True)
        curves = _copy_snapshots(node, timeRange)
        count += len(curves)
        for snapshot in curves.values():
            times.extend(entry[0] for entry in snapshot["keys"])
        order.append(name)
        data[name] = curves
    _clipboard.update(secondsPerFrame=None, order=order, data=data, start=min(times) if times else None,
                      end=max(times) if times else None)
    return count


def copySteppedRange():
    """再生範囲のステップカーブを両端の保持値と元の秒単位付きでコピーする。"""
    start, end = Time.getRange()
    order, data = [], {}
    for node in keys.selectedNodes():
        name = node.getName(node=True, removeNamespace=True)
        if name in data:
            raise ValueError("Select controls with distinct short names.")
        curves = {}
        for plug in keys.animatedPlugs(node, channelBox=False):
            curve = plug.getAnimCurve()
            if curve is None or not curve.isTimeInput():
                continue
            source = cmds.connectionInfo(curve.getName() + ".input", sourceFromDestination=True)
            if source and source != "time1.outTime":
                continue
            snapshot = keys.curveSnapshot(curve)
            entries = snapshot["keys"]
            if not entries or any(left[2]["outTangentType"] != "step" for left, right in zip(entries, entries[1:])
                                  if left[0] < end and right[0] > start):
                continue
            if start < entries[0][0] or end > entries[-1][0]:
                continue
            selected = [row for row in entries if start <= row[0] <= end]
            for boundary in sorted({start, end}):
                if not any(row[0] == boundary for row in selected):
                    held = next(row for row in reversed(entries) if row[0] <= boundary)
                    selected.append([boundary, held[1], held[2]])
            curves[plug.getAttributeName()] = dict(snapshot, keys=sorted(selected, key=lambda row: row[0]))
        order.append(name)
        data[name] = curves
    if not any(data.values()):
        raise ValueError("No stepped curve spans the playback range.")
    seconds = om2.MTime(1, om2.MTime.uiUnit()).asUnits(om2.MTime.kSeconds)
    _clipboard.update(order=order, data=data, start=start, end=end, secondsPerFrame=seconds)
    return sum(len(curves) for curves in data.values())


def copyTimeDrivenSteps(step, phase=0):
    """共有時間ドライバーの評価結果を、元キーを保ったままステップクリップへコピーする。"""
    if step not in (2, 3) or phase not in range(step):
        raise ValueError("Choose a 2 or 3 frame step and a phase within it.")
    start, end = keys.timelineRange() or Time.getRange()
    if start >= end or not float(start).is_integer() or not float(end).is_integer():
        raise ValueError("Choose a whole-frame range.")
    samples = sorted({start, end, *range(int(start) + phase, int(end), step)})
    data = {}
    for node in keys.selectedNodes():
        name = node.getName(node=True, removeNamespace=True)
        if name in data:
            raise ValueError("Select controls with distinct short names.")
        curves = {}
        for plug in keys.animatedPlugs(node):
            curve = plug.getAnimCurve()
            if curve is None or not curve.isTimeInput():
                continue
            drivers = cmds.listConnections(curve.getName() + ".input", source=True, destination=False, type="animCurveTT") or []
            if len(drivers) != 1 or not cmds.attributeQuery("animBarTimeMembers", node=drivers[0], exists=True):
                continue
            snapshot = keys.curveSnapshot(curve)
            rows = []
            for frame in samples:
                mapped = cmds.getAttr(drivers[0] + ".output", time=frame)
                rows.append([frame, curve.evaluate(mapped), {"inTangentType": "linear", "outTangentType": "step", "lock": False}])
            curves[plug.getAttributeName()] = dict(snapshot, weighted=False, keys=rows)
        data[name] = curves
    if not any(data.values()):
        raise ValueError("Select controls animated through an Anim Bar time driver.")
    seconds = om2.MTime(1, om2.MTime.uiUnit()).asUnits(om2.MTime.kSeconds)
    _clipboard.update(order=list(data), data=data, start=start, end=end, secondsPerFrame=seconds)
    return sum(len(curves) for curves in data.values())


def _copy_snapshots(node, time_range):
    """指定範囲にキーを持つコピー対象をアトリビュート名ごとに取得する。"""
    curves = {}
    for plug in keys.animatedPlugs(node, channelBox=False):
        snapshot = keys.curveSnapshot(keys.animCurveOf(plug), time_range)
        if snapshot["keys"]:
            curves[plug.getAttributeName()] = snapshot
    return curves


def previewCopy(timeRange=None):
    """選択中の各チャンネルのコピー対象判定と入力の種類を返す。

    Args:
        timeRange (tuple | None): コピー範囲。省略時は通常のコピーと同じ範囲。

    Returns:
        list[tuple]: プラグ名、入力の種類、コピーされるキー数。
    """
    if timeRange is None:
        timeRange = keys.timelineRange()
    counts = {}
    seen = set()
    for node in reversed(list(keys.selectedNodes())):
        name = node.getName(node=True, removeNamespace=True)
        if name in seen:
            continue
        seen.add(name)
        for attr, snapshot in _copy_snapshots(node, timeRange).items():
            counts[f"{node.getName(full=True)}.{attr}"] = len(snapshot["keys"])
    return [(plug, kind + (" [locked]" if locked else ""), counts.get(plug, 0))
            for kind, plug, _, locked in keys.inspectChannels()]


def previewClipExport(timeRange=None, *, channelBoxOnly=False):
    """選択範囲の直接接続キーと現在の静的値を収集し、書き出す内容と除外理由を返す。"""
    time_range = keys.timelineRange() if timeRange is None else timeRange
    return _clip_from_rows(keys.inspectChannels(channelBoxOnly=channelBoxOnly), time_range)


def previewPublishedExport(timeRange):
    """選択したリグの公開ポート宣言と実際の入力を照合し、書き出し内容と除外理由を返す。"""
    ports, excluded, rows = keys.inspectPublishedChannels()
    accepted = []
    labels = {}
    for plug, declarations in ports.items():
        labels[plug] = ", ".join(f"{role} ({kind})" for role, kind in declarations)
        if any(kind not in ("default", "static") for _, kind in declarations):
            reason = "Excluded port kind"
        elif plug not in rows:
            reason = "Not a keyable scalar"
        elif any(kind == "static" for _, kind in declarations) and rows[plug][0] != "Static":
            reason = "Static port has an input"
        else:
            accepted.append(rows[plug])
            continue
        excluded[plug] = labels[plug] + ": " + reason
    clip, skipped = _clip_from_rows(accepted, timeRange)
    for plug, reason in skipped.items():
        excluded[plug] = labels[plug] + ": " + reason
    for plug, entry in clip["channels"].items():
        entry["publishedPorts"] = labels[plug]
    return clip, excluded


def _clip_from_rows(rows, time_range):
    """診断済みの入力から指定範囲のクリップを組み立てる。"""
    channels = {}
    excluded = {}
    for kind, plug, source, locked in rows:
        if locked:
            excluded[plug] = kind + " [locked]"
        elif kind == "Static":
            value = cmds.getAttr(plug)
            if isinstance(value, (int, float)):
                channels[plug] = {"value": value, "type": cmds.getAttr(plug, type=True)}
            else:
                excluded[plug] = "Unsupported static value"
        elif kind == "Time keys" and cmds.isConnected(source, plug):
            curve = mlib.getNode(source.split(".", 1)[0])
            snapshot = keys.curveSnapshot(curve, time_range)
            if snapshot["keys"]:
                channels[plug] = {"curve": snapshot, "type": curve.getType()}
            else:
                excluded[plug] = "No keys in range"
        else:
            excluded[plug] = kind if kind != "Time keys" else "Converted input"
    units = {"time": cmds.currentUnit(query=True, time=True), "staticAngle": cmds.currentUnit(query=True, angle=True),
             "staticDistance": cmds.currentUnit(query=True, linear=True), "curveAngle": "deg", "curveDistance": "cm"}
    return {"format": "AnimBarClip", "version": 1, "units": units, "range": time_range,
            "frame": cmds.currentTime(query=True), "channels": channels}, excluded


def writeClip(path, clip):
    """確認したクリップをJSONで保存し、書き込み完了後に保存先を置き換える。"""
    path = Path(path)
    content = json.dumps(clip, ensure_ascii=False, indent=2, allow_nan=False)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def hasCopy():
    """コピーした内容があるかを返す。

    Returns:
        bool: あればTrue。
    """
    return bool(_clipboard["data"])


@undoChunk("animBarPasteAnimation")
def pasteAnimation(nodes=None, mode="selected", inPlace=False, namespace=None, invertCycle=False):
    """コピーしたアニメーションを貼り付ける。貼り付ける範囲の既存のキーは置き換え、範囲の外のキーは残す。

    Args:
        nodes (Iterable[Node] | None): 貼り付け先。Noneは選択。
        mode (str): ``"selected"`` はコピーした順に選択へ、``"name"`` は名前で対応する同名ノードへ
            (namespace の名前空間で探す)。
        inPlace (bool): Trueは最初のキーを現在時刻へずらす。
        namespace (str | None): mode="name" で探す名前空間。Noneは選んだ最初のノードの名前空間。
        invertCycle (bool): Trueは反対側のノードへ、反転するアトリビュートの値を反転し、コピーした範囲の半分だけ
            時刻をずらして貼る(範囲を越えたキーは先頭へ回す。歩きのように左右が半周期ずれた繰り返しを作る)。

    Returns:
        int: 貼り付けたカーブの数。

    Raises:
        ValueError: コピーした内容が無い場合。
    """
    if not hasCopy():
        raise ValueError("Copy animation first")
    nodes = keys.selectedNodes() if nodes is None else list(nodes)
    time_scale = 1.0
    if _clipboard.get("secondsPerFrame"):
        time_scale = om2.MTime(_clipboard["secondsPerFrame"], om2.MTime.kSeconds).asUnits(om2.MTime.uiUnit())
    offset = Time.getCurrent() - _clipboard["start"] * time_scale if inPlace and _clipboard["start"] is not None else 0.0
    pairs = []
    if mode == "selected":
        pairs = list(zip(_clipboard["order"], nodes))
        if len(nodes) > len(_clipboard["order"]) and len(_clipboard["order"]) == 1:
            pairs = [(_clipboard["order"][0], node) for node in nodes]
    elif mode == "name":
        if namespace is None:
            namespace = nodes[0].getNamespace().name if nodes else ""
        prefix = namespace.strip(":") + ":" if namespace and namespace != ":" else ""
        for name in _clipboard["order"]:
            matches = cmds.ls(":" + prefix + name, long=True) or []
            if len(matches) > 1:
                raise ValueError(f"Multiple paste targets match {prefix}{name}")
            if matches:
                pairs.append((name, mlib.getNode(matches[0])))
    else:
        raise ValueError("mode must be 'selected' or 'name'")
    count = 0
    for name, node in pairs:
        if invertCycle:
            other = mirror.oppositeNode(node)
            node = other or node
        inverted = mirror.invertedAttributes(node) if invertCycle else ()
        for attribute, snapshot in _clipboard["data"].get(name, {}).items():
            if not node.hasAttr(attribute):
                continue
            plug = node.getPlug(attribute)
            if not keys.isEditable(plug):
                continue
            if invertCycle:
                snapshot = _half_cycle(snapshot)
            if time_scale != 1:
                snapshot = dict(snapshot, keys=[[time * time_scale, value, tangent] for time, value, tangent in snapshot["keys"]])
            curve = keys.animCurveOf(plug)
            if curve is None:
                first = snapshot["keys"][0]
                plug.setKey(time=first[0] + offset, value=first[1])
                curve = keys.animCurveOf(plug)
            transform = (lambda value: -value) if attribute in inverted else None
            keys.applySnapshot(curve, snapshot, offset=offset, transform=transform)
            count += 1
    return count


def _half_cycle(snapshot):
    """コピーした範囲の半分だけキーの時刻をずらし、範囲を越えたキーを先頭へ回した写しを返す。

    Args:
        snapshot (dict): keys.curveSnapshot の辞書。

    Returns:
        dict: 時刻を変えた写し(キーは時刻の順)。範囲が0なら元のまま。
    """
    start, end = _clipboard["start"], _clipboard["end"]
    span = end - start
    if span <= keys.TIME_EPSILON:
        return snapshot
    entries = {}
    for time, value, tangent in snapshot["keys"]:
        shifted = time + span / 2.0
        if shifted > end + keys.TIME_EPSILON:
            shifted -= span
        # 両端に同じ値のキーがある繰り返しでは、回した先が重なるため最初のものを残す。
        entries.setdefault(round(shifted, 6), [shifted, value, tangent])
    ordered = [entries[key] for key in sorted(entries)]
    # 繰り返しを閉じるため、先頭にキーが無ければ最後のキーと同じ値のキーを先頭に置く。
    if ordered and ordered[0][0] > start + keys.TIME_EPSILON and abs(ordered[-1][0] - end) <= keys.TIME_EPSILON:
        ordered.insert(0, [start, ordered[-1][1], ordered[-1][2]])
    return dict(snapshot, keys=ordered)
