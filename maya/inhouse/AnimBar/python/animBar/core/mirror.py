"""名前の左右の対応から反対側のコントロールを探し、ポーズを左右反転・入れ替えする。

対応は既定で ``L_``/``R_``・``_L``/``_R``・``Left``/``Right``・``left``/``right``・``lf``/``rt`` の組を試す。
反転するアトリビュートの既定は、左右のコントロールが ``translateX`` だけ(左右の軸を鏡写しに作ったリグ)、
中心のコントロール(反対側の名前が無いもの)が ``translateX``・``rotateY``・``rotateZ``。:func:`setInvertRules` で変えられ、
ノードに ``animBarMirrorInvert`` (カンマ区切りの文字列)を足すと、そのノードだけ反転するアトリビュートを変えられる。
中心のコントロールは反転するアトリビュートの符号だけを変える。

:func:`mirrorPose` は現在時刻のポーズ、:func:`mirrorAnimation` は範囲のキー(接線・インフィニティごと)を写す。
"""

import re

import mlib
from mlib.common import Time
from mlib.decorator import undoChunk

from . import keys

#: 試す左右の名前の組(左, 右)。
NAME_PAIRS = (("L_", "R_"), ("_L", "_R"), ("Left", "Right"), ("left", "right"), ("lf", "rt"), ("_l", "_r"), ("l_", "r_"))

#: 既定で符号を反転するアトリビュート(左右のコントロール)。
DEFAULT_INVERT_SIDE = ("translateX",)

#: 既定で符号を反転するアトリビュート(中心のコントロール)。
DEFAULT_INVERT_CENTER = ("translateX", "rotateY", "rotateZ")

#: 今の反転の規則。
_rules = {"side": DEFAULT_INVERT_SIDE, "center": DEFAULT_INVERT_CENTER}

#: ノードごとに反転するアトリビュートを指定するアトリビュート名。
INVERT_ATTRIBUTE = "animBarMirrorInvert"


def oppositeName(name):
    """名前の左右を入れ替えた名前を返す。名前空間とDAGパスはそのまま保つ。

    Args:
        name (str): ノードの名前(短い名前・完全パスのどちらでもよい)。

    Returns:
        str | None: 反対側の名前。左右の目印が無ければNone。
    """
    head, _, short = name.rpartition("|")
    namespace, _, base = short.rpartition(":")
    for left, right in NAME_PAIRS:
        for this, other in ((left, right), (right, left)):
            if "_" in this:
                replaced = _swap_token(base, this, other)
            elif this[0].isupper():
                # キャメルケースの単語(armLeft・LeftArm)。直後に小文字が続くものは別の単語として扱わない。
                replaced = re.sub(re.escape(this) + r"(?![a-z])", other, base, count=1)
            else:
                replaced = re.sub(r"(?<![A-Za-z])" + re.escape(this) + r"(?![a-z])", other, base, count=1)
            if replaced != base:
                return (head + "|" if head else "") + (namespace + ":" if namespace else "") + replaced
    return None


def oppositeNode(node):
    """反対側のノードを返す。

    Args:
        node (Node): ノード。

    Returns:
        Node | None: 反対側のノード。見つからなければNone。
    """
    name = oppositeName(node.getName())
    if name is None or not mlib.objExists(name):
        return None
    matches = mlib.ls(name)
    return matches[0] if len(matches) == 1 else None


def setInvertRules(side=None, center=None):
    """左右・中心のコントロールで符号を反転するアトリビュートを変える。

    Args:
        side (Iterable[str] | None): 左右のコントロールのロング名。Noneは変えない。
        center (Iterable[str] | None): 中心のコントロールのロング名。Noneは変えない。

    Returns:
        dict: 変えた後の規則 ``{"side": (...), "center": (...)}``。
    """
    if side is not None:
        _rules["side"] = tuple(side)
    if center is not None:
        _rules["center"] = tuple(center)
    return dict(_rules)


def resetInvertRules():
    """反転の規則を既定へ戻す。

    Returns:
        dict: 既定の規則。
    """
    return setInvertRules(DEFAULT_INVERT_SIDE, DEFAULT_INVERT_CENTER)


def invertedAttributes(node):
    """ノードで符号を反転するアトリビュートのロング名を返す。

    Args:
        node (Node): ノード。

    Returns:
        tuple[str, ...]: アトリビュートのロング名。
    """
    if node.hasAttr(INVERT_ATTRIBUTE):
        text = node.getPlug(INVERT_ATTRIBUTE).get() or ""
        return tuple(item.strip() for item in text.split(",") if item.strip())
    return _rules["center"] if oppositeNode(node) is None else _rules["side"]


def mirroredValue(plug, time=None):
    """アトリビュートの、反対側のコントロールの値を左右反転した値を返す。

    Args:
        plug (Plug | None): アトリビュート。
        time (float | None): 時刻(フレーム)。Noneは現在時刻。

    Returns:
        float | None: 反転した値。反対側が無い・同じアトリビュートが無い場合はNone。
    """
    if plug is None:
        return None
    node = plug.getNode()
    other = oppositeNode(node) or node
    name = plug.getLongName()
    if not other.hasAttr(name):
        return None
    source = other.getPlug(name)
    if time is None or keys.animCurveOf(source) is None:
        value = source.get()
    else:
        # レイヤーを重ねたアトリビュートでもその時刻の最終的な値を読むため、カーブではなくアトリビュートを評価する。
        with Time.preserved():
            Time.setCurrent(time)
            value = source.get()
    return -value if name in invertedAttributes(node) else value


