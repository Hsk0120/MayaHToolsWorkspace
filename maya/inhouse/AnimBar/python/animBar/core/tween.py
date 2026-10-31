"""前後のキーの間の値でキーを打つツイーン。

比率 0 は前のキー、1 は後ろのキー、0.5 は中間。0 未満・1 を超える値は前後のキーを越えて
行き過ぎる(オーバーシュート)。Graph Editor でキーを選んでいれば選んだ各キーを、選んでいなければ
選んだノードのアトリビュートの現在時刻に、前後のキーの間の値を書く。
"""

from mlib.common import Time
from mlib.decorator import undoChunk

from . import keys


def tweenValue(previous, following, ratio):
    """前後の値の間を比率で補間する。

    Args:
        previous (float): 前のキーの値。
        following (float): 後ろのキーの値。
        ratio (float): 比率。0は前、1は後ろ。範囲外は行き過ぎ。

    Returns:
        float: 補間した値。
    """
    return previous + (following - previous) * ratio


@undoChunk("animBarTween")
def tween(ratio):
    """選んだキー、または選んだノードの現在時刻に、前後のキーの間の値を書く。

    現在時刻にキーが無いアトリビュートにはキーを作る。前後どちらかのキーが無いアトリビュートは変えない。

    Args:
        ratio (float): 比率。0は前のキー、1は後ろのキー、0.5は中間。

    Returns:
        int: 値を書いたキーの数。
    """
    ratio = float(ratio)
    count = 0
    selected = keys.graphEditorKeys()
    if selected:
        for curve, indices in selected.items():
            count += _tween_indices(curve, indices, ratio)
        return count
    now = Time.getCurrent()
    for node in keys.selectedNodes():
        for plug in keys.animatedPlugs(node):
            curve = keys.animCurveOf(plug)
            previous, following = keys.neighborKeys(curve, now)
            if previous is None or following is None:
                continue
            values = curve.getKeyValues()
            value = tweenValue(values[previous], values[following], ratio)
            index = keys.keyIndexAt(curve, now)
            if index is None:
                curve.setKey(now, value, *_new_key_tangents(curve, previous))
            else:
                keys.setKeyValue(curve, index, value)
            count += 1
    return count


def _tween_indices(curve, indices, ratio):
    """選んだキーを、選んでいない前後のキーの間の値にする。

    連続して選んだキーは、前から順に、直前のキー(書き換えた後の値)と選んだ範囲の後ろのキーを基準にする
    (選んだ範囲が平らにならず、前後のキーの間をなだらかにつなぐ)。

    Args:
        curve (AnimCurve): カーブ。
        indices (list[int]): 選んだキーの番号(昇順)。
        ratio (float): 比率。

    Returns:
        int: 値を書いたキーの数。
    """
    values = curve.getKeyValues()
    chosen = set(indices)
    count = 0
    for index in indices:
        previous = index - 1
        following = index + 1
        while following in chosen:
            following += 1
        if previous < 0 or following >= len(values):
            continue
        values[index] = tweenValue(values[previous], values[following], ratio)
        keys.setKeyValue(curve, index, values[index])
        count += 1
    return count


def _new_key_tangents(curve, previous):
    """ツイーンで新しく打つキーの接線型を、前のキーの出力接線型から決める。

    step のブロッキング中に打っても step のままにする。fixed は角度を引き継げないため auto にし、
    入力側の step は使えないため auto にする。

    Args:
        curve (AnimCurve): カーブ。
        previous (int): 前のキーの番号。

    Returns:
        tuple[str, str]: (入力接線型, 出力接線型)。
    """
    name = curve.getTangent(previous)["outTangentType"] or "auto"
    if name == "fixed":
        name = "auto"
    return ("auto" if name in ("step", "stepnext") else name), name


@undoChunk("animBarTweenLinear")
def tweenLinear(direction):
    """現在時刻の値を、前(direction=-1)または後ろ(1)の2つのキーを結ぶ直線の延長にする。

    動きの勢いをそのまま続けた(または逆にさかのぼった)値でキーを打つ。現在時刻にキーが無ければ作る。
    2つのキーが無いアトリビュートは変えない。

    Args:
        direction (int): -1は前の2キー、1は後ろの2キー。

    Returns:
        int: 値を書いたアトリビュートの数。
    """
    now = Time.getCurrent()
    count = 0
    for node in keys.selectedNodes():
        for plug in keys.animatedPlugs(node):
            curve = keys.animCurveOf(plug)
            inputs, values = curve.getKeyInputs(), curve.getKeyValues()
            if direction < 0:
                around = [index for index, time in enumerate(inputs) if time < now - keys.TIME_EPSILON][-2:]
            else:
                around = [index for index, time in enumerate(inputs) if time > now + keys.TIME_EPSILON][:2]
            if len(around) < 2:
                continue
            first, second = around
            span = inputs[second] - inputs[first]
            value = values[first] + (values[second] - values[first]) * (now - inputs[first]) / span
            index = keys.keyIndexAt(curve, now)
            if index is None:
                curve.setKey(now, value, *_new_key_tangents(curve, around[-1] if direction < 0 else around[0]))
            else:
                keys.setKeyValue(curve, index, value)
            count += 1
    return count


@undoChunk("animBarCopyNeighborKey")
def copyNeighborKey(direction):
    """現在時刻のキーを、前(direction=-1)または後ろ(1)のキーと同じ値にする。

    Args:
        direction (int): -1は前のキー、1は後ろのキー。

    Returns:
        int: 値を書いたアトリビュートの数。
    """
    return tween(0.0 if direction < 0 else 1.0)
