"""キーの時間の操作(前後へ動かす・間を空ける/詰める・キーをそろえる)と、値のリセット・全体への反映。"""

import mlib
from mlib.common import Time
from mlib.decorator import undoChunk

from . import keys


@undoChunk("animBarNudgeKeys")
def nudgeKeys(frames, everything=False):
    """選んだキー(無ければ選んだノードの現在時刻のキー)を前後へ動かす。

    Args:
        frames (float): 動かすフレーム数。負は前へ。
        everything (bool): Trueは選択に関係なく、シーンの全カーブの現在時刻のキーを動かす。

    Returns:
        int: 動かしたキーの数。
    """
    frames = float(frames)
    if everything:
        now = Time.getCurrent()
        moves = []
        for curve in mlib.ls(type="animCurve"):
            if not curve.isTimeInput():
                continue
            index = keys.keyIndexAt(curve, now)
            if index is not None:
                moves.append((curve, [index]))
    else:
        moves = [(target.curve, target.indices) for target in keys.targets()]
    count = 0
    for curve, indices in moves:
        # 選んだキーは一緒に動かす(選んでいない隣のキーは越えない)。
        curve.moveKey(indices, timeOffset=frames)
        count += len(indices)
    if count and not everything and not keys.graphEditorKeys():
        Time.setCurrent(Time.getCurrent() + frames)
    return count


@undoChunk("animBarInsertFrames")
def insertFrames(frames, nodes=None):
    """現在時刻より後ろのキーを動かし、間を空ける(負は詰める)。

    Args:
        frames (float): 空けるフレーム数。負は詰める(詰めた先にキーがあれば止める)。
        nodes (Iterable[Node] | None): 対象。Noneは選択。

    Returns:
        int: 動かしたカーブの数。

    Raises:
        ValueError: 詰めると現在時刻より前のキーと重なる場合(何も変えない)。
    """
    frames = float(frames)
    now = Time.getCurrent()
    nodes = keys.selectedNodes() if nodes is None else list(nodes)
    curves = []
    for node in nodes:
        for plug in keys.animatedPlugs(node, channelBox=False):
            curve = plug.getAnimCurve()
            inputs = curve.getKeyInputs()
            after = [value for value in inputs if value > now + keys.TIME_EPSILON]
            if not after:
                continue
            before = [value for value in inputs if value <= now + keys.TIME_EPSILON]
            if frames < 0 and before and min(after) + frames <= max(before) + keys.TIME_EPSILON:
                raise ValueError("Removing {} frames would overlap the key at frame {}".format(-frames, max(before)))
            curves.append(curve)
    for curve in curves:
        last = max(curve.getKeyInputs())
        curve.moveKey(time=(now + keys.TIME_EPSILON, last), timeOffset=frames)
    return len(curves)


@undoChunk("animBarShareKeys")
def shareKeys(nodes=None, selectedOnly=False):
    """選んだノードのキーの時刻をそろえ、どのノードにも同じ時刻のキーを打つ(値は変えない)。

    Args:
        nodes (Iterable[Node] | None): 対象。Noneは選択。
        selectedOnly (bool): TrueはGraph Editorで選んだキーの時刻だけをそろえる。

    Returns:
        int: 打ったキーの数。
    """
    nodes = keys.selectedNodes() if nodes is None else list(nodes)
    times = keys.keyTimesOf(nodes, selectedOnly=selectedOnly)
    count = 0
    for node in nodes:
        plugs = keys.animatedPlugs(node, channelBox=False)
        for plug in plugs:
            curve = plug.getAnimCurve()
            existing = curve.getKeyInputs()
            for time in times:
                if all(abs(time - value) > keys.TIME_EPSILON for value in existing):
                    # insert で、その時刻のカーブの値のままキーを足す(今の値で打つとカーブの形が変わる)。
                    plug.setKey(time=time, insert=True)
                    count += 1
    return count


@undoChunk("animBarResetValues")
def resetValues(nodes=None, attributes=None, key=None):
    """選んだノードのアトリビュートを既定値へ戻す。

    Args:
        nodes (Iterable[Node] | None): 対象。Noneは選択。
        attributes (Iterable[str] | None): 戻すアトリビュート名(``"translate"`` 等の親も可)。Noneはキー可能な全部
            (Channel Boxで選んでいればそれだけ)。
        key (bool | None): Trueは戻した値にキーを打つ。Noneはアニメーションのあるアトリビュートだけ打つ。

    Returns:
        int: 戻したアトリビュートの数。
    """
    nodes = keys.selectedNodes() if nodes is None else list(nodes)
    now = Time.getCurrent()
    count = 0
    for node in nodes:
        plugs = keys.keyablePlugs(node)
        if attributes is not None:
            wanted = set(attributes)
            plugs = [plug for plug in plugs if plug.getLongName() in wanted or
                     (plug.getParent() is not None and plug.getParent().getLongName() in wanted)]
        for plug in plugs:
            plug.reset()
            if key or (key is None and plug.getAnimCurve() is not None):
                plug.setKey(time=now)
            count += 1
    return count


@undoChunk("animBarTransformAll")
def transformAll(nodes=None):
    """現在時刻で変えた値の差を、そのアトリビュートの全キーへ足す(ポーズの変更をアニメーション全体へ反映)。

    現在時刻で値を変えてキーを打つ前に呼ぶ。カーブの現在時刻の値と、今の値の差だけ全キーを動かす。

    Args:
        nodes (Iterable[Node] | None): 対象。Noneは選択。

    Returns:
        int: 動かしたカーブの数。
    """
    nodes = keys.selectedNodes() if nodes is None else list(nodes)
    now = Time.getCurrent()
    count = 0
    for node in nodes:
        for plug in keys.animatedPlugs(node):
            curve = plug.getAnimCurve()
            value = plug.get()
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            delta = value - curve.evaluate(now)
            if abs(delta) > 1e-9:
                curve.moveKey(valueOffset=delta)
                count += 1
    return count