def selectOpposite(nodes=None, add=False):
    """選んだコントロールの反対側を選ぶ。

    Args:
        nodes (Iterable[Node] | None): 対象。Noneは選択。
        add (bool): Trueは今の選択に足す(両側を選ぶ)。Falseは反対側だけを選ぶ(反対側の無い中心のものは残す)。

    Returns:
        list[Node]: 選んだノード。
    """
    nodes = keys.selectedNodes() if nodes is None else list(nodes)
    chosen = list(nodes) if add else []
    for node in nodes:
        other = oppositeNode(node) or node
        if other not in chosen:
            chosen.append(other)
    mlib.select(chosen, replace=True)
    return chosen


def _pairs(nodes, mode):
    """写す元と先の組を返す。

    Args:
        nodes (list[Node]): 選んだノード。
        mode (str): ``"mirror"``・``"flip"``・``"self"``。

    Returns:
        list[tuple[Node, Node]]: (元, 先)の組。重なりは除く。
    """
    pairs = []
    for node in nodes:
        other = oppositeNode(node) or node
        if mode == "mirror":
            candidates = [(node, other)]
        elif mode == "self":
            candidates = [(other, node)]
        else:
            candidates = [(node, other), (other, node)]
        for pair in candidates:
            if pair not in pairs:
                pairs.append(pair)
    return pairs


def _check_mode(mode):
    """モードの名前を確かめる。"""
    if mode not in ("mirror", "flip", "self"):
        raise ValueError("mode must be 'mirror', 'flip' or 'self'")


@undoChunk("animBarMirrorAnimation")
def mirrorAnimation(nodes=None, mode="mirror", timeRange=None):
    """選んだコントロールのアニメーションを反対側へ写す・入れ替える。

    範囲は timeRange、無ければタイムスライダーで選んだ範囲、Graph Editor で選んだキーの範囲の順に決め、
    どれも無ければ全キーを写す(先の全キーを置き換える)。範囲を写すときは、先の範囲の外のキーは残す。

    Args:
        nodes (Iterable[Node] | None): 対象。Noneは選択。
        mode (str): :func:`mirrorPose` と同じ。
        timeRange (tuple[float, float] | None): 写す範囲(両端を含むフレーム)。

    Returns:
        int: 写したカーブの数。
    """
    _check_mode(mode)
    nodes = keys.selectedNodes() if nodes is None else list(nodes)
    if timeRange is None:
        timeRange = keys.timelineRange()
    if timeRange is None:
        times = keys.keyTimesOf([], selectedOnly=True)
        timeRange = (times[0], times[-1]) if times else None
    # 入れ替えでは先に書くと元が変わるため、書く前に全部の元を読む。
    writes = []
    for source, target in _pairs(nodes, mode):
        inverted = invertedAttributes(target)
        for plug in keys.animatedPlugs(source, channelBox=False):
            name = plug.getLongName()
            if source == target and name not in inverted:
                continue
            if not target.hasAttr(name):
                continue
            snapshot = keys.curveSnapshot(keys.animCurveOf(plug), timeRange)
            if snapshot["keys"]:
                writes.append((target.getPlug(name), snapshot, name in inverted))
    count = 0
    for plug, snapshot, invert in writes:
        if not keys.isEditable(plug):
            continue
        curve = keys.animCurveOf(plug)
        if curve is None:
            first = snapshot["keys"][0]
            plug.setKey(time=first[0], value=-first[1] if invert else first[1])
            curve = keys.animCurveOf(plug)
        keys.applySnapshot(curve, snapshot, transform=_negate if invert else None,
                           replace="all" if timeRange is None else "range")
        count += 1
    return count


def _negate(value):
    """値の符号を反転する(applySnapshot へ渡す)。"""
    return -value


@undoChunk("animBarMirrorPose")
def mirrorPose(nodes=None, mode="mirror", key=None):
    """選んだコントロールのポーズを反対側へ写す・入れ替える。

    Args:
        nodes (Iterable[Node] | None): 対象。Noneは選択。
        mode (str): ``"mirror"`` は選んだ側の値を反対側へ写す。``"flip"`` は左右の値を入れ替える。
            ``"self"`` は反対側の値を自身へ写す。
        key (bool | None): Trueは書いた値にキーを打つ。Noneはアニメーションのあるアトリビュートだけ打つ。

    Returns:
        int: 値を書いたアトリビュートの数。
    """
    _check_mode(mode)
    nodes = keys.selectedNodes() if nodes is None else list(nodes)
    writes = []
    for source, target in _pairs(nodes, mode):
        for plug in keys.keyablePlugs(source, channelBox=False):
            name = plug.getLongName()
            if not target.hasAttr(name):
                continue
            value = plug.get()
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            if name in invertedAttributes(target):
                value = -value
            writes.append((target.getPlug(name), value))
    count = 0
    now = Time.getCurrent()
    for plug, value in writes:
        if not keys.isEditable(plug):
            continue
        plug.set(value)
        if key or (key is None and keys.animCurveOf(plug) is not None):
            plug.setKey(time=now)
        count += 1
    return count


def _swap_token(text, this, other):
    """区切り記号つきの目印(``L_``・``_L`` 等)を1つだけ入れ替える。

    Args:
        text (str): 名前。
        this (str): 探す目印。
        other (str): 置き換える目印。

    Returns:
        str: 入れ替えた名前。見つからなければそのまま。
    """
    if this.endswith("_"):
        if text.startswith(this):
            return other + text[len(this):]
        index = text.find("_" + this)
        return text if index < 0 else text[:index + 1] + other + text[index + 1 + len(this):]
    if text.endswith(this):
        return text[:-len(this)] + other
    index = text.find(this + "_")
    return text if index < 0 else text[:index] + other + text[index + len(this):]
