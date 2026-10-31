"""アニメーションのコピーと貼付け(別のノード・別のキャラクター・現在時刻へずらす・繰り返しの反転)。

コピーしたアニメーションは、アトリビュートごとのキー(時刻・値・接線の型・角度・ウェイト・ロック)と
インフィニティを :func:`keys.curveSnapshot` の形でメモリに持つ。貼付けは貼る範囲の既存のキーだけを置き換え、
範囲の外のキーは残す。キャラクターの間の貼付けは、名前空間を除いた名前で対応を取る。
"""

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
        timeRange (tuple[float, float] | None): コピーする範囲。Noneは全キー。

    Returns:
        int: コピーしたカーブの数。
    """
    nodes = keys.selectedNodes() if nodes is None else list(nodes)
    order, data, count, times = [], {}, 0, []
    for node in nodes:
        name = node.getNodeName(removeNamespace=True)
        curves = {}
        for plug in keys.animatedPlugs(node, channelBox=False):
            snapshot = keys.curveSnapshot(plug.getAnimCurve(), timeRange)
            if snapshot["keys"]:
                curves[plug.getLongName()] = snapshot
                times.extend(entry[0] for entry in snapshot["keys"])
                count += 1
        order.append(name)
        data[name] = curves
    _clipboard.update(order=order, data=data, start=min(times) if times else None,
                      end=max(times) if times else None)
    return count


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
    offset = Time.getCurrent() - _clipboard["start"] if inPlace and _clipboard["start"] is not None else 0.0
    pairs = []
    if mode == "selected":
        pairs = list(zip(_clipboard["order"], nodes))
        if len(nodes) > len(_clipboard["order"]) and len(_clipboard["order"]) == 1:
            pairs = [(_clipboard["order"][0], node) for node in nodes]
    elif mode == "name":
        if namespace is None:
            namespace = nodes[0].getNamespace().getName() if nodes else ""
        prefix = namespace.strip(":") + ":" if namespace and namespace != ":" else ""
        for name in _clipboard["order"]:
            if mlib.objExists(prefix + name):
                pairs.append((name, mlib.nodes.Node(prefix + name)))
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
            if plug.isLocked() or (plug.getSource() is not None and plug.getAnimCurve() is None):
                continue
            if invertCycle:
                snapshot = _half_cycle(snapshot)
            curve = plug.getAnimCurve()
            if curve is None:
                first = snapshot["keys"][0]
                plug.setKey(time=first[0] + offset, value=first[1])
                curve = plug.getAnimCurve()
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
