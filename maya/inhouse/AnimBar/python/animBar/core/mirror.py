"""名前の左右の対応から反対側のコントロールを探し、ポーズを左右反転・入れ替えする。

対応は既定で ``L_``/``R_``・``_L``/``_R``・``Left``/``Right``・``left``/``right``・``lf``/``rt`` の組を試す。
反転するアトリビュートは既定で ``translateX``・``rotateY``・``rotateZ``(YZ面で左右対称に作った一般的なリグ)。
ノードに ``animBarMirrorInvert`` (カンマ区切りの文字列)を足すと、そのノードだけ反転するアトリビュートを変えられる。
中心のコントロール(反対側の名前が無いもの)は反転するアトリビュートの符号だけを変える。
"""

import re

import mlib
from mlib.common import Time
from mlib.decorator import undoChunk

from . import keys

#: 試す左右の名前の組(左, 右)。
NAME_PAIRS = (("L_", "R_"), ("_L", "_R"), ("Left", "Right"), ("left", "right"), ("lf", "rt"), ("_l", "_r"), ("l_", "r_"))

#: 既定で符号を反転するアトリビュート。
DEFAULT_INVERT = ("translateX", "rotateY", "rotateZ")

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
    return DEFAULT_INVERT


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
    curve = source.getAnimCurve()
    value = curve.evaluate(Time.getCurrent() if time is None else time) if curve is not None else source.get()
    return -value if name in invertedAttributes(node) else value


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
    if mode not in ("mirror", "flip", "self"):
        raise ValueError("mode must be 'mirror', 'flip' or 'self'")
    nodes = keys.selectedNodes() if nodes is None else list(nodes)
    writes = []
    done = set()
    for node in nodes:
        other = oppositeNode(node)
        pairs = [(node, other or node)] if mode != "flip" else [(node, other or node), (other or node, node)]
        if mode == "self":
            pairs = [(other or node, node)]
        for source, target in pairs:
            if (source, target) in done:
                continue
            done.add((source, target))
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
        if plug.isLocked() or (plug.getSource() is not None and plug.getAnimCurve() is None):
            continue
        plug.set(value)
        if key or (key is None and plug.getAnimCurve() is not None):
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
